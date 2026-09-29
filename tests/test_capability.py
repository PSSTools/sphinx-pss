"""P0-TEST-3 — the ``pssparser`` capability probe.

Replaces the former version floor (``design/pssparser-followup-plan.md``
section 4). ``pssparser`` versions name the PSS LRM revision targeted, and a
source-tree build reports ``0.0.0``, so no version comparison can say whether
doc-comment extraction works. The behavior that must hold is unchanged: a parser
that cannot extract doc comments fails hard, with a message that says what is
wrong rather than what version was expected.
"""

from __future__ import annotations

import pytest

from sphinx_pss import _capability
from sphinx_pss._capability import PssParserCapabilityError, check_pssparser

pytestmark = pytest.mark.unit


@pytest.fixture
def fresh_probe(monkeypatch):
    """Discard any cached pass so each test runs the probe itself."""
    monkeypatch.setattr(_capability, "_verified", None)


def test_installed_parser_passes_the_probe(fresh_probe) -> None:
    version = check_pssparser()
    assert version, "returns the installed version for reporting"


def test_probe_result_is_cached(fresh_probe, monkeypatch) -> None:
    check_pssparser()

    def fail():  # pragma: no cover - must not be reached
        raise AssertionError("probe re-ran")

    monkeypatch.setattr(_capability, "_probe_docstring", fail)
    check_pssparser()


def test_source_tree_version_is_not_rejected(fresh_probe, monkeypatch) -> None:
    """A working-tree build reports 0.0.0; the version must not decide."""
    monkeypatch.setattr(_capability, "installed_version", lambda: "0.0.0")
    assert check_pssparser() == "0.0.0"


@pytest.mark.parametrize(
    "doc,symptom",
    [
        (None, "rand int f"),
        ("", "rand int f"),
        ("* Summary.\n         *\n         * Body.", "not normalized"),
    ],
)
def test_incapable_parser_is_rejected_with_an_actionable_message(
    fresh_probe, monkeypatch, doc, symptom
) -> None:
    monkeypatch.setattr(_capability, "installed_version", lambda: "3.0.1")
    monkeypatch.setattr(_capability, "_probe_docstring", lambda: doc)

    with pytest.raises(PssParserCapabilityError) as excinfo:
        check_pssparser()

    message = str(excinfo.value)
    assert "3.0.1" in message, "says what was actually found"
    assert symptom in message, "names the symptom, not just a version"
    assert "rebuilt" in message, (
        "the likeliest cause against a working-tree build is a stale build, "
        "and the message should say so"
    )
    assert _capability._verified is None, "a failure is not cached as a pass"
