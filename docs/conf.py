"""Sphinx configuration for the sphinx-pss documentation set.

This site dogfoods the extension on itself: from Phase 1 it documents the
``tests/fixtures/pss`` sample model with the extension's own directives, which
makes ``sphinx-build -W`` the project's best regression signal.
"""

import pathlib

project = "sphinx-pss"
author = "Matthew Ballance"
copyright = "2026, Matthew Ballance"

_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

extensions = [
    "myst_parser",
    "sphinx.ext.graphviz",
    "sphinx.ext.intersphinx",
    "sphinx_pss",
]

myst_enable_extensions = ["colon_fence", "deflist", "fieldlist"]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

html_theme = "furo"
html_static_path = ["_static"]

intersphinx_mapping = {
    "sphinx": ("https://www.sphinx-doc.org/en/master/", None),
}

# --- sphinx-pss ------------------------------------------------------------
# The published docs document the test fixtures, so the examples in this site
# are built from sources that the test suite also asserts against.
pss_source_dirs = [str(_REPO_ROOT / "tests" / "fixtures" / "pss")]
pss_doc_style = "native"
pss_document_stdlib = False
pss_default_options = {"members": True, "member-order": "source"}

nitpicky = False
