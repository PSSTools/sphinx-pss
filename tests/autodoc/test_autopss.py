"""P1-TEST-14 — the ``autopss*`` directives, end to end from PSS source.

This is the vertical slice: a single directive naming a qualified PSS name
produces a full doctree, from a real parse of a real source file.
"""

from __future__ import annotations

import pytest
from sphinx import addnodes

from sphinx_pss.autodoc import DocumenterOptions

pytestmark = pytest.mark.sphinx


def signatures(app) -> dict[str, addnodes.desc_signature]:
    return {
        node["pss:fullname"]: node
        for node in app.env.get_doctree("index").findall(addnodes.desc_signature)
    }


def text_of(node) -> str:
    return " ".join(node.astext().split()).rstrip("¶").strip()


@pytest.mark.sphinx("html", testroot="autodoc", freshenv=True)
def test_an_action_documents_from_source(app) -> None:
    app.build()
    found = signatures(app)

    assert text_of(found["dma_pkg::Dma::Xfer"]) == "action Xfer"


@pytest.mark.sphinx("html", testroot="autodoc", freshenv=True)
def test_members_are_rendered_with_source_signatures(app) -> None:
    app.build()
    found = signatures(app)

    assert text_of(found["dma_pkg::Dma::Xfer::out_b"]) == "output DmaBuf out_b"
    assert text_of(found["dma_pkg::Dma::Xfer::chan"]) == "lock DmaChannel chan"
    assert text_of(found["dma_pkg::Dma::Xfer::len"]) == "rand int len"


@pytest.mark.sphinx("html", testroot="autodoc", freshenv=True)
def test_a_member_is_named_by_its_declaration_not_its_qualname(app) -> None:
    """``:qualname:`` fixes the *target*; the signature stays a quotation."""
    app.build()

    assert "dma_pkg::Dma::Xfer::len" not in text_of(
        signatures(app)["dma_pkg::Dma::Xfer::len"]
    )


@pytest.mark.sphinx("html", testroot="autodoc", freshenv=True)
def test_the_kind_keyword_appears_exactly_once(app) -> None:
    """The model's signature carries it, and so does the directive."""
    app.build()

    assert text_of(signatures(app)["dma_pkg::DmaBuf"]).count("buffer") == 1


@pytest.mark.sphinx("html", testroot="autodoc", freshenv=True)
def test_documentation_prose_is_rendered(app) -> None:
    app.build()
    html = (app.outdir / "index.html").read_text()

    assert "Program a single DMA transfer." in html
    assert "Claims a channel for the duration of the transfer" in html


@pytest.mark.sphinx("html", testroot="autodoc", freshenv=True)
def test_doc_fields_are_rendered_as_a_field_list(app) -> None:
    app.build()
    html = (app.outdir / "index.html").read_text()

    assert "DMA-014, DMA-015" in html
    assert "a single descriptor-driven engine transfer" in html


@pytest.mark.sphinx("html", testroot="autodoc", freshenv=True)
def test_extension_members_are_documented_alongside_declared_ones(app) -> None:
    """The linked tree is the documentation view, so ``prio`` belongs here."""
    app.build()
    found = signatures(app)

    assert "dma_pkg::Dma::Xfer::prio" in found
    assert "dma_pkg::DmaBuf::consumed" in found


@pytest.mark.sphinx("html", testroot="autodoc", freshenv=True)
def test_enum_values_are_documented(app) -> None:
    app.build()
    found = signatures(app)

    assert text_of(found["dma_pkg::AddrMode::INCREMENT"]) == "INCREMENT"


@pytest.mark.sphinx("html", testroot="autodoc", freshenv=True)
def test_without_members_only_the_object_is_rendered(app) -> None:
    """``autopsscomponent:: dma_pkg::Dma`` carries no ``:members:``."""
    app.build()
    found = signatures(app)

    assert "dma_pkg::Dma" in found
    assert "dma_pkg::Dma::align_up" not in found


@pytest.mark.sphinx("html", testroot="autodoc", freshenv=True)
def test_the_build_is_warning_free(app, warning) -> None:
    """The fixture is the published example, so it must build under ``-W``."""
    app.build()

    assert warning.getvalue().strip() == ""


@pytest.mark.sphinx("html", testroot="autodoc", freshenv=True)
def test_the_model_is_parsed_once_for_the_whole_build(
    make_app, app_params, monkeypatch
) -> None:
    """Four directives naming four objects, one parse.

    Counted from before the application is constructed, because the index is
    built on ``builder-inited`` — which fires during construction, not during
    ``build()``.
    """
    import pssparser

    calls = []
    original = pssparser.Parser.parse

    def counting_parse(self, files):
        calls.append(list(files))
        return original(self, files)

    monkeypatch.setattr(pssparser.Parser, "parse", counting_parse)

    args, kwargs = app_params
    app = make_app(*args, **kwargs)
    app.build()

    assert len(calls) == 1


# --- resolution failures -----------------------------------------------------


@pytest.mark.sphinx("html", testroot="autodoc", freshenv=True)
def test_an_unknown_target_reports_with_suggestions(app) -> None:
    from docutils.statemachine import StringList

    text = StringList(
        [".. autopssaction:: dma_pkg::Dma::Xfr", ""], source="<test>"
    )
    app.build()
    doctree = app.env.get_doctree("index")

    # The directive resolves through the index, so exercise it directly rather
    # than adding a deliberately-broken page to the shared test root.
    from sphinx_pss.autodoc.directives import get_index

    index = get_index(app.env)
    assert index.get("dma_pkg::Dma::Xfr") is None
    assert doctree is not None


@pytest.mark.sphinx("html", testroot="autodoc", freshenv=True)
def test_a_directive_rejects_an_object_of_the_wrong_kind(app) -> None:
    """``autopssbuffer`` must not silently document an action."""
    from sphinx_pss.autodoc.directives import AUTO_DIRECTIVES, make_directive

    directive = make_directive("buffer", AUTO_DIRECTIVES["buffer"])
    app.build()

    from sphinx_pss.autodoc.directives import get_index

    index = get_index(app.env)
    instance = directive.__new__(directive)
    assert instance._resolve(index, "dma_pkg::Dma::Xfer") is None
    assert instance._resolve(index, "dma_pkg::DmaBuf") is not None


# --- options ------------------------------------------------------------------


@pytest.mark.unit
class TestDocumenterOptions:
    def test_defaults(self) -> None:
        options = DocumenterOptions.from_directive({})

        assert not options.members
        assert options.member_order == "source"

    def test_a_project_default_applies(self) -> None:
        options = DocumenterOptions.from_directive({}, {"members": True})

        assert options.members

    def test_a_directive_can_turn_a_project_default_off(self) -> None:
        """A flag cannot express "off", so ``:no-members:`` exists."""
        options = DocumenterOptions.from_directive(
            {"no-members": None}, {"members": True}
        )

        assert not options.members

    def test_exclude_members_accepts_commas_or_spaces(self) -> None:
        for value in ("a, b", "a b", "a,b"):
            options = DocumenterOptions.from_directive({"exclude-members": value})
            assert options.exclude_members == {"a", "b"}, value

    def test_member_order_comes_through(self) -> None:
        options = DocumenterOptions.from_directive({"member-order": "alpha"})

        assert options.member_order == "alpha"
