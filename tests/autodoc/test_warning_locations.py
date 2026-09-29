"""Warnings about a doc comment point at the comment, in the ``.pss`` file.

The fix a reader needs to make is in the source comment, so a warning that
names the page that rendered it -- ``index.rst:91`` in a six-line file, as
reported before this was fixed -- is only a clue, not a location.
"""

from __future__ import annotations

import re

import pytest

pytestmark = pytest.mark.sphinx


def _locations(warning) -> list[tuple[str, int, str]]:
    """``(file name, line, message)`` for each warning."""
    found = []
    for line in warning.getvalue().splitlines():
        match = re.search(r"([^/\s]+):(\d+): WARNING: (.*)", line)
        if match:
            found.append((match.group(1), int(match.group(2)), match.group(3)))
    return found


@pytest.mark.sphinx("html", testroot="doc-locations", freshenv=True)
def test_a_markup_error_in_a_doc_comment_points_at_its_source_line(
    app, warning
) -> None:
    app.build()

    [markup] = [w for w in _locations(warning) if "start-string" in w[2]]
    assert markup[:2] == ("model.pss", 8), (
        "docutils reports an inline error at the start of its paragraph, "
        "which is line 8 of model.pss"
    )


@pytest.mark.sphinx("html", testroot="doc-locations", freshenv=True)
def test_an_undeclared_doc_field_points_at_the_field(app, warning) -> None:
    app.build()

    [field] = [w for w in _locations(warning) if "missing_b" in w[2]]
    assert field[:2] == ("model.pss", 15), "the :input missing_b: line"


@pytest.mark.sphinx("html", testroot="doc-locations", freshenv=True)
def test_no_doc_comment_warning_is_attributed_to_the_page(app, warning) -> None:
    app.build()

    assert not [w for w in _locations(warning) if w[0] == "index.rst"]
