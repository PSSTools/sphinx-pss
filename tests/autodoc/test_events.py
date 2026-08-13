"""P1-IMPL-17 — the autodoc events fire and are honored.

These are the extension points a project uses to bend the output without
forking anything: rewriting doc text on the way through, and overriding which
members are documented. They mirror ``autodoc-process-docstring`` and
``autodoc-skip-member``.
"""

from __future__ import annotations

import pytest

from sphinx_pss.autodoc import EVENT_PROCESS_DOC, EVENT_SKIP_MEMBER

pytestmark = pytest.mark.sphinx


@pytest.mark.sphinx("html", testroot="autodoc", freshenv=True)
def test_both_events_are_registered(app) -> None:
    assert EVENT_PROCESS_DOC in app.events.events
    assert EVENT_SKIP_MEMBER in app.events.events


@pytest.mark.sphinx("html", testroot="autodoc", freshenv=True)
def test_process_doc_fires_for_every_documented_object(app) -> None:
    seen = []

    app.connect(
        EVENT_PROCESS_DOC,
        lambda app_, kind, qualname, options, doc: seen.append((kind, qualname)),
    )
    app.build()

    assert ("action", "dma_pkg::Dma::Xfer") in seen
    assert ("flow_ref", "dma_pkg::Dma::Xfer::out_b") in seen


@pytest.mark.sphinx("html", testroot="autodoc", freshenv=True)
def test_a_handler_can_rewrite_the_documentation(app) -> None:
    """The ``ParsedDoc`` is mutated in place, as autodoc's event is."""

    def rewrite(app_, kind, qualname, options, doc):
        if qualname == "dma_pkg::Dma::Xfer":
            doc.summary = "Rewritten by a handler."

    app.connect(EVENT_PROCESS_DOC, rewrite)
    app.build()
    html = (app.outdir / "index.html").read_text()

    assert "Rewritten by a handler." in html
    assert "Program a single DMA transfer." not in html


@pytest.mark.sphinx("html", testroot="autodoc", freshenv=True)
def test_skip_member_fires_for_every_candidate(app) -> None:
    seen = []

    app.connect(
        EVENT_SKIP_MEMBER,
        lambda app_, kind, qualname, skip, options: seen.append(qualname) or None,
    )
    app.build()

    assert "dma_pkg::Dma::Xfer::out_b" in seen


@pytest.mark.sphinx("html", testroot="autodoc", freshenv=True)
def test_a_handler_can_skip_a_member(app) -> None:
    def skip_claims(app_, kind, qualname, skip, options):
        return True if kind == "resource_claim" else None

    app.connect(EVENT_SKIP_MEMBER, skip_claims)
    app.build()
    html = (app.outdir / "index.html").read_text()

    assert 'id="pss-dma_pkg.Dma.Xfer.chan"' not in html
    assert 'id="pss-dma_pkg.Dma.Xfer.out_b"' in html


@pytest.mark.sphinx("html", testroot="autodoc", freshenv=True)
def test_a_handler_can_force_an_undocumented_member_in(app) -> None:
    """Returning ``False`` overrides the default skip."""

    def keep_everything(app_, kind, qualname, skip, options):
        return False

    app.connect(EVENT_SKIP_MEMBER, keep_everything)
    app.build()
    html = (app.outdir / "index.html").read_text()

    assert 'id="pss-dma_pkg.Dma.Xfer.out_b"' in html


@pytest.mark.sphinx("html", testroot="autodoc", freshenv=True)
def test_returning_none_leaves_the_default_decision_alone(app) -> None:
    app.connect(EVENT_SKIP_MEMBER, lambda *args: None)
    app.build()
    html = (app.outdir / "index.html").read_text()

    assert 'id="pss-dma_pkg.Dma.Xfer.chan"' in html
