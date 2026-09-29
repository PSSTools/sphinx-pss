"""P1-TEST-4 — the linked tree becomes a `PssObject` tree."""

from __future__ import annotations

import pytest

from sphinx_pss.model.builder import build_objects, render_field_signature
from sphinx_pss.model.objects import ALL_KINDS, PssObject
from sphinx_pss.model.parse import parse_model

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def objects(sample_model) -> list[PssObject]:
    return build_objects(sample_model)


@pytest.fixture(scope="module")
def by_qualname(objects) -> dict[str, PssObject]:
    return {obj.qualname: obj for root in objects for obj in root.walk()}


def test_packages_are_the_roots(objects) -> None:
    assert [o.name for o in objects] == ["dma_pkg", "dma_ext_pkg"]
    assert all(o.kind == "package" for o in objects)


@pytest.mark.parametrize(
    "qualname,kind",
    [
        ("dma_pkg", "package"),
        ("dma_pkg::AddrMode", "enum"),
        ("dma_pkg::AddrMode::INCREMENT", "enum_item"),
        ("dma_pkg::DmaBuf", "buffer"),
        ("dma_pkg::SampleFlow", "stream"),
        ("dma_pkg::EngineState", "state"),
        ("dma_pkg::DmaChannel", "resource"),
        ("dma_pkg::AddrPair", "struct"),
        ("dma_pkg::Dma", "component"),
        ("dma_pkg::Dma::Xfer", "action"),
        ("dma_pkg::Dma::align_up", "function"),
        ("dma_pkg::Dma::channel_p", "pool"),
        ("dma_pkg::Dma::Xfer::len", "field"),
        ("dma_pkg::Dma::Xfer::in_s", "flow_ref"),
        ("dma_pkg::Dma::Xfer::chan", "resource_claim"),
        ("dma_pkg::Dma::Xfer::c_len_aligned", "constraint"),
    ],
)
def test_kind_mapping(by_qualname, qualname: str, kind: str) -> None:
    """Every kind Phase 1 documents, including all five StructKind values."""
    assert qualname in by_qualname, f"{qualname} was not built"
    assert by_qualname[qualname].kind == kind


def test_every_kind_is_declared(by_qualname) -> None:
    for obj in by_qualname.values():
        assert obj.kind in ALL_KINDS


def test_members_are_in_source_order(by_qualname) -> None:
    """``:member-order: source`` is the default, so order is load-bearing."""
    xfer = by_qualname["dma_pkg::Dma::Xfer"]
    assert [c.name for c in xfer.children][:6] == [
        "in_s",
        "out_b",
        "chan",
        "len",
        "addrs",
        "notify",
    ]


def test_qualnames_nest_through_components(by_qualname) -> None:
    xfer = by_qualname["dma_pkg::Dma::Xfer"]
    assert xfer.name == "Xfer"
    assert xfer.qualname == "dma_pkg::Dma::Xfer"


# --- signatures -------------------------------------------------------------


@pytest.mark.parametrize(
    "qualname,signature",
    [
        ("dma_pkg", "package dma_pkg"),
        ("dma_pkg::DmaBuf", "buffer DmaBuf"),
        ("dma_pkg::AddrPair", "struct AddrPair"),
        ("dma_pkg::Dma", "component Dma"),
        ("dma_pkg::Dma::Xfer", "action Xfer"),
        ("dma_pkg::AddrMode", "enum AddrMode"),
        # Qualifiers appear in the order PSS writes them.
        ("dma_pkg::Dma::num_channels", "static const int num_channels"),
        ("dma_pkg::Dma::Xfer::len", "rand int len"),
        ("dma_pkg::Dma::Xfer::notify", "bool notify"),
        # A user-defined type keeps its written name in the signature.
        ("dma_pkg::Dma::Xfer::addrs", "rand AddrPair addrs"),
        # Flow refs and claims lead with their direction / mode.
        ("dma_pkg::Dma::Xfer::in_s", "input EngineState in_s"),
        ("dma_pkg::Dma::Xfer::out_b", "output DmaBuf out_b"),
        ("dma_pkg::Dma::Xfer::chan", "lock DmaChannel chan"),
        ("dma_pkg::Dma::channel_p", "pool DmaChannel channel_p"),
        ("dma_pkg::Dma::Xfer::c_len_aligned", "constraint c_len_aligned"),
        ("dma_pkg::Dma::align_up", "int align_up(int n)"),
    ],
)
def test_signatures(by_qualname, qualname: str, signature: str) -> None:
    assert by_qualname[qualname].signature == signature


def test_a_default_width_integer_renders_as_written(tmp_path) -> None:
    """The parser fills in a default width; rendering it back is wrong.

    ``int a;`` must not come out as ``int [31:0] a`` — the author wrote
    ``int``, and a signature is a quotation of the source.
    """
    source = tmp_path / "w.pss"
    source.write_text(
        "package w { struct S { int a; bit b; int [15:0] c; bit [7:0] d; } }"
    )

    objects = build_objects(parse_model([str(source)]))
    fields = {
        o.name: o.signature
        for root in objects
        for o in root.walk()
        if o.kind == "field"
    }

    assert fields == {
        "a": "int a",
        "b": "bit b",
        "c": "int [15:0] c",
        "d": "bit [7:0] d",
    }


def test_render_field_signature_omits_absent_parts() -> None:
    assert render_field_signature("x") == "x"
    assert render_field_signature("x", type_name="int") == "int x"
    assert render_field_signature("x", ["rand"], "int") == "rand int x"


# --- type references --------------------------------------------------------


def test_type_refs_hold_the_written_name_before_the_index_resolves_them(
    by_qualname,
) -> None:
    """Resolution is the index's job, because the parser cannot do it.

    ``TypeIdentifier.getTarget()`` is unreachable from Python (finding
    ``U-3``), so the builder records what was written and
    `sphinx_pss.model.index.PssIndex` resolves it.
    """
    assert by_qualname["dma_pkg::Dma::Xfer::out_b"].type_ref == "DmaBuf"
    assert by_qualname["dma_pkg::Dma::Xfer::addrs"].type_ref == "AddrPair"


def test_builtin_types_are_recorded_as_written(by_qualname) -> None:
    assert by_qualname["dma_pkg::Dma::Xfer::notify"].type_ref == "bool"
    assert by_qualname["dma_pkg::Dma::Xfer::len"].type_ref == "int"


# --- function parameters ----------------------------------------------------


def test_function_parameters_become_children(by_qualname) -> None:
    align_up = by_qualname["dma_pkg::Dma::align_up"]
    assert [c.name for c in align_up.children] == ["n"]
    assert align_up.children[0].type_ref == "int"
    assert align_up.type_ref == "int"


def test_function_parameters_are_qualified_by_their_function(by_qualname) -> None:
    [param] = by_qualname["dma_pkg::Dma::align_up"].children
    assert param.qualname == "dma_pkg::Dma::align_up::n"


def test_parameters_shared_across_functions_do_not_collide(tmp_path) -> None:
    from sphinx_pss.model.index import PssIndex

    source = tmp_path / "params.pss"
    source.write_text(
        "package p {\n"
        "    function int f(int i0, int i1) { return i0 + i1; }\n"
        "    function int g(int i0) { return i0; }\n"
        "}\n"
    )
    index = PssIndex(parse_model([str(source)]))

    assert "p::f::i0" in index
    assert "p::g::i0" in index
    assert "i0" not in index, "a parameter must not be indexed at top level"


# --- flow spec --------------------------------------------------------------


def test_actions_carry_a_flow_spec(by_qualname) -> None:
    flow = by_qualname["dma_pkg::Dma::Xfer"].flow

    assert [r.name for r in flow.inputs] == ["in_s"]
    assert [r.name for r in flow.outputs] == ["out_b"]
    assert [c.name for c in flow.locks] == ["chan"]
    assert flow.shares == []


def test_a_non_action_has_no_flow_spec(by_qualname) -> None:
    assert by_qualname["dma_pkg::DmaBuf"].flow is None


def test_an_action_with_no_flow_has_a_falsey_spec(by_qualname) -> None:
    configure = by_qualname["dma_pkg::Dma::Configure"]
    assert configure.flow.outputs  # it does produce a state
    assert not configure.flow.inputs


# --- anonymous scopes -------------------------------------------------------


def test_an_inline_covergroup_is_not_documented_as_a_package(tmp_path) -> None:
    source = tmp_path / "cg.pss"
    source.write_text(
        "component C {\n"
        "    action A {\n"
        "        rand bit[4] v;\n"
        "        // An in-line covergroup.\n"
        "        covergroup { cp : coverpoint v; } cg_i;\n"
        "    }\n"
        "}\n"
    )
    objects = build_objects(parse_model([str(source)]))

    names = [obj.qualname for root in objects for obj in root.walk()]
    assert not [n for n in names if "<" in n], names


# --- annotations ------------------------------------------------------------


def test_annotation_parameters_are_keyed_by_name(tmp_path) -> None:
    source = tmp_path / "ann.pss"
    source.write_text(
        "package p {\n"
        "    annotation desc_c { string text; int level; }\n"
        '    @desc_c {.text = "hello", .level = 3}\n'
        "    struct S { }\n"
        "}\n"
    )
    [package] = build_objects(parse_model([str(source)]))
    [struct] = [c for c in package.children if c.name == "S"]

    [annotation] = struct.annotations
    assert annotation.name == "desc_c"
    assert set(annotation.params) == {"text", "level"}


# --- prototype-only functions -----------------------------------------------

FUNCTIONS = """\
package p {
    /** Imported. */
    import target function void poke(bit[32] addr, int data);
    function int h(int z);
    /** Defined later. */
    function int h(int z) { return z; }
}
"""


def _functions(model) -> dict[str, PssObject]:
    [package] = [o for o in build_objects(model) if o.name == "p"]
    return {o.name: o for o in package.children if o.kind == "function"}


@pytest.fixture(params=["linked", "degraded"])
def functions(request, tmp_path) -> dict[str, PssObject]:
    source = tmp_path / "f.pss"
    source.write_text(FUNCTIONS)
    sources = [str(source)]
    if request.param == "degraded":
        broken = tmp_path / "broken.pss"
        broken.write_text("component C { NoSuchType f; }")
        sources.append(str(broken))
    model = parse_model(sources, tolerate_link_errors=True)
    assert model.linked is (request.param == "linked")
    return _functions(model)


def test_an_import_function_has_its_full_signature(functions) -> None:
    poke = functions["poke"]
    assert poke.signature == "import target void poke(bit [31:0] addr, int data)"
    assert [c.name for c in poke.children] == ["addr", "data"]
    assert poke.raw_doc == "Imported."
    assert poke.location is not None


def test_a_prototype_and_its_definition_are_one_function(functions) -> None:
    h = functions["h"]
    assert h.signature == "int h(int z)"
    assert h.raw_doc == "Defined later.", "first non-empty doc comment wins"
    assert h.location.line == 4, "located at the first declaration"
