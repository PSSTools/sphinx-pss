"""A project that documents the canonical sample model from source.

``sphinx.testing`` copies a test root into a temporary directory before
building it, so a path derived from ``__file__`` would point into that copy,
where the ``.pss`` fixtures are not. ``tests/conftest.py`` exports
``SPHINX_PSS_FIXTURES`` for that reason; the fallback keeps a manual
``sphinx-build`` of this directory working.
"""

import os
import pathlib

extensions = ["sphinx_pss"]

_FIXTURES = pathlib.Path(
    os.environ.get(
        "SPHINX_PSS_FIXTURES",
        pathlib.Path(__file__).resolve().parents[2] / "fixtures" / "pss",
    )
)

pss_source_files = [
    str(_FIXTURES / "dma_pkg.pss"),
    str(_FIXTURES / "dma_ext.pss"),
]
