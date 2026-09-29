"""Finds pss-corpus for the ``corpus`` tests (plan ``S0-IMPL-3``).

The search follows the corpus's consumer contract (pss-corpus ``README.md``,
"Using it"), duplicated here on purpose rather than shared:

1. ``$PSS_CORPUS`` -- an explicit path, for a working copy
2. ``packages/pss-corpus`` -- the ``default-dev`` ivpm dependency
3. ``../pss-corpus`` -- a sibling checkout

**A missing corpus fails; it does not skip.** A gate that skips when its input
is absent reports success in exactly the case it exists to catch. The
``corpus`` marker is already opt-in, so asking for these tests without a
corpus is an error worth hearing about.

Every module here sets ``pytestmark = pytest.mark.corpus`` itself: a marker
added from a collection hook can land after ``-m`` has already deselected.

A plain module, imported as ``corpus_finder``, rather than ``conftest.py``:
every directory's ``conftest`` is importable as ``conftest``, so helpers
imported from one resolve ambiguously.
"""

from __future__ import annotations

import os
import pathlib

try:
    import tomllib
except ImportError:  # Python 3.10
    import tomli as tomllib

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


def _find_corpus() -> pathlib.Path | None:
    candidates = []
    if os.environ.get("PSS_CORPUS"):
        candidates.append(pathlib.Path(os.environ["PSS_CORPUS"]))
    candidates += [
        _REPO_ROOT / "packages" / "pss-corpus",
        _REPO_ROOT.parent / "pss-corpus",
    ]
    for path in candidates:
        if (path / "curated").is_dir():
            return path
    return None


#: The corpus checkout, or None. Read through `corpus_files` and `require`.
CORPUS = _find_corpus()


def _parsing_buckets(root: pathlib.Path) -> set[str]:
    """Buckets the corpus's own manifest says are expected to parse."""
    manifest = tomllib.loads((root / "manifest.toml").read_text())
    return {name for name, policy in manifest["bucket"].items() if policy.get("parses")}


#: Why there is nothing to test, when there isn't.
_MISSING = (
    "pss-corpus not found. It is a default-dev ivpm dependency and belongs at "
    "packages/pss-corpus: run `ivpm update -d default-dev`, or set PSS_CORPUS. "
    "This fails rather than skips on purpose."
)


def corpus_files() -> list:
    """Every ``.pss`` file in a bucket the manifest marks ``parses = true``.

    For ``pytest.mark.parametrize``. ``pathological/`` is excluded by the
    manifest, not by name here, so a new bucket arrives with its policy
    attached.

    Collection must not fail: it runs even when ``-m`` deselects every corpus
    test, as it does in the default suite. So a missing corpus yields one
    ``None`` parameter, and `require` fails the test that receives it.
    """
    if CORPUS is None:
        return [pytest.param(None, id="no-corpus")]
    buckets = _parsing_buckets(CORPUS)
    files = sorted(
        p
        for p in (CORPUS / "curated").rglob("*.pss")
        if p.relative_to(CORPUS / "curated").parts[0] in buckets
    )
    return files or [pytest.param(None, id="empty-corpus")]


def require(path: pathlib.Path | None) -> pathlib.Path:
    """Fail the calling test when the corpus is missing or empty."""
    if path is None:
        pytest.fail(_MISSING if CORPUS is None else f"pss-corpus at {CORPUS} has no parseable files")
    return path


def corpus_id(path: pathlib.Path) -> str:
    return str(path.relative_to(CORPUS / "curated"))
