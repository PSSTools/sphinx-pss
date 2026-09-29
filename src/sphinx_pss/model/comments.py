#****************************************************************************
#* comments.py
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
"""Ordinary comments attached to AST nodes: the one reader of the comments API.

Doc comments on declarations come from the docstring API (``getDocRaw()``),
which is what the rest of the model reads. Step markers need more than that
API keeps: comments on *statements*, trailing comments, and comments separated
from their statement by a blank line (programming-steps design, sections 3.3
and 6.1). Those come from ``Parser(collect_comments=True)``, and this module is
the only code that reads them, so a change in that API has one place to land.

Four facts about the API shape everything here:

- **Each ``//``-style line is its own comment.** A three-line ``///`` run
  arrives as three ``Comment`` objects; `comment_runs` puts it back together,
  because the design treats the run as one comment (rule 3).
- **Attachment order is not source order.** A statement's trailing comment is
  listed before its leading ones, so `comments_of` sorts by position.
- **A comment after a block's last statement belongs to the block.** It is
  on the enclosing scope's ``getTrailing_comments()``, not on any statement;
  `closing_comments` reads it.
- **``getText()`` is not usable for doc forms.** It strips ``//`` from a ``///``
  line and leaves the third slash behind, so the form is taken from
  ``getRaw()`` and the text is re-derived from it by `strip_markers`.
"""

from __future__ import annotations

import dataclasses
import enum
import re
from typing import Any, Iterable

__all__ = [
    "CommentForm",
    "Placement",
    "SourceComment",
    "closing_comments",
    "comment_runs",
    "comments_of",
    "doc_form",
    "leading_comments",
    "strip_markers",
]


class Placement(enum.IntEnum):
    """Where a comment sits relative to the node it is attached to.

    The values are ``Comment.getPlacement()``'s.
    """

    #: Directly above the node.
    LEADING = 0
    #: After the node, on its last line.
    TRAILING = 1
    #: Above the node, with a blank line between them.
    DETACHED = 2


class CommentForm(str, enum.Enum):
    """The comment style, which decides whether markers are read at all."""

    #: ``/// text``
    LINE_DOC = "line_doc"
    #: ``/** text */``
    BLOCK_DOC = "block_doc"
    #: ``// text`` or ``/* text */``: never scanned for markers (rule 1).
    PLAIN = "plain"

    @property
    def is_doc(self) -> bool:
        return self is not CommentForm.PLAIN


@dataclasses.dataclass(frozen=True)
class SourceComment:
    """One comment as attached by the parser, in a form that outlives it.

    ``lines`` is the text with the comment markers removed, one entry per
    source line, so ``line + i`` is the source line of ``lines[i]``.
    """

    raw: str
    lines: tuple[str, ...]
    form: CommentForm
    placement: Placement
    is_block: bool
    fileid: int
    line: int
    col: int

    @property
    def text(self) -> str:
        return "\n".join(self.lines)

    @property
    def end_line(self) -> int:
        return self.line + max(len(self.lines), 1) - 1


def doc_form(raw: str) -> CommentForm:
    """Classify a comment by its opening characters.

    ``////`` and longer are plain, as in Doxygen: a rule of slashes is a
    separator, not a doc comment. ``/**/`` is an empty plain block comment, not
    a doc comment that forgot to close.
    """
    text = raw.lstrip()
    if text.startswith("///"):
        return CommentForm.PLAIN if text.startswith("////") else CommentForm.LINE_DOC
    if text.startswith("/**"):
        return CommentForm.PLAIN if text.startswith(("/**/", "/***")) else CommentForm.BLOCK_DOC
    return CommentForm.PLAIN


#: A continuation line of a block comment: indentation, then an optional ``*``
#: that is not the start of the closing ``*/``.
_BLOCK_GUTTER = re.compile(r"^\s*\*(?!/)")


def strip_markers(raw: str) -> list[str]:
    """Remove comment markers from ``raw``, keeping one entry per source line.

    - Line comments lose ``//`` or ``///`` and at most one following space.
    - Block comments lose ``/*`` or ``/**``, the closing ``*/``, and a leading
      ``*`` gutter on continuation lines together with one following space.

    Leading and trailing blank lines are kept, so line numbers stay aligned
    with the source; callers that want prose strip them.
    """
    text = raw.rstrip("\n")
    if text.lstrip().startswith("//"):
        body = text.lstrip()
        body = body[3:] if doc_form(body) is CommentForm.LINE_DOC else body[2:]
        return [_drop_one_space(body).rstrip()]

    body = text.strip()
    body = body[3:] if body.startswith("/**") and not body.startswith("/**/") else body[2:]
    if body.endswith("*/"):
        body = body[:-2]
    out = []
    for i, line in enumerate(body.split("\n")):
        if i > 0:
            m = _BLOCK_GUTTER.match(line)
            line = line[m.end():] if m else line.lstrip()
        out.append(_drop_one_space(line).rstrip())
    return out


def _drop_one_space(text: str) -> str:
    return text[1:] if text.startswith(" ") else text


def comments_of(node: Any) -> list[SourceComment]:
    """Every comment the parser attached to ``node``, in source order.

    Empty when the node carries none, or when the model was parsed without
    ``collect_comments`` (the parser then attaches nothing).
    """
    count = getattr(node, "numComments", None)
    if count is None:
        return []
    comments = [_convert(node.getComment(i)) for i in range(count())]
    comments.sort(key=lambda c: (c.fileid, c.line, c.col))
    return comments


def leading_comments(node: Any) -> list[SourceComment]:
    """The comments above ``node``: everything but its trailing comment."""
    return [c for c in comments_of(node) if c.placement is not Placement.TRAILING]


def closing_comments(scope: Any) -> list[SourceComment]:
    """Comments after the last statement of ``scope``, before its ``}``.

    The parser has no statement to attach these to, so it keeps them on the
    scope itself. A step marker here opens a step with nothing in it.
    """
    count = getattr(scope, "numTrailing_comments", None)
    if count is None:
        return []
    comments = [_convert(scope.getTrailing_comment(i)) for i in range(count())]
    comments.sort(key=lambda c: (c.fileid, c.line, c.col))
    return comments


def comment_runs(comments: Iterable[SourceComment]) -> list[SourceComment]:
    """Merge consecutive ``///`` lines into one comment each.

    Lines join a run when they are ``///`` comments on adjacent source lines
    with the same placement. The run keeps the first line's position, so its
    ``lines`` still map one-to-one onto source lines. Everything else (block
    comments, plain comments, a ``///`` line after a gap) passes through
    unchanged.
    """
    out: list[SourceComment] = []
    for c in comments:
        prev = out[-1] if out else None
        if (
            prev is not None
            and c.form is CommentForm.LINE_DOC
            and prev.form is CommentForm.LINE_DOC
            and c.placement is prev.placement
            and c.fileid == prev.fileid
            and c.line == prev.end_line + 1
        ):
            out[-1] = dataclasses.replace(
                prev,
                raw=prev.raw + c.raw,
                lines=prev.lines + c.lines,
            )
        else:
            out.append(c)
    return out


def _convert(comment: Any) -> SourceComment:
    raw = comment.getRaw()
    loc = comment.getLocation()
    try:
        placement = Placement(comment.getPlacement())
    except ValueError:  # pragma: no cover - a placement newer than this module
        placement = Placement.LEADING
    return SourceComment(
        raw=raw,
        lines=tuple(strip_markers(raw)),
        form=doc_form(raw),
        placement=placement,
        is_block=bool(comment.getIs_block()),
        fileid=loc.fileid,
        line=loc.lineno,
        col=loc.linepos,
    )
