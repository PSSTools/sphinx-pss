"""Flowchart lowering: a step tree as a graph (programming-steps plan ``S4-TEST-2``).

The graph is checked without a back-end. Graphs are compared as readable text:
each edge as ``from -> to``, using node labels, with ``[label]`` for a labelled
edge and ``(back)`` for a loop's back-edge; nodes as ``shape: label``, prefixed
with the clusters they are in.
"""

from __future__ import annotations

import pathlib

import pytest

from sphinx_pss.model.graph import Graph
from sphinx_pss.model.parse import parse_model
from sphinx_pss.model.steps import steps_for
from sphinx_pss.model.steps_flowchart import plain_text, steps_flowchart

pytestmark = pytest.mark.unit

STEPS_DIR = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "pss" / "steps"
ETH = [str(STEPS_DIR / n) for n in ("eth_mac.pss", "eth_ext_a.pss", "eth_ext_b.pss")]


@pytest.fixture(scope="module")
def eth():
    return parse_model(ETH)


@pytest.fixture
def chart(tmp_path):
    """The flowchart of ``target`` in ``source``, parsed as ``t.pss``."""

    def run(source: str, target: str = "p::f", **options) -> Graph:
        path = tmp_path / "t.pss"
        path.write_text(source)
        return steps_flowchart(steps_for(parse_model([str(path)]), target, **options))

    return run


def _body(statements: str) -> str:
    return (
        "package p {\n"
        "    function void w(int v);\n"
        "    function bit[32] r();\n"
        "    function void f(bool b, int x) {\n"
        f"{statements}"
        "    }\n"
        "}\n"
    )


def edges(graph: Graph) -> list[str]:
    label = {n.id: n.label for n in graph.nodes}
    out = []
    for e in graph.edges:
        text = f"{label[e.src]} -> {label[e.dst]}"
        if e.label:
            text += f" [{e.label}]"
        if e.back:
            text += " (back)"
        out.append(text)
    return out


def nodes(graph: Graph) -> list[str]:
    clusters = {c.id: c for c in graph.clusters}

    def path(cluster_id):
        names = []
        while cluster_id is not None:
            names.insert(0, clusters[cluster_id].label)
            cluster_id = clusters[cluster_id].parent
        return names

    return [" / ".join([*path(n.cluster), f"{n.shape}: {n.label}"]) for n in graph.nodes]


# --- the fixture ----------------------------------------------------------------


def test_calls_inline_as_nested_clusters(eth) -> None:
    graph = steps_flowchart(steps_for(eth, "eth_pkg::init_eth", numbering="outline"))

    assert nodes(graph) == [
        "terminal: Start",
        "process: 1 Initialize the Ethernet controller",
        "init_controller / process: a) Disable the controller",
        "init_controller / process: b) Wait for the controller to go idle",
        "init_controller / process: c) Disable and clear the Ethernet interrupts",
        "init_controller / process: d) Clear the descriptor start addresses",
        "process: 2 Initialize the MAC",
        "init_mac / process: a) Reset the MAC",
        "init_mac / process: b) Initialize the MII management interface",
        "init_mac / init_miim / process: i. Reset the RMII module, if RMII is in use",
        "init_mac / init_miim / process: ii. Reset the MII management block",
        "init_mac / init_miim / process: iii. Select the MDC clock divider",
        "init_mac / init_miim / process: iv. Release the MII management block",
        "init_mac / process: c) Enable the receiver",
        "process: 3 Enable the controller",
        "terminal: End",
    ]
    # A straight line: nothing in init_eth branches or loops.
    assert len(graph.edges) == len(graph.nodes) - 1
    assert [(c.label, c.link) for c in graph.clusters] == [
        ("init_controller", "eth_pkg::init_controller"),
        ("init_mac", "eth_pkg::init_mac"),
        ("init_miim", "eth_pkg::init_miim"),
    ]


def test_match_and_loops(eth) -> None:
    graph = steps_flowchart(steps_for(eth, "eth_pkg::set_speed"))

    assert edges(graph) == [
        "Start -> 1 Program the speed",
        "1 Program the speed -> speed",
        "speed -> 1.1 Select 10 Mbps [SPEED_10]",
        "speed -> 1.2 Select 100 Mbps [SPEED_100]",
        "1.1 Select 10 Mbps -> 2 Poll the PHY until the link is up",
        "1.2 Select 100 Mbps -> 2 Poll the PHY until the link is up",
        # repeat ... while: the body first, then the test, and back.
        "2 Poll the PHY until the link is up -> 2.1 Read the PHY status",
        "2.1 Read the PHY status -> (read_reg(0x2A0) & 0x4) == 0",
        "(read_reg(0x2A0) & 0x4) == 0 -> 2.1 Read the PHY status [yes] (back)",
        "(read_reg(0x2A0) & 0x4) == 0 -> 3 Settle [no]",
        # repeat (n): a loop header, a back-edge, and a way out.
        "3 Settle -> Repeat retries times",
        "Repeat retries times -> 3.1 Wait one MDC period",
        "3.1 Wait one MDC period -> Repeat retries times (back)",
        "Repeat retries times -> End [done]",
    ]
    shapes = {n.label: n.shape for n in graph.nodes}
    assert shapes["speed"] == "decision"
    assert shapes["(read_reg(0x2A0) & 0x4) == 0"] == "decision"
    assert shapes["Repeat retries times"] == "loop"


def test_a_foreach(eth) -> None:
    assert edges(steps_flowchart(steps_for(eth, "eth_pkg::clear_rx"))) == [
        "Start -> 1 Release each descriptor",
        "1 Release each descriptor -> For each d in descriptors",
        "For each d in descriptors -> 1.1 Clear its ownership bit",
        "1.1 Clear its ownership bit -> For each d in descriptors (back)",
        "For each d in descriptors -> End [done]",
    ]


def test_recursion_is_a_box_that_refers_back(eth) -> None:
    graph = steps_flowchart(steps_for(eth, "eth_pkg::flush_rx"))

    assert nodes(graph) == [
        "terminal: Start",
        "process: 1 Drain one descriptor",
        "drain_one / process: 1.1 Release the descriptor",
        "drain_one / process: 1.2 Flush the rest",
        "drain_one / decision: n > 0",
        "drain_one / subroutine: Repeat from step 1 (flush_rx)",
        "terminal: End",
    ]
    assert edges(graph)[-3:] == [
        "n > 0 -> Repeat from step 1 (flush_rx) [yes]",
        "Repeat from step 1 (flush_rx) -> End",
        "n > 0 -> End [no]",
    ]
    assert graph.nodes[5].link == "eth_pkg::flush_rx"


def test_linked_calls_are_one_box(eth) -> None:
    graph = steps_flowchart(steps_for(eth, "eth_pkg::init_mac", expand_calls="link"))

    assert nodes(graph) == [
        "terminal: Start",
        "process: 1 Reset the MAC",
        "process: 2 Initialize the MII management interface",
        "subroutine: Follow the steps of init_miim",
        "process: 3 Enable the receiver",
        "terminal: End",
    ]
    assert graph.nodes[3].link == "eth_pkg::init_miim"
    assert graph.clusters == []
    assert graph.links() == ["eth_pkg::init_miim"]


def test_extensions_are_clusters(eth) -> None:
    graph = steps_flowchart(steps_for(eth, "eth_pkg::eth_c::send_a", exec_kind="body"))

    assert nodes(graph) == [
        "terminal: Start",
        "process: 1 Queue the frame",
        "Added by an extension / process: 2 Start transmission",
        "Added by an extension / process: 3 Wait for the frame to go out",
        "terminal: End",
    ]
    assert [c.tooltip for c in graph.clusters] == ["eth_ext_a.pss:9", "eth_ext_b.pss:7"]
    assert graph.title == "the steps of 'exec body' of eth_pkg::eth_c::send_a"


def test_every_node_but_the_terminals_says_where_it_is_from(eth) -> None:
    graph = steps_flowchart(steps_for(eth, "eth_pkg::set_speed"))

    assert [n.tooltip for n in graph.nodes if n.shape == "terminal"] == ["", ""]
    assert all(n.tooltip.startswith("eth_mac.pss:") for n in graph.nodes if n.shape != "terminal")


def test_the_source_description_is_the_callers(eth) -> None:
    graph = steps_flowchart(steps_for(eth, "eth_pkg::clear_rx"), lambda ref: f"line {ref.line}")

    assert [n.tooltip for n in graph.nodes] == ["", "line 128", "line 129", "line 130", ""]


# --- shapes the fixture doesn't have ------------------------------------------------


def test_an_if_chain_is_a_diamond_per_condition(chart) -> None:
    graph = chart(
        _body(
            "        if (b) {\n"
            "            /// Step: A\n"
            "            w(1);\n"
            "        } else if (x > 2) {\n"
            "            w(2);\n"
            "        } else {\n"
            "            /// Step: C\n"
            "            w(3);\n"
            "        }\n"
            "        /// Step: D\n"
            "        w(4);\n"
        )
    )

    assert edges(graph) == [
        "Start -> b",
        "b -> 1 A [yes]",
        # An arm with no steps is an edge straight past the chain.
        "b -> x > 2 [no]",
        "x > 2 -> 2 C [no]",
        "1 A -> 3 D",
        "x > 2 -> 3 D [yes]",
        "2 C -> 3 D",
        "3 D -> End",
    ]


def test_an_if_without_else_falls_through(chart) -> None:
    graph = chart(_body("        if (b) {\n            /// Step: A\n            w(1);\n        }\n"))

    assert edges(graph) == ["Start -> b", "b -> 1 A [yes]", "1 A -> End", "b -> End [no]"]


def test_a_while_tests_before_its_body(chart) -> None:
    graph = chart(_body("        while (r() != 0) {\n            /// Step: Poll\n            w(1);\n        }\n"))

    assert edges(graph) == [
        "Start -> r() != 0",
        "r() != 0 -> 1 Poll [yes]",
        "1 Poll -> r() != 0 (back)",
        "r() != 0 -> End [no]",
    ]


def test_a_match_default_is_otherwise(chart) -> None:
    graph = chart(
        _body(
            "        match (x) {\n"
            "            [1]: {\n"
            "                /// Step: One\n"
            "                w(1);\n"
            "            }\n"
            "            default: {\n"
            "                /// Step: Other\n"
            "                w(2);\n"
            "            }\n"
            "        }\n"
        )
    )

    assert edges(graph)[1:3] == ["x -> 1 One [1]", "x -> 2 Other [otherwise]"]


def test_a_repeat_while_whose_body_starts_with_a_branch(chart) -> None:
    graph = chart(
        _body(
            "        repeat {\n"
            "            if (b) {\n"
            "                /// Step: A\n"
            "                w(1);\n"
            "            }\n"
            "        } while (r() == 0);\n"
        )
    )

    # The back-edge goes to the branch, the first thing the body draws.
    assert "r() == 0 -> b [yes] (back)" in edges(graph)
    assert "Start -> b" in edges(graph)


def test_an_empty_body_is_start_then_end(eth) -> None:
    graph = steps_flowchart(steps_for(eth, "eth_pkg::init_mac", expand_calls="none"))

    # With calls unexpanded, init_mac is its three steps, in a line.
    assert len(graph.nodes) == 5
    assert edges(graph)[0] == "Start -> 1 Reset the MAC"


def test_output_is_the_same_every_time(eth) -> None:
    first = steps_flowchart(steps_for(eth, "eth_pkg::init_eth"))
    second = steps_flowchart(steps_for(eth, "eth_pkg::init_eth"))

    assert nodes(first) == nodes(second)
    assert edges(first) == edges(second)
    assert [n.id for n in first.nodes] == [f"n{i}" for i in range(1, len(first.nodes) + 1)]


# --- labels ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "title, text",
    [
        ("Reset the MAC", "Reset the MAC"),
        ("Set ``RESETRMII``", "Set RESETRMII"),
        ("Call :pss:func:`init_miim`", "Call init_miim"),
        ("Call :pss:func:`the MIIM set-up <init_miim>`", "Call the MIIM set-up"),
        ("Call :pss:func:`~eth_pkg::init_miim`", "Call init_miim"),
        ("Wait *twice*", "Wait twice"),
        ("Wait **now**", "Wait now"),
        ("Poll `BUSY`", "Poll BUSY"),
        ("Read 2 * 3 words", "Read 2 * 3 words"),
        (r"A \*literal\* star", "A *literal* star"),
    ],
)
def test_plain_text_drops_inline_markup(title: str, text: str) -> None:
    assert plain_text(title) == text
