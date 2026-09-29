#****************************************************************************
#* parse.py
#*
#* Copyright 2026 Matthew Ballance and Contributors
#*
#* Licensed under the Apache License, Version 2.0 (the "License"); you may
#* not use this file except in compliance with the License.
#* You may obtain a copy of the License at:
#*
#*   http://www.apache.org/licenses/LICENSE-2.0
#*
#* Unless required by applicable law or agreed to in writing, software
#* distributed under the License is distributed on an "AS IS" BASIS,
#* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#* See the License for the specific language governing permissions and
#* limitations under the License.
#****************************************************************************
"""Owns the ``pssparser`` lifecycle for one documentation build.

Two constraints shape this module, and both come from the parser rather than
from Sphinx:

**Ownership.** ``Parser.link()`` transfers ownership of the per-file
``GlobalScope``\\ s to the linked root and clears the parser's internal list.
Holding Python wrappers obtained before that point is a double-ownership fault.
So `ParsedModel` keeps the ``Parser`` alive for as long as anything reads the
tree, and every traversal goes through the linked root or ``user_units()``.

**Failure.** ``link()`` records the root, ``file_map`` and ``user_units()``
before it raises, so a model that parses but does not link is still walkable
per file. That is what the degraded mode reads.
"""

from __future__ import annotations

import dataclasses
import os
import pathlib
from typing import Any, Callable, Iterable, Iterator

from sphinx.errors import SphinxError

from .locations import node_type_name

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
    #: Things derived from the model on first use and kept for the build:
    #: the call index and the token cache of programming steps. Keyed by the
    #: module that owns each entry; see `cached`.
    derived: dict[str, Any] = dataclasses.field(default_factory=dict, repr=False, compare=False)

    @property
    def errors(self) -> list[Diagnostic]:
        return [d for d in self.diagnostics if d.is_error]

    def user_units(self) -> list[Any]:
        """Per-file ``GlobalScope``\\ s, excluding the standard library."""
        return list(self.parser.user_units())

    def cached(self, key: str, factory: Callable[[], Any]) -> Any:
        """``derived[key]``, computed by ``factory`` the first time it's asked for."""
        if key not in self.derived:
            self.derived[key] = factory()
        return self.derived[key]


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

    from .._capability import PssParserCapabilityError, check_pssparser

    try:
        check_pssparser()
    except PssParserCapabilityError as e:
        # Re-raised as a SphinxError so the message survives EventManager's
        # re-wrapping; see PssParseError.
        raise PssParseError(str(e)) from e

    sources = [str(s) for s in sources]
    missing = [s for s in sources if not os.path.isfile(s)]
    if missing:
        raise PssParseError(
            "PSS source file(s) not found: " + ", ".join(sorted(missing))
        )

    # ``collect_comments`` attaches ordinary comments, including those on
    # procedural statements, which is where programming-step markers live
    # (programming-steps design, section 5). It is always on rather than only
    # when a page asks for steps: the model is built once, at builder-inited,
    # before any directive is read. It changes nothing the docstring API
    # returns, and it is cheap -- today it is faster, because it makes the
    # parser lex each file up front (section 5.1).
    parser = Parser(collect_docstrings=True, collect_comments=True)
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

    # On a failed link the per-file scopes are still reachable through
    # ``user_units()``, and they are what a degraded build walks: declarations
    # and doc comments survive, but ``extend`` merging, inheritance, type
    # resolution, cross references and diagrams do not, because all of them
    # are products of linking (design section 4.4).
    return ParsedModel(
        parser=parser,
        root=root if linked else None,
        file_map=dict(parser.file_map),
        sources=sources,
        diagnostics=diagnostics,
        linked=linked,
    )


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

    Linking wraps a type declaration in a ``SymbolTypeScope``; the wrapped
    declaration is what carries the kind-specific shape (``Struct.getKind()``,
    the super type, template parameters). Doc comments do not need it: the
    linker copies each declaration's docstring onto its symbol. A wrapper with
    no target (``SymbolScope``, ``SymbolEnumScope``, a prototype-only
    ``SymbolFunctionScope``) is returned unchanged.
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
