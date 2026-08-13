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

from ._version_floor import check_pssparser_version

if TYPE_CHECKING:
    from sphinx.application import Sphinx

__version__ = "0.0.1"

# Fail at import rather than mid-build. See _version_floor for why this is an
# assertion and not a capability probe.
check_pssparser_version()


def setup(app: Sphinx) -> dict[str, Any]:
    """Sphinx extension entry point."""
    from . import autodoc as _autodoc
    from . import config as _config
    from . import domain as _domain
    from .lexer import PssLexer

    _config.setup(app)
    _domain.setup(app)
    _autodoc.setup(app)

    # Pygments ships no PSS lexer, so ``.. code-block:: pss`` would otherwise
    # warn (and fail a ``-W`` build) in any project documenting PSS.
    app.add_lexer("pss", PssLexer)

    return {
        "version": __version__,
        "parallel_read_safe": False,
        "parallel_write_safe": True,
    }
