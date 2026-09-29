"""Programming steps in activities (activity-diagrams plan ``AD4-TEST-2``).

The parser doesn't attach comments to activity statements yet (pssparser
``AC1``-``AC3``), so these tests put `support.geometric_comments` in its place
(plan decision D4). Trees are compared through `support.activity_outline`:
``# 2.1 Title @12`` is a step, ``*`` when its marker titles a control statement.
"""

from __future__ import annotations

import pytest

from sphinx_pss.model.activity import activity_for
from sphinx_pss.model.activity_steps import has_steps, stepped, unread_marker
from sphinx_pss.model.parse import parse_model
from support import activity_outline, use_geometric_comments

pytestmark = pytest.mark.unit


@pytest.fixture
def steps(tmp_path, monkeypatch):
    """The stepped activity of ``p::c::t``, whose activity is ``body``."""

    def run(body: str, fields: str = "a x, y; b z;", *, geometric: bool = True):
        path = tmp_path / "t.pss"
        path.write_text(
            "package p { component c {\n"
            "  action a { rand int v; }\n"
            "  action b { rand int w; }\n"
            f"  action t {{ {fields} rand bool go; rand int n;\n"
            "    activity {\n"
            f"{body}"
            "    }\n"
            "  }\n"
            "} }\n"
        )
        model = parse_model([str(path)])
        if geometric:
            use_geometric_comments(monkeypatch, model)
        activity = stepped(model, activity_for(model, "p::c::t"))
        return activity, model

    return run


def _tree(activity) -> list[str]:
    return activity_outline(activity)[1:]


def test_in_sequence_a_step_reaches_to_the_next_marker(steps) -> None:
    activity, _ = steps(
        "      /// Step: Set up\n"
        "      x;\n"
        "      z;\n"
        "      /// Step: Run\n"
        "      y;\n"
    )

    assert _tree(activity) == ["  # 1 Set up @6", "    x : a", "    z : b", "  # 2 Run @9", "    y : a"]
    assert activity.issues == []


def test_in_parallel_a_step_covers_its_own_branch(steps) -> None:
    activity, _ = steps(
        "      parallel {\n"
        "        /// Step: Copy\n"
        "        x;\n"
        "        y;\n"
        "      }\n"
    )

    assert _tree(activity) == ["  parallel", "    # 1 Copy @7", "      x : a", "    y : a"]
    # y is outside every step: the table would leave it out.
    assert [(i.code, i.line) for i in activity.issues] == [("step_prelude_call", 9)]
    assert "traversal of 'y' is outside every step" in activity.issues[0].message


def test_a_schedule_follows_the_parallel_rule(steps) -> None:
    """Decision D1."""
    activity, _ = steps(
        "      schedule {\n"
        "        /// Step: First branch\n"
        "        x;\n"
        "        /// Step: Second branch\n"
        "        y;\n"
        "      }\n"
    )

    assert _tree(activity) == ["  schedule", "    # 1 First branch @7", "      x : a", "    # 2 Second branch @9", "      y : a"]


def test_a_sequence_branch_holds_a_procedure(steps) -> None:
    activity, _ = steps(
        "      /// Step: Move the data\n"
        "      parallel {\n"
        "        sequence {\n"
        "          /// Step: Fill\n"
        "          x;\n"
        "          /// Step: Copy\n"
        "          y;\n"
        "        }\n"
        "        /// Step: Poll\n"
        "        z;\n"
        "      }\n"
    )

    assert _tree(activity) == [
        "  # 1 Move the data * @6",
        "    parallel",
        "      sequence",
        "        # 1.1 Fill @9",
        "          x : a",
        "        # 1.2 Copy @11",
        "          y : a",
        "      # 1.3 Poll @14",
        "        z : b",
    ]
    assert activity.issues == []


def test_select_arms_and_match_choices_each_take_their_marker(steps) -> None:
    activity, _ = steps(
        "      select {\n"
        "        /// Step: Fast path\n"
        "        (go) [3]: x;\n"
        "        /// Step: Safe path\n"
        "        z;\n"
        "      }\n"
        "      match (n) {\n"
        "        /// Step: Small\n"
        "        [0..3]: y;\n"
        "        default: z;\n"
        "      }\n"
    )

    assert _tree(activity) == [
        "  select",
        "    [go] (3)",
        "      # 1 Fast path @7",
        "        x : a",
        "    []",
        "      # 2 Safe path @9",
        "        z : b",
        "  match n",
        "    [0..3]",
        "      # 3 Small @13",
        "        y : a",
        "    default",
        "      z : b",
    ]
    assert [i.line for i in activity.issues] == [15]


def test_loop_and_if_bodies_are_sequential_scopes(steps) -> None:
    activity, _ = steps(
        "      /// Step: Repeat the copy\n"
        "      repeat (n) {\n"
        "        /// Step: Copy\n"
        "        x;\n"
        "        y;\n"
        "      }\n"
        "      if (go) {\n"
        "        /// Step: Check\n"
        "        z;\n"
        "      }\n"
    )

    assert _tree(activity) == [
        "  # 1 Repeat the copy * @6",
        "    repeat_count (n)",
        "      sequence",
        "        # 1.1 Copy @8",
        "          x : a",
        "          y : a",
        "    if go",
        "      sequence",
        "        # 1.2 Check @13",
        "          z : b",
    ]


def test_trailing_markers_and_closing_markers(steps) -> None:
    activity, _ = steps(
        "      x; /// Step: Start\n"
        "      z;\n"
        "      /// Step: Nothing left\n"
    )

    assert _tree(activity) == ["  # 1 Start @6", "    x : a", "    z : b", "  # 2 Nothing left @8"]


def test_plain_comments_are_not_markers(steps) -> None:
    activity, _ = steps("      // Step: Not a marker\n      x;\n")

    assert not has_steps(activity)
    assert activity.issues == []


def test_several_markers_on_one_statement(steps) -> None:
    activity, _ = steps("      /// Step: Empty\n      /// Step: Real\n      x;\n")

    assert _tree(activity) == ["  # 1 Empty @6", "  # 2 Real @7", "    x : a"]


def test_numbering_continues_across_blocks(tmp_path, monkeypatch) -> None:
    path = tmp_path / "t.pss"
    path.write_text(
        "package p { component c {\n"
        "  action a { }\n"
        "  action t { a x, y;\n"
        "    activity {\n"
        "      /// Step: One\n"
        "      x;\n"
        "    }\n"
        "  }\n"
        "  extend action t {\n"
        "    activity {\n"
        "      /// Step: Two\n"
        "      y;\n"
        "    }\n"
        "  }\n"
        "} }\n"
    )
    model = parse_model([str(path)])
    use_geometric_comments(monkeypatch, model)

    assert activity_outline(stepped(model, activity_for(model, "p::c::t"))) == [
        "== block",
        "  # 1 One @5",
        "    x : a",
        "== extension",
        "  # 2 Two @11",
        "    y : a",
    ]


def test_without_the_parser_the_markers_are_unread_but_found(steps) -> None:
    """Design 4.7: until pssparser AC1, the source text still shows the markers are there."""
    activity, model = steps("      x;\n      /** Step: Hidden */\n      y;\n", geometric=False)

    assert not has_steps(activity)
    found = unread_marker(model, activity)
    assert (found.line, found.path.endswith("t.pss")) == (7, True)


def test_an_activity_without_markers_has_nothing_unread(steps) -> None:
    activity, model = steps("      // just a note\n      x;\n", geometric=False)

    assert unread_marker(model, activity) is None


# --- the lint (plan AD4-IMPL-2) --------------------------------------------------------


def test_the_lint_reads_activity_statements(tmp_path, monkeypatch) -> None:
    from sphinx_pss.model.steps_lint import lint_markers

    path = tmp_path / "t.pss"
    path.write_text(
        "package p { component c {\n"
        "  action a { }\n"
        "  action t { a x, y;\n"
        "    /// Step: Above the activity keyword\n"
        "    activity {\n"
        "      /// Step: Fine\n"
        "      x;\n"
        "      /// step: a near miss\n"
        "      parallel {\n"
        "        y;\n"
        "        /// Step: Nothing after me\n"
        "      }\n"
        "    }\n"
        "  }\n"
        "} }\n"
    )
    model = parse_model([str(path)])
    use_geometric_comments(monkeypatch, model)

    assert [(i.code, i.line) for i in lint_markers(model)] == [
        ("step_misplaced", 4),
        ("step_syntax", 8),
        ("step_empty", 11),
    ]


def test_the_lint_is_silent_on_activities_the_parser_hasnt_commented(tmp_path) -> None:
    from sphinx_pss.model.steps_lint import lint_markers

    path = tmp_path / "t.pss"
    path.write_text(
        "package p { component c {\n"
        "  action a { }\n"
        "  action t { a x;\n"
        "    activity {\n"
        "      /// step: a near miss the parser doesn't attach\n"
        "      x;\n"
        "    }\n"
        "  }\n"
        "} }\n"
    )
    assert lint_markers(parse_model([str(path)])) == []


# --- in the diagram (plan AD4-IMPL-3) ----------------------------------------------------

DMA_STEPS = (
    "      /// Step: Configure\n"
    "      x;\n"
    "      /// Step: Move the data\n"
    "      parallel {\n"
    "        /// Step: First half\n"
    "        y;\n"
    "        /// Step: Second half\n"
    "        z;\n"
    "      }\n"
)


def _graph(make, body, **options):
    from sphinx_pss.model.activity_diagram import activity_diagram

    activity, model = make(body)
    return activity_diagram(model, activity_for(model, "p::c::t"), **options)


def _nodes(graph) -> list[str]:
    from model.test_activity_lowering import nodes

    return nodes(graph)


def test_steps_are_shaded_clusters_nested_in_structure(steps) -> None:
    graph = _graph(steps, DMA_STEPS)

    assert _nodes(graph) == [
        "initial: initial#1",
        "1 Configure (step) / action: x : a",
        "2 Move the data (step) / bar: bar#3",
        "2 Move the data (step) / 2.1 First half (step) / action: y : a",
        "2 Move the data (step) / 2.2 Second half (step) / action: z : b",
        "2 Move the data (step) / bar: bar#6",
        "final: final#7",
    ]
    assert graph.clusters[0].tooltip == "t.pss:6"


def test_collapsed_steps_are_one_box_each(steps) -> None:
    graph = _graph(steps, DMA_STEPS, steps="collapsed")

    assert _nodes(graph) == [
        "initial: initial#1",
        "process: 1 Configure",
        "process: 2 Move the data",
        "final: final#4",
    ]


def test_steps_none_ignores_the_markers(steps) -> None:
    graph = _graph(steps, DMA_STEPS, steps="none")

    assert graph.clusters == []
    assert "action: y : a" in _nodes(graph)


def test_a_steps_detail_is_its_hover_text(steps) -> None:
    graph = _graph(steps, "      /// Step: Configure\n      /// Both halves share one chain.\n      x;\n")

    assert graph.clusters[0].tooltip == "t.pss:6\nBoth halves share one chain."


def test_steps_of_an_inlined_activity_are_numbered_from_its_traversal(tmp_path, monkeypatch) -> None:
    from sphinx_pss.model.activity_diagram import activity_diagram

    path = tmp_path / "t.pss"
    path.write_text(
        "package p { component c {\n"
        "  action a { }\n"
        "  action inner { a x;\n"
        "    activity {\n"
        "      /// Step: Inner step\n"
        "      x;\n"
        "    }\n"
        "  }\n"
        "  action t { inner i;\n"
        "    activity {\n"
        "      /// Step: Outer step\n"
        "      i;\n"
        "    }\n"
        "  }\n"
        "} }\n"
    )
    model = parse_model([str(path)])
    use_geometric_comments(monkeypatch, model)
    graph = activity_diagram(model, activity_for(model, "p::c::t"), depth=2)

    assert _nodes(graph)[1] == "1 Outer step (step) / i : inner / i › 1 Inner step (step) / action: x : a"


def test_an_unknown_steps_mode_is_an_error(steps) -> None:
    from sphinx_pss.model.activity import ActivityError

    with pytest.raises(ActivityError, match="unknown steps mode 'boxes'"):
        _graph(steps, "      x;\n", steps="boxes")
