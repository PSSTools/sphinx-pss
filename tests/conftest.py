"""Shared pytest fixtures for the sphinx-pss suite.

Marker taxonomy (see design/implementation-plan.md, "Test taxonomy"):

``unit``      pure Python, no Sphinx application
``sphinx``    a real build over a ``tests/roots/`` mini-project
``corpus``    slow runs over the pssparser corpus / PSS standard library, opt-in
``upstream``  asserts a pssparser behavior we depend on; a failure, not a skip
"""

from __future__ import annotations

import os
import pathlib

import pytest

pytest_plugins = ("sphinx.testing.fixtures",)

#: Hand-authored ``.pss`` fixture sources.
FIXTURE_DIR = pathlib.Path(__file__).parent / "fixtures" / "pss"

#: Sphinx mini-projects driven by ``@pytest.mark.sphinx``.
ROOTS_DIR = pathlib.Path(__file__).parent / "roots"

# ``sphinx.testing`` copies a test root into a temporary directory before
# building it, so a root's ``conf.py`` cannot find the ``.pss`` fixtures from
# its own ``__file__``. Exporting the real location is the least surprising fix
# available: it works for pytest and leaves a manual ``sphinx-build`` of a root
# working through the fallback in each ``conf.py``.
os.environ.setdefault("SPHINX_PSS_FIXTURES", str(FIXTURE_DIR))


@pytest.fixture(scope="session")
def pss_fixture_dir() -> pathlib.Path:
    return FIXTURE_DIR


@pytest.fixture(scope="session")
def rootdir() -> pathlib.Path:
    """Where ``@pytest.mark.sphinx(testroot=...)`` looks for its projects."""
    return ROOTS_DIR


# --- the canonical sample model ---------------------------------------------
#
# Session-scoped on purpose: every parse pulls in the PSS standard library, so
# re-parsing per test would dominate the suite's runtime without adding
# coverage. Tests that need to observe parsing itself build their own model.

#: The sample plus its cross-file extension. Kept together because the
#: extension is what makes provenance observable.
SAMPLE_SOURCES = ("dma_pkg.pss", "dma_ext.pss")


@pytest.fixture(scope="session")
def sample_sources(pss_fixture_dir) -> list[str]:
    return [str(pss_fixture_dir / name) for name in SAMPLE_SOURCES]


@pytest.fixture(scope="session")
def sample_model(sample_sources):
    from sphinx_pss.model.parse import parse_model

    return parse_model(sample_sources)


@pytest.fixture(scope="session")
def sample_index(sample_model):
    from sphinx_pss.model.index import PssIndex

    return PssIndex(sample_model)
