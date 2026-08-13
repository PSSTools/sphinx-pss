"""Version floor on ``pssparser``.

``sphinx-pss`` requires the doc-comment subsystem introduced by
``DocCommentExtractor`` / ``DocAnchorScope`` (see
``docs/design/pssparser-enhancement-plan.md``). Against an older parser, doc
comments are missing on attributed fields, unrelated comment blocks merge, and
block comments arrive with ``*`` markers and full source indentation intact.

Partially-working doc extraction is worse than a clear failure, so this fails
hard rather than degrading (enhancement-plan section 8).

.. warning::

   **This check is known to be asking the wrong question, and is scheduled for
   replacement** — see ``docs/design/pssparser-followup-plan.md`` section 4.

   ``pssparser`` versions as ``<PSS major>.<PSS minor>.<patch>``: the first two
   components name the PSS LRM revision the parser targets, and the patch is a
   counter. So a version number says nothing about whether doc-comment
   extraction works, and no choice of floor can make it say so — a floor high
   enough to imply the rework would also be demanding a newer *language*
   revision than this project needs.

   The replacement is a capability probe: parse a few lines of PSS in memory
   and assert the doc comment arrives attached and normalized. Same hard
   failure, but it tests the thing that actually matters. Until that lands,
   the floor below is set to the patch release carrying the rework, which is
   approximately right and no worse than what it replaces.
"""

from __future__ import annotations

#: Minimum ``pssparser`` release, as a comparable tuple. Interim: see the
#: module docstring for why a version comparison cannot express the real
#: requirement.
MIN_PSSPARSER_VERSION = (3, 0, 3)


class PssParserTooOldError(ImportError):
    """The installed ``pssparser`` predates the doc-comment rework."""


def _numeric_prefix(version: str) -> tuple[int, ...]:
    """Parse the leading ``N.N.N`` of a version string.

    ``pssparser`` reports development versions such as ``3.1.0+v3.0.2-dirty``,
    so everything from the first non-numeric-or-dot character is discarded.
    """
    parts: list[int] = []
    for chunk in version.split("."):
        digits = ""
        for ch in chunk:
            if not ch.isdigit():
                break
            digits += ch
        if not digits:
            break
        parts.append(int(digits))
        if len(digits) != len(chunk):
            break
    return tuple(parts)


def installed_version() -> str:
    """Return the installed ``pssparser`` version as a string.

    ``pssparser.__version__`` is a ``(version, suffix)`` tuple, and the
    installed *distribution* metadata can lag the source tree in an editable
    install, so the package's own attribute is authoritative here.
    """
    import pssparser

    raw = pssparser.__version__
    if isinstance(raw, (tuple, list)):
        raw = raw[0]
    return str(raw)


def check_pssparser_version() -> str:
    """Verify the installed ``pssparser`` meets the floor.

    Returns the installed version string. Raises `PssParserTooOldError` if it
    does not, or plain `ImportError` if ``pssparser`` is not importable.
    """
    try:
        version = installed_version()
    except ImportError as e:  # pragma: no cover - environment-specific
        raise ImportError(
            "sphinx-pss requires the 'pssparser' package, which could not be "
            "imported. pssparser is a C++/Cython extension and must be built, "
            "not merely downloaded; see docs/getting-started.md."
        ) from e

    minimum = ".".join(str(p) for p in MIN_PSSPARSER_VERSION)
    if _numeric_prefix(version) < MIN_PSSPARSER_VERSION:
        raise PssParserTooOldError(
            f"sphinx-pss requires pssparser >= {minimum}, but {version} is "
            "installed. Older releases cannot extract doc comments from "
            "attributed fields ('rand int x;'), merge unrelated comment "
            "blocks, and leave '*' markers and source indentation in block "
            "comments.\n\n"
            "If you are building pssparser from a working tree, check that it "
            "has been rebuilt since the doc-comment rework landed — the "
            "version stamp and the built code can disagree."
        )
    return version
