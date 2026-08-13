"""sphinx-pss — Sphinx autodoc support for Accellera PSS source.

The extension is wired up in `setup`; everything else lives in submodules:

``config``    the ``pss_*`` configuration values
``model``     ``pssparser`` front-end producing a normalized ``PssObject`` tree
``docparse``  doc-comment dialects producing a ``ParsedDoc``
``domain``    the ``pss`` Sphinx domain — object directives, roles, index
``autodoc``   the ``autopss*`` directives and their documenters
``viewcode``  ``[source]`` links into rendered PSS listings
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .__version__ import get_version
from ._version_floor import check_pssparser_version

if TYPE_CHECKING:
    from sphinx.application import Sphinx

__version__ = get_version()

# Fail at import rather than mid-build. See _version_floor for why this is an
# assertion and not a capability probe.
check_pssparser_version()


def setup(app: Sphinx) -> dict[str, Any]:
    """Sphinx extension entry point."""
    from . import autodoc as _autodoc
    from . import config as _config
    from . import domain as _domain

    _config.setup(app)
    _domain.setup(app)
    _autodoc.setup(app)

    # No ``add_lexer`` call: ``pygments-pss`` registers ``pss`` through a
    # ``pygments.lexers`` entry point, so Pygments finds it wherever it looks
    # -- ``pygmentize``, MkDocs and plain docutils included, not only a Sphinx
    # app that happens to load this extension. Depending on the package is the
    # whole wiring; see ``design/pssparser-followup-plan.md`` section 5.

    return {
        "version": __version__,
        "parallel_read_safe": False,
        "parallel_write_safe": True,
    }
