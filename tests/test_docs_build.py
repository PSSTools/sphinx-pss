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
