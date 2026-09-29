"""The step tree: targets, ranges, nesting, control flow and numbering.

Programming-steps plan ``S2-TEST-2``, covering ``S2-IMPL-1`` to ``-4``, ``-9``
and ``-10``. Trees are compared whole, as `support.steps_outline` lines, so a
change anywhere in a tree shows up as a readable diff.
"""

from __future__ import annotations

import pathlib

import pytest
from support import steps_outline

from sphinx_pss.model.parse import parse_model
from sphinx_pss.model.steps import (
    EXEC_KINDS,
    Step,
    StepsError,
    StepsUnavailable,
    steps_for,
)

pytestmark = pytest.mark.unit

STEPS_DIR = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "pss" / "steps"
ETH = [str(STEPS_DIR / n) for n in ("eth_mac.pss", "eth_ext_a.pss", "eth_ext_b.pss")]


@pytest.fixture(scope="module")
def eth():
    return parse_model(ETH)


@pytest.fixture
def tree(tmp_path):
    """The outline of ``target``'s steps in ``source``, parsed as ``t.pss``."""

    def run(source: str, target: str = "p::f", **options) -> list[str]:
        path = tmp_path / "t.pss"
        path.write_text(source)
        return steps_outline(steps_for(parse_model([str(path)]), target, **options))

    return run


def _body(statements: str) -> str:
    """``statements`` as the body of ``p::f``; the first is on line 5."""
    return (
        "package p {\n"
        "    function void w(int v);\n"
        "    function bit[32] r();\n"
        "    function void f(bool b, int x) {\n"
        f"{statements}"
        "    }\n"
        "}\n"
    )


# --- the fixture ---------------------------------------------------------------


def test_init_eth_in_outline_numbering_is_the_frm_structure(eth) -> None:
    """Plan ``S3-TEST-3``'s structure, checked on the model: 1, a), i."""
    assert steps_outline(steps_for(eth, "eth_pkg::init_eth", numbering="outline")) == [
        "1 Initialize the Ethernet controller @89",
        "  -> eth_pkg::init_controller",
        "    a) Disable the controller @35",
        "    b) Wait for the controller to go idle @40",
        "    c) Disable and clear the Ethernet interrupts @43",
        "    d) Clear the descriptor start addresses @47",
        "2 Initialize the MAC @92",
        "  -> eth_pkg::init_mac",
        "    a) Reset the MAC @74",
        "    b) Initialize the MII management interface @78",
        "      -> eth_pkg::init_miim",
        "        i. Reset the RMII module, if RMII is in use @54",
        "        ii. Reset the MII management block @61",
        "        iii. Select the MDC clock divider @64",
        "        iv. Release the MII management block @68",
        "    c) Enable the receiver @81",
        "3 Enable the controller @95",
    ]


def test_init_eth_in_decimal_numbering(eth) -> None:
    numbers = [s.number for s in steps_for(eth, "eth_pkg::init_eth").steps()]
    assert numbers == [
        "1", "1.1", "1.2", "1.3", "1.4",
        "2", "2.1", "2.2", "2.2.1", "2.2.2", "2.2.3", "2.2.4", "2.3",
        "3",
    ]  # fmt: skip


def test_an_if_without_steps_is_part_of_its_step(eth) -> None:
    """``init_miim``'s RMII reset: the ``if`` holds no markers, so it isn't drawn."""
    assert steps_outline(steps_for(eth, "eth_pkg::init_miim")) == [
        "1 Reset the RMII module, if RMII is in use @54",
        "2 Reset the MII management block @61",
        "3 Select the MDC clock divider @64",
        "4 Release the MII management block @68",
    ]


def test_marked_match_and_loops(eth) -> None:
    assert steps_outline(steps_for(eth, "eth_pkg::set_speed")) == [
        "1 Program the speed @101",
        "  [match speed]*",
        "  choice [SPEED_10]",
        "    1.1 Select 10 Mbps @104",
        "  choice [SPEED_100]",
        "    1.2 Select 100 Mbps @108",
        "2 Poll the PHY until the link is up @113",
        "  [repeat_while (read_reg(0x2A0) & 0x4) == 0]*",
        "    2.1 Read the PHY status @115",
        "3 Settle @119",
        "  [repeat_count i : retries]*",
        "    3.1 Wait one MDC period @121",
    ]


def test_a_foreach(eth) -> None:
    assert steps_outline(steps_for(eth, "eth_pkg::clear_rx")) == [
        "1 Release each descriptor @128",
        "  [foreach d : descriptors]*",
        "    1.1 Clear its ownership bit @130",
    ]


def test_a_component_exec_block(eth) -> None:
    doc = steps_for(eth, "eth_pkg::eth_c", exec_kind="init_down", depth=1)
    assert steps_outline(doc) == [
        "1 Bring up the Ethernet port @154",
        "  -> eth_pkg::init_eth",
        "    1.1 Initialize the Ethernet controller @89",
        "    1.2 Initialize the MAC @92",
        "    1.3 Enable the controller @95",
    ]
    assert doc.exec_kind == "init_down"


def test_a_step_carries_its_source_and_detail(eth) -> None:
    doc = steps_for(eth, "eth_pkg::init_miim")
    step = next(s for s in doc.steps() if s.title == "Select the MDC clock divider")

    assert step.source.path == ETH[0]
    assert step.source.line == 64
    assert step.detail == ("SYSCLK / 40 keeps MDC below 2.5 MHz.",)
    assert step.detail_line == 65


def test_the_fixture_renders_without_prelude_calls(eth) -> None:
    """``init_eth`` declares ``revision = read_reg(...)`` before its first step."""
    for target in ("init_eth", "init_controller", "init_mac", "init_miim", "set_speed"):
        assert steps_for(eth, f"eth_pkg::{target}").issues == []


# --- ranges ---------------------------------------------------------------------


def test_a_step_runs_to_the_next_marker(tree) -> None:
    source = _body(
        "        /// Step: One\n"
        "        w(1);\n"
        "        w(2);\n"
        "        if (b) { w(3); }\n"
        "        /// Step: Two\n"
        "        w(4);\n"
    )
    assert tree(source) == ["1 One @5", "2 Two @9"]


def test_trailing_and_detached_markers(tree) -> None:
    source = _body(
        "        w(1); /// Step: Trailing\n"
        "        w(2);\n"
        "        /// Step: Detached\n"
        "\n"
        "        w(3);\n"
    )
    assert tree(source) == ["1 Trailing @5", "2 Detached @7"]


def test_markers_with_nothing_in_them_are_still_steps(tree) -> None:
    """The lint reports these (``pss.step_empty``); the tree keeps them in place."""
    source = _body(
        "        /// Step: A\n"
        "        /// Step: B\n"
        "        w(1);\n"
        "        /// Step: C\n"
    )
    assert tree(source) == ["1 A @5", "2 B @6", "3 C @8"]


def test_plain_comments_are_not_steps(tree) -> None:
    source = _body(
        "        // Step: plain\n"
        "        w(1);\n"
        "        /* Step: plain block */\n"
        "        w(2);\n"
        "        /// Step: Real\n"
        "        w(3);\n"
    )
    assert tree(source) == ["1 Real @9"]


def test_a_block_comment_marker_and_its_detail(tmp_path) -> None:
    path = tmp_path / "t.pss"
    path.write_text(
        _body(
            "        /** A note for the reader of the code.\n"
            "         *  Step: Enable the receiver\n"
            "         *\n"
            "         *  Done last.\n"
            "         */\n"
            "        w(1);\n"
        )
    )
    [step] = steps_for(parse_model([str(path)]), "p::f").steps()

    assert (step.title, step.source.line) == ("Enable the receiver", 6)
    assert (step.detail, step.detail_line) == (("Done last.",), 8)


# --- nesting --------------------------------------------------------------------


def test_markers_in_a_nested_block_are_sub_steps(tree) -> None:
    source = _body(
        "        /// Step: Outer\n"
        "        w(0);\n"
        "        if (b) {\n"
        "            /// Step: Inner\n"
        "            w(1);\n"
        "        }\n"
        "        {\n"
        "            /// Step: In a bare block\n"
        "            w(2);\n"
        "        }\n"
    )
    assert tree(source) == [
        "1 Outer @5",
        "  if b",
        "    1.1 Inner @8",
        "  1.2 In a bare block @12",
    ]


def test_a_nested_block_before_the_first_step_hangs_off_its_control(tree) -> None:
    """Design 4.2: no step holds the ``if``, so it sits at the outer level."""
    source = _body(
        "        if (b) {\n"
        "            /// Step: Only when b\n"
        "            w(1);\n"
        "        }\n"
        "        /// Step: Always\n"
        "        w(2);\n"
    )
    assert tree(source) == ["if b", "  1 Only when b @6", "2 Always @9"]


def test_a_marker_after_the_last_statement_is_an_empty_step(tree) -> None:
    source = _body(
        "        /// Step: A\n"
        "        w(1);\n"
        "        if (b) {\n"
        "            w(2);\n"
        "            /// Step: Trailing\n"
        "        }\n"
    )
    assert tree(source) == ["1 A @5", "  if b", "    1.1 Trailing @9"]


# --- control flow ----------------------------------------------------------------


def test_an_if_chain_shows_every_arm(tree) -> None:
    source = _body(
        "        /// Step: Choose\n"
        "        if (b) {\n"
        "            /// Step: First\n"
        "            w(1);\n"
        "        } else if ((x & 3) == 1) {\n"
        "            w(2);\n"
        "        } else {\n"
        "            /// Step: Last\n"
        "            w(3);\n"
        "        }\n"
    )
    assert tree(source) == [
        "1 Choose @5",
        "  if b*",
        "    1.1 First @7",
        "  else_if (x & 3) == 1",
        "  else",
        "    1.2 Last @12",
    ]


def test_an_unmarked_control_is_not_flagged(tree) -> None:
    source = _body(
        "        /// Step: Poll\n"
        "        w(0);\n"
        "        while ((r() & 1) != 0) {\n"
        "            /// Step: Once\n"
        "            w(1);\n"
        "        }\n"
    )
    assert tree(source) == ["1 Poll @5", "  [while (r() & 1) != 0]", "    1.1 Once @8"]


@pytest.mark.parametrize(
    "loop,expected",
    [
        ("while (b) {", "[while b]*"),
        ("repeat (3) {", "[repeat_count 3]*"),
        ("repeat (i : x + 1) {", "[repeat_count i : x + 1]*"),
    ],
)
def test_each_loop_kind_is_labelled(tree, loop, expected) -> None:
    source = _body(
        "        /// Step: Loop\n"
        f"        {loop}\n"
        "            /// Step: Body\n"
        "            w(1);\n"
        "        }\n"
    )
    assert tree(source) == ["1 Loop @5", f"  {expected}", "    1.1 Body @7"]


def test_a_match_with_a_default(tree) -> None:
    source = _body(
        "        match (x) {\n"
        "            [1]: {\n"
        "                /// Step: One\n"
        "                w(1);\n"
        "            }\n"
        "            default: {\n"
        "                /// Step: Other\n"
        "                w(0);\n"
        "            }\n"
        "        }\n"
    )
    assert tree(source) == [
        "[match x]",
        "choice [1]",
        "  1 One @7",
        "default",
        "  2 Other @11",
    ]


# --- targets ----------------------------------------------------------------------


def test_the_exec_kinds() -> None:
    assert set(EXEC_KINDS) == {
        "body", "init_down", "init_up", "pre_solve", "post_solve",
        "pre_body", "run_start", "run_end",
    }  # fmt: skip


@pytest.mark.parametrize(
    "target,options,message",
    [
        ("eth_pkg::nope", {}, "no PSS function or type named 'eth_pkg::nope'"),
        ("eth_pkg", {}, "'eth_pkg' is not a function or a type"),
        ("eth_pkg::write_reg", {}, "function 'eth_pkg::write_reg' has no body"),
        ("eth_pkg::init_eth", {"exec_kind": "body"}, "is a function"),
        ("eth_pkg::eth_c", {}, "is a type: name its exec block"),
        ("eth_pkg::eth_c", {"exec_kind": "bodyy"}, "unknown exec kind 'bodyy'; expected one of: body, init_down"),
        ("eth_pkg::eth_c", {"exec_kind": "run_start"}, "has no 'exec run_start' block"),
        ("eth_pkg::init_eth", {"numbering": "roman"}, "unknown numbering 'roman'"),
        ("eth_pkg::init_eth", {"expand_calls": "all"}, "unknown expand-calls mode 'all'"),
        ("eth_pkg::init_eth", {"depth": -1}, "depth must not be negative"),
    ],
)
def test_a_bad_target_or_option_is_an_error(eth, target, options, message) -> None:
    with pytest.raises(StepsError, match=None) as info:
        steps_for(eth, target, **options)
    assert message in str(info.value)


def test_a_model_that_did_not_link_has_no_steps(tmp_path) -> None:
    """Plan ``S2-IMPL-10``: the directive turns this into one warning (S3)."""
    path = tmp_path / "t.pss"
    path.write_text("package p {\n    function void f() {\n        undefined_fn();\n    }\n}\n")
    model = parse_model([str(path)], tolerate_link_errors=True)
    assert not model.linked

    with pytest.raises(StepsUnavailable, match="did not link"):
        steps_for(model, "p::f")


# --- numbering --------------------------------------------------------------------


def test_outline_numbering_cycles_below_roman(tree) -> None:
    """Level four starts the 1, a), i. cycle again."""
    source = _body(
        "        /// Step: L1\n"
        "        {\n"
        "            /// Step: L2\n"
        "            {\n"
        "                /// Step: L3\n"
        "                {\n"
        "                    /// Step: L4\n"
        "                    w(1);\n"
        "                }\n"
        "            }\n"
        "        }\n"
    )
    assert [line.split(" @")[0].strip() for line in tree(source, numbering="outline")] == [
        "1 L1",
        "a) L2",
        "i. L3",
        "1 L4",
    ]


def test_letters_and_numerals_past_the_first_few(tree) -> None:
    body = "        /// Step: Top\n        {\n" + "".join(
        f"            /// Step: S{n}\n            w({n});\n" for n in range(1, 29)
    ) + "        }\n"
    numbers = [line.split()[0] for line in tree(_body(body), numbering="outline")]
    assert numbers[1:4] == ["a)", "b)", "c)"]
    assert numbers[26:29] == ["z)", "aa)", "ab)"]


def test_steps_are_objects_not_values() -> None:
    """Two steps with the same title are different rows."""
    from sphinx_pss.model.objects import SourceRef

    a = Step("Same", SourceRef("t.pss", 1))
    b = Step("Same", SourceRef("t.pss", 1))
    assert a != b
