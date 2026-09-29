#****************************************************************************
#* source_text.py
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
"""Source text of conditions, read from the token stream (steps design 4.3).

Expressions carry no location, and the AST drops the parentheses an author
wrote, so a condition cannot be printed from the AST as written. The token
stream can: ``pssparser.tokens`` is lossless, and statements and blocks carry
start positions. Every lookup here starts from one of those positions and
walks the tokens to the parentheses, braces or colon that delimit the text:

- `SourceText.after_keyword`: ``if``, ``while``, ``repeat``, ``foreach`` and
  ``match`` conditions, from the statement's own position.
- `SourceText.before`: an ``if`` or ``else if`` condition, from the position of
  the clause's body. Clauses have no location of their own, but their bodies
  do, and the condition's ``)`` is the token just before the body.
- `SourceText.after_body`: the ``while`` of ``repeat { } while (c)``.
- `SourceText.choice_label`: a ``match`` choice's ``[1..3]`` or ``default``.
- `SourceText.statement_end`: the ``;`` that ends a simple statement, which
  bounds the calls it makes (`sphinx_pss.model.calls`).

Positions are the parser's: 1-based lines and 1-based columns. Every lookup
returns ``None`` when the tokens are not what it expects, so a construct this
module doesn't know gives a missing label, never an exception.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Sequence

__all__ = ["SourceText", "normalize"]

_OPEN = {"(": ")", "[": "]", "{": "}"}
_CLOSE = {v: k for k, v in _OPEN.items()}


@dataclasses.dataclass(frozen=True)
class _Tok:
    """One token: its text, and whether it is whitespace or a comment."""

    text: str
    line: int
    #: 1-based, to match the parser's locations.
    col: int
    trivia: bool


class _FileTokens:
    """The tokens of one file, and the default-channel ones by position."""

    def __init__(self, toks: Sequence[_Tok]) -> None:
        self.toks = list(toks)
        #: Indices into `toks` of the tokens that aren't trivia.
        self.code = [i for i, t in enumerate(self.toks) if not t.trivia]
        self._at = {(self.toks[i].line, self.toks[i].col): n for n, i in enumerate(self.code)}

    def find(self, line: int, col: int) -> int | None:
        """The index into `code` of the token starting at ``(line, col)``."""
        return self._at.get((line, col))

    def tok(self, n: int) -> _Tok:
        return self.toks[self.code[n]]

    def match_forward(self, n: int) -> int | None:
        """The closing token of the bracket at ``code[n]``."""
        want = _OPEN.get(self.tok(n).text)
        if want is None:
            return None
        depth = 0
        for m in range(n, len(self.code)):
            text = self.tok(m).text
            if text in _OPEN:
                depth += 1
            elif text in _CLOSE:
                depth -= 1
                if depth == 0:
                    return m if text == want else None
        return None

    def match_backward(self, n: int) -> int | None:
        """The opening token of the bracket closed at ``code[n]``."""
        want = _CLOSE.get(self.tok(n).text)
        if want is None:
            return None
        depth = 0
        for m in range(n, -1, -1):
            text = self.tok(m).text
            if text in _CLOSE:
                depth += 1
            elif text in _OPEN:
                depth -= 1
                if depth == 0:
                    return m if text == want else None
        return None

    def text_between(self, first: int, last: int) -> str:
        """Normalized source text strictly between ``code[first]`` and ``code[last]``."""
        return normalize(self.toks[self.code[first] + 1 : self.code[last]])

    def end_of_statement(self, n: int) -> int | None:
        """The ``;`` ending the statement that starts at ``code[n]``."""
        depth = 0
        for m in range(n, len(self.code)):
            text = self.tok(m).text
            if text in _OPEN:
                depth += 1
            elif text in _CLOSE:
                depth -= 1
                if depth < 0:
                    return None
            elif text == ";" and depth == 0:
                return m
        return None

    def end_of_body(self, n: int) -> int | None:
        """The last token of the block or statement starting at ``code[n]``."""
        if self.tok(n).text == "{":
            return self.match_forward(n)
        return self.end_of_statement(n)


def normalize(toks: Sequence[_Tok]) -> str:
    """The text of ``toks`` as one line.

    Code tokens are kept as written. A run of whitespace that is all on one
    line is kept too, so ``a  &&  b`` stays as the author spaced it; a run that
    breaks the line or holds a comment becomes a single space.
    """
    out: list[str] = []
    gap: list[_Tok] = []
    for tok in toks:
        if tok.trivia:
            gap.append(tok)
            continue
        if gap:
            out.append(_gap_text(gap))
            gap = []
        out.append(tok.text)
    return "".join(out).strip()


def _gap_text(gap: Sequence[_Tok]) -> str:
    text = "".join(t.text for t in gap)
    if "\n" in text or any(not t.text.isspace() for t in gap):
        return " "
    return text


class SourceText:
    """Token-level lookups over a model's source files, each tokenized once."""

    def __init__(self, file_map: dict[int, str]) -> None:
        self._file_map = file_map
        self._files: dict[int, _FileTokens | None] = {}

    def file(self, fileid: int) -> _FileTokens | None:
        if fileid not in self._files:
            self._files[fileid] = self._load(fileid)
        return self._files[fileid]

    def _load(self, fileid: int) -> _FileTokens | None:
        path = self._file_map.get(fileid)
        if not path:
            return None
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError:
            return None
        return _FileTokens(_tokens(data))

    def _start(self, loc: Any) -> tuple[_FileTokens, int] | None:
        """The file and the token at a parser location (``fileid``, ``lineno``, ``linepos``)."""
        if loc is None or loc.lineno < 0:
            return None
        ft = self.file(loc.fileid)
        if ft is None:
            return None
        n = ft.find(loc.lineno, loc.linepos)
        return (ft, n) if n is not None else None

    # --- the lookups ----------------------------------------------------------

    def after_keyword(self, loc: Any) -> str | None:
        """The text in the parentheses after the keyword at ``loc``.

        ``while ((r() & 1) != 0)`` gives ``(r() & 1) != 0``.
        """
        found = self._start(loc)
        if found is None:
            return None
        ft, n = found
        if n + 1 >= len(ft.code) or ft.tok(n + 1).text != "(":
            return None
        close = ft.match_forward(n + 1)
        return ft.text_between(n + 1, close) if close is not None else None

    def before(self, loc: Any) -> str | None:
        """The text in the parentheses that end just before ``loc``.

        ``loc`` is a clause body, so this is its ``if`` or ``else if``
        condition.
        """
        found = self._start(loc)
        if found is None:
            return None
        ft, n = found
        if n == 0 or ft.tok(n - 1).text != ")":
            return None
        opening = ft.match_backward(n - 1)
        return ft.text_between(opening, n - 1) if opening is not None else None

    def after_body(self, loc: Any, keyword: str = "while") -> str | None:
        """The condition after the body at ``loc``: ``repeat { } while (c)``."""
        found = self._start(loc)
        if found is None:
            return None
        ft, n = found
        end = ft.end_of_body(n)
        if end is None or end + 2 >= len(ft.code):
            return None
        if ft.tok(end + 1).text != keyword or ft.tok(end + 2).text != "(":
            return None
        close = ft.match_forward(end + 2)
        return ft.text_between(end + 2, close) if close is not None else None

    def choice_label(self, loc: Any) -> str | None:
        """The label of the ``match`` choice whose body is at ``loc``.

        Everything between the previous choice (or the ``match``'s ``{``) and
        the ``:`` before the body: ``[1..3]``, ``[A, B]``, ``default``.
        """
        found = self._start(loc)
        if found is None:
            return None
        ft, n = found
        colon = n - 1
        if colon < 1 or ft.tok(colon).text != ":":
            return None
        m = colon - 1
        while m >= 0:
            text = ft.tok(m).text
            if text in ("]", ")"):
                opening = ft.match_backward(m)
                if opening is None:
                    return None
                m = opening - 1
                continue
            if text in ("{", "}", ";"):
                break
            m -= 1
        return ft.text_between(m, colon) or None

    def statement_end(self, loc: Any) -> tuple[int, int] | None:
        """``(line, col)`` of the ``;`` ending the statement at ``loc``."""
        found = self._start(loc)
        if found is None:
            return None
        ft, n = found
        end = ft.end_of_statement(n)
        if end is None:
            return None
        tok = ft.tok(end)
        return tok.line, tok.col


def _tokens(data: bytes) -> list[_Tok]:
    from pssparser import tokens

    stream = tokens.tokenize(data)
    return [
        _Tok(
            text=t.text,
            line=t.line,
            col=t.col + 1,
            trivia=t.channel != tokens.CHANNEL_DEFAULT,
        )
        for t in stream.tokens
        if t.channel != tokens.CHANNEL_BOM
    ]
