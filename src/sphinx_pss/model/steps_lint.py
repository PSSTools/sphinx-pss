#****************************************************************************
#* steps_lint.py
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
"""Whole-model lint of programming-step markers (design section 3.5).

Run once per build, over every user source file, whether or not any page
asks for steps (plan decision D5): a mistyped marker is a mistake wherever it
is. Three codes, all ``type="pss"`` warnings:

``step_syntax``
    Inside a function body or ``exec`` block, a line whose first word is
    ``step`` or ``steps`` (any case) that is not a valid marker.
``step_misplaced``
    A valid marker anywhere else: on a declaration, or at package or
    component scope. It is ignored.
``step_empty``
    A marker with no title, or one with no statements: another marker
    follows before any statement does, or the block ends.

Only ``///`` and ``/** */`` comments are read. Nothing is ever reported for a
plain ``//`` or ``/* */`` comment. Near misses are only looked for inside
bodies: a doc comment on a declaration is prose, and ``/// Steps are
generated`` there is not a typo.

The walk is over the per-file syntax trees (``user_units()``) rather than the
linked model, because comments are attached there, each file is visited once,
and it works on a model that did not link.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Iterable, Iterator

from .comments import SourceComment, closing_comments, comment_runs, comments_of
from .locations import node_type_name
from .parse import ParsedModel, iter_children
from .steps_markers import Marker, is_near_miss, parse_markers

__all__ = [
    "STEP_EMPTY",
    "STEP_MISPLACED",
    "STEP_SYNTAX",
    "StepIssue",
    "lint_markers",
]

STEP_SYNTAX = "step_syntax"
STEP_MISPLACED = "step_misplaced"
STEP_EMPTY = "step_empty"

#: The declaration node whose children are statements. Its own comments are
#: above the ``exec`` keyword, so they are declaration comments.
_EXEC_BLOCK = "ExecBlock"
#: A ``{ }`` block: a function body, a clause or loop body, or a bare block.
_BLOCK = "ExecScope"
#: A function with a body. Its comments are the function's doc comment; the
#: statements are under ``getBody()``.
_FUNCTION_DEFINITION = "FunctionDefinition"


@dataclasses.dataclass(frozen=True)
class StepIssue:
    """One marker problem, located at the offending comment line."""

    code: str
    message: str
    path: str
    line: int

    def location(self) -> str:
        """``file:line``, in the form Sphinx's logger takes."""
        return f"{self.path}:{self.line}"


def lint_markers(model: ParsedModel) -> list[StepIssue]:
    """Every step-marker problem in ``model``'s user sources, in source order."""
    linter = _Linter(model.file_map)
    for unit in model.user_units():
        linter.declaration(unit)
    return sorted(linter.issues, key=lambda i: (i.path, i.line))


class _Linter:
    def __init__(self, file_map: dict[int, str]) -> None:
        self.file_map = file_map
        self.issues: list[StepIssue] = []
        #: ``(fileid, line, col)`` of every comment already read. A comment
        #: can in principle be reachable twice, and must be reported once.
        self._seen: set[tuple[int, int, int]] = set()

    # --- the walk ------------------------------------------------------------

    def declaration(self, node: Any) -> None:
        """A node outside any body: markers on it are misplaced."""
        self.misplaced(comments_of(node))

        kind = node_type_name(node)
        if kind == _EXEC_BLOCK:
            # Its closing comments are inside the block.
            self.statements(node)
            return
        self.misplaced(closing_comments(node))
        if kind == _FUNCTION_DEFINITION:
            body = node.getBody()
            if body is not None:
                self.statement(body)
        else:
            for child in iter_children(node):
                self.declaration(child)

    def statements(self, scope: Any) -> None:
        """The statements of a block, then the comments before its ``}``."""
        for child in iter_children(scope):
            self.statement(child)
        markers = self.attached(closing_comments(scope))
        if markers:
            last = markers[-1]
            if last.title:
                self.report(
                    STEP_EMPTY,
                    f"step {last.title!r} has no statements: the block ends "
                    "after its marker",
                    last,
                )

    def statement(self, node: Any) -> None:
        """A statement, a ``{ }`` block, or an ``if`` clause or ``match`` choice."""
        self.attached(comments_of(node))
        if node_type_name(node) == _BLOCK:
            self.statements(node)
            return
        for sub in _sub_blocks(node):
            self.statement(sub)

    # --- checks --------------------------------------------------------------

    def attached(self, comments: list[SourceComment]) -> list[_Located]:
        """Check the comments on one statement, returning its markers.

        Every marker on one statement starts a step there, so all but the
        last have nothing in them.
        """
        markers: list[_Located] = []
        for comment in self.doc_comments(comments):
            for i, text in enumerate(comment.lines):
                if is_near_miss(text):
                    self.report(
                        STEP_SYNTAX,
                        f"not a step marker: {text.strip()!r}. A marker is "
                        "written 'Step: <title>', with a capital S and a colon",
                        _Located(comment, comment.line + i),
                    )
            for marker in parse_markers(comment.lines, comment.line):
                located = _Located(comment, marker.line, marker)
                if not marker.title:
                    self.report(STEP_EMPTY, "step marker has no title", located)
                markers.append(located)

        for earlier in markers[:-1]:
            if earlier.title:
                self.report(
                    STEP_EMPTY,
                    f"step {earlier.title!r} has no statements: the next "
                    "marker follows it directly",
                    earlier,
                )
        return markers

    def misplaced(self, comments: list[SourceComment]) -> None:
        for comment in self.doc_comments(comments):
            for marker in parse_markers(comment.lines, comment.line):
                self.report(
                    STEP_MISPLACED,
                    "step marker outside a function body or exec block is "
                    f"ignored: 'Step: {marker.title}'",
                    _Located(comment, marker.line, marker),
                )

    def doc_comments(self, comments: Iterable[SourceComment]) -> Iterator[SourceComment]:
        """The ``///`` and ``/** */`` runs among ``comments`` not yet read."""
        for comment in comment_runs(comments):
            key = (comment.fileid, comment.line, comment.col)
            if not comment.form.is_doc or key in self._seen:
                continue
            self._seen.add(key)
            yield comment

    def report(self, code: str, message: str, where: _Located) -> None:
        path = self.file_map.get(where.comment.fileid, f"<file {where.comment.fileid}>")
        self.issues.append(StepIssue(code, message, path, where.line))


@dataclasses.dataclass(frozen=True)
class _Located:
    """A comment line: a marker's, or a near miss's."""

    comment: SourceComment
    line: int
    marker: Marker | None = None

    @property
    def title(self) -> str:
        return self.marker.title if self.marker else ""


def _sub_blocks(stmt: Any) -> Iterator[Any]:
    """The nested blocks of a procedural statement.

    ``if`` clauses and ``match`` choices are under their own accessors, and
    loop bodies under ``getBody()``. A ``repeat`` or ``foreach`` also has its
    loop variable as a child, which is walked like any statement.
    """
    for child in iter_children(stmt):
        yield child
    get_body = getattr(stmt, "getBody", None)
    if get_body is not None:
        body = get_body()
        if body is not None:
            yield body
    for i in range(stmt.numIf_then() if hasattr(stmt, "numIf_then") else 0):
        yield stmt.getIf_then(i)
    get_else = getattr(stmt, "getElse_then", None)
    if get_else is not None:
        other = get_else()
        if other is not None:
            yield other
    for i in range(stmt.numChoices() if hasattr(stmt, "numChoices") else 0):
        yield stmt.getChoice(i)
