"""P1-TEST-8 — the project-wide index, and the parse-once contract.

"One parse per build" is the contract everything else rests on (design section
6.1), so it is asserted directly rather than assumed.
"""

from __future__ import annotations

import pytest

from sphinx_pss.model.index import PssIndex, build_index
from sphinx_pss.model.parse import PssParseError

pytestmark = pytest.mark.unit


# --- lookup -----------------------------------------------------------------


@pytest.mark.parametrize(
    "qualname",
    [
        "dma_pkg",
        "dma_pkg::DmaBuf",
        "dma_pkg::Dma",
        "dma_pkg::Dma::Xfer",
        "dma_pkg::Dma::Xfer::len",
        "dma_pkg::AddrMode::WRAP",
    ],
)
def test_qualified_names_resolve_at_every_depth(sample_index, qualname: str) -> None:
    assert qualname in sample_index
    assert sample_index.get(qualname).qualname == qualname


def test_an_unknown_name_resolves_to_none(sample_index) -> None:
    assert sample_index.get("dma_pkg::NoSuchThing") is None
    assert "dma_pkg::NoSuchThing" not in sample_index


def test_iteration_covers_every_object(sample_index) -> None:
    assert len(list(sample_index)) == len(sample_index)
    assert len(sample_index) > 30


def test_of_kind_filters(sample_index) -> None:
    actions = sample_index.of_kind("action")

    assert {a.name for a in actions} == {"Configure", "Xfer", "Check"}


def test_flow_objects_are_the_four_flow_kinds(sample_index) -> None:
    assert [o.name for o in sample_index.flow_objects] == [
        "DmaBuf",
        "SampleFlow",
        "EngineState",
        "DmaChannel",
    ]
    assert "AddrPair" not in [o.name for o in sample_index.flow_objects]


# --- reference resolution ---------------------------------------------------


def test_an_unqualified_name_resolves_from_its_scope(sample_index) -> None:
    """PSS name resolution is lexical, so the enclosing scope decides."""
    assert (
        sample_index.resolve_qualname("DmaBuf", scope="dma_pkg::Dma::Xfer")
        == "dma_pkg::DmaBuf"
    )


def test_the_innermost_scope_wins(sample_index) -> None:
    """``Xfer`` sees ``dma_pkg::Dma::Xfer``'s own members before the package's."""
    assert (
        sample_index.resolve_qualname("len", scope="dma_pkg::Dma::Xfer")
        == "dma_pkg::Dma::Xfer::len"
    )


def test_an_already_qualified_name_resolves(sample_index) -> None:
    assert (
        sample_index.resolve_qualname("dma_pkg::DmaBuf", scope="") == "dma_pkg::DmaBuf"
    )


def test_an_ambiguous_bare_name_does_not_resolve(sample_index) -> None:
    """``mode`` exists in two unrelated scopes; guessing would be wrong."""
    assert len(sample_index.candidates("mode")) == 2
    assert sample_index.resolve("mode", scope="") is None


def test_candidates_lists_every_match(sample_index) -> None:
    names = {o.qualname for o in sample_index.candidates("mode")}

    assert names == {"dma_pkg::EngineState::mode", "dma_pkg::Dma::Configure::mode"}


def test_type_refs_are_resolved_to_qualnames(sample_index) -> None:
    """Design section 8 specifies ``type_ref`` as resolved, so links work."""
    out_b = sample_index.get("dma_pkg::Dma::Xfer::out_b")

    assert out_b.type_ref == "dma_pkg::DmaBuf"


def test_an_unresolvable_type_keeps_its_written_form(sample_index) -> None:
    """A built-in type has no page; the reader still sees the source text."""
    assert sample_index.get("dma_pkg::Dma::Xfer::len").type_ref == "int"


def test_flow_spec_entries_are_resolved(sample_index) -> None:
    flow = sample_index.get("dma_pkg::Dma::Xfer").flow

    assert flow.outputs[0].qualname == "dma_pkg::DmaBuf"
    assert flow.locks[0].qualname == "dma_pkg::DmaChannel"
    assert flow.outputs[0].type_name == "DmaBuf", "the written name is retained"


# --- the standard library ---------------------------------------------------


def test_the_stdlib_is_absent_from_the_documented_set(sample_index) -> None:
    assert sample_index.get("std_pkg") is None


def test_the_stdlib_is_present_when_requested(sample_model) -> None:
    index = PssIndex(sample_model, document_stdlib=True)

    assert index.get("std_pkg") is not None
    assert index.get("addr_reg_pkg") is not None


# --- parse-once -------------------------------------------------------------


def test_the_index_parses_once_no_matter_how_many_lookups(
    sample_sources, monkeypatch
) -> None:
    """The contract every directive depends on.

    A directive that re-parsed would still render correctly, so nothing but a
    direct count catches a regression here.
    """
    import pssparser

    calls = []
    original = pssparser.Parser.parse

    def counting_parse(self, files):
        calls.append(list(files))
        return original(self, files)

    monkeypatch.setattr(pssparser.Parser, "parse", counting_parse)

    index = build_index(source_files=sample_sources)
    for _ in range(20):
        index.get("dma_pkg::Dma::Xfer")
        index.resolve("DmaBuf", scope="dma_pkg::Dma::Xfer")
        list(index)

    assert len(calls) == 1


# --- construction errors ----------------------------------------------------


def test_no_sources_is_an_error_not_an_empty_index() -> None:
    """An empty API reference that reports success wastes the most time."""
    with pytest.raises(PssParseError, match="pss_source_dirs"):
        build_index()
