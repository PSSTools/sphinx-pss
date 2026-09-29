"""Marker recognition (programming-steps plan ``S1-IMPL-1`` / ``S1-TEST-1``).

Pure text: the comment has already been found and its markers stripped. The
cases are those of design section 3.1 (rule 2) and section 3.5.
"""

from __future__ import annotations

import pytest

from sphinx_pss.model.comments import strip_markers
from sphinx_pss.model.steps_markers import (
    Marker,
    is_near_miss,
    parse_marker,
    parse_markers,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "text,title,number",
    [
        ("Step: Reset the MAC", "Reset the MAC", None),
        ("Step 3: Reset the MAC", "Reset the MAC", "3"),
        ("Step 2.1: Program the address", "Program the address", "2.1"),
        ("Step:Reset", "Reset", None),
        ("  Step: indented", "indented", None),
        ("Step: Wait: then poll", "Wait: then poll", None),
    ],
)
def test_valid_markers(text, title, number) -> None:
    marker = parse_marker([text], first_line=10)

    assert marker == Marker(title=title, detail=(), number=number, line=10)


def test_a_bare_marker_has_an_empty_title() -> None:
    """Reported as ``pss.step_empty``, not read as prose."""
    assert parse_marker(["Step:"]).title == ""
    assert parse_marker(["Step 3:  "]).title == ""


@pytest.mark.parametrize(
    "text",
    [
        "step: reset",
        "STEP 3 Reset",
        "Steps: reset",
        "Step Reset the MAC",
        "Step",
        "Step 3 Reset",
        "Step3: Reset",
    ],
)
def test_near_misses_are_not_markers(text) -> None:
    assert parse_marker([text]) is None
    assert is_near_miss(text)


@pytest.mark.parametrize(
    "text",
    [
        "Reset the MAC",
        "Stepping through the table",
        "Step-by-step setup",
        "Stepper motor control",
        "The next step: reset",
        "",
    ],
)
def test_prose_is_neither(text) -> None:
    assert parse_marker([text]) is None
    assert not is_near_miss(text)


def test_valid_markers_are_not_near_misses() -> None:
    assert not is_near_miss("Step: Reset")
    assert not is_near_miss("Step 2.1: Reset")
    assert not is_near_miss("Step:")


def test_detail_is_the_rest_of_the_comment() -> None:
    lines = strip_markers(
        "/** Step: Enable the receiver\n"
        " *  Done last, so no frame arrives half-configured.\n"
        " *\n"
        " *  - RXEN is bit 0.\n"
        " */"
    )
    marker = parse_marker(lines, first_line=40)

    assert marker.title == "Enable the receiver"
    assert marker.line == 40
    assert marker.detail == (
        "Done last, so no frame arrives half-configured.",
        "",
        "- RXEN is bit 0.",
    )


def test_lines_before_the_marker_are_ignored() -> None:
    marker = parse_marker(["Some prose first.", "Step: Reset", "Detail."], first_line=5)

    assert marker.title == "Reset"
    assert marker.line == 6
    assert marker.detail == ("Detail.",)


def test_each_marker_takes_the_lines_up_to_the_next() -> None:
    markers = parse_markers(["Step: A", "about a", "Step: B", "about b"], first_line=1)

    assert [(m.title, m.detail, m.line) for m in markers] == [
        ("A", ("about a",), 1),
        ("B", ("about b",), 3),
    ]


def test_no_markers() -> None:
    assert parse_markers(["just prose"]) == []
    assert parse_marker([]) is None


def test_the_detail_knows_its_source_line() -> None:
    """Plan ``S3-IMPL-3`` reports markup errors in the detail at their ``.pss`` line."""
    markers = parse_markers(
        ["Step: A", "", "  first detail", "  second", "Step: B", "Step: C", "about c"],
        first_line=20,
    )

    assert [(m.title, m.detail_line) for m in markers] == [("A", 22), ("B", 0), ("C", 26)]
    assert markers[0].detail == ("first detail", "second")
