"""P1-TEST-7 — where each member of a merged type came from.

The linker merges ``extend`` bodies into the base type, which is what makes the
linked tree the right documentation view. It is also why provenance matters:
without it, a reader of ``Xfer`` cannot tell that ``prio`` is contributed by a
different file, and idiomatic PSS spreads types across files as a matter of
course (design section 5.3).
"""

from __future__ import annotations

import pytest

from sphinx_pss.model.objects import PROVENANCE_DECLARATION, PROVENANCE_EXTENSION

pytestmark = pytest.mark.unit


def test_the_extension_is_merged_into_the_base_type(sample_index) -> None:
    xfer = sample_index.get("dma_pkg::Dma::Xfer")

    assert xfer.child("len") is not None, "declared in dma_pkg.pss"
    assert xfer.child("prio") is not None, "contributed by dma_ext.pss"


def test_declared_members_carry_declaration_provenance(sample_index) -> None:
    member = sample_index.get("dma_pkg::Dma::Xfer").child("len")

    assert member.defined_in.origin == PROVENANCE_DECLARATION
    assert not member.defined_in.is_extension
    assert member.defined_in.source.path.endswith("dma_pkg.pss")


def test_extension_members_carry_extension_provenance(sample_index) -> None:
    xfer = sample_index.get("dma_pkg::Dma::Xfer")

    for name in ("prio", "preemptible", "c_prio_range"):
        member = xfer.child(name)
        assert member.defined_in.is_extension, name
        assert member.defined_in.origin == PROVENANCE_EXTENSION
        assert member.defined_in.source.path.endswith("dma_ext.pss")


def test_provenance_records_the_extend_site_line(sample_index) -> None:
    """Rendering says "Added by ... (dma_ext.pss:18)", so the line must be real."""
    prio = sample_index.get("dma_pkg::Dma::Xfer").child("prio")

    assert prio.defined_in.source.line > 0
    assert prio.location.line == prio.defined_in.source.line


def test_provenance_works_across_type_kinds(sample_index) -> None:
    """The extension in the fixture also extends a buffer, not just an action."""
    buf = sample_index.get("dma_pkg::DmaBuf")

    assert buf.child("size").defined_in.origin == PROVENANCE_DECLARATION
    assert buf.child("consumed").defined_in.is_extension


def test_extension_members_keep_their_own_documentation(sample_index) -> None:
    """The doc comes from the extend site, which is where it was written."""
    prio = sample_index.get("dma_pkg::Dma::Xfer").child("prio")

    assert prio.raw_doc == "Scheduling priority for this transfer; higher runs first."


def test_declaration_members_come_first(sample_index) -> None:
    """Ordering is declaration members, then each extend site in link order."""
    names = [c.name for c in sample_index.get("dma_pkg::Dma::Xfer").children]
    extension_names = {"prio", "preemptible", "c_prio_range"}

    first_extension = min(names.index(n) for n in extension_names)
    assert all(
        n not in extension_names for n in names[:first_extension]
    ), "an extension member appeared before a declared one"
