#****************************************************************************
#* locations.py
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
#: rule below must not be applied to them. A function parameter is written by
#: the user but carries no location of its own; its function's location stands
#: in for it.
UNLOCATED_NODE_TYPES = frozenset({"FunctionParamDecl"})


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


def match_lines(lines: list[str], original: list[str]) -> list[int | None]:
    """For each of ``lines``, the index of the ``original`` line it came from.

    ``lines`` is a transformed copy of ``original`` that keeps its order: a
    comment after marker stripping and dedent, or rendered documentation after
    a dialect has split it into summary, body and fields. Each non-blank line
    is matched to the first remaining original line that contains it; a blank
    line, or one no longer present verbatim, maps to ``None``. Matching is by
    content rather than by count because a transformation may drop lines, as
    normalization drops a comment's opening ``/**``.
    """
    result: list[int | None] = []
    cursor = 0
    for line in lines:
        needle = line.strip()
        found = None
        if needle:
            for i in range(cursor, len(original)):
                if needle in original[i]:
                    found = i
                    break
        if found is not None:
            cursor = found + 1
        result.append(found)
    return result


def fill_line_map(indices: list[int | None], base: int) -> tuple[int, ...]:
    """Turn `match_lines` output into source lines, ``base`` being line 0.

    An unmatched entry takes the line after its predecessor's, which is right
    for the blank lines between paragraphs and a close guess otherwise.
    """
    lines: list[int] = []
    previous = base - 1
    for index in indices:
        current = base + index if index is not None else previous + 1
        lines.append(current)
        previous = current
    return tuple(lines)
