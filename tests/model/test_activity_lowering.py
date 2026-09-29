"""Activity lowering: an activity as a UML graph (activity-diagrams plan ``AD2-TEST-1``).

The graph is checked without a back-end, as readable text: nodes as
``shape: label`` prefixed with the clusters they are in, and edges as
``from -> to``, with ``[label]``, ``(object)`` or ``(constraint)`` for the
edge's label and style. A node with no label is named by its shape and
position, ``bar#3``.
"""

from __future__ import annotations

import pathlib

import pytest

from sphinx_pss.model.activity import ActivityError, activity_for
from sphinx_pss.model.activity_diagram import activity_diagram
from sphinx_pss.model.graph import Graph
from sphinx_pss.model.parse import parse_model

pytestmark = pytest.mark.unit

ACT_DIR = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "pss" / "activities"
DMA = "act_pkg::dma_c::"


@pytest.fixture(scope="module")
def model():
    return parse_model([str(ACT_DIR / n) for n in ("activity_model.pss", "activity_ext.pss")])


def _name(graph: Graph, node_id: str) -> str:
    n = graph.node(node_id)
    return n.label or f"{n.shape}#{graph.nodes.index(n) + 1}"


def nodes(graph: Graph) -> list[str]:
    clusters = {c.id: c for c in graph.clusters}

    def path(cluster_id):
        names = []
        while cluster_id is not None:
            c = clusters[cluster_id]
            names.insert(0, c.label + (" (step)" if c.kind == "step" else ""))
            cluster_id = c.parent
        return names

    return [" / ".join([*path(n.cluster), f"{n.shape}: {_name(graph, n.id)}"]) for n in graph.nodes]


def edges(graph: Graph) -> list[str]:
    out = []
    for e in graph.edges:
        text = f"{_name(graph, e.src)} -> {_name(graph, e.dst)}"
        if e.label:
            text += f" [{e.label}]"
        if e.style != "control":
            text += f" ({e.style}{'' if e.directed else ', undirected'})"
        out.append(text)
    return out


@pytest.fixture
def diagram(tmp_path):
    """The diagram of ``p::c::t``, whose activity is ``body``, with actions ``a`` and ``b``."""

    def run(body: str, fields: str = "a x, y; b z;", **options) -> Graph:
        path = tmp_path / "t.pss"
        path.write_text(
            "package p { component c {\n"
            "  action a { rand int v; }\n"
            "  action b { rand int w; }\n"
            f"  action t {{ {fields} rand bool go; rand int n;\n"
            f"    activity {{\n{body}\n    }}\n"
            "  }\n"
            "} }\n"
        )
        model = parse_model([str(path)])
        return activity_diagram(model, activity_for(model, "p::c::t"), **options)

    return run


def test_a_sequence_is_a_chain_from_initial_to_final(diagram) -> None:
    graph = diagram("x; z;")

    assert nodes(graph) == ["initial: initial#1", "action: x : a", "action: z : b", "final: final#4"]
    assert edges(graph) == ["initial#1 -> x : a", "x : a -> z : b", "z : b -> final#4"]


def test_parallel_is_a_fork_and_a_join(diagram) -> None:
    graph = diagram("parallel { x; y; }")

    assert edges(graph) == [
        "initial#1 -> bar#2",
        "bar#2 -> x : a",
        "bar#2 -> y : a",
        "x : a -> bar#5",
        "y : a -> bar#5",
        "bar#5 -> final#6",
    ]


def test_a_join_specification_labels_the_join(diagram) -> None:
    assert nodes(diagram("parallel join_first(1) { x; y; }"))[4] == "bar: {join_first(1)}"


def test_join_none_ends_each_branch_and_goes_straight_on(diagram) -> None:
    graph = diagram("parallel join_none { x; y; } z;")

    assert edges(graph) == [
        "initial#1 -> bar#2",
        "bar#2 -> x : a",
        "bar#2 -> y : a",
        "x : a -> flow_final#5",
        "y : a -> flow_final#6",
        "bar#2 -> z : b",
        "z : b -> final#8",
    ]


def test_a_schedule_has_hollow_bars_in_its_own_cluster(diagram) -> None:
    graph = diagram("schedule { s1: x; s2: y; constraint sequence { s1, s2 }; }")

    assert nodes(graph)[1:5] == [
        "schedule / hollow_bar: hollow_bar#2",
        "schedule / action: s1: x : a",
        "schedule / action: s2: y : a",
        "schedule / hollow_bar: hollow_bar#5",
    ]
    assert "s1: x : a -> s2: y : a [sequence] (constraint)" in edges(graph)


def test_a_parallel_scheduling_constraint_is_undirected(diagram) -> None:
    graph = diagram("schedule { s1: x; s2: y; constraint parallel { s1, s2 }; }")

    assert "s1: x : a -> s2: y : a [parallel] (constraint, undirected)" in edges(graph)


def test_select_is_a_decision_and_a_merge_without_weights(diagram) -> None:
    graph = diagram("select { (go) [3]: x; [1]: y; z; }")

    assert edges(graph) == [
        "initial#1 -> select",
        "select -> x : a [[go]]",
        "select -> y : a",
        "select -> z : b",
        "x : a -> merge#6",
        "y : a -> merge#6",
        "z : b -> merge#6",
        "merge#6 -> final#7",
    ]


def test_weights_label_select_arms_on_request(diagram) -> None:
    labels = [e.label for e in diagram("select { (go) [3]: x; [1]: y; z; }", weights=True).edges[1:4]]

    assert labels == ["[go] (3)", "(1)", ""]


def test_if_without_else_goes_to_the_merge(diagram) -> None:
    graph = diagram("if (go) x;")

    assert edges(graph) == [
        "initial#1 -> decision#2",
        "decision#2 -> x : a [[go]]",
        "x : a -> merge#4",
        "decision#2 -> merge#4 [[else]]",
        "merge#4 -> final#5",
    ]


def test_match_labels_its_choices(diagram) -> None:
    graph = diagram("match (n) { [0..3]: x; default: y; }")

    assert edges(graph)[1:3] == ["n -> x : a [[0..3]]", "n -> y : a [[default]]"]


@pytest.mark.parametrize(
    ("body", "title"),
    [
        ("repeat (n) { x; }", "repeat (n)"),
        ("repeat (i : 4) { x; }", "repeat (i : 4)"),
        ("repeat { x; } while (go);", "repeat … while (go)"),
        ("replicate (j : 4) { x; }", "«parallel» replicate (j : 4)"),
        ("atomic { x; }", "atomic"),
    ],
)
def test_loops_and_regions_are_titled_clusters(diagram, body, title) -> None:
    graph = diagram(body)

    assert nodes(graph)[1] == f"{title} / action: x : a"
    assert edges(graph) == ["initial#1 -> x : a", "x : a -> final#3"]


def test_foreach_is_an_iterative_expansion_region(diagram) -> None:
    graph = diagram("foreach (e : arr) { x; }", fields="a x; rand int arr[4];")

    assert nodes(graph)[1] == "«iterative» foreach (e : arr) / action: x : a"


def test_a_with_constraint_is_a_note_beside_its_node(diagram) -> None:
    graph = diagram("do a with { v == 1; };")

    assert nodes(graph)[1:3] == ["action: a", "note: with {v == 1;}"]
    assert "a -> with {v == 1;} (anchor, undirected)" in edges(graph)


def test_a_long_with_constraint_is_abbreviated(diagram) -> None:
    text = " && ".join(f"v != {i}" for i in range(20))
    note = diagram(f"do a with {{ {text}; }};").nodes[2]

    assert len(note.label) == len("with {}") + 60
    assert note.label.endswith("…}")
    assert text in note.tooltip


def test_a_bind_between_single_traversals_is_an_object_flow(diagram) -> None:
    graph = diagram("x; z; bind x.v z.w;")

    assert "x : a -> z : b [v ↔ w] (object, undirected)" in edges(graph)
    assert graph.caption_notes == []


def test_a_bind_to_a_handle_traversed_twice_is_a_caption_note(diagram) -> None:
    graph = diagram("x; x; z; bind x.v z.w;")

    assert not [e for e in graph.edges if e.style == "object"]
    assert graph.caption_notes == ["Also bound: x.v ↔ z.w"]


def test_a_bind_to_the_context_actions_field_is_a_parameter_node(model) -> None:
    graph = activity_diagram(model, activity_for(model, DMA + "xfer_in"))

    assert "parameter: in_data" in nodes(graph)
    assert "in_data -> c1 : copy [src] (object, undirected)" in edges(graph)


def test_labels_rakes_abstract_types_and_links(model) -> None:
    graph = activity_diagram(model, activity_for(model, DMA + "all_kinds"))
    labels = {n.label: n.link for n in graph.nodes if n.shape == "action"}

    assert labels["b1: c1 : copy"] == DMA + "copy"
    assert labels["«any» any_xfer"] == DMA + "any_xfer"
    assert "d : derived_xfer ⋔" in {n.label for n in activity_diagram(model, activity_for(model, DMA + "two_level")).nodes}


def test_several_blocks_are_an_implicit_schedule(model) -> None:
    graph = activity_diagram(model, activity_for(model, DMA + "multi"))

    assert nodes(graph) == [
        "initial: initial#1",
        "schedule / hollow_bar: hollow_bar#2",
        "schedule / activity / action: cfg : configure",
        "schedule / activity (extend, activity_ext.pss:5) / action: chk : check",
        "schedule / hollow_bar: hollow_bar#5",
        "final: final#6",
    ]


def test_an_inherited_activity_says_so_in_the_caption(model) -> None:
    assert activity_diagram(model, activity_for(model, DMA + "inherits_only")).caption_notes == [
        f"Inherited from {DMA}base_xfer"
    ]


def test_depth_opens_compound_traversals(model) -> None:
    graph = activity_diagram(model, activity_for(model, DMA + "two_level"), depth=3)

    assert nodes(graph) == [
        "initial: initial#1",
        "action: cfg : configure",
        "d : derived_xfer / super: base_xfer / action: cfg : configure",
        "d : derived_xfer / action: chk : check",
        "final: final#5",
    ]
    assert graph.clusters[0].link == DMA + "derived_xfer"


def test_depth_stops_at_recursion(model) -> None:
    graph = activity_diagram(model, activity_for(model, DMA + "ping"), depth=4)

    assert "pong / action: ping (recursive, see above)" in nodes(graph)


def test_depth_is_bounded(model) -> None:
    with pytest.raises(ActivityError, match="depth must be from 1 to 4, not 5"):
        activity_diagram(model, activity_for(model, DMA + "ping"), depth=5)


def test_the_same_activity_gives_the_same_graph(model) -> None:
    from sphinx_pss.autodoc.diagrams import to_dot

    other = parse_model([str(ACT_DIR / n) for n in ("activity_model.pss", "activity_ext.pss")])
    first = to_dot(activity_diagram(model, activity_for(model, DMA + "all_kinds"), depth=2))
    again = to_dot(activity_diagram(other, activity_for(other, DMA + "all_kinds"), depth=2))

    assert first == again
