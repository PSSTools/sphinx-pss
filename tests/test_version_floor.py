"""P0-TEST-3 — the ``pssparser`` version floor.

Scheduled for replacement by a capability probe — see
``docs/design/pssparser-followup-plan.md`` section 4. ``pssparser`` versions as
``<PSS major>.<PSS minor>.<patch>``, so the number names the LRM revision
targeted rather than any capability, and no floor can express what this project
actually requires.

What must survive that change is the *behavior*: a parser that cannot extract
doc comments fails hard, with a message that says what is wrong rather than
what version was expected.
"""

from __future__ import annotations

import pytest

from sphinx_pss import _version_floor
from sphinx_pss._version_floor import (
    MIN_PSSPARSER_VERSION,
    PssParserTooOldError,
    _numeric_prefix,
    check_pssparser_version,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "text,expected",
    [
        ("3.1.0", (3, 1, 0)),
        ("3.1.0+v3.0.2-dirty", (3, 1, 0)),
        ("3.1", (3, 1)),
        ("10.2.3", (10, 2, 3)),
        ("3.1.0rc1", (3, 1, 0)),
    ],
)
def test_numeric_prefix(text: str, expected: tuple[int, ...]) -> None:
    assert _numeric_prefix(text) == expected


def test_installed_parser_meets_the_floor() -> None:
    version = check_pssparser_version()
    assert _numeric_prefix(version) >= MIN_PSSPARSER_VERSION


def test_old_parser_is_rejected_with_an_actionable_message(monkeypatch) -> None:
    monkeypatch.setattr(_version_floor, "installed_version", lambda: "3.0.1")

    with pytest.raises(PssParserTooOldError) as excinfo:
        check_pssparser_version()

    message = str(excinfo.value)
    assert "3.0.1" in message, "says what was actually found"
    assert "rand int x" in message, "names the symptom, not just a version"
    assert "rebuilt" in message, (
        "the likeliest cause against a working-tree build is a stale build, "
        "and the message should say so"
    )
