"""P1-TEST-15 — the ``:pss:…:`` roles resolve, and say something useful when they cannot.

An unresolved reference is a documentation bug, so the warning has to be an
instruction rather than an observation: for an ambiguous name it lists what the
name could have meant, which is the difference between a two-second fix and a
grep.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.sphinx


@pytest.fixture()
def built(app, warning):
    app.build()
    return (app.outdir / "index.html").read_text(), warning.getvalue()


@pytest.mark.sphinx("html", testroot="xref", freshenv=True)
def test_a_qualified_name_resolves(built) -> None:
    html, _ = built
    assert 'href="#pss-p.C1.A"' in html


@pytest.mark.sphinx("html", testroot="xref", freshenv=True)
def test_a_unique_bare_name_resolves(built) -> None:
    """``:pss:buffer:`Buf``` works from anywhere when there is only one Buf."""
    html, _ = built
    assert 'href="#pss-p.Buf"' in html


@pytest.mark.sphinx("html", testroot="xref", freshenv=True)
def test_the_generic_role_resolves_any_kind(built) -> None:
    html, _ = built
    assert 'href="#pss-p.C2"' in html


@pytest.mark.sphinx("html", testroot="xref", freshenv=True)
def test_an_unknown_target_warns(built) -> None:
    _, warnings = built
    assert "unknown PSS object :pss:action:`Missing`" in warnings


@pytest.mark.sphinx("html", testroot="xref", freshenv=True)
def test_an_ambiguous_name_lists_its_candidates(built) -> None:
    _, warnings = built

    assert "ambiguous PSS reference :pss:action:`Shared`" in warnings
    assert "p::C1::Shared" in warnings
    assert "p::C2::Shared" in warnings


@pytest.mark.sphinx("html", testroot="xref", freshenv=True)
def test_a_role_of_the_wrong_kind_does_not_resolve(built) -> None:
    """``:pss:buffer:`` must not silently link to an action of that name."""
    _, warnings = built
    assert "unknown PSS object :pss:buffer:`p::C1::A`" in warnings


@pytest.mark.sphinx("html", testroot="xref", freshenv=True)
def test_a_tilde_shortens_the_title(built) -> None:
    """``:pss:action:`~p::C1::A``` renders as ``A`` and still links."""
    html, _ = built

    assert ">A<" in html
    assert html.count('href="#pss-p.C1.A"') >= 2


@pytest.mark.sphinx("html", testroot="xref", freshenv=True)
def test_only_the_intended_references_warn(built) -> None:
    _, warnings = built

    assert warnings.count("[pss.ref]") == 3


@pytest.mark.sphinx("html", testroot="basic", freshenv=True)
def test_generated_type_references_never_warn(app, warning) -> None:
    """Every ``int`` field would otherwise produce a warning.

    The signature renderer emits a reference for each declared type without
    knowing whether it is documentable, so built-ins are expected misses.
    """
    app.build()

    assert "[pss.ref]" not in warning.getvalue()


@pytest.mark.sphinx("html", testroot="xref", freshenv=True)
def test_the_inventory_lists_every_object(app) -> None:
    """Feeds intersphinx and the search index."""
    app.build()
    objects = dict(
        (name, kind)
        for name, _, kind, _, _, _ in app.env.domains["pss"].get_objects()
    )

    assert objects["p::C1::A"] == "action"
    assert objects["p::Buf"] == "buffer"
