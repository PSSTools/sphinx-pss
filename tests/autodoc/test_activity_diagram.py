"""``pss:activity-diagram`` in a Sphinx build (activity-diagrams plan ``AD2-TEST-3``).

``test-activity`` asks for the activity fixture four ways: a diagram, a diagram
with its outline (``both``) and a caption, a diagram two levels deep, and an
outline alone for an action that inherits its activity. Two actions are
documented, so the diagrams have something to link to.
"""

from __future__ import annotations

import re
import shutil

import pytest
from docutils import nodes
from sphinx.util.console import strip_colors

from sphinx_pss.autodoc.diagrams import pss_diagram

needs_dot = pytest.mark.skipif(shutil.which("dot") is None, reason="Graphviz's dot is not installed")

DMA = "act_pkg::dma_c::"


def _messages(warning) -> list[tuple[int, str]]:
    found = []
    for line in strip_colors(warning.getvalue()).splitlines():
        match = re.search(r"[^/\s]+:(\d+): (?:WARNING|ERROR): (.*)", line)
        if match:
            found.append((int(match.group(1)), match.group(2)))
    return found


def _resolved(app):
    return app.env.get_and_resolve_doctree("index", app.builder, tags=app.tags)


def _outlines(doctree) -> list[str]:
    return [n["pss:target"] for n in doctree.findall(nodes.container) if "pss-activity-outline" in n["classes"]]


def _graphviz(doctree) -> list:
    from sphinx.ext.graphviz import graphviz

    return list(doctree.findall(graphviz))


@needs_dot
@pytest.mark.sphinx("html", testroot="activity", freshenv=True, warningiserror=True)
def test_each_request_draws_what_it_asks_for(app, warning) -> None:
    app.build()
    doctree = _resolved(app)
    charts = _graphviz(doctree)

    assert _messages(warning) == []
    assert not list(doctree.findall(pss_diagram))
    assert [c["alt"] for c in charts] == [
        f"Activity diagram of {DMA}all_kinds: 33 actions traversed",
        f"Activity diagram of {DMA}multi: 2 actions traversed",
        f"Activity diagram of {DMA}two_level: 2 actions traversed",
    ]
    assert _outlines(doctree) == [DMA + "multi", DMA + "inherits_only"]
    assert len(list((app.outdir / "_images").glob("graphviz-*.svg"))) == 3


@needs_dot
@pytest.mark.sphinx("html", testroot="activity", freshenv=True)
def test_the_caption_names_the_action_and_what_isnt_drawn(app) -> None:
    app.build()
    figures = list(_resolved(app).findall(nodes.figure))

    captions = [f.next_node(nodes.caption).astext() for f in figures]
    assert captions == [DMA + "all_kinds", "Two blocks, scheduled", DMA + "two_level"]
    assert figures[0].next_node(nodes.legend).astext() == "Also bound: f.data ↔ c1.src"


@needs_dot
@pytest.mark.sphinx("html", testroot="activity", freshenv=True)
def test_traversals_link_to_documented_actions(app) -> None:
    app.build()
    svg = "".join(p.read_text() for p in (app.outdir / "_images").glob("graphviz-*.svg"))

    assert set(re.findall(r'href="([^"]*)"', svg)) == {
        "../index.html#pss-act_pkg.dma_c.copy",
        "../index.html#pss-act_pkg.dma_c.derived_xfer",
    }


@needs_dot
@pytest.mark.sphinx("html", testroot="activity", freshenv=True)
def test_both_folds_the_outline_away_in_html(app) -> None:
    app.build()
    html = (app.outdir / "index.html").read_text()

    assert html.count('<details class="pss-activity-outline"><summary>Outline</summary>') == 1
    # The outline alone isn't folded: it is all there is.
    assert html.count('class="pss-activity-outline docutils container"') == 2


@pytest.mark.sphinx("html", testroot="activity", freshenv=True)
def test_the_outline_reads_as_the_activity(app) -> None:
    app.build()
    outline = next(
        n for n in _resolved(app).findall(nodes.container) if n.get("pss:target") == DMA + "multi"
    )

    assert [line for line in outline.astext().splitlines() if line] == [
        "schedule (every activity block)",
        "activity",
        "cfg : configure",
        "activity (extend, activity_ext.pss:5)",
        "chk : check",
    ]


@pytest.mark.sphinx("html", testroot="activity", freshenv=True, confoverrides={"pss_diagrams": "off"}, warningiserror=True)
def test_off_shows_every_activity_as_its_outline(app, warning) -> None:
    app.build()
    doctree = _resolved(app)

    assert _messages(warning) == []
    assert _graphviz(doctree) == []
    assert _outlines(doctree) == [DMA + n for n in ("all_kinds", "multi", "two_level", "inherits_only")]


@pytest.mark.sphinx("html", testroot="activity", freshenv=True, confoverrides={"graphviz_dot": "/nonexistent/dot"})
def test_a_missing_dot_is_one_warning_and_outlines(app, warning) -> None:
    app.build()

    assert [m for _, m in _messages(warning)] == [
        "sphinx-pss: Graphviz's '/nonexistent/dot' command was not found (graphviz_dot), so "
        "diagrams are left out. Install Graphviz, or set pss_diagrams = 'mermaid' or 'off' [pss.diagrams]"
    ]
    assert len(_outlines(_resolved(app))) == 4


@pytest.mark.sphinx(
    "html",
    testroot="activity",
    freshenv=True,
    confoverrides={"pss_diagrams": "mermaid", "extensions": ["sphinx_pss", "sphinxcontrib.mermaid"]},
    warningiserror=True,
)
def test_mermaid_draws_each_activity(app) -> None:
    mermaid = pytest.importorskip("sphinxcontrib.mermaid").mermaid
    app.build()
    charts = list(_resolved(app).findall(mermaid))

    assert len(charts) == 3
    assert all(c["code"].startswith("flowchart TD\n") for c in charts)


@pytest.mark.sphinx("html", testroot="activity-errors", freshenv=True)
def test_mistakes_are_errors_at_the_directive(app, warning) -> None:
    app.build()
    text = strip_colors(warning.getvalue())

    assert _messages(warning) == [
        (4, "sphinx-pss: action 'act_pkg::dma_c::configure' has no activity [docutils]"),
        (6, "sphinx-pss: no PSS action named 'act_pkg::dma_c::nothing_here' [docutils]"),
        (8, "sphinx-pss: 'act_pkg::data_buf' is a buffer, not an action, so it has no activity [docutils]"),
        (10, 'Error in "pss:activity-diagram" directive:'),
        (13, 'Error in "pss:activity-diagram" directive:'),
    ]
    assert '"poster" unknown; choose from "diagram", "outline", or "both".' in text
    assert "at most 4." in text


@needs_dot
def test_two_builds_write_the_same_diagrams(make_app, rootdir, tmp_path) -> None:
    codes = []
    for build in ("a", "b"):
        srcdir = tmp_path / build
        shutil.copytree(rootdir / "test-activity", srcdir)
        app = make_app("html", srcdir=srcdir, freshenv=True)
        app.build()
        codes.append([c["code"] for c in _graphviz(_resolved(app))])

    assert len(codes[0]) == 3
    assert codes[0] == codes[1]
