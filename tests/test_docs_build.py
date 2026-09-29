"""P1-ACC — the published documentation builds, and dogfoods the extension.

``docs/examples/sample.md`` documents the test fixtures with the extension's own
directives, so this is the broadest integration check available: a failure means
the whole path from ``.pss`` source to rendered HTML is broken, not just one
layer of it.

Marked ``sphinx`` rather than ``corpus`` because it is the phase acceptance
test and needs to run on every change, not nightly.
"""

from __future__ import annotations

import pathlib

import pytest

pytestmark = pytest.mark.sphinx

DOCS_DIR = pathlib.Path(__file__).resolve().parents[1] / "docs"


@pytest.fixture(scope="module")
def docs_build(tmp_path_factory):
    """Build the real ``docs/`` under ``-W``, writing only to a temp directory.

    Built in place rather than from a copy: ``docs/conf.py`` and the example
    page reach the ``.pss`` fixtures by relative path, and a copy would have to
    reproduce the repository layout around it to be the same test. Only
    ``outdir`` and ``doctreedir`` are redirected, so nothing is written into
    the working tree.
    """
    from sphinx.application import Sphinx
    from sphinx.util.docutils import docutils_namespace

    out = tmp_path_factory.mktemp("docs")
    srcdir = DOCS_DIR

    warnings: list[str] = []

    class _Collector:
        def write(self, text: str) -> None:
            if text.strip():
                warnings.append(text)

        def flush(self) -> None:
            pass

    with docutils_namespace():
        app = Sphinx(
            srcdir=str(srcdir),
            confdir=str(srcdir),
            outdir=str(out / "html"),
            doctreedir=str(out / "doctrees"),
            buildername="html",
            warningiserror=True,
            status=None,
            warning=_Collector(),
        )
        app.build()

    return app, warnings


def test_the_documentation_builds_without_warnings(docs_build) -> None:
    _, warnings = docs_build

    assert warnings == []


def test_the_example_page_documents_the_fixture_model(docs_build) -> None:
    """Asserted on the doctree: HTML splits a signature across markup spans."""
    from sphinx import addnodes

    app, _ = docs_build
    doctree = app.env.get_doctree("examples/sample")

    rendered = {
        node["pss:fullname"]: " ".join(node.astext().split()).rstrip("¶").strip()
        for node in doctree.findall(addnodes.desc_signature)
    }

    assert rendered["dma_pkg::Dma::Xfer"] == "action Xfer"
    assert rendered["dma_pkg::DmaBuf"] == "buffer DmaBuf"
    assert rendered["dma_pkg::Dma::Xfer::out_b"] == "output DmaBuf out_b"
    assert rendered["dma_pkg::Dma::Xfer::chan"] == "lock DmaChannel chan"
    assert "Program a single DMA transfer." in doctree.astext()


def test_cross_references_in_the_example_resolve(docs_build) -> None:
    """Type names in signatures link to the type's own description."""
    app, _ = docs_build
    html = (pathlib.Path(app.outdir) / "examples" / "sample.html").read_text()

    assert 'href="#pss-dma_pkg.DmaBuf"' in html


def test_extension_members_appear_in_the_example(docs_build) -> None:
    app, _ = docs_build
    html = (pathlib.Path(app.outdir) / "examples" / "sample.html").read_text()

    assert 'id="pss-dma_pkg.Dma.Xfer.prio"' in html
    assert 'id="pss-dma_pkg.DmaBuf.consumed"' in html


def test_doc_fields_render_in_the_example(docs_build) -> None:
    app, _ = docs_build
    html = (pathlib.Path(app.outdir) / "examples" / "sample.html").read_text()

    assert "DMA-014, DMA-015" in html


def test_objects_reach_the_toc(docs_build) -> None:
    app, _ = docs_build
    toc = app.env.tocs["examples/sample"].astext()

    assert "Xfer" in toc
    assert "DmaBuf" in toc


def test_the_inventory_is_exported(docs_build) -> None:
    """Feeds intersphinx, so another project can reference these objects."""
    app, _ = docs_build

    assert (pathlib.Path(app.outdir) / "objects.inv").exists()
    assert "dma_pkg::Dma::Xfer" in app.env.domains["pss"].objects


def test_the_steps_page_shows_the_fixture(docs_build) -> None:
    """The page's first example is included from ``steps_pkg.pss`` by marker
    text, so an edit to the fixture that moves those lines shows up here."""
    from docutils import nodes

    app, _ = docs_build
    first = next(app.env.get_doctree("usage/steps").findall(nodes.literal_block)).astext()

    assert "function void init_mac(bool rmii) {" in first
    assert "/// Step: Reset the MAC" in first
    assert "component mac_c" not in first


def _step_tables(app, docname: str) -> list[list[tuple[str, str]]]:
    """Each step table on a page, as ``(number, title)`` rows, header left out."""
    from docutils import nodes

    tables = []
    for table in app.env.get_doctree(docname).findall(nodes.table):
        if "pss-steps" not in table["classes"]:
            continue
        rows = list(table.findall(nodes.row))[1:]
        tables.append([
            (row[0].astext(), row[1].children[0].astext().strip())
            for row in rows
        ])
    return tables


def test_the_steps_page_renders_each_live_table(docs_build) -> None:
    """``S3-DOC-1``: every table on the page is rendered from the fixtures by
    the build, so each one's rows are checked here."""
    app, _ = docs_build
    tables = _step_tables(app, "usage/steps")

    assert len(tables) == 5
    init_mac, set_speed, linked, flush_rx, mac_c = tables
    assert init_mac == [
        ("1", "Reset the MAC"),
        ("2", "Wait for the reset to complete"),
        ("3", "Initialize the MIIM interface"),
        ("3.1", "Select the interface mode"),
        ("3.2", "Set the MDC clock divider"),
        ("4", "Enable the receiver"),
    ]
    assert set_speed == [
        ("1", "Program the speed"),
        ("", "When SPEED_10:"),
        ("1.1", "Select 10 Mbps"),
        ("", "When SPEED_100:"),
        ("1.2", "Select 100 Mbps"),
        ("2", "Poll the PHY until the link is up"),
        ("2.1", "Read the PHY status"),
        ("3", "Settle"),
        ("3.1", "Wait one MDC period"),
    ]
    assert ("", "Follow the steps of init_miim") in linked
    assert "3.1" not in [number for number, _ in linked]
    assert flush_rx[-1] == ("", "Repeat from step 1 (flush_rx)")
    assert ("", "Added by an extension") in mac_c
    assert mac_c[-1] == ("2", "Report that the MAC is up")


def test_the_steps_page_shows_the_source_of_each_table(docs_build) -> None:
    """The literal includes are by marker text; this catches one that drifts."""
    app, _ = docs_build
    text = app.env.get_doctree("usage/steps").astext()

    assert "function void set_speed(speed_e speed, int retries) {" in text
    assert "function void drain_one(int n) {" in text
    assert "extend component mac_c {" in text
    assert "/// Step: Report that the MAC is up" in text


def test_the_ethernet_example_renders_both_numberings(docs_build) -> None:
    """``S3-DOC-2``: the FRM's 1 → a) → i. structure, and the decimal default."""
    app, _ = docs_build
    outline, decimal, shallow, component = _step_tables(app, "examples/steps")

    assert [number for number, _ in outline] == [
        "1", "a)", "b)", "c)", "d)", "2", "a)", "b)", "i.", "ii.", "iii.", "iv.", "c)", "3",
    ]
    assert [title for _, title in outline] == [title for _, title in decimal]
    assert decimal[8] == ("2.2.1", "Reset the RMII module, if RMII is in use")
    assert [number for number, _ in shallow] == ["1", "1.1", "1.2", "1.3", "1.4", "2", "2.1", "2.2", "2.3", "3"]
    assert component[0] == ("1", "Bring up the Ethernet port")
    assert component[-1] == ("1.3", "Enable the controller")


def _flowcharts(app, docname: str) -> list:
    """Each step flowchart on a page, as the graph the build drew."""
    from sphinx_pss.autodoc.diagrams import pss_diagram

    return [node["graph"] for node in app.env.get_doctree(docname).findall(pss_diagram)]


def test_the_steps_page_draws_a_live_flowchart(docs_build) -> None:
    """``S4-DOC-1``: ``set_speed`` as a flowchart, drawn by Graphviz."""
    app, _ = docs_build
    (chart,) = [g for g in _flowcharts(app, "usage/steps") if g.title.startswith("the steps of")]

    assert chart.title == "the steps of eth_pkg::set_speed"
    assert [n.label for n in chart.nodes if n.shape == "decision"] == ["speed", "(read_reg(0x2A0) & 0x4) == 0"]
    html = (app.outdir / "usage" / "steps.html").read_text()
    assert 'class="graphviz pss-diagram pss-steps-flowchart"' in html
    # Two step flowcharts, the steps page's two activity diagrams, and the
    # activities page's three. Sphinx names an image by its text, and without
    # a parser that reads activity steps the steps page's two are the same.
    from sphinx_pss._capability import activity_comments_supported

    images = 7 if activity_comments_supported() else 6
    assert len(list((app.outdir / "_images").glob("graphviz-*.svg"))) == images


def test_the_ethernet_example_draws_the_outline_flowchart(docs_build) -> None:
    """``S4-DOC-1``: ``:format: both`` gives the table and a flowchart of the same steps."""
    app, _ = docs_build
    (chart,) = _flowcharts(app, "examples/steps")
    outline = _step_tables(app, "examples/steps")[0]

    boxes = [n.label for n in chart.nodes if n.shape == "process"]
    assert boxes == [f"{number} {title}" for number, title in outline]
    assert [c.label for c in chart.clusters] == ["init_controller", "init_mac", "init_miim"]


def test_the_mermaid_example_is_what_sphinx_pss_writes(docs_build) -> None:
    """``S4-DOC-2``: the diagrams page's Mermaid text, regenerated from the fixture."""
    import glob

    from docutils import nodes

    from sphinx_pss.autodoc.diagrams import to_mermaid
    from sphinx_pss.model.parse import parse_model
    from sphinx_pss.model.steps import steps_for
    from sphinx_pss.model.steps_flowchart import steps_flowchart

    app, _ = docs_build
    shown = next(
        block.astext()
        for block in app.env.get_doctree("usage/diagrams").findall(nodes.literal_block)
        if "diagram-example-mermaid" in block["ids"]
    )
    fixtures = sorted(glob.glob(str(DOCS_DIR.parent / "tests" / "fixtures" / "pss" / "steps" / "*.pss")))
    model = parse_model(fixtures)

    assert shown + "\n" == to_mermaid(steps_flowchart(steps_for(model, "eth_pkg::set_speed")))


# --- activities (activity-diagrams plan AD2-DOC-1) ----------------------------------


def test_the_activities_page_draws_the_example_twice(docs_build) -> None:
    """``AD2-DOC-1``: the example at depth 1 and 2, drawn by Graphviz."""
    app, _ = docs_build
    shallow, deep, entry = _flowcharts(app, "usage/activities")

    assert shallow.title == deep.title == "the activity of xfer_pkg::dma_c::xfer"
    assert entry.title == "the activity of xfer_pkg::dma_c::burst_copy"
    assert [n.label for n in shallow.nodes if n.shape == "action"] == [
        "cfg : configure",
        "f : fill",
        "c1 : copy",
        "c2 : burst_copy ⋔",
        "chk : check",
    ]
    assert [c.label for c in deep.clusters] == ["c2 : burst_copy", "repeat (beats)"]
    html = (app.outdir / "usage" / "activities.html").read_text()
    assert html.count('class="graphviz pss-diagram pss-activity-diagram"') == 3


def test_the_activities_page_shows_what_the_table_says(docs_build) -> None:
    """``AD2-DOC-1``: the page's claims about the example hold for the drawing."""
    app, _ = docs_build
    shallow = _flowcharts(app, "usage/activities")[0]
    labels = {e.label for e in shallow.edges}

    assert {"[verify]", "[else]", "data ↔ src", "dst ↔ data"} <= labels
    assert "note" in {n.shape for n in shallow.nodes}
    svg = "".join(p.read_text() for p in (app.outdir / "_images").glob("graphviz-*.svg"))
    assert "activities.html#pss-xfer_pkg.dma_c.configure" in svg
    assert "activities.html#pss-xfer_pkg.dma_c.copy" in svg


def test_the_activities_page_shows_the_outline(docs_build) -> None:
    """``AD2-DOC-1``: ``:format: outline`` renders the nested list."""
    from docutils import nodes

    app, _ = docs_build
    doctree = app.env.get_doctree("usage/activities")
    (outline,) = [n for n in doctree.findall(nodes.container) if "pss-activity-outline" in n["classes"]]

    assert [line for line in outline.astext().splitlines() if line] == [
        "cfg : configure with { channel < 4; }",
        "f : fill",
        "parallel",
        "c1 : copy",
        "c2 : burst_copy",
        "if verify",
        "then",
        "chk : check",
        "bind f.data c1.src",
        "bind c1.dst chk.data",
    ]


def test_the_activities_page_puts_a_diagram_in_an_entry(docs_build) -> None:
    """``AD3-DOC-1``: ``:activity-diagram:`` on ``autopssaction``."""
    from sphinx import addnodes

    from sphinx_pss.autodoc.diagrams import pss_diagram

    app, _ = docs_build
    doctree = app.env.get_doctree("usage/activities")
    entry = next(
        d for d in doctree.findall(addnodes.desc) if "burst_copy" in d.next_node(addnodes.desc_signature).astext()
    )

    (diagram,) = list(entry.findall(pss_diagram))
    assert diagram["pss:target"] == "xfer_pkg::dma_c::burst_copy"


def test_the_steps_page_draws_steps_in_an_activity_iff_the_parser_reads_them(docs_build) -> None:
    """``AD4-DOC-1``: regions and collapse, shown exactly when pssparser attaches the markers."""
    from sphinx_pss._capability import activity_comments_supported

    app, _ = docs_build
    regions, collapsed = [g for g in _flowcharts(app, "usage/steps") if g.title.startswith("the activity of")]

    step_clusters = [c.label for c in regions.clusters if c.kind == "step"]
    boxes = [n.label for n in collapsed.nodes if n.shape == "process"]
    if activity_comments_supported():
        assert step_clusters == [
            "1 Configure the channel",
            "2 Move the data",
            "2.1 Copy the first half",
            "2.2 Copy the second half",
            "3 Check the result",
        ]
        assert boxes == ["1 Configure the channel", "2 Move the data", "3 Check the result"]
    else:
        # The page says so; the build warned once (suppressed in docs/conf.py).
        assert step_clusters == [] and boxes == []
        assert "Needs a newer pssparser" in (app.outdir / "usage" / "steps.html").read_text()
