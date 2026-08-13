"""P1-TEST-11 — documentation fields are checked against the model.

This is the property that distinguishes the field vocabulary from a naming
convention: a comment that names something the element does not declare is a
build warning, so documentation cannot drift away from the code it describes
without somebody being told (design section 3.1).
"""

from __future__ import annotations

import pytest

from sphinx_pss.docparse import parse_doc, validate
from sphinx_pss.model.objects import PssObject

pytestmark = pytest.mark.unit


def action(doc: str, members: list[tuple[str, str]] | None = None) -> PssObject:
    """An action with ``members`` given as ``(kind, name)`` pairs."""
    obj = PssObject(kind="action", name="Xfer", qualname="p::C::Xfer", raw_doc=doc)
    for kind, name in members or []:
        obj.children.append(
            PssObject(
                kind=kind,
                name=name,
                qualname=f"{obj.qualname}::{name}",
                # Documented, so the undocumented-member check stays quiet
                # unless a test is specifically about it.
                raw_doc="Documented at its declaration.",
            )
        )
    return obj


def issues(obj: PssObject, category: str | None = None):
    found = validate(parse_doc(obj), obj)
    if category is not None:
        found = [i for i in found if i.category == category]
    return found


# --- a field naming something that is not declared --------------------------


def test_an_undeclared_flow_reference_warns() -> None:
    obj = action(":output out_b: filled", [("flow_ref", "result")])

    found = issues(obj, "undeclared")

    assert len(found) == 1
    assert "out_b" in found[0].message
    assert "does not declare" in found[0].message


def test_the_warning_lists_what_is_declared() -> None:
    """So the fix is visible without opening the source."""
    obj = action(":output out_b: filled", [("flow_ref", "result")])

    assert "result" in issues(obj, "undeclared")[0].message


def test_the_warning_carries_the_comment_line() -> None:
    obj = action("Summary.\n\n:output nope: x", [("flow_ref", "real")])

    assert issues(obj, "undeclared")[0].line == 3


def test_a_declared_reference_does_not_warn() -> None:
    obj = action(":output out_b: filled", [("flow_ref", "out_b")])

    assert issues(obj, "undeclared") == []


@pytest.mark.parametrize(
    "field,kind",
    [
        ("input", "flow_ref"),
        ("output", "flow_ref"),
        ("lock", "resource_claim"),
        ("share", "resource_claim"),
        ("field", "field"),
        ("constraint", "constraint"),
    ],
)
def test_each_validated_field_checks_the_right_member_kind(
    field: str, kind: str
) -> None:
    assert issues(action(f":{field} x: text", [(kind, "x")]), "undeclared") == []
    assert issues(action(f":{field} x: text", [(kind, "y")]), "undeclared")


def test_a_field_of_the_wrong_member_kind_warns() -> None:
    """``:output:`` must name a flow reference, not a plain attribute field."""
    obj = action(":output len: bytes", [("field", "len")])

    assert issues(obj, "undeclared")


# --- unknown and misapplied fields ------------------------------------------


def test_a_misspelled_field_warns_rather_than_rendering() -> None:
    """Otherwise ``:ouput:`` silently becomes a generic field and looks fine."""
    found = issues(action(":ouput out_b: filled"), "undeclared")

    assert len(found) == 1
    assert "unknown documentation field" in found[0].message
    assert "output" in found[0].message, "the known fields should be listed"


def test_a_field_used_on_the_wrong_kind_warns() -> None:
    """``:pool:`` documents a component, and an action cannot declare one."""
    obj = PssObject(
        kind="action", name="A", qualname="p::A", raw_doc=":pool p: the pool"
    )

    found = issues(obj, "undeclared")

    assert len(found) == 1
    assert "does not apply to a action" in found[0].message


def test_a_free_form_field_is_never_cross_validated() -> None:
    """``:req:`` takes arbitrary IDs; there is nothing in the AST to check."""
    assert issues(action(":req: DMA-014, DMA-015"), "undeclared") == []


def test_a_field_with_no_argument_is_not_cross_validated() -> None:
    assert issues(action(":output: something"), "undeclared") == []


# --- the other direction: declared but undocumented -------------------------


def test_an_undocumented_flow_reference_is_reported() -> None:
    obj = action("Summary.")
    obj.children.append(
        PssObject(kind="flow_ref", name="out_b", qualname="p::C::Xfer::out_b")
    )

    found = issues(obj, "undocumented")

    assert len(found) == 1
    assert "out_b" in found[0].message


def test_a_field_entry_counts_as_documenting_a_member() -> None:
    obj = action(":output out_b: the filled buffer")
    obj.children.append(
        PssObject(kind="flow_ref", name="out_b", qualname="p::C::Xfer::out_b")
    )

    assert issues(obj, "undocumented") == []


def test_a_doc_comment_counts_as_documenting_a_member() -> None:
    obj = action("Summary.", [("flow_ref", "out_b")])

    assert issues(obj, "undocumented") == []


def test_plain_attribute_fields_are_not_reported_as_undocumented() -> None:
    """Only the members whose purpose the AST cannot convey are reported.

    A ``rand int len`` reads for itself; an ``output DmaBuf out_b`` does not
    say what the buffer carries.
    """
    obj = action("Summary.")
    obj.children.append(PssObject(kind="field", name="len", qualname="p::C::Xfer::len"))

    assert issues(obj, "undocumented") == []


def test_undocumented_and_undeclared_are_distinguishable() -> None:
    """``:undoc-members:`` shows one; the other is always a warning."""
    obj = action(":output nope: x")
    obj.children.append(
        PssObject(kind="flow_ref", name="real", qualname="p::C::Xfer::real")
    )

    categories = {i.category for i in validate(parse_doc(obj), obj)}

    assert categories == {"undeclared", "undocumented"}


# --- against the real fixture ------------------------------------------------


def test_the_sample_model_validates_clean(sample_index) -> None:
    """The published example must not warn, or the docs cannot build under -W."""
    problems = []
    for obj in sample_index:
        for issue in validate(parse_doc(obj), obj):
            if issue.category == "undeclared":
                problems.append(f"{obj.qualname}: {issue.message}")

    assert problems == []
