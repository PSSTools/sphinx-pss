"""The PSS Pygments lexer.

Not in the original plan: it surfaced building ``docs/`` under ``-W``, where a
``pss`` code block warns because Pygments has no PSS lexer. Since ``viewcode``
(Phase 3) needs the same lexer to render source listings, it lives in the
extension rather than in the docs configuration.
"""

from __future__ import annotations

import pytest
from pygments.token import Comment, Keyword, Name, Number, String

from sphinx_pss.lexer import PssLexer

pytestmark = pytest.mark.unit


def tokens(source: str) -> list[tuple]:
    return [(t, v) for _, t, v in PssLexer().get_tokens_unprocessed(source)]


def test_declaration_keyword_and_name() -> None:
    assert (Keyword.Declaration, "action") in tokens("action Xfer { }")
    assert (Name.Class, "Xfer") in tokens("action Xfer { }")


@pytest.mark.parametrize(
    "keyword,token",
    [
        ("rand", Keyword.Declaration),
        ("static", Keyword.Declaration),
        ("int", Keyword.Type),
        ("bit", Keyword.Type),
        ("input", Keyword),
        ("lock", Keyword),
        ("true", Keyword.Constant),
    ],
)
def test_keyword_classification(keyword: str, token) -> None:
    assert (token, keyword) in tokens(keyword + " x;")


def test_longer_keyword_wins_over_its_prefix() -> None:
    """``init_down`` must not lex as ``init`` followed by a name."""
    assert (Keyword, "init_down") in tokens("exec init_down { }")


def test_doc_comment_forms_are_distinguished_from_ordinary_comments() -> None:
    assert (Comment.Special, "/// doc") in tokens("/// doc\nint x;")
    assert (Comment.Single, "// aside") in tokens("// aside\nint x;")


def test_block_comments_terminate() -> None:
    result = tokens("/** doc */ int x;")
    assert (Keyword.Type, "int") in result


def test_sized_literals_and_strings() -> None:
    assert (Number, "8'hFF") in tokens("x == 8'hFF;")
    assert (String, "hello") in tokens('s = "hello";')


def test_annotations_are_recognized() -> None:
    result = tokens('@doc {.text = "x"}')
    assert (Name.Decorator, "doc") in result


def test_qualified_names() -> None:
    assert (Name.Namespace, "dma_pkg") in tokens("dma_pkg::Dma d;")
