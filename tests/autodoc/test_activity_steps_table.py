"""The step table of a compound action (activity-diagrams plan ``AD5-TEST-1``).

``test-activity-steps`` asks for the design 4.5 example's table twice, the
second time with ``:expand-exec:``, and documents ``configure`` so the
boundary row can link to it. `support.geometric_comments` stands in for
pssparser ``AC1`` (plan decision D4).
"""

from __future__ import annotations

import re

import pytest
from docutils import nodes
from sphinx.util.console import strip_colors

from support import geometric_comments


def _messages(warning) -> list[tuple[str, int, str]]:
    found = []
    for line in strip_colors(warning.getvalue()).splitlines():
        match = re.search(r"([^/\s]+):(\d+): (?:WARNING|ERROR): (.*)", line)
        if match:
            found.append((match.group(1), int(match.group(2)), match.group(3)))
    return found


def _tables(app) -> list[list[tuple[str, str]]]:
    """Each step table as ``(number, step text)`` rows, indentation stripped."""
    doctree = app.env.get_and_resolve_doctree("index", app.builder, tags=app.tags)
    out = []
    for table in doctree.findall(nodes.table):
        if "pss-steps" not in table["classes"]:
            continue
        rows = []
        for row in table.findall(nodes.row):
            entries = list(row.findall(nodes.entry))
            if len(entries) != 4 or row.parent.tagname == "thead":
                continue
            rows.append((entries[0].astext(), entries[1].astext().strip("  ")))
        out.append(rows)
    return out


@pytest.fixture
def with_comments(app, monkeypatch):
    from sphinx_pss.autodoc.directives import get_index
    from sphinx_pss.model import activity

    statement, block = geometric_comments(get_index(app.env).model)
    monkeypatch.setattr(activity, "statement_comments", statement)
    monkeypatch.setattr(activity, "block_comments", block)


@pytest.mark.sphinx("html", testroot="activity-steps", freshenv=True, warningiserror=True)
def test_the_table_of_the_design_example(app, with_comments) -> None:
    app.build()
    plain, expanded, _ = _tables(app)

    assert plain == [
        ("1", "Configure the channel"),
        ("2", "Move the data\n\nIn parallel:"),
        ("2.1", "Copy the first half"),
        ("2.2", "Copy the second half"),
        ("3", "Check the result"),
    ]
    assert expanded[:4] == [
        ("1", "Configure the channel"),
        ("", "The exec body of configure:"),
        ("1.1", "Write the descriptor"),
        ("1.2", "Enable the channel"),
    ]


@pytest.mark.sphinx("html", testroot="activity-steps", freshenv=True)
def test_the_boundary_row_links_to_the_action(app, with_comments) -> None:
    app.build()
    html = (app.outdir / "index.html").read_text()

    (row,) = re.findall(r'<tr class="pss-steps-call-exec.*?</tr>', html, re.S)
    assert 'href="#pss-sxfer_pkg.dma_c.configure"' in row


@pytest.mark.sphinx("html", testroot="activity-steps", freshenv=True)
def test_without_the_parser_the_table_says_why(app, warning) -> None:
    app.build()

    assert [m[2].split(",")[0] for m in _messages(warning)] == [
        "sphinx-pss: step markers in activities need a pssparser that attaches comments to activity statements"
    ]
    assert _tables(app) == []


@pytest.mark.sphinx("html", testroot="activity-steps-errors", freshenv=True)
def test_a_flowchart_of_an_activity_is_refused(app, warning, with_comments) -> None:
    app.build()

    assert _messages(warning) == [
        (
            "index.rst",
            4,
            "sphinx-pss: 'sxfer_pkg::dma_c::xfer' is a compound action, whose steps are shown as a "
            "table only. Draw its activity with pss:activity-diagram, and ':steps: collapsed' for one "
            "box per step [docutils]",
        )
    ]


@pytest.mark.sphinx("html", testroot="activity-steps", freshenv=True, warningiserror=True)
def test_each_control_has_its_row(app, with_comments) -> None:
    """Design 4.4: a schedule is never mistaken for a parallel (D1); weights on request (D2)."""
    app.build()
    shapes = _tables(app)[2]

    assert shapes == [
        ("1", "Race\n\nIn parallel, until the first 1 finish:"),
        ("1.1", "Copy one way"),
        ("1.2", "Copy the other way"),
        ("", "In an order the tool chooses (s1, then s2, then s3):"),
        ("1.3", "Early"),
        ("1.4", "Middle"),
        ("1.5", "Late"),
        ("", "4 copies, in parallel:"),
        ("1.6", "One copy"),
        ("", "Without interleaving:"),
        ("1.7", "Uninterrupted"),
        ("", "One of:"),
        ("", "If fast (weight 3):"),
        ("1.8", "Fast"),
        ("", "Or:"),
        ("1.9", "Any time"),
    ]



@pytest.mark.sphinx("html", testroot="activity-steps", freshenv=True, warningiserror=True)
def test_the_steps_page_shows_what_the_table_renders(app, with_comments) -> None:
    """``AD5-DOC-1``: the table on ``docs/usage/steps.md`` is the one ``:expand-exec:`` renders."""
    import pathlib

    page = pathlib.Path(__file__).resolve().parents[2] / "docs" / "usage" / "steps.md"
    text = page.read_text()
    block = text[text.index(":name: activity-step-table-example") :].split("```", 1)[0]
    shown = []
    for line in block.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 2 and cells[0] not in ("#", "---"):
            shown.append((cells[0], cells[1].replace("`", "").replace("<br>", "\n\n")))

    app.build()

    assert _tables(app)[1] == shown
