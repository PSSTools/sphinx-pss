"""Step-marker lint reaches the build as located, suppressible warnings.

Plan ``S1-IMPL-3``: the lint runs once, at ``builder-inited``, and each
problem is a ``pss.step_*`` warning at the comment's line in the ``.pss``
file. The page that happens to be building has nothing to do with it.
"""

from __future__ import annotations

import re

import pytest
from sphinx.util.console import strip_colors

pytestmark = pytest.mark.sphinx


def _warnings(warning) -> list[tuple[str, int, str]]:
    """``(file name, line, type)`` for each warning."""
    found = []
    for line in strip_colors(warning.getvalue()).splitlines():
        match = re.search(r"([^/\s]+):(\d+): WARNING: .*\[(pss\.\w+)\]$", line)
        if match:
            found.append((match.group(1), int(match.group(2)), match.group(3)))
    return found


@pytest.mark.sphinx(
    "html",
    testroot="step-lint",
    freshenv=True,
    confoverrides={"show_warning_types": True},
)
def test_each_problem_is_a_located_warning(app, warning) -> None:
    app.build()

    assert _warnings(warning) == [
        ("model.pss", 4, "pss.step_misplaced"),
        ("model.pss", 10, "pss.step_syntax"),
        ("model.pss", 12, "pss.step_empty"),
        ("model.pss", 16, "pss.step_empty"),
    ]


@pytest.mark.sphinx(
    "html",
    testroot="step-lint",
    freshenv=True,
    confoverrides={"suppress_warnings": ["pss.step_empty", "pss.step_misplaced"]},
)
def test_suppress_warnings_silences_a_code(app, warning) -> None:
    app.build()

    text = warning.getvalue()
    assert "not a step marker: 'step: a near miss'" in text
    assert "no title" not in text
    assert "no statements" not in text
    assert "outside a function body" not in text


@pytest.mark.sphinx("html", testroot="step-lint", freshenv=True)
def test_the_lint_runs_once_per_build(app, warning) -> None:
    app.build()

    assert warning.getvalue().count("not a step marker") == 1
