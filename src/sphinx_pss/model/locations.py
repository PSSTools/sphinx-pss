"""Source locations, and which nodes have a real one.

``pssparser`` gives every ``ScopeChild`` a ``Location{fileid, lineno, linepos,
extent}``. Turning that into a `SourceRef` needs the parser's ``file_map``,
which is only populated after ``link()`` — so this module takes the map as an
argument rather than reaching for a parser.
"""

from __future__ import annotations

from typing import Any

from .objects import SourceRef

#: ``fileid`` of the PSS standard library. ``Parser`` always loads
#: ``std_pkg`` / ``addr_reg_pkg`` / ``executor_pkg`` / ``sync_pkg``, and gives
#: them file 0. They stay in the index so references into them resolve, but
#: they are excluded from the documented set unless ``pss_document_stdlib``
#: (design section 4.4).
STDLIB_FILEID = 0

#: Node types whose location is legitimately absent, so the "synthesized"
#: rule below must not be applied to them.
#:
#: ``EnumItem`` is the case that matters: enum values are built into a typed
#: list rather than through ``addChild``, and never receive a location — see
#: the ``U-2`` finding in the implementation plan. Applying the rule blindly
#: would silently drop every enum value from the documentation.
UNLOCATED_NODE_TYPES = frozenset({"EnumItem", "FunctionParamDecl", "TemplateParamDecl"})


def node_type_name(node: Any) -> str:
    """The ``pssparser`` class name of ``node``, for kind dispatch."""
    return type(node).__name__


def is_synthesized(node: Any) -> bool:
    """True when ``node`` was injected by the compiler rather than written.

    ``set_executor`` prototypes and the ``comp`` component back-reference are
    the common cases; both carry ``lineno == -1``. Nodes whose type never gets
    a location at all are exempt (`UNLOCATED_NODE_TYPES`), otherwise the rule
    would discard real, documented elements.
    """
    if node_type_name(node) in UNLOCATED_NODE_TYPES:
        return False

    location = getattr(node, "getLocation", None)
    if location is None:
        return False
    loc = location()
    return loc is None or loc.lineno < 0


def is_stdlib(node: Any) -> bool:
    """True when ``node`` comes from the always-loaded PSS standard library."""
    location = getattr(node, "getLocation", None)
    if location is None:
        return False
    loc = location()
    return loc is not None and loc.fileid == STDLIB_FILEID


def to_source_ref(loc: Any, file_map: dict[int, str]) -> SourceRef | None:
    """Convert a ``pssparser`` ``Location`` to a `SourceRef`.

    Returns ``None`` for an absent or unset location, so callers can tell
    "no location" from "line 0" without a sentinel.
    """
    if loc is None or loc.lineno < 0:
        return None
    return SourceRef(
        path=file_map.get(loc.fileid, f"<file {loc.fileid}>"),
        line=loc.lineno,
        col=max(loc.linepos, 0),
        fileid=loc.fileid,
    )


def node_source_ref(node: Any, file_map: dict[int, str]) -> SourceRef | None:
    """`to_source_ref` applied to ``node``'s own location."""
    location = getattr(node, "getLocation", None)
    if location is None:
        return None
    return to_source_ref(location(), file_map)
