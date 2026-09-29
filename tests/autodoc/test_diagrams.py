"""The shared diagram back-end, through step flowcharts.

Programming-steps plan ``S4-TEST-1`` (which is implementation plan ``P2-TEST-5``
for the parts that exist) and ``S4-TEST-3``:

- the text each back-end writes, checked without Sphinx;
- ``graphviz`` draws, ``off`` draws nothing, and a missing ``dot`` or an
  unloaded ``sphinxcontrib-mermaid`` is one warning and a table instead;
- links resolve to the documented object;
- two builds write the same diagrams, byte for byte.

``test-steps-flowchart`` asks for a flowchart three ways: ``pss:steps`` with
``:format: flowchart``, the same with ``both``, and ``:steps:`` on an
``autopssfunction``.
"""

from __future__ import annotations

import re
import shutil
import subprocess

import pytest
from sphinx.util.console import strip_colors

from sphinx_pss.autodoc.diagrams import pss_diagram, to_dot, to_mermaid
from sphinx_pss.model.graph import Graph

needs_dot = pytest.mark.skipif(shutil.which("dot") is None, reason="Graphviz's dot is not installed")


def _messages(warning) -> list[tuple[str, int, str]]:
    found = []
    for line in strip_colors(warning.getvalue()).splitlines():
        match = re.search(r"([^/\s]+):(\d+): (?:WARNING|ERROR): (.*)", line)
        if match:
            found.append((match.group(1), int(match.group(2)), match.group(3)))
    return found


def _resolved(app):
    """The page as it is written: diagrams replaced by the back-end's nodes."""
    return app.env.get_and_resolve_doctree("index", app.builder, tags=app.tags)


def _graphviz(doctree) -> list:
    from sphinx.ext.graphviz import graphviz

    return list(doctree.findall(graphviz))


def _step_tables(doctree) -> list:
    from docutils import nodes

    return [t for t in doctree.findall(nodes.table) if "pss-steps" in t["classes"]]


def _sample() -> Graph:
    """Start, a step with awkward characters, a decision in a nested cluster, a loop back."""
    g = Graph("the steps of p::f")
    start = g.add_node("Start", "terminal")
    outer = g.add_cluster("callee", link="p::callee", tooltip="t.pss:3")
    inner = g.add_cluster("deeper", parent=outer.id)
    step = g.add_node('1 Write "0x1" to C:\\dev & <go> #1', "process", cluster=outer.id, tooltip="t.pss:4")
    test = g.add_node("(r() & 0x4) == 0", "decision", cluster=inner.id)
    call = g.add_node("Follow the steps of g", "subroutine", link="p::g")
    end = g.add_node("End", "terminal")
    g.add_edge(start, step)
    g.add_edge(step, test)
    g.add_edge(test, step, "yes", back=True)
    g.add_edge(test, call, "no")
    g.add_edge(call, end)
    return g


# --- the text of each back-end ----------------------------------------------------


@pytest.mark.unit
def test_dot_text() -> None:
    dot = to_dot(_sample(), {"p::g": "api.html#pss-p.g"})

    assert dot.splitlines()[4:] == [
        "    subgraph cluster_c1 {",
        '        label="callee"; style="rounded,dashed"; fontsize=9;',
        '        tooltip="t.pss:3";',
        "        subgraph cluster_c2 {",
        '            label="deeper"; style="rounded,dashed"; fontsize=9;',
        '            n3 [label="(r() & 0x4) == 0", shape=diamond];',
        "        }",
        '        n2 [label="1 Write \\"0x1\\" to C:\\\\dev & <go>\\n#1", shape=box, tooltip="t.pss:4"];',
        "    }",
        '    n1 [label="Start", shape=box, style="rounded"];',
        '    n4 [label="Follow the steps of g", shape=box, peripheries=2, URL="api.html#pss-p.g", target="_top"];',
        '    n5 [label="End", shape=box, style="rounded"];',
        "    n1 -> n2;",
        "    n2 -> n3;",
        '    n3 -> n2 [label="yes", constraint=false];',
        '    n3 -> n4 [label="no"];',
        "    n4 -> n5;",
        "}",
    ]


@pytest.mark.unit
def test_a_resolved_cluster_link_is_written() -> None:
    dot = to_dot(_sample(), {"p::callee": "api.html#pss-p.callee"})

    assert '        URL="api.html#pss-p.callee"; target="_top";' in dot.splitlines()
    assert "URL" not in to_dot(_sample())


@pytest.mark.unit
@needs_dot
def test_dot_accepts_the_text() -> None:
    result = subprocess.run(["dot", "-Tsvg"], input=to_dot(_sample()), capture_output=True, text=True)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""


@pytest.mark.unit
def test_mermaid_text() -> None:
    text = to_mermaid(_sample(), {"p::g": "api.html#pss-p.g"})

    assert text.splitlines() == [
        "flowchart TD",
        '    subgraph c1["callee"]',
        '        subgraph c2["deeper"]',
        '            n3{"(r() #38; 0x4) == 0"}',
        "        end",
        '        n2["1 Write #34;0x1#34; to C:\\dev #38; #60;go#62;<br/>#35;1"]',
        "    end",
        '    n1(["Start"])',
        '    n4[["Follow the steps of g"]]',
        '    n5(["End"])',
        "    n1 --> n2",
        "    n2 --> n3",
        '    n3 -->|"yes"| n2',
        '    n3 -->|"no"| n4',
        "    n4 --> n5",
        '    click n4 href "api.html#pss-p.g"',
    ]


@pytest.mark.unit
def test_every_shape_has_a_drawing() -> None:
    g = Graph("shapes")
    for shape in ("terminal", "process", "decision", "loop", "subroutine"):
        g.add_node(shape, shape)

    assert [line.split("[", 1)[1] for line in to_dot(g).splitlines()[4:9]] == [
        'label="terminal", shape=box, style="rounded"];',
        'label="process", shape=box];',
        'label="decision", shape=diamond];',
        'label="loop", shape=hexagon];',
        'label="subroutine", shape=box, peripheries=2];',
    ]
    assert to_mermaid(g).splitlines()[1:] == [
        '    n1(["terminal"])',
        '    n2["process"]',
        '    n3{"decision"}',
        '    n4{{"loop"}}',
        '    n5[["subroutine"]]',
    ]
    with pytest.raises(ValueError, match="unknown node shape 'ellipse'"):
        g.add_node("x", "ellipse")


# --- graphviz ------------------------------------------------------------------------


@needs_dot
@pytest.mark.sphinx("html", testroot="steps-flowchart", freshenv=True, warningiserror=True)
def test_graphviz_draws_each_flowchart(app, warning) -> None:
    app.build()
    doctree = _resolved(app)
    charts = _graphviz(doctree)

    assert _messages(warning) == []
    assert len(charts) == 3
    assert all("pss-steps-flowchart" in c["classes"] for c in charts)
    assert [c["alt"] for c in charts] == [
        "Flowchart of the steps of eth_pkg::set_speed",
        "Flowchart of the steps of eth_pkg::init_mac",
        "Flowchart of the steps of eth_pkg::clear_rx",
    ]
    assert not list(doctree.findall(pss_diagram))
    # Only ':format: both' has a table as well.
    assert [t["pss:target"] for t in _step_tables(doctree)] == ["eth_pkg::init_mac"]
    assert len(list((app.outdir / "_images").glob("graphviz-*.svg"))) == 3


@needs_dot
@pytest.mark.sphinx("html", testroot="steps-flowchart", freshenv=True)
def test_a_linked_call_links_to_the_documented_function(app) -> None:
    app.build()
    init_mac = _graphviz(_resolved(app))[1]["code"]

    assert (
        'label="Follow the steps of init_miim", shape=box, peripheries=2, '
        'URL="index.html#pss-eth_pkg.init_miim", target="_top"'
    ) in init_mac
    svg = next(p for p in (app.outdir / "_images").glob("graphviz-*.svg") if "init_miim" in p.read_text())
    # sphinx.ext.graphviz rebases it from the page to the image directory.
    assert 'href="../index.html#pss-eth_pkg.init_miim"' in svg.read_text()


@needs_dot
@pytest.mark.sphinx("html", testroot="steps-flowchart", freshenv=True)
def test_the_flag_puts_the_flowchart_in_the_entry(app) -> None:
    from sphinx import addnodes

    app.build()
    doctree = _resolved(app)
    entry = next(
        d
        for d in doctree.findall(addnodes.desc)
        if any(s.get("pss:fullname") == "eth_pkg::clear_rx" for s in d.findall(addnodes.desc_signature))
    )

    assert len(_graphviz(entry)) == 1


@needs_dot
@pytest.mark.sphinx("html", testroot="steps-flowchart", freshenv=True, confoverrides={"graphviz_output_format": "png"})
def test_png_output_keeps_links_in_an_image_map(app) -> None:
    app.build()
    html = (app.outdir / "index.html").read_text()

    assert re.search(r'<area [^>]*href="index.html#pss-eth_pkg.init_miim"', html)


# --- degrading -------------------------------------------------------------------------


@pytest.mark.sphinx(
    "html", testroot="steps-flowchart", freshenv=True, confoverrides={"pss_diagrams": "off"}, warningiserror=True
)
def test_off_draws_nothing_and_shows_the_tables(app, warning) -> None:
    app.build()
    doctree = _resolved(app)

    assert _messages(warning) == []
    assert _graphviz(doctree) == []
    assert [t["pss:target"] for t in _step_tables(doctree)] == [
        "eth_pkg::set_speed",
        "eth_pkg::init_mac",
        "eth_pkg::clear_rx",
    ]


@pytest.mark.sphinx(
    "html", testroot="steps-flowchart", freshenv=True, confoverrides={"graphviz_dot": "/nonexistent/dot"}
)
def test_a_missing_dot_is_one_warning(app, warning) -> None:
    app.build()
    doctree = _resolved(app)

    assert _messages(warning) == [
        (
            "index.rst",
            4,
            "sphinx-pss: Graphviz's '/nonexistent/dot' command was not found (graphviz_dot), so "
            "diagrams are left out. Install Graphviz, or set pss_diagrams = 'mermaid' or 'off' "
            "[pss.diagrams]",
        )
    ]
    assert _graphviz(doctree) == []
    assert len(_step_tables(doctree)) == 3


@pytest.mark.sphinx(
    "html",
    testroot="steps-flowchart",
    freshenv=True,
    confoverrides={"graphviz_dot": "/nonexistent/dot", "suppress_warnings": ["pss.diagrams"]},
    warningiserror=True,
)
def test_the_warning_can_be_suppressed(app, warning) -> None:
    app.build()

    assert _messages(warning) == []


@pytest.mark.sphinx("html", testroot="steps-flowchart", freshenv=True, confoverrides={"pss_diagrams": "mermaid"})
def test_mermaid_without_its_extension_is_one_warning(app, warning) -> None:
    app.build()

    assert _messages(warning) == [
        (
            "index.rst",
            4,
            "sphinx-pss: pss_diagrams is 'mermaid', but sphinxcontrib-mermaid isn't loaded, so "
            "diagrams are left out. Install it and add 'sphinxcontrib.mermaid' to extensions in "
            "conf.py [pss.diagrams]",
        )
    ]
    assert len(_step_tables(_resolved(app))) == 3


# --- mermaid ----------------------------------------------------------------------------


@pytest.mark.sphinx(
    "html",
    testroot="steps-flowchart",
    freshenv=True,
    confoverrides={"pss_diagrams": "mermaid", "extensions": ["sphinx_pss", "sphinxcontrib.mermaid"]},
    warningiserror=True,
)
def test_mermaid_draws_each_flowchart(app, warning) -> None:
    mermaid = pytest.importorskip("sphinxcontrib.mermaid").mermaid

    app.build()
    charts = list(_resolved(app).findall(mermaid))

    assert _messages(warning) == []
    assert len(charts) == 3
    assert all(c["code"].startswith("flowchart TD\n") for c in charts)
    assert '    click n4 href "index.html#pss-eth_pkg.init_miim" "eth_mac.pss:79"' in charts[1]["code"].splitlines()
    assert 'class="mermaid' in (app.outdir / "index.html").read_text()


# --- S4-TEST-3: determinism ----------------------------------------------------------


@pytest.mark.parametrize("backend", ["graphviz", "mermaid"])
@pytest.mark.sphinx("html", testroot="steps-flowchart")
def test_two_builds_write_the_same_diagrams(make_app, rootdir, tmp_path, backend) -> None:
    if backend == "graphviz" and shutil.which("dot") is None:
        pytest.skip("Graphviz's dot is not installed")
    if backend == "mermaid":
        pytest.importorskip("sphinxcontrib.mermaid")
    overrides = {"pss_diagrams": backend, "extensions": ["sphinx_pss", "sphinxcontrib.mermaid"]}
    if backend == "graphviz":
        overrides["extensions"] = ["sphinx_pss"]

    codes = []
    for build in ("a", "b"):
        srcdir = tmp_path / build
        shutil.copytree(rootdir / "test-steps-flowchart", srcdir)
        app = make_app("html", srcdir=srcdir, freshenv=True, confoverrides=overrides)
        app.build()
        doctree = _resolved(app)
        codes.append([n["code"] for n in doctree.findall(lambda n: "code" in getattr(n, "attributes", {}))])

    assert len(codes[0]) == 3
    assert codes[0] == codes[1]
