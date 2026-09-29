"""The comments reader (programming-steps plan ``S0-IMPL-2`` / ``S0-TEST-2``).

Two halves: the pure text functions, which need no parser, and the readers,
run against real parses so the tests fail if the comments API shifts under
them. Every comment form is crossed with every placement, because a marker is
valid in all three placements (design section 3.4) and the form is what
decides whether it is read at all (rule 1).
"""

from __future__ import annotations

import pytest

from sphinx_pss.model.comments import (
    CommentForm,
    Placement,
    closing_comments,
    comment_runs,
    comments_of,
    doc_form,
    leading_comments,
    strip_markers,
)

pytestmark = pytest.mark.unit


# --- doc_form ----------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,form",
    [
        ("/// text\n", CommentForm.LINE_DOC),
        ("///text\n", CommentForm.LINE_DOC),
        ("///\n", CommentForm.LINE_DOC),
        ("/** text */", CommentForm.BLOCK_DOC),
        ("/**\n * text\n */", CommentForm.BLOCK_DOC),
        ("// text\n", CommentForm.PLAIN),
        ("/* text */", CommentForm.PLAIN),
        # A rule of slashes or stars is decoration, not a doc comment.
        ("//////////\n", CommentForm.PLAIN),
        ("/*********/", CommentForm.PLAIN),
        # The empty block comment is not an unterminated doc comment.
        ("/**/", CommentForm.PLAIN),
    ],
)
def test_doc_form(raw, form) -> None:
    assert doc_form(raw) is form


# --- strip_markers -----------------------------------------------------------


@pytest.mark.parametrize(
    "raw,lines",
    [
        ("/// Step: Reset the MAC\n", ["Step: Reset the MAC"]),
        ("///Step: tight\n", ["Step: tight"]),
        ("///   indented\n", ["  indented"]),
        ("// plain\n", ["plain"]),
        ("/** Step: one line */", ["Step: one line"]),
        ("/* plain block */", ["plain block"]),
        (
            "/** Step: Configure\n         *  more\n         */",
            ["Step: Configure", " more", ""],
        ),
        (
            "/**\n * Step: After a bare opener\n * Detail.\n */",
            ["", "Step: After a bare opener", "Detail.", ""],
        ),
        # No gutter: indentation is dropped rather than kept as reST quoting.
        ("/** Step: A\n    no gutter */", ["Step: A", "no gutter"]),
        ("/**/", [""]),
    ],
)
def test_strip_markers(raw, lines) -> None:
    assert strip_markers(raw) == lines


def test_strip_markers_keeps_one_entry_per_source_line() -> None:
    """``SourceComment.line + i`` must be the source line of ``lines[i]``."""
    raw = "/**\n * a\n *\n * b\n */"
    assert len(strip_markers(raw)) == raw.count("\n") + 1


# --- readers, against real parses -------------------------------------------

FORMS = {
    "line_doc": ("/// x y", CommentForm.LINE_DOC),
    "block_doc": ("/** x y */", CommentForm.BLOCK_DOC),
    "line": ("// x y", CommentForm.PLAIN),
    "block": ("/* x y */", CommentForm.PLAIN),
}

#: Where the comment goes relative to ``w(1);``, the function's second
#: statement (line 5 when leading, so every case can assert a line).
PLACEMENTS = {
    Placement.LEADING: "{c}\n        w(1);",
    Placement.TRAILING: "w(1); {c}",
    Placement.DETACHED: "{c}\n\n        w(1);",
}


def _body(source: str, qname: str = "p::f"):
    """Parse ``source`` and return the parser (kept alive) and ``qname``'s body."""
    from pssparser import Parser
    from pssparser.utils import SymbolScopeUtil

    parser = Parser(collect_docstrings=True, collect_comments=True)
    parser.parses([("t.pss", source)])
    root = parser.link()
    return parser, SymbolScopeUtil(root).getQname(qname).getTarget().getBody()


def _statements(body) -> list:
    return [body.getChild(i) for i in range(len(body.getChildren()))]


def _function(statements: str) -> str:
    return (
        "package p {\n"
        "    function void w(int v);\n"
        "    function void f() {\n"
        "        int a = 0;\n"
        f"        {statements}\n"
        "    }\n"
        "}\n"
    )


@pytest.mark.parametrize("placement", list(PLACEMENTS), ids=lambda p: p.name.lower())
@pytest.mark.parametrize("form_id", list(FORMS))
def test_every_form_in_every_placement(form_id, placement) -> None:
    text, form = FORMS[form_id]
    _parser, body = _body(_function(PLACEMENTS[placement].format(c=text)))
    decl, call = _statements(body)

    assert comments_of(decl) == []
    [comment] = comments_of(call)
    assert comment.form is form
    assert comment.placement is placement
    assert comment.lines == ("x y",)
    assert comment.line == 5
    assert comment.raw.startswith(text.split()[0])


def test_comments_come_back_in_source_order() -> None:
    """The parser lists a trailing comment before the leading ones."""
    _parser, body = _body(_function("/// first\n        // second\n        w(1); // third"))
    [_, call] = _statements(body)

    assert [c.text for c in comments_of(call)] == ["first", "second", "third"]
    assert [c.text for c in leading_comments(call)] == ["first", "second"]


def test_a_line_doc_run_with_a_marker_in_the_middle() -> None:
    """Rule 3 reads a ``///`` run as one comment: prose, marker, detail."""
    _parser, body = _body(
        _function(
            "/// Some prose first.\n"
            "        /// Step: Reset the MAC\n"
            "        /// Detail line.\n"
            "        w(1);"
        )
    )
    [_, call] = _statements(body)

    assert len(comments_of(call)) == 3
    [run] = comment_runs(comments_of(call))
    assert run.form is CommentForm.LINE_DOC
    assert run.lines == ("Some prose first.", "Step: Reset the MAC", "Detail line.")
    assert (run.line, run.end_line) == (5, 7)


def test_runs_break_on_form_gap_and_placement() -> None:
    _parser, body = _body(
        _function(
            "/// a\n"
            "        // b\n"
            "        /// c\n"
            "\n"
            "        /// d\n"
            "        w(1); /// e"
        )
    )
    [_, call] = _statements(body)

    runs = comment_runs(comments_of(call))
    assert [r.lines for r in runs] == [("a",), ("b",), ("c",), ("d",), ("e",)]


def test_a_block_doc_comment_keeps_its_line_numbers() -> None:
    _parser, body = _body(
        _function("/** Step: Configure\n         *  Detail.\n         */\n        w(1);")
    )
    [_, call] = _statements(body)
    [comment] = comments_of(call)

    assert comment.is_block
    assert comment.lines == ("Step: Configure", " Detail.", "")
    assert (comment.line, comment.end_line) == (5, 7)


def test_a_comment_after_the_last_statement_belongs_to_the_block() -> None:
    _parser, body = _body(_function("w(1);\n        /// Step: nothing follows"))
    [_, call] = _statements(body)

    assert comments_of(call) == []
    [comment] = closing_comments(body)
    assert comment.text == "Step: nothing follows"
    assert comment.line == 6


def test_nodes_without_comments_are_empty() -> None:
    assert comments_of(object()) == []
    assert closing_comments(object()) == []


def test_without_collection_nothing_is_attached() -> None:
    """``comments_of`` degrades to empty, rather than failing, on such a parse."""
    from pssparser import Parser
    from pssparser.utils import SymbolScopeUtil

    parser = Parser(collect_docstrings=True)
    parser.parses([("t.pss", _function("/// Step: x\n        w(1);"))])
    root = parser.link()
    body = SymbolScopeUtil(root).getQname("p::f").getTarget().getBody()

    assert all(comments_of(s) == [] for s in _statements(body))
