"""Condition text from the token stream (programming-steps plan ``S2-IMPL-5`` / ``S2-TEST-6``).

Each lookup starts at a position, the way the step builder calls it: a
statement's keyword, or a clause or choice body. Positions here are found in
the source text, so the tests don't depend on the parser's locations; the
step-tree tests cover those.
"""

from __future__ import annotations

import collections

import pytest

from sphinx_pss.model.source_text import SourceText

pytestmark = pytest.mark.unit

Loc = collections.namedtuple("Loc", "fileid lineno linepos")

SOURCE = """\
package p {
    function void f(bool b, int x) {
        if (b && (x > 2)) { w(1); } else if (x   ==   1) { w(2); } else { w(3); }
        while (((r(0) & 0x8000)) != 0) { }
        repeat (i : 4) { w(i); }
        repeat { w(5); } while ((r(1) & 0x4) == 0);
        repeat w(6); while (b);
        foreach (e : arr) { w(e); }
        match (x + 1) {
            [1]: { w(1); }
            [2..3], [5]: { w(2); }
            [7]: w(7);
            default: { w(0); }
        }
        if (b &&   // the first half
            x > 3) {
            w(4);
        }
        write_reg(0x10, {1, 2}[0]); w(9);
    }
}
"""


@pytest.fixture
def text(tmp_path):
    path = tmp_path / "t.pss"
    path.write_text(SOURCE)
    return SourceText({1: str(path)})


def at(needle: str, nth: int = 0) -> Loc:
    """The position of the ``nth`` occurrence of ``needle`` in `SOURCE`."""
    start = -1
    for _ in range(nth + 1):
        start = SOURCE.index(needle, start + 1)
    line = SOURCE.count("\n", 0, start) + 1
    col = start - (SOURCE.rfind("\n", 0, start) + 1) + 1
    return Loc(1, line, col)


@pytest.mark.parametrize(
    "keyword,expected",
    [
        ("if (b &&", "b && (x > 2)"),
        ("while", "((r(0) & 0x8000)) != 0"),
        ("repeat (i", "i : 4"),
        ("foreach", "e : arr"),
        ("match", "x + 1"),
    ],
)
def test_the_condition_after_a_keyword(text, keyword, expected) -> None:
    assert text.after_keyword(at(keyword)) == expected


def test_a_multi_line_condition_is_one_line_without_its_comment(text) -> None:
    assert text.after_keyword(at("if (b &&", 1)) == "b && x > 3"


def test_spacing_on_one_line_is_kept(text) -> None:
    """``else if (x   ==   1)``: the author's spacing, found from the clause body."""
    assert text.before(at("{ w(2); }")) == "x   ==   1"


def test_the_first_clause_is_found_from_its_body_too(text) -> None:
    assert text.before(at("{ w(1); }")) == "b && (x > 2)"


def test_an_else_body_has_no_condition(text) -> None:
    assert text.before(at("{ w(3); }")) is None


@pytest.mark.parametrize(
    "body,expected",
    [("{ w(5); }", "(r(1) & 0x4) == 0"), ("w(6);", "b")],
)
def test_the_condition_after_a_repeat_body(text, body, expected) -> None:
    assert text.after_body(at(body)) == expected


@pytest.mark.parametrize(
    "body,expected",
    [
        ("{ w(1); }", "[1]"),
        ("{ w(2); }", "[2..3], [5]"),
        ("w(7);", "[7]"),
        ("{ w(0); }", "default"),
    ],
)
def test_match_choice_labels(text, body, expected) -> None:
    # The match's choices are the second occurrence of each body text.
    nth = 1 if body in ("{ w(1); }", "{ w(2); }") else 0
    assert text.choice_label(at(body, nth)) == expected


def test_a_statement_ends_at_its_own_semicolon(text) -> None:
    """Brackets and braces inside the statement don't end it early."""
    line, col = text.statement_end(at("write_reg"))
    assert (line, col) == (at("; w(9)").lineno, at("; w(9)").linepos)


def test_a_position_that_is_not_a_token_gives_none(text) -> None:
    assert text.after_keyword(Loc(1, 1, 2)) is None
    assert text.before(Loc(1, 200, 1)) is None
    assert text.statement_end(Loc(1, -1, -1)) is None


def test_a_missing_file_gives_none(tmp_path) -> None:
    text = SourceText({1: str(tmp_path / "gone.pss")})
    assert text.after_keyword(Loc(1, 1, 1)) is None
    assert text.after_keyword(Loc(2, 1, 1)) is None


def test_each_file_is_tokenized_once(text) -> None:
    text.after_keyword(at("while"))
    first = text.file(1)
    text.after_keyword(at("match"))
    assert text.file(1) is first


# --- activities (activity-diagrams plan AD1-TEST-2) ----------------------------------

ACTIVITY = """\
activity {
    parallel join_first ( n + 1 ) { a; b; }
    schedule join_branch (x, y) { x: a; y: b; }
    parallel { a; }
    select {
        (go && fast) [ 3 ]: a;
        [w + 1]: { b; }
        c;
        (go): d;
    }
    do A with { len ==  4;  addr > 0; };
    do B;
    constraint { n < 8; }
}
"""


@pytest.fixture
def act(tmp_path):
    path = tmp_path / "a.pss"
    path.write_text(ACTIVITY)
    return SourceText({1: str(path)})


def act_at(needle: str, nth: int = 0) -> Loc:
    start = -1
    for _ in range(nth + 1):
        start = ACTIVITY.index(needle, start + 1)
    line = ACTIVITY.count("\n", 0, start) + 1
    col = start - (ACTIVITY.rfind("\n", 0, start) + 1) + 1
    return Loc(1, line, col)


def test_a_join_spec_is_the_text_before_the_brace(act) -> None:
    assert act.between_keyword_and_brace(act_at("parallel")) == "join_first ( n + 1 )"
    assert act.between_keyword_and_brace(act_at("schedule")) == "join_branch (x, y)"
    assert act.between_keyword_and_brace(act_at("parallel", 1)) is None


def test_a_select_arm_gives_its_guard_and_weight(act) -> None:
    assert act.select_arm(act_at("a;", 3)) == ("go && fast", "3")
    assert act.select_arm(act_at("{ b; }")) == (None, "w + 1")
    assert act.select_arm(act_at("c;")) == (None, None)
    assert act.select_arm(act_at("d;")) == ("go", None)


def test_a_with_clause_is_its_constraints(act) -> None:
    assert act.with_clause(act_at("do A")) == "len ==  4;  addr > 0;"
    assert act.with_clause(act_at("do B")) is None


def test_braced_after_is_the_first_brace_pair(act) -> None:
    assert act.braced_after(act_at("constraint")) == "n < 8;"
    assert act.braced_after(act_at("do B")) is None
