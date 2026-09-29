"""Steps in activities in a Sphinx build (activity-diagrams plan ``AD4-TEST-3``).

``test-activity-steps`` shows the design 4.5 example as an outline, with and
without steps. With `support.geometric_comments` standing in for pssparser
``AC1`` the steps appear; with the real parser they can't, and the build says
so once (``pss.step_unsupported``).
"""

from __future__ import annotations

import re

import pytest
from docutils import nodes
from sphinx.util.console import strip_colors

from support import geometric_comments

X = "sxfer_pkg::dma_c::xfer"


def _messages(warning) -> list[tuple[str, int, str]]:
    found = []
    for line in strip_colors(warning.getvalue()).splitlines():
        match = re.search(r"([^/\s]+):(\d+): (?:WARNING|ERROR): (.*)", line)
        if match:
            found.append((match.group(1), int(match.group(2)), match.group(3)))
    return found


def _outline_lines(app) -> list[list[str]]:
    doctree = app.env.get_doctree("index")
    return [
        [line for line in c.astext().splitlines() if line]
        for c in doctree.findall(nodes.container)
        if "pss-activity-outline" in c["classes"]
    ]


@pytest.fixture
def with_comments(app, monkeypatch):
    """Put the stand-in for pssparser AC1 in place, for this build's model."""
    from sphinx_pss.autodoc.directives import get_index
    from sphinx_pss.model import activity

    statement, block = geometric_comments(get_index(app.env).model)
    monkeypatch.setattr(activity, "statement_comments", statement)
    monkeypatch.setattr(activity, "block_comments", block)


@pytest.mark.sphinx("html", testroot="activity-steps", freshenv=True, warningiserror=True)
def test_the_outline_shows_the_steps(app, with_comments, warning) -> None:
    app.build()

    stepped, plain = _outline_lines(app)
    assert stepped == [
        "1 Configure the channel",
        "cfg : configure",
        "2 Move the data",
        "parallel",
        "2.1 Copy the first half",
        "c1 : copy",
        "2.2 Copy the second half",
        "c2 : copy",
        "3 Check the result",
        "chk : check",
    ]
    assert plain == ["cfg : configure", "parallel", "c1 : copy", "c2 : copy", "chk : check"]
    assert _messages(warning) == []


@pytest.mark.sphinx("html", testroot="activity-steps", freshenv=True)
def test_without_the_parser_the_build_says_why_once(app, warning) -> None:
    app.build()

    assert _messages(warning) == [
        (
            "steps_xfer.pss",
            30,
            "sphinx-pss: step markers in activities need a pssparser that attaches comments to "
            "activity statements, and the installed one doesn't, so activity steps aren't shown. "
            "Upgrade pssparser, or suppress this with suppress_warnings = ['pss.step_unsupported'] "
            "[pss.step_unsupported]",
        )
    ]
    assert _outline_lines(app)[0][0] == "cfg : configure"


@pytest.mark.sphinx(
    "html",
    testroot="activity-steps",
    freshenv=True,
    warningiserror=True,
    confoverrides={"suppress_warnings": ["pss.step_unsupported"]},
)
def test_the_warning_can_be_suppressed(app) -> None:
    app.build()
