"""Call resolution and expansion (programming-steps plan ``S2-IMPL-6``, ``-7`` / ``S2-TEST-3``).

A call inside a step's range, to a function with markers, expands into that
function's steps. Calls are followed through the linker's bindings, so every
call shape of plan section 1.2 is covered: a package function, a component
function called bare and through ``comp.``, and ``comp.sub.fn()``.
"""

from __future__ import annotations

import pytest
from support import steps_outline

from sphinx_pss.model.calls import call_index, symbol_index
from sphinx_pss.model.parse import iter_children, parse_model
from sphinx_pss.model.steps import steps_for

pytestmark = pytest.mark.unit

CALLS = """\
package p {
    import addr_reg_pkg::*;

    function void w(int v);

    function void pkg_fn() {
        /// Step: In the package function
        w(1);
    }

    function void unmarked() {
        w(2);
    }

    component regs_c : reg_group_c {
        reg_c<bit[32]> ctrl;
    }

    component sub_c {
        function void sub_fn() {
            /// Step: In the sub-component function
            w(3);
        }
    }

    component pss_top {
        sub_c sub;
        regs_c regs;

        function void top_fn() {
            /// Step: In the component function
            pkg_fn();
        }

        exec init_down {
            /// Step: Initialize
            top_fn();
        }

        action a {
            exec body {
                /// Step: Every shape of call
                comp.sub.sub_fn();
                comp.top_fn();
                pkg_fn();
                unmarked();
                comp.regs.ctrl.write_val(5);
            }
        }
    }
}
"""


@pytest.fixture(scope="module")
def calls(tmp_path_factory):
    path = tmp_path_factory.mktemp("calls") / "calls.pss"
    path.write_text(CALLS)
    return parse_model([str(path)])


@pytest.fixture
def tree(tmp_path):
    def run(source: str, target: str = "p::f", **options) -> list[str]:
        path = tmp_path / "t.pss"
        path.write_text(source)
        return steps_outline(steps_for(parse_model([str(path)]), target, **options))

    return run


# --- resolution -------------------------------------------------------------------


def test_every_call_shape_resolves(calls) -> None:
    [block] = [
        c for c in iter_children(symbol_index(calls).scopes["p::pss_top::a"])
        if type(c).__name__ == "ExecBlock"
    ]
    found = [call_index(calls).calls_in(stmt) for stmt in iter_children(block)]

    assert [[(c.name, c.callee.qualname if c.callee else None) for c in cs] for cs in found] == [
        [("sub_fn", "p::sub_c::sub_fn")],
        [("top_fn", "p::pss_top::top_fn")],
        [("pkg_fn", "p::pkg_fn")],
        [("unmarked", "p::unmarked")],
        [("write_val", None)],  # the standard library: no callee, never expanded
    ]


# --- expansion ----------------------------------------------------------------------


def test_member_and_package_calls_expand_in_call_order(calls) -> None:
    """Unmarked and library callees are opaque: part of the step, not expanded."""
    assert steps_outline(steps_for(calls, "p::pss_top::a", exec_kind="body")) == [
        "1 Every shape of call @42",
        "  -> p::sub_c::sub_fn",
        "    1.1 In the sub-component function @21",
        "  -> p::pss_top::top_fn",
        "    1.2 In the component function @31",
        "      -> p::pkg_fn",
        "        1.2.1 In the package function @7",
        "  -> p::pkg_fn",
        "    1.3 In the package function @7",
    ]


def test_a_component_exec_calls_its_own_function(calls) -> None:
    assert steps_outline(steps_for(calls, "p::pss_top", exec_kind="init_down")) == [
        "1 Initialize @36",
        "  -> p::pss_top::top_fn",
        "    1.1 In the component function @31",
        "      -> p::pkg_fn",
        "        1.1.1 In the package function @7",
    ]


@pytest.mark.parametrize(
    "depth,expected",
    [
        (0, ["1 Initialize @36"]),
        (1, ["1 Initialize @36", "  -> p::pss_top::top_fn", "    1.1 In the component function @31"]),
        (2, ["1 Initialize @36", "  -> p::pss_top::top_fn", "    1.1 In the component function @31",
             "      -> p::pkg_fn", "        1.1.1 In the package function @7"]),
    ],
)  # fmt: skip
def test_depth_limits_how_many_levels_expand(calls, depth, expected) -> None:
    doc = steps_for(calls, "p::pss_top", exec_kind="init_down", depth=depth)
    assert steps_outline(doc) == expected


def test_link_mode_references_the_callee(calls) -> None:
    doc = steps_for(calls, "p::pss_top", exec_kind="init_down", expand_calls="link")
    assert steps_outline(doc) == ["1 Initialize @36", "  -> p::pss_top::top_fn (link)"]


def test_none_mode_expands_nothing(calls) -> None:
    doc = steps_for(calls, "p::pss_top::a", exec_kind="body", expand_calls="none")
    assert steps_outline(doc) == ["1 Every shape of call @42"]


RECURSIVE = """\
package p {
    function void w(int v);
    function void ping(int n) {
        /// Step: Ping
        w(n);
        /// Step: Maybe pong
        if (n > 0) {
            pong(n - 1);
        }
    }
    function void pong(int n) {
        /// Step: Pong
        ping(n);
    }
    function void f(int n) {
        /// Step: Start
        ping(n);
    }
    function void self_call(int n) {
        /// Step: Again
        self_call(n - 1);
    }
}
"""


def test_mutual_recursion_is_cut_with_a_reference_back(tree) -> None:
    assert tree(RECURSIVE) == [
        "1 Start @16",
        "  -> p::ping",
        "    1.1 Ping @4",
        "    1.2 Maybe pong @6",
        "      if n > 0*",
        "        -> p::pong",
        "          1.2.1 Pong @12",
        "            -> p::ping (see 1.1)",
    ]


def test_a_function_calling_itself_refers_to_its_first_step(tree) -> None:
    assert tree(RECURSIVE, "p::self_call") == ["1 Again @20", "  -> p::self_call (see 1)"]


def test_an_if_that_only_holds_an_expanding_call_is_shown(tree) -> None:
    """The condition is kept: the callee's steps only happen when it holds."""
    assert tree(RECURSIVE, "p::ping")[2:4] == ["  if n > 0*", "    -> p::pong"]


def test_calls_in_arguments_and_initializers_expand(tree) -> None:
    source = """\
package p {
    function int g() {
        /// Step: In g
        return 1;
    }
    function void w(int v);
    function void f() {
        /// Step: Outer
        w(g());
        int x = g();
    }
}
"""
    assert tree(source) == ["1 Outer @8", "  -> p::g", "    1.1 In g @3", "  -> p::g", "    1.2 In g @3"]


def test_calls_in_conditions_do_not_expand(tree) -> None:
    source = """\
package p {
    function bool ready() {
        /// Step: Check
        return true;
    }
    function void w(int v);
    function void f() {
        /// Step: Wait
        while (!ready()) { w(1); }
    }
}
"""
    assert tree(source) == ["1 Wait @8"]


def test_a_declared_only_callee_is_opaque(tree) -> None:
    source = """\
package p {
    import target C function void ext_fn();
    function void f() {
        /// Step: Call out
        ext_fn();
    }
}
"""
    assert tree(source) == ["1 Call out @4"]
