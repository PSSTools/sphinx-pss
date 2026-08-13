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
