"""P1-TEST-5 — compiler-injected members are filtered, real ones are not.

The rule is ``lineno < 0``, but applying it blindly is wrong: some node types
never receive a location at all, and enum values are the case that bites
(finding ``U-2``). These tests pin both halves.
"""

from __future__ import annotations

import pytest

from sphinx_pss.model.builder import build_objects
from sphinx_pss.model.locations import UNLOCATED_NODE_TYPES, is_synthesized
from sphinx_pss.model.parse import parse_model

pytestmark = pytest.mark.unit


class _FakeLocation:
    def __init__(self, lineno: int, fileid: int = 1) -> None:
        self.lineno = lineno
        self.fileid = fileid
        self.linepos = 0


class _FakeNode:
    """Stands in for a parser node, named so the type test can see it."""

    def __init__(self, lineno: int) -> None:
        self._loc = _FakeLocation(lineno)

    def getLocation(self):
        return self._loc


class EnumItem(_FakeNode):
    """A node type that legitimately has no location."""


def test_a_negative_line_marks_a_synthesized_node() -> None:
    assert is_synthesized(_FakeNode(-1))
    assert not is_synthesized(_FakeNode(1))


def test_unlocated_node_types_are_exempt() -> None:
    """Without this, every enum value disappears from the documentation."""
    assert "EnumItem" in UNLOCATED_NODE_TYPES
    assert not is_synthesized(EnumItem(-1))


def test_injected_members_do_not_appear(sample_model) -> None:
    """``set_executor`` and ``comp`` are injected into every component/action."""
    names = {
        obj.name for root in build_objects(sample_model) for obj in root.walk()
    }

    assert "set_executor" not in names
    assert "comp" not in names


def test_enum_values_survive(sample_model) -> None:
    values = [
        obj.name
        for root in build_objects(sample_model)
        for obj in root.walk()
        if obj.kind == "enum_item"
    ]

    assert values == ["INCREMENT", "FIXED", "WRAP"]


def test_a_real_member_named_like_an_injected_one_is_kept(tmp_path) -> None:
    """The filter is by location, not by name."""
    source = tmp_path / "c.pss"
    source.write_text(
        """
        package p {
            component C {
                // A user's own field that happens to be called comp.
                int comp;
            }
        }
        """
    )

    fields = [
        obj
        for root in build_objects(parse_model([str(source)]))
        for obj in root.walk()
        if obj.kind == "field"
    ]

    assert [f.name for f in fields] == ["comp"]
    assert fields[0].is_documented


def test_the_standard_library_is_excluded_by_default(sample_model) -> None:
    packages = [o.name for o in build_objects(sample_model)]

    assert packages == ["dma_pkg", "dma_ext_pkg"]
    for stdlib_package in ("std_pkg", "addr_reg_pkg", "executor_pkg", "sync_pkg"):
        assert stdlib_package not in packages


def test_the_standard_library_is_included_on_request(sample_model) -> None:
    packages = {o.name for o in build_objects(sample_model, document_stdlib=True)}

    assert {"std_pkg", "addr_reg_pkg", "executor_pkg", "sync_pkg"} <= packages
