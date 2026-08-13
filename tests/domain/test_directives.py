"""P1-TEST-12 — the ``pss:*`` object directives render.

Asserted against the doctree rather than HTML wherever possible: HTML string
matching breaks when a theme changes and says nothing about structure. The few
HTML checks that remain are for things that only exist after writing —
permalinks and the general index.
"""

from __future__ import annotations

import pytest
from sphinx import addnodes

pytestmark = pytest.mark.sphinx


@pytest.fixture()
def doctree(app):
    app.build()
    return app.env.get_doctree("index")


@pytest.fixture()
def signatures(doctree):
    """Every rendered signature, by the fullname stashed on it."""
    return {
        node["pss:fullname"]: node
        for node in doctree.findall(addnodes.desc_signature)
    }


@pytest.mark.sphinx("html", testroot="basic")
def test_the_extension_registers_the_domain(app) -> None:
    """The other half of P0-TEST-2."""
    assert "pss" in app.env.domains
    assert app.env.domains["pss"].name == "pss"


@pytest.mark.sphinx("html", testroot="basic")
@pytest.mark.parametrize(
    "qualname",
    [
        "dma_pkg",
        "dma_pkg::DmaBuf",
        "dma_pkg::DmaBuf::size",
        "dma_pkg::DmaChannel",
        "dma_pkg::Dma",
        "dma_pkg::Dma::align_up",
        "dma_pkg::Dma::Xfer",
        "dma_pkg::Dma::Xfer::out_b",
        "dma_pkg::Dma::Xfer::chan",
        "dma_pkg::Dma::Xfer::c_len_aligned",
    ],
)
def test_every_directive_renders(signatures, qualname: str) -> None:
    assert qualname in signatures


@pytest.mark.sphinx("html", testroot="basic")
def test_nesting_produces_qualified_names(signatures) -> None:
    """A member written inside a component body gets the component's scope."""
    assert "dma_pkg::Dma::Xfer" in signatures
    assert "Xfer" not in signatures


@pytest.mark.sphinx("html", testroot="basic")
def test_scope_closes_after_a_body(signatures) -> None:
    """``DmaChannel`` follows ``DmaBuf``'s body and must not nest inside it."""
    assert "dma_pkg::DmaChannel" in signatures
    assert "dma_pkg::DmaBuf::DmaChannel" not in signatures


@pytest.mark.sphinx("html", testroot="basic")
def test_signatures_read_as_pss_source(signatures) -> None:
    """A signature is a quotation of the declaration, not a rearrangement."""

    def text(qualname: str) -> str:
        return " ".join(signatures[qualname].astext().split()).rstrip("¶").strip()

    assert text("dma_pkg::DmaBuf") == "buffer DmaBuf"
    assert text("dma_pkg::DmaBuf::size") == "rand int size"
    assert text("dma_pkg::Dma::Xfer::out_b") == "output DmaBuf out_b"
    assert text("dma_pkg::Dma::Xfer::chan") == "lock DmaChannel chan"
    assert text("dma_pkg::Dma::align_up") == "function int align_up(int n)"


@pytest.mark.sphinx("html", testroot="basic")
def test_the_domain_records_every_object(app) -> None:
    app.build()
    objects = app.env.domains["pss"].objects

    assert objects["dma_pkg::Dma::Xfer"][2] == "action"
    assert objects["dma_pkg::DmaBuf"][2] == "buffer"
    assert objects["dma_pkg::Dma::Xfer::chan"][2] == "resource_claim"


# --- index entries and permalinks -------------------------------------------


@pytest.mark.sphinx("html", testroot="basic")
def test_index_entries_are_emitted(doctree) -> None:
    entries = [
        entry
        for node in doctree.findall(addnodes.index)
        for entry in node["entries"]
    ]
    labels = {e[1] for e in entries}

    assert "Xfer (action in PSS)" in labels
    assert "DmaBuf (buffer in PSS)" in labels


@pytest.mark.sphinx("html", testroot="basic")
def test_the_general_index_lists_objects(app) -> None:
    app.build()
    html = (app.outdir / "genindex.html").read_text()

    assert "Xfer" in html
    assert "DmaBuf" in html


@pytest.mark.sphinx("html", testroot="basic")
def test_permalinks_are_present(app) -> None:
    app.build()
    html = (app.outdir / "index.html").read_text()

    assert 'id="pss-dma_pkg.Dma.Xfer"' in html
    assert 'href="#pss-dma_pkg.Dma.Xfer"' in html


@pytest.mark.sphinx("html", testroot="basic")
def test_node_ids_preserve_case(app) -> None:
    """Lowercasing would collide ``DmaBuf`` with ``dmabuf``.

    PSS convention is PascalCase types beside snake_case members, so a
    case-folding id scheme makes collisions depend on what else a project
    happens to declare.
    """
    app.build()
    _, node_id, _ = app.env.domains["pss"].objects["dma_pkg::DmaBuf"]

    assert node_id == "pss-dma_pkg.DmaBuf"


# --- the TOC ----------------------------------------------------------------


@pytest.mark.sphinx("html", testroot="basic")
def test_objects_get_toc_entries(doctree) -> None:
    """Sphinx asks for the hierarchy before target ids exist.

    The fullname is stashed during ``handle_signature`` for exactly this
    reason; without it every object silently drops out of the sidebar.
    """
    parts = {
        node["pss:fullname"]: node.get("_toc_parts")
        for node in doctree.findall(addnodes.desc_signature)
    }

    assert parts["dma_pkg::Dma::Xfer"] == ("dma_pkg", "Dma", "Xfer")
    assert parts["dma_pkg::DmaBuf"] == ("dma_pkg", "DmaBuf")


@pytest.mark.sphinx("html", testroot="basic")
def test_the_toc_entry_is_the_short_name(app) -> None:
    app.build()
    toc = app.env.tocs["index"].astext()

    assert "Xfer" in toc
    assert "dma_pkg::Dma::Xfer" not in toc, "the sidebar shows the short name"
