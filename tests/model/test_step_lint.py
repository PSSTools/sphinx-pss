"""The whole-model marker lint (programming-steps plan ``S1-IMPL-3`` / ``S1-TEST-2``).

Each case is a small model parsed from source, so a change in how the parser
attaches comments shows up here as well as in the ``upstream`` guards.
"""

from __future__ import annotations

import pathlib

import pytest

from sphinx_pss.model.parse import parse_model
from sphinx_pss.model.steps_lint import (
    STEP_EMPTY,
    STEP_MISPLACED,
    STEP_SYNTAX,
    lint_markers,
)

pytestmark = pytest.mark.unit

FIXTURE_DIR = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "pss"


@pytest.fixture
def lint(tmp_path):
    """Lint ``source`` as ``t.pss``; ``(code, line)`` for each issue."""

    def run(source: str, *, tolerate_link_errors: bool = False) -> list[tuple[str, int]]:
        path = tmp_path / "t.pss"
        path.write_text(source)
        model = parse_model([str(path)], tolerate_link_errors=tolerate_link_errors)
        issues = lint_markers(model)
        assert all(i.path == str(path) for i in issues)
        return [(i.code, i.line) for i in issues]

    return run


def _body(statements: str) -> str:
    """``statements`` inside a function body; its first line is line 5."""
    return (
        "package p {\n"
        "    function void w(int v);\n"
        "    function bit[32] r();\n"
        "    function void f(bool b, int x) {\n"
        f"{statements}"
        "    }\n"
        "}\n"
    )


# --- valid markers are silent -------------------------------------------------


def test_markers_in_every_placement_and_nesting_are_silent(lint) -> None:
    assert (
        lint(
            _body(
                "        /// Step: Leading\n"
                "        w(1);\n"
                "        /// Step: Detached\n"
                "\n"
                "        w(2);\n"
                "        w(3); /// Step: Trailing\n"
                "        /** Step: Block\n"
                "         *  With detail.\n"
                "         */\n"
                "        w(4);\n"
                "        if (b) {\n"
                "            /// Step: In a branch\n"
                "            w(5);\n"
                "        } else if (x > 1) {\n"
                "            /// Step: In another\n"
                "            w(6);\n"
                "        } else {\n"
                "            /// Step: In the last\n"
                "            w(7);\n"
                "        }\n"
                "        while ((r() & 1) != 0) {\n"
                "            /// Step: In a loop\n"
                "            w(8);\n"
                "        }\n"
                "        repeat (2) {\n"
                "            /// Step: In a count loop\n"
                "            w(9);\n"
                "        }\n"
                "        match (x) {\n"
                "            [1]: {\n"
                "                /// Step: In a choice\n"
                "                w(10);\n"
                "            }\n"
                "        }\n"
                "        {\n"
                "            /// Step: In a bare block\n"
                "            w(11);\n"
                "        }\n"
            )
        )
        == []
    )


def test_markers_in_exec_blocks_are_silent(lint) -> None:
    source = (
        "package p {\n"
        "    function void w(int v);\n"
        "    component c {\n"
        "        exec init_down {\n"
        "            /// Step: Initialize\n"
        "            w(1);\n"
        "        }\n"
        "        action a {\n"
        "            exec body {\n"
        "                /// Step: Run\n"
        "                w(2);\n"
        "            }\n"
        "        }\n"
        "    }\n"
        "    extend component c {\n"
        "        exec init_down {\n"
        "            /// Step: Extended\n"
        "            w(3);\n"
        "        }\n"
        "    }\n"
        "}\n"
    )
    assert lint(source) == []


def test_the_fixture_is_clean() -> None:
    """``steps_pkg.pss`` is documented under ``-W``; it must stay silent."""
    model = parse_model([str(FIXTURE_DIR / "steps_pkg.pss")])
    assert lint_markers(model) == []


# --- plain comments are never read ---------------------------------------------


@pytest.mark.parametrize(
    "comment",
    [
        "// Step: plain line",
        "// step: plain near miss",
        "/* Step: plain block */",
        "/* STEP 3 plain block near miss */",
        "//// Step: a rule of slashes",
        "// Step:",
    ],
)
def test_plain_comments_are_never_reported(lint, comment) -> None:
    body = _body(f"        {comment}\n        w(1);\n")
    declarations = (
        "package p {\n"
        f"    {comment}\n"
        "    struct s {\n"
        f"        {comment}\n"
        "        int a;\n"
        "    }\n"
        "}\n"
    )
    assert lint(body) == []
    assert lint(declarations) == []


# --- step_syntax -----------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    ["step: reset", "STEP 3 Reset", "Steps: reset", "Step Reset", "Step"],
)
def test_near_misses_in_a_body(lint, text) -> None:
    assert lint(_body(f"        /// {text}\n        w(1);\n")) == [(STEP_SYNTAX, 5)]


def test_a_near_miss_is_located_at_its_own_line(lint) -> None:
    source = _body(
        "        /**\n"
        "         * Reset the MAC.\n"
        "         * step: reset\n"
        "         */\n"
        "        w(1);\n"
    )
    assert lint(source) == [(STEP_SYNTAX, 7)]


def test_near_misses_on_declarations_are_prose(lint) -> None:
    source = (
        "package p {\n"
        "    /// Steps are numbered by the tool.\n"
        "    /// step 1 of the handshake\n"
        "    struct s {\n"
        "        int a;\n"
        "    }\n"
        "}\n"
    )
    assert lint(source) == []


# --- step_misplaced ---------------------------------------------------------------


def test_misplaced_markers(lint) -> None:
    source = (
        "/// Step: Above the package\n"  # 1
        "package p {\n"
        "    /// Step: On a struct\n"  # 3
        "    struct s {\n"
        "        /// Step: On a field\n"  # 5
        "        int a;\n"
        "    }\n"
        "    /// Step: On a function\n"  # 8
        "    function void w(int v) {\n"
        "        /// Step: In its body\n"
        "        w(v);\n"
        "    }\n"
        "    component c {\n"
        "        /// Step: On an action\n"  # 14
        "        action a {\n"
        "            /// Step: On an exec block\n"  # 16
        "            exec body {\n"
        "                w(1);\n"
        "            }\n"
        "        }\n"
        "        /// Step: At component scope\n"  # 21
        "    }\n"
        "    /// Step: At package scope\n"  # 23
        "}\n"
    )
    assert lint(source) == [(STEP_MISPLACED, n) for n in (1, 3, 5, 8, 14, 16, 21, 23)]


def test_a_misplaced_marker_names_its_title(tmp_path) -> None:
    path = tmp_path / "t.pss"
    path.write_text("package p {\n    /// Step: On a struct\n    struct s { int a; }\n}\n")
    [issue] = lint_markers(parse_model([str(path)]))

    assert issue.location() == f"{path}:2"
    assert "'Step: On a struct'" in issue.message


# --- step_empty -----------------------------------------------------------------


def test_a_marker_with_no_title(lint) -> None:
    assert lint(_body("        /// Step:\n        w(1);\n")) == [(STEP_EMPTY, 5)]


def test_a_marker_after_the_last_statement(lint) -> None:
    source = _body(
        "        /// Step: A\n"
        "        w(1);\n"
        "        if (b) {\n"
        "            w(2);\n"
        "            /// Step: Nothing follows\n"  # 9
        "        }\n"
        "        /// Step: Nothing follows either\n"  # 11
    )
    assert lint(source) == [(STEP_EMPTY, 9), (STEP_EMPTY, 11)]


def test_a_marker_followed_directly_by_another(lint) -> None:
    source = _body(
        "        /// Step: A\n"  # 5
        "        /// Step: B\n"
        "        w(1);\n"
        "        /// Step: C\n"  # 8
        "\n"
        "        /// Step: D\n"
        "        w(2);\n"
        "        /// Step: E\n"  # 12
        "        w(3); /// Step: F\n"
    )
    assert lint(source) == [(STEP_EMPTY, 5), (STEP_EMPTY, 8), (STEP_EMPTY, 12)]


def test_a_bare_marker_is_reported_once(lint) -> None:
    """No title is the problem; that it has no statements is not repeated."""
    assert lint(_body("        w(1);\n        /// Step:\n")) == [(STEP_EMPTY, 6)]


# --- the model as a whole ----------------------------------------------------------


def test_issues_come_back_in_source_order_across_files(tmp_path) -> None:
    a = tmp_path / "a.pss"
    b = tmp_path / "b.pss"
    a.write_text("package pa {\n    /// Step: X\n    struct s { int a; }\n}\n")
    b.write_text("package pb {\n\n    /// Step: Y\n    struct s { int a; }\n}\n")
    issues = lint_markers(parse_model([str(b), str(a)]))

    assert [(pathlib.Path(i.path).name, i.line) for i in issues] == [("a.pss", 2), ("b.pss", 3)]


def test_a_model_that_did_not_link_is_still_linted(lint) -> None:
    source = (
        "package p {\n"
        "    function void f() {\n"
        "        /// step: typo\n"
        "        undefined_fn();\n"
        "    }\n"
        "}\n"
    )
    assert lint(source, tolerate_link_errors=True) == [(STEP_SYNTAX, 3)]
