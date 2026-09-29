"""The step tree of a compound action (activity-diagrams plan ``AD5-TEST-1``).

`steps_for` on an action with an activity and no ``exec_kind`` projects its
stepped activity onto the step tree. Traversals expand like calls; into an
atomic action's ``exec body`` only with ``expand_exec`` (decision D3). Trees
are compared through `support.steps_outline`; `support.geometric_comments`
stands in for pssparser ``AC1``.
"""

from __future__ import annotations

import pytest

from sphinx_pss.model.parse import parse_model
from sphinx_pss.model.steps import StepsError, steps_for
from support import steps_outline, use_geometric_comments

pytestmark = pytest.mark.unit

SOURCE = """\
package p {
    function void w(int v);
    component c {
        action leaf {
            exec body {
                /// Step: Leaf work
                w(1);
            }
        }
        abstract action any_leaf { }
        action inner {
            leaf l;
            activity {
                /// Step: Inner work
                l;
            }
        }
        action outer {
            inner i;
            leaf l;
            activity {
                /// Step: Outer work
                i;
                do any_leaf;
                l;
            }
        }
        action ping {
            pong p;
            activity {
                /// Step: Ping
                p;
            }
        }
        action pong {
            activity {
                /// Step: Pong
                do ping;
            }
        }
        action unmarked {
            inner i;
            activity { i; }
        }
    }
}
"""


@pytest.fixture
def model(tmp_path, monkeypatch):
    path = tmp_path / "t.pss"
    path.write_text(SOURCE)
    m = parse_model([str(path)])
    use_geometric_comments(monkeypatch, m)
    return m


def test_a_compound_traversal_expands_into_its_activity_steps(model) -> None:
    doc = steps_for(model, "p::c::outer")

    assert doc.activity
    assert steps_outline(doc) == ["1 Outer work @22", "  -> p::c::inner", "    1.1 Inner work @14"]


def test_an_atomic_traversal_expands_only_on_request(model) -> None:
    doc = steps_for(model, "p::c::outer", expand_exec=True)

    assert steps_outline(doc) == [
        "1 Outer work @22",
        "  -> p::c::inner",
        "    1.1 Inner work @14",
        "      -> p::c::leaf (exec)",
        "        1.1.1 Leaf work @6",
        "  -> p::c::leaf (exec)",
        "    1.2 Leaf work @6",
    ]


@pytest.mark.parametrize(
    ("options", "outline"),
    [
        ({"expand_calls": "link"}, ["1 Outer work @22", "  -> p::c::inner (link)"]),
        ({"expand_calls": "none"}, ["1 Outer work @22"]),
        ({"depth": 0}, ["1 Outer work @22"]),
    ],
)
def test_expansion_modes_and_depth(model, options, outline) -> None:
    assert steps_outline(steps_for(model, "p::c::outer", **options)) == outline


def test_recursion_is_cut_at_the_first_repeat(model) -> None:
    assert steps_outline(steps_for(model, "p::c::ping")) == [
        "1 Ping @31",
        "  -> p::c::pong",
        "    1.1 Pong @37",
        "      -> p::c::ping (see 1)",
    ]


def test_an_action_without_markers_has_no_steps(model) -> None:
    doc = steps_for(model, "p::c::unmarked")

    assert doc.activity and list(doc.steps()) == []


def test_an_exec_kind_still_means_the_exec_blocks(model) -> None:
    assert steps_outline(steps_for(model, "p::c::leaf", exec_kind="body")) == ["1 Leaf work @6"]
    with pytest.raises(StepsError, match="is a type: name its exec block"):
        steps_for(model, "p::c::leaf")
