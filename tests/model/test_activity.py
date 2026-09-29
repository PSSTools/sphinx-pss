"""The activity model: lifting, resolution and text (activity-diagrams plan ``AD1-TEST-1``).

Trees are compared as text through `support.activity_outline`, over the
fixture in ``tests/fixtures/pss/activities`` (one activity per construct) and
small sources written per test.
"""

from __future__ import annotations

import pathlib

import pytest

from sphinx_pss.model.activity import (
    ActivityError,
    ActivityUnavailable,
    Unknown,
    activity_for,
    has_activity,
)
from sphinx_pss.model.parse import parse_model
from support import activity_outline

pytestmark = pytest.mark.unit

ACT_DIR = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "pss" / "activities"
SOURCES = [str(ACT_DIR / n) for n in ("activity_model.pss", "activity_ext.pss")]
DMA = "act_pkg::dma_c::"


@pytest.fixture(scope="module")
def model():
    m = parse_model(SOURCES)
    assert m.linked and not m.diagnostics
    return m


def test_every_construct_lifts_as_written(model) -> None:
    activity = activity_for(model, DMA + "all_kinds")

    assert activity_outline(activity) == [
        "== block",
        "  cfg : configure",
        "  seq1: sequence",
        "    f : fill",
        "    c1 : copy",
        "  parallel",
        "    c1 : copy",
        "    c2 : copy",
        "  parallel none: join_none",
        "    c1 : copy",
        "    c2 : copy",
        "  parallel first: join_first (1)",
        "    c1 : copy",
        "    c2 : copy",
        "  parallel select: join_select (1)",
        "    c1 : copy",
        "    c2 : copy",
        "  parallel branch: join_branch (b1)",
        "    b1: c1 : copy",
        "    c2 : copy",
        "  schedule",
        "    s1: c1 : copy",
        "    s2: c2 : copy",
        "    constraint parallel {s1, s2}",
        "  select",
        "    [fast] (3)",
        "      c1 : copy",
        "    [] (1)",
        "      c2 : copy",
        "    []",
        "      chk : check",
        "  if fast",
        "    sequence",
        "      c1 : copy",
        "  else",
        "    sequence",
        "      c2 : copy",
        "  if n > 2",
        "    chk : check",
        "  match n",
        "    [0..3]",
        "      c1 : copy",
        "    default",
        "      c2 : copy",
        "  repeat_count (n)",
        "    sequence",
        "      c1 : copy",
        "  repeat_count (i : 4)",
        "    sequence",
        "      c1 : copy",
        "  repeat_while (n > 0)",
        "    sequence",
        "      c1 : copy",
        "  foreach (e : arr)",
        "    sequence",
        "      c1 : copy",
        "  replicate (4)",
        "    sequence",
        "      c2 : copy",
        "  replicate (j : n)",
        "    sequence",
        "      c2 : copy",
        "  atomic",
        "    sequence",
        "      c1 : copy",
        "      c2 : copy",
        "  do configure with {channel == 1;}",
        "  do any_xfer *",
        "  constraint {n < 8;}",
        "  bind f.data c1.src",
    ]
    assert activity.issues == []


def test_targets_are_the_linkers_qualified_names(model) -> None:
    targets = {n.target for n in activity_for(model, DMA + "all_kinds").nodes() if hasattr(n, "handle")}

    assert targets == {DMA + t for t in ("configure", "fill", "copy", "check", "any_xfer")}


def test_statements_carry_their_source_lines(model) -> None:
    activity = activity_for(model, DMA + "all_kinds")
    first, seq = activity.blocks[0].children[:2]

    assert activity.blocks[0].source.line == 40
    assert (first.source.line, seq.source.line) == (41, 42)
    assert all(n.source is not None for n in activity.nodes() if type(n).__name__ != "Sequence")


def test_several_blocks_come_in_link_order(model) -> None:
    activity = activity_for(model, DMA + "multi")

    assert activity_outline(activity) == ["== block", "  cfg : configure", "== extension", "  chk : check"]
    assert activity.blocks[1].source.path.endswith("activity_ext.pss")


def test_super_resolves_to_the_base(model) -> None:
    assert activity_outline(activity_for(model, DMA + "derived_xfer")) == [
        "== block",
        f"  super -> {DMA}base_xfer ⋔",
        "  chk : check",
    ]


def test_an_action_without_blocks_inherits_its_bases(model) -> None:
    activity = activity_for(model, DMA + "inherits_only")

    assert activity.inherited_from == DMA + "base_xfer"
    assert activity_outline(activity) == ["== block", "  cfg : configure"]
    assert has_activity(model, DMA + "inherits_only")


def test_a_traversal_of_a_compound_action_has_the_rake(model) -> None:
    assert activity_outline(activity_for(model, DMA + "two_level"))[1:] == ["  cfg : configure", "  d : derived_xfer ⋔"]
    assert activity_outline(activity_for(model, DMA + "ping"))[1:] == [
        "  select",
        "    []",
        "      do pong ⋔",
        "    []",
        "      do configure",
    ]


def test_a_bind_to_the_context_actions_input(model) -> None:
    assert activity_outline(activity_for(model, DMA + "xfer_in"))[1:] == ["  c1 : copy", "  bind in_data c1.src"]


def test_the_tree_is_cached_per_model(model) -> None:
    assert activity_for(model, DMA + "multi") is activity_for(model, DMA + "multi")


@pytest.mark.parametrize(
    ("target", "message"),
    [
        (DMA + "configure", "action 'act_pkg::dma_c::configure' has no activity"),
        (DMA + "nope", "no PSS action named 'act_pkg::dma_c::nope'"),
        ("act_pkg::data_buf", "'act_pkg::data_buf' is not an action, so it has no activity"),
    ],
)
def test_a_target_without_an_activity_is_an_error(model, target, message) -> None:
    with pytest.raises(ActivityError, match="^" + message.replace("(", r"\(").replace(")", r"\)") + "$"):
        activity_for(model, target)
    assert not has_activity(model, target)


def test_an_unlinked_model_is_unavailable(tmp_path) -> None:
    path = tmp_path / "t.pss"
    path.write_text("package p { component c { action a { b x; activity { x; } } } }\n")

    with pytest.raises(ActivityUnavailable):
        activity_for(parse_model([str(path)], tolerate_link_errors=True), "p::c::a")


def test_do_on_a_handle_is_a_handle_traversal(tmp_path) -> None:
    path = tmp_path / "t.pss"
    path.write_text(
        "package p { component c {\n"
        "  action b { }\n"
        "  action a { b h; activity { do h; } }\n"
        "} }\n"
    )
    assert activity_outline(activity_for(parse_model([str(path)]), "p::c::a")) == ["== block", "  h : b"]


def test_a_labeled_block_keeps_its_label_and_a_braced_select_arm_its_guard(tmp_path) -> None:
    path = tmp_path / "t.pss"
    path.write_text(
        "package p { component c {\n"
        "  action b { }\n"
        "  action a {\n"
        "    b x, y; rand bool go;\n"
        "    activity {\n"
        "      top: parallel { x; y; }\n"
        "      select { (go): { x; } { y; } }\n"
        "    }\n"
        "  }\n"
        "} }\n"
    )
    assert activity_outline(activity_for(parse_model([str(path)]), "p::c::a")) == [
        "== block",
        "  top: parallel",
        "    x : b",
        "    y : b",
        "  select",
        "    [go]",
        "      sequence",
        "        x : b",
        "    []",
        "      sequence",
        "        y : b",
    ]


def test_an_unknown_statement_kind_is_kept_and_reported(model, monkeypatch) -> None:
    from sphinx_pss.model import activity as a

    real = a._Lifter.statement

    def statement(self, stmt):
        if type(stmt).__name__ == "ActivityBindStmt":
            self.issue(self.ref(stmt), "the activity has a statement sphinx-pss doesn't know (X)")
            return Unknown("X", source=self.ref(stmt))
        return real(self, stmt)

    monkeypatch.setattr(a._Lifter, "statement", statement)
    activity = a._Lifter(model).activity(DMA + "xfer_in")

    assert activity_outline(activity)[-1] == "  ? X"
    assert [(i.code, i.line) for i in activity.issues] == [("activity", 146)]
