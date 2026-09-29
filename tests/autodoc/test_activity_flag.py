"""``:activity-diagram:`` on the autopss directives (activity-diagrams plan ``AD3-TEST-1``).

``test-activity-autodoc`` documents the docs example's actions: ``xfer`` with
the flag and its prefixed options, the atomic ``configure`` with the flag, the
compound ``burst_copy`` with the flag turned off, and the whole component with
its members. The tests ask for outlines, so they don't need Graphviz.
"""

from __future__ import annotations

import pytest
from docutils import nodes

X = "xfer_pkg::dma_c::"


def _outlines(app) -> list[str]:
    """The action each outline on the page is of, in page order."""
    doctree = app.env.get_doctree("index")
    return [c["pss:target"] for c in doctree.findall(nodes.container) if "pss-activity-outline" in c["classes"]]


@pytest.mark.sphinx("html", testroot="activity-autodoc", freshenv=True, warningiserror=True)
def test_the_flag_puts_the_activity_in_the_entry(app) -> None:
    app.build()

    # Only xfer asked for one: configure is atomic, and the component asked
    # for nothing.
    targets = _outlines(app)
    assert targets == [X + "xfer"]


@pytest.mark.sphinx("html", testroot="activity-autodoc", freshenv=True, warningiserror=True)
def test_prefixed_options_reach_the_diagram(app) -> None:
    app.build()
    outline = next(
        c for c in app.env.get_doctree("index").findall(nodes.container) if c.get("pss:target") == X + "xfer"
    )

    # :activity-format: outline gave an outline; :activity-weights: is
    # accepted (xfer has no select to show it on).
    assert "parallel" in outline.astext()


@pytest.mark.sphinx(
    "html",
    testroot="activity-autodoc",
    freshenv=True,
    warningiserror=True,
    confoverrides={"pss_default_options": {"activity-diagram": True, "activity-format": "outline"}},
)
def test_a_project_default_reaches_members_and_can_be_turned_off(app) -> None:
    app.build()
    targets = _outlines(app)

    # xfer explicitly; then, as members of the component, burst_copy and xfer.
    # burst_copy's own entry turned it off, and the atomic actions have none.
    assert targets == [X + "xfer", X + "burst_copy", X + "xfer"]
