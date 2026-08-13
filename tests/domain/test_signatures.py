"""P1-TEST-13 — signature parsing and the nodes it produces.

Parameters must be real ``desc_parameter`` nodes rather than a formatted
string, because that is what lets the type names inside them become links and
what lets a theme lay a long signature out sensibly.
"""

from __future__ import annotations

import pytest
from sphinx import addnodes

from sphinx_pss.domain import make_node_id, parse_signature

pytestmark = pytest.mark.unit


# --- the parser --------------------------------------------------------------


def test_a_bare_name() -> None:
    parsed = parse_signature("Xfer")

    assert parsed.name == "Xfer"
    assert parsed.qualifiers == []
    assert parsed.parameters is None
    assert parsed.type_name is None


def test_qualifiers_and_a_type() -> None:
    parsed = parse_signature("rand int size")

    assert parsed.name == "size"
    assert parsed.qualifiers == ["rand"]
    assert parsed.type_name == "int"


def test_several_qualifiers_keep_source_order() -> None:
    parsed = parse_signature("static const int num_channels")

    assert parsed.qualifiers == ["static", "const"]
    assert parsed.type_name == "int"
    assert parsed.name == "num_channels"


def test_a_flow_reference() -> None:
    parsed = parse_signature("output DmaBuf out_b")

    assert parsed.qualifiers == ["output"]
    assert parsed.type_name == "DmaBuf"
    assert parsed.name == "out_b"


def test_a_function_prototype() -> None:
    parsed = parse_signature("int align_up(int n)")

    assert parsed.name == "align_up"
    assert parsed.type_name == "int"
    assert parsed.parameters == ["int n"]


def test_several_parameters() -> None:
    parsed = parse_signature("void f(int a, bit [7:0] b, string c)")

    assert parsed.parameters == ["int a", "bit [7:0] b", "string c"]


def test_an_empty_parameter_list_is_not_none() -> None:
    """``f()`` must render ``()``; ``f`` must not."""
    assert parse_signature("void f()").parameters == []
    assert parse_signature("f").parameters is None


def test_a_base_type() -> None:
    parsed = parse_signature("action Derived : Base")

    assert parsed.name == "Derived"
    assert parsed.extends == "Base"


def test_a_qualified_base_type() -> None:
    assert parse_signature("action D : p::Base").extends == "p::Base"


def test_an_unparseable_signature_degrades_to_a_name() -> None:
    """Refusing to render an unusual declaration is worse than rendering it plainly."""
    parsed = parse_signature("!!! nonsense $$$")

    assert parsed.name == "$$$"
    assert parsed.parameters is None


def test_an_empty_signature() -> None:
    assert parse_signature("   ").name == ""


# --- node ids ----------------------------------------------------------------


@pytest.mark.parametrize(
    "qualname,node_id",
    [
        ("dma_pkg", "pss-dma_pkg"),
        ("dma_pkg::DmaBuf", "pss-dma_pkg.DmaBuf"),
        ("dma_pkg::Dma::Xfer::c_len", "pss-dma_pkg.Dma.Xfer.c_len"),
    ],
)
def test_node_ids_are_readable_and_case_preserving(qualname: str, node_id: str) -> None:
    assert make_node_id(qualname) == node_id


def test_node_ids_distinguish_case() -> None:
    assert make_node_id("p::DmaBuf") != make_node_id("p::dmabuf")


def test_unsafe_characters_are_replaced() -> None:
    assert " " not in make_node_id("p::a b")
    assert "<" not in make_node_id("p::A<T>")


# --- the emitted nodes -------------------------------------------------------


@pytest.mark.sphinx
class TestSignatureNodes:
    @pytest.mark.sphinx("html", testroot="basic")
    def test_parameters_are_real_nodes(self, app) -> None:
        app.build()
        doctree = app.env.get_doctree("index")

        signature = next(
            node
            for node in doctree.findall(addnodes.desc_signature)
            if node["pss:fullname"] == "dma_pkg::Dma::align_up"
        )
        paramlist = next(signature.findall(addnodes.desc_parameterlist))
        parameters = list(paramlist.findall(addnodes.desc_parameter))

        assert len(parameters) == 1
        assert parameters[0].astext() == "int n"

    @pytest.mark.sphinx("html", testroot="basic")
    def test_a_type_in_a_signature_becomes_a_link(self, app) -> None:
        app.build()
        html = (app.outdir / "index.html").read_text()

        # ``out_b``'s declared type resolves to the buffer's own description.
        assert 'href="#pss-dma_pkg.DmaBuf"' in html

    @pytest.mark.sphinx("html", testroot="basic")
    def test_a_builtin_type_does_not_warn(self, app, warning) -> None:
        """``int`` has no page, and warning about it on every field is noise."""
        app.build()

        assert "int" not in warning.getvalue()
