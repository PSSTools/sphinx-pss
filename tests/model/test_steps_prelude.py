"""Calls the step table would leave out (plan ``S2-IMPL-8`` / ``S2-TEST-4``, design ``STEP-T4``).

A call statement or call assignment outside every step is device activity
the table doesn't show, so it is a ``pss.step_prelude_call`` problem at its
own line. Declarations are exempt, however they initialize, and so are the
conditions of control statements. A body with no steps is never checked.
"""

from __future__ import annotations

import pytest

from sphinx_pss.model.parse import parse_model
from sphinx_pss.model.steps import STEP_PRELUDE_CALL, steps_for

pytestmark = pytest.mark.unit


@pytest.fixture
def prelude(tmp_path):
    """``(code, line)`` of each problem in ``target``'s steps."""

    def run(source: str, target: str = "p::f") -> list[tuple[str, int]]:
        path = tmp_path / "t.pss"
        path.write_text(source)
        doc = steps_for(parse_model([str(path)]), target)
        assert all(i.path == str(path) for i in doc.issues)
        return [(i.code, i.line) for i in doc.issues]

    return run


def _body(statements: str) -> str:
    """``statements`` as the body of ``p::f``; the first is on line 6."""
    return (
        "package p {\n"
        "    function void w(int v);\n"
        "    function bit[32] r();\n"
        "    function void helper() { w(0); }\n"
        "    function void f(bool b) {\n"
        f"{statements}"
        "    }\n"
        "}\n"
    )


def test_a_call_before_the_first_step(prelude) -> None:
    source = _body(
        "        w(1);\n"
        "        helper();\n"
        "        /// Step: First\n"
        "        w(2);\n"
    )
    assert prelude(source) == [(STEP_PRELUDE_CALL, 6), (STEP_PRELUDE_CALL, 7)]


def test_a_call_nested_in_an_if_before_the_first_step(prelude) -> None:
    source = _body(
        "        if (b) {\n"
        "            w(1);\n"
        "        }\n"
        "        /// Step: First\n"
        "        w(2);\n"
    )
    assert prelude(source) == [(STEP_PRELUDE_CALL, 7)]


def test_an_assignment_from_a_call_is_reported(prelude) -> None:
    """Plan decision D3."""
    source = _body(
        "        bit[32] s;\n"
        "        s = r();\n"
        "        /// Step: First\n"
        "        w(2);\n"
    )
    assert prelude(source) == [(STEP_PRELUDE_CALL, 7)]


def test_a_declaration_initialized_from_a_call_is_not(prelude) -> None:
    source = _body(
        "        bit[32] s = r();\n"
        "        /// Step: First\n"
        "        w(s);\n"
    )
    assert prelude(source) == []


def test_a_call_in_a_condition_is_not(prelude) -> None:
    source = _body(
        "        while ((r() & 1) != 0) { }\n"
        "        if (r() == 0) { }\n"
        "        /// Step: First\n"
        "        w(2);\n"
    )
    assert prelude(source) == []


def test_calls_inside_steps_are_not(prelude) -> None:
    source = _body(
        "        /// Step: First\n"
        "        w(1);\n"
        "        if (b) {\n"
        "            w(2);\n"
        "        }\n"
    )
    assert prelude(source) == []


def test_an_unmarked_function_is_never_checked(prelude) -> None:
    assert prelude(_body("        w(1);\n        helper();\n")) == []


def test_a_call_after_a_nested_step_but_outside_every_step(prelude) -> None:
    """The ``if``'s step ends with its block, and no outer step has started."""
    source = _body(
        "        if (b) {\n"
        "            /// Step: Only when b\n"
        "            w(1);\n"
        "        }\n"
        "        w(2);\n"
        "        /// Step: Always\n"
        "        w(3);\n"
    )
    assert prelude(source) == [(STEP_PRELUDE_CALL, 10)]


def test_a_library_call_in_an_exec_block_is_reported(tmp_path) -> None:
    path = tmp_path / "t.pss"
    path.write_text(
        "package p {\n"
        "    import addr_reg_pkg::*;\n"
        "    function void w(int v);\n"
        "    component regs_c : reg_group_c {\n"
        "        reg_c<bit[32]> ctrl;\n"
        "    }\n"
        "    component pss_top {\n"
        "        regs_c regs;\n"
        "        action a {\n"
        "            exec body {\n"
        "                comp.regs.ctrl.write_val(5);\n"
        "                /// Step: First\n"
        "                w(1);\n"
        "            }\n"
        "        }\n"
        "    }\n"
        "}\n"
    )
    doc = steps_for(parse_model([str(path)]), "p::pss_top::a", exec_kind="body")
    assert [(i.code, i.line) for i in doc.issues] == [(STEP_PRELUDE_CALL, 11)]


def test_the_message_names_the_call(tmp_path) -> None:
    path = tmp_path / "t.pss"
    path.write_text(_body("        helper();\n        /// Step: First\n        w(2);\n"))
    [issue] = steps_for(parse_model([str(path)]), "p::f").issues

    assert issue.location() == f"{path}:6"
    assert issue.message.startswith("call to 'helper' is outside every step")


def test_an_expanded_callee_is_checked_once(prelude) -> None:
    """A callee is part of what is shown, however many times it is called."""
    source = """\
package p {
    function void w(int v);
    function void callee() {
        w(0);
        /// Step: In the callee
        w(1);
    }
    function void f() {
        /// Step: Twice
        callee();
        callee();
    }
}
"""
    assert prelude(source) == [(STEP_PRELUDE_CALL, 4)]
