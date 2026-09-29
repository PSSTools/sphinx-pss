#****************************************************************************
#* steps.py
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
"""``SPSS001``: plain comments that would be step markers as doc comments.

Only ``///`` and ``/** */`` comments are read for ``Step:`` markers
(programming-steps design, section 3.1, rule 1), and sphinx-pss never warns
about plain ``//`` and ``/* */`` comments (section 3.5). A codebase that
already writes ``// Step: …`` gets no steps and no warning. This checker is
the migration aid for it: it reports each plain-comment line that matches
rule 2, which is a marker once the comment is written as a doc comment.

It is off by default, so installing sphinx-pss adds nothing to a
``pssparser`` run. ``enabled = true`` under ``[checker.sphinx-pss-steps]``
turns it on.

It reads the source text through the tokenizer rather than the AST: the
comments are what it checks, and it needs no parse. Where the comment sits is
not checked. A converted marker outside a function body or ``exec`` block is
reported by the Sphinx build as ``pss.step_misplaced``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pssparser import tokens
from pssparser.checkers import CheckerBase, MarkerDef

from ..model.comments import CommentForm, doc_form, strip_markers
from ..model.steps_markers import MARKER_RE

if TYPE_CHECKING:
    from pssparser.checkers import CheckContext

__all__ = ["StepCommentChecker"]

_COMMENT_CHANNELS = (tokens.CHANNEL_SL_COMMENT, tokens.CHANNEL_ML_COMMENT)


class StepCommentChecker(CheckerBase):
    """Report plain comments that look like programming-step markers."""

    name = "sphinx-pss-steps"
    description = "Plain // Step: comments that sphinx-pss would read as /// Step: (off by default)"

    marker_defs = [
        MarkerDef(
            id="SPSS001",
            severity="warning",
            summary="Plain comment looks like a step marker",
            detail=(
                "sphinx-pss reads ``Step:`` markers only from ``///`` and "
                "``/** */`` comments, so a ``// Step: ...`` or "
                "``/* Step: ... */`` comment is not a step. Write it as "
                "``/// Step: ...`` or ``/** Step: ... */`` to make it one.\n\n"
                "Off by default. Enable it with ``enabled = true`` under "
                "``[checker.sphinx-pss-steps]`` while converting a codebase."
            ),
        ),
    ]

    runs_without_link = True

    options_schema = {
        "enabled": {
            "type": "bool",
            "default": False,
            "help": "Report plain comments that would be step markers as /// or /** */ comments.",
        },
    }

    #: Filled in by ``configure()``; this is what applies when the checker is
    #: constructed directly.
    options = {"enabled": False}

    def check(self, context: "CheckContext") -> None:
        if not self.options.get("enabled"):
            return
        for path in context.files:
            try:
                with open(path, "rb") as fp:
                    stream = tokens.tokenize(fp.read())
            except (OSError, UnicodeDecodeError):
                # The core checker reports a file it can't read.
                continue
            for token in stream:
                if token.channel in _COMMENT_CHANNELS:
                    self._check_comment(context, path, token)

    def _check_comment(self, context: "CheckContext", path: str, token) -> None:
        if doc_form(token.text) is not CommentForm.PLAIN:
            return
        block = token.channel == tokens.CHANNEL_ML_COMMENT
        source_lines = token.text.rstrip("\n").split("\n")
        for i, text in enumerate(strip_markers(token.text)):
            line = text.strip()
            if not MARKER_RE.match(line):
                continue
            col = source_lines[i].find(line) + 1
            if i == 0:
                col += token.col
            doc = "/** Step: ... */" if block else "/// Step: ..."
            kind = "block comment" if block else "comment"
            context.add_marker(
                code="SPSS001",
                file=path,
                line=token.line + i,
                col=col,
                extent=len(line),
                message=f"plain {kind} looks like a step marker; write it as {doc!r} to make it a step",
            )
