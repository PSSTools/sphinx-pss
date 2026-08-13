"""Owns the ``pssparser`` lifecycle for one documentation build.

Two constraints shape this module, and both come from the parser rather than
from Sphinx:

**Ownership.** ``Parser.link()`` transfers ownership of the per-file
``GlobalScope``\\ s to the linked root and clears the parser's internal list.
Holding Python wrappers obtained before that point is a double-ownership fault.
So `ParsedModel` keeps the ``Parser`` alive for as long as anything reads the
tree, and every traversal goes through the linked root or ``user_units()``.

**Reachability.** A package's and an enum's doc comment are collected by the
parser but are not reachable from the linked tree — ``SymbolScope`` and
``SymbolEnumScope`` expose no declaration (finding ``U-1`` in the
implementation plan). `ParsedModel.declaration_at` closes that by indexing the
declaration nodes from ``user_units()`` on ``(fileid, lineno)``, which the
linked node's own location joins to exactly.
"""

from __future__ import annotations

import dataclasses
import os
import pathlib
from typing import Any, Iterable, Iterator

from sphinx.errors import SphinxError

from .locations import STDLIB_FILEID, node_type_name

#: Extension of a PSS source file.
PSS_SUFFIX = ".pss"

#: Marker severities the parser reports, mapped to how the build should treat
#: them. Anything unrecognized is treated as a warning rather than dropped.
SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"


class PssParseError(SphinxError):
    """The model could not be built, and degrading would hide the reason.

    Derives from `SphinxError` so it reaches the user intact:
    ``EventManager.emit`` re-wraps any other exception as "Handler … threw an
    exception", which buries the parser diagnostics this message exists to
    carry. Outside a Sphinx build it is an ordinary exception.
    """

    category = "PSS model error"


@dataclasses.dataclass(frozen=True)
class Diagnostic:
    """A parser marker, normalized for reporting as a Sphinx warning."""

    severity: str
    message: str
    path: str | None = None
    line: int | None = None
    col: int | None = None

    @property
    def is_error(self) -> bool:
        return self.severity == SEVERITY_ERROR

    def location(self) -> str | None:
        """``file:line``, in the form Sphinx's logger takes."""
        if not self.path:
            return None
        return f"{self.path}:{self.line}" if self.line else self.path

    def __str__(self) -> str:
        where = self.location()
        return f"{where}: {self.message}" if where else self.message


def _normalize_severity(value: Any) -> str:
    text = str(getattr(value, "name", value)).lower()
    if "err" in text or "fatal" in text:
        return SEVERITY_ERROR
    if "warn" in text:
        return SEVERITY_WARNING
    return SEVERITY_INFO


def _marker_to_diagnostic(marker: Any) -> Diagnostic:
    """Normalize one ``Parser.markers`` entry.

    Markers arrive as mappings, but the exact key set has changed across parser
    releases, so each field is looked up defensively and the whole marker is
    stringified as a last resort. A diagnostic that renders imperfectly is far
    better than one that is dropped.
    """
    if isinstance(marker, dict):
        get = marker.get
    else:  # pragma: no cover - defensive, for object-shaped markers

        def get(key, default=None):
            return getattr(marker, key, default)

    return Diagnostic(
        severity=_normalize_severity(get("severity", SEVERITY_WARNING)),
        message=str(get("message", marker)),
        path=get("file") or get("path"),
        line=get("line") or get("lineno"),
        col=get("col") or get("linepos"),
    )


def discover_sources(
    source_dirs: Iterable[str],
    source_files: Iterable[str],
    confdir: str | os.PathLike[str] | None = None,
) -> list[str]:
    """Resolve ``pss_source_dirs`` / ``pss_source_files`` to a source list.

    Explicit files come first and in the order given — for PSS that ordering is
    a real input, since a project can hand the parser a deliberately ordered
    build unit. Directory contents are then appended in sorted order so a build
    is reproducible regardless of how the filesystem enumerates.
    """
    base = pathlib.Path(confdir) if confdir else pathlib.Path.cwd()

    def resolve(entry: str) -> pathlib.Path:
        path = pathlib.Path(entry)
        return path if path.is_absolute() else (base / path)

    sources: list[str] = []
    seen: set[str] = set()

    def add(path: pathlib.Path) -> None:
        key = str(path.resolve())
        if key not in seen:
            seen.add(key)
            sources.append(str(path))

    for entry in source_files:
        add(resolve(entry))

    for entry in source_dirs:
        directory = resolve(entry)
        if not directory.is_dir():
            raise PssParseError(
                f"pss_source_dirs: {entry!r} is not a directory "
                f"(resolved to {directory})"
            )
        for path in sorted(directory.rglob(f"*{PSS_SUFFIX}")):
            add(path)

    return sources


@dataclasses.dataclass
class ParsedModel:
    """A parsed and linked PSS model, plus everything needed to read it.

    Holds a strong reference to the ``Parser``: see the module docstring.
    """

    parser: Any
    root: Any
    file_map: dict[int, str]
    sources: list[str]
    diagnostics: list[Diagnostic] = dataclasses.field(default_factory=list)
    linked: bool = True

    #: ``(fileid, lineno)`` -> declaration node from ``user_units()``. See the
    #: module docstring and finding ``U-1``.
    _declarations: dict[tuple[int, int], Any] = dataclasses.field(
        default_factory=dict, repr=False
    )

    #: Per-file scopes used when ``linked`` is False. Empty otherwise — a
    #: linked model is always read through `root`.
    degraded_units: list[Any] = dataclasses.field(default_factory=list, repr=False)

    @property
    def errors(self) -> list[Diagnostic]:
        return [d for d in self.diagnostics if d.is_error]

    def declaration_at(self, loc: Any) -> Any | None:
        """The pre-link declaration node written at ``loc``, if there is one.

        Used only to recover what the linked tree does not expose — currently a
        package's and an enum's doc comment. The linked tree stays the
        documentation view for everything else.
        """
        if loc is None or loc.lineno < 0:
            return None
        return self._declarations.get((loc.fileid, loc.lineno))

    def user_units(self) -> list[Any]:
        """Per-file ``GlobalScope``\\ s, excluding the standard library."""
        if not self.linked:
            return list(self.degraded_units)
        return list(self.parser.user_units())


def _index_declarations(parser: Any) -> dict[tuple[int, int], Any]:
    """Index every declaration node in the user's files by ``(fileid, line)``.

    A location is unique per declaration in practice — two declarations cannot
    begin on the same line of the same file in PSS — so no collision policy is
    needed beyond first-wins, which keeps the outermost declaration when a
    grammar wrapper shares a start position.
    """
    index: dict[tuple[int, int], Any] = {}

    def visit(node: Any) -> None:
        get_location = getattr(node, "getLocation", None)
        if get_location is not None:
            loc = get_location()
            if loc is not None and loc.lineno >= 0 and loc.fileid != STDLIB_FILEID:
                index.setdefault((loc.fileid, loc.lineno), node)

        get_children = getattr(node, "getChildren", None)
        if get_children is None:
            return
        children = get_children()
        for i in range(len(children)):
            visit(node.getChild(i))

    for unit in parser.user_units():
        visit(unit)

    return index


def parse_model(
    sources: Iterable[str],
    *,
    tolerate_link_errors: bool = False,
) -> ParsedModel:
    """Parse and link ``sources``, returning the model everything else reads.

    With ``tolerate_link_errors`` the build continues after a link failure
    using the per-file scopes: declarations and doc comments survive, but
    ``extend`` merging, inheritance and type resolution do not, so cross
    references and diagrams are unavailable. Every marker is reported either
    way — a degraded build must be visibly degraded, not quietly wrong
    (design section 4.4).
    """
    from pssparser import ParseException, Parser

    sources = [str(s) for s in sources]
    missing = [s for s in sources if not os.path.isfile(s)]
    if missing:
        raise PssParseError(
            "PSS source file(s) not found: " + ", ".join(sorted(missing))
        )

    parser = Parser(collect_docstrings=True)
    try:
        parser.parse(sources)
    except ParseException as e:
        # The parser raises rather than returning markers when a file does not
        # parse at all. Degrading is not on offer here even under
        # ``tolerate_link_errors``: that option covers models that parse but do
        # not *link*, and there is nothing to walk after a syntax error.
        diagnostics = [_marker_to_diagnostic(m) for m in getattr(e, "markers", ())]
        detail = "\n".join(f"  {d}" for d in diagnostics) or f"  {e}"
        raise PssParseError(f"PSS sources did not parse:\n{detail}") from e

    diagnostics = [_marker_to_diagnostic(m) for m in parser.markers]
    parse_errors = [d for d in diagnostics if d.is_error]
    if parse_errors and not tolerate_link_errors:
        raise PssParseError(
            "PSS sources did not parse:\n"
            + "\n".join(f"  {d}" for d in parse_errors)
        )

    root = None
    linked = True
    try:
        root = parser.link()
    except ParseException as e:
        linked = False
        diagnostics = [_marker_to_diagnostic(m) for m in getattr(e, "markers", ())]
        if not any(d.is_error for d in diagnostics):
            diagnostics.append(Diagnostic(SEVERITY_ERROR, f"link failed: {e}"))
    else:
        # ``markers`` accumulates across parse() and link(), so re-read rather
        # than append.
        diagnostics = [_marker_to_diagnostic(m) for m in parser.markers]

    if not linked and not tolerate_link_errors:
        raise PssParseError(
            "PSS sources did not link:\n"
            + "\n".join(f"  {d}" for d in diagnostics if d.is_error)
            + "\n\nSet pss_tolerate_link_errors = True to document declarations "
            "and doc comments anyway; cross references, extension merging and "
            "diagrams will be unavailable."
        )

    if not linked:
        return _degraded_model(sources, diagnostics)

    return ParsedModel(
        parser=parser,
        root=root,
        file_map=dict(parser.file_map),
        sources=sources,
        diagnostics=diagnostics,
        linked=True,
        _declarations=_index_declarations(parser),
    )


def _degraded_model(sources: list[str], diagnostics: list[Diagnostic]) -> ParsedModel:
    """Build a per-file model for sources that parse but do not link.

    A failed ``link()`` leaves nothing walkable: it raises before snapshotting
    ``file_map`` and before ``_root`` is set, so ``user_units()`` returns an
    empty list and ``file_map`` is empty (finding ``U-5``). The recovery is to
    parse again into a parser that is **never linked**, whose per-file scopes
    are therefore still owned by it and safe to read for as long as it lives.

    What survives is declarations and their doc comments. ``extend`` merging,
    inheritance, type resolution, cross references and diagrams do not, because
    all of them are products of linking (design section 4.4).
    """
    from pssparser import Parser

    parser = Parser(collect_docstrings=True)
    parser.parse(sources)

    # Reading these two attributes is the compatibility shim for U-5: neither
    # the per-file scopes nor the fileid map is reachable through the public
    # API before link(). Safe here precisely because this parser never links,
    # so ownership never transfers.
    units = list(getattr(parser, "_files", ()))
    file_map = dict(getattr(parser, "_filenames", {}))

    model = ParsedModel(
        parser=parser,
        root=None,
        file_map=file_map,
        sources=sources,
        diagnostics=diagnostics,
        linked=False,
    )
    model.degraded_units = [u for u in units if u.getFileid() in file_map]
    return model


def iter_children(node: Any) -> Iterator[Any]:
    """Yield ``node``'s children.

    ``pssparser`` exposes children as a length-only sequence plus an indexed
    accessor, so this is the one place that shape is spelled out.
    """
    get_children = getattr(node, "getChildren", None)
    if get_children is None:
        return
    children = get_children()
    for i in range(len(children)):
        yield node.getChild(i)


def unwrap(node: Any) -> Any:
    """Return the declaration behind a linked symbol-scope wrapper.

    Linking wraps a type declaration in a ``SymbolTypeScope`` whose own
    ``getDocstring()`` is empty while the declaration holds the text
    (``pssparser`` enhancement plan section 10.3). ``SymbolScope`` and
    ``SymbolEnumScope`` have no target at all (finding ``U-1``), in which case
    the wrapper is returned unchanged and the caller falls back to
    `ParsedModel.declaration_at`.
    """
    get_target = getattr(node, "getTarget", None)
    if get_target is None:
        return node
    try:
        target = get_target()
    except TypeError:  # pragma: no cover - some getTarget overloads take an index
        return node
    return target if target is not None else node


__all__ = [
    "Diagnostic",
    "ParsedModel",
    "PssParseError",
    "discover_sources",
    "iter_children",
    "node_type_name",
    "parse_model",
    "unwrap",
]
