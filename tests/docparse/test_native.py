"""P1-TEST-9 — the ``native`` dialect."""

from __future__ import annotations

import pytest

from sphinx_pss.docparse import get_parser, parse_doc, registered_styles, split_summary
from sphinx_pss.docparse.native import extract_xrefs
from sphinx_pss.model.objects import PssObject

pytestmark = pytest.mark.unit


def doc(text: str | None, kind: str = "action") -> "object":
    obj = PssObject(kind=kind, name="A", qualname="p::A", raw_doc=text)
    return parse_doc(obj)


# --- summary / body split ---------------------------------------------------


def test_the_first_paragraph_is_the_summary() -> None:
    parsed = doc("Program a transfer.\n\nAnd here is the body.")

    assert parsed.summary == "Program a transfer."
    assert parsed.rst_body == "And here is the body."


def test_a_summary_may_wrap() -> None:
    """A summary is a paragraph, not a line — PSS declarations are wordy."""
    parsed = doc("Program a single DMA\ntransfer end to end.\n\nBody.")

    assert parsed.summary == "Program a single DMA\ntransfer end to end."
    assert parsed.rst_body == "Body."


def test_a_single_paragraph_is_all_summary() -> None:
    parsed = doc("Just a summary.")

    assert parsed.summary == "Just a summary."
    assert parsed.rst_body == ""


def test_empty_documentation_is_falsey() -> None:
    assert not doc("")
    assert not doc(None)
    assert not doc("   \n  \n")


def test_the_body_keeps_its_paragraphs() -> None:
    parsed = doc("Summary.\n\nFirst body paragraph.\n\nSecond body paragraph.")

    assert parsed.rst_body == "First body paragraph.\n\nSecond body paragraph."


def test_indentation_in_the_body_is_left_alone() -> None:
    """Indentation is reStructuredText syntax, and normalizing is upstream's job."""
    parsed = doc("Summary.\n\nA literal block::\n\n    some_code();")

    assert "\n    some_code();" in parsed.rst_body


@pytest.mark.parametrize(
    "text,summary,body",
    [
        ("", "", ""),
        ("one", "one", ""),
        ("one\n\ntwo", "one", "two"),
        ("one\n\n\ntwo", "one", "two"),
        ("\n\none", "", "one"),
    ],
)
def test_split_summary_edge_cases(text: str, summary: str, body: str) -> None:
    assert split_summary(text) == (summary, body)


# --- fields -----------------------------------------------------------------


def test_fields_are_separated_from_prose() -> None:
    parsed = doc("Summary.\n\nBody text.\n\n:param n: the count")

    assert parsed.summary == "Summary."
    assert parsed.rst_body == "Body text."
    assert [(f.name, f.argument, f.body) for f in parsed.fields] == [
        ("param", "n", "the count")
    ]


def test_an_at_sign_line_is_ordinary_prose() -> None:
    """``//@…`` is a comment, not an annotation, and is rendered as written."""
    parsed = doc('@doc(text = "x")\n\nBody.')

    assert '@doc(text = "x")' in parsed.summary


# --- cross references -------------------------------------------------------


def test_explicit_roles_are_collected() -> None:
    parsed = doc("See :pss:action:`dma_pkg::Dma::Xfer` and :pss:buffer:`DmaBuf`.")

    assert parsed.xrefs == ["dma_pkg::Dma::Xfer", "DmaBuf"]


def test_a_repeated_reference_is_collected_once() -> None:
    assert extract_xrefs(":pss:action:`X` :pss:action:`X`") == ["X"]


def test_text_with_no_roles_has_no_xrefs() -> None:
    assert extract_xrefs("Plain prose about actions and buffers.") == []


# --- registry ---------------------------------------------------------------


def test_native_is_registered() -> None:
    assert "native" in registered_styles()
    assert get_parser("native").name == "native"


def test_an_unknown_style_names_the_available_ones() -> None:
    """A silent fallback would parse documentation by the wrong rules."""
    with pytest.raises(KeyError) as excinfo:
        get_parser("nonsense")

    assert "native" in str(excinfo.value)


def test_a_per_element_style_wins_over_the_project_setting() -> None:
    """What makes a per-directive ``:doc-style:`` option work."""
    obj = PssObject(
        kind="action", name="A", qualname="p::A", raw_doc="Text.", doc_style="native"
    )

    assert parse_doc(obj, style="nonexistent").summary == "Text."
