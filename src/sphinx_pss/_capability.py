#****************************************************************************
#* _capability.py
#*
#* Copyright 2026 Matthew Ballance and Contributors
#*
#* Licensed under the Apache License, Version 2.0 (the "License"); you may
#* not use this file except in compliance with the License.
#* You may obtain a copy of the License at:
#*
#*   http://www.apache.org/licenses/LICENSE-2.0
#*
#* Unless required by applicable law or agreed to in writing, software
#* distributed under the License is distributed on an "AS IS" BASIS,
#* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#* See the License for the specific language governing permissions and
#* limitations under the License.
#****************************************************************************
"""Capability probe on ``pssparser``.

``sphinx-pss`` requires the doc-comment subsystem introduced by
``DocCommentExtractor`` / ``DocAnchorScope`` (see
``design/pssparser-enhancement-plan.md``). Against an older parser, doc
comments are missing on attributed fields, unrelated comment blocks merge, and
block comments arrive with ``*`` markers and full source indentation intact.
Partially-working doc extraction is worse than a clear failure, so this fails
hard rather than degrading (enhancement-plan section 8).

The check parses a few lines of PSS from memory and asserts the doc comment
arrives attached and normalized, rather than comparing version numbers
(``design/pssparser-followup-plan.md`` section 4). A version cannot answer the
question: ``pssparser`` versions name the PSS LRM revision targeted, not any
capability, and a source-tree build reports ``0.0.0`` because only a release
tag carries a real number. The version is still read, but only to make the
failure message actionable.
"""

from __future__ import annotations

#: The probe model. One attributed field under a block comment exercises all
#: three things the extension cannot work without: a docstring at all, attached
#: to an *attributed* field (``rand int f``), with ``*`` markers and source
#: indentation stripped.
_PROBE_SOURCE = """\
package _sphinx_pss_probe {
    struct S {
        /** Summary.
         *
         * Body.
         */
        rand int f;
    }
}
"""

#: What a capable parser returns for the probe field.
_PROBE_EXPECTED = "Summary.\n\nBody."

#: Cached result of a passing probe (the installed version string), so repeated
#: builds in one process pay for the parse once.
_verified: str | None = None


class PssParserCapabilityError(ImportError):
    """The installed ``pssparser`` cannot extract doc comments as required."""


def installed_version() -> str:
    """Return the installed ``pssparser`` version, for messages only.

    Prefers ``get_version()``, which appends ``git describe`` in a source tree
    (``0.0.0+v3.1.7-2-g1ec757b``) — far more useful in a report than the bare
    ``0.0.0`` a working-tree build carries.
    """
    import pssparser

    get_version = getattr(pssparser, "get_version", None)
    if get_version is not None:
        return str(get_version())
    raw = pssparser.__version__
    if isinstance(raw, (tuple, list)):
        raw = "".join(str(p) for p in raw)
    return str(raw)


def _probe_docstring() -> str | None:
    """Parse the probe and return the field's doc comment, or None."""
    from pssparser import Parser

    parser = Parser(collect_docstrings=True)
    parser.parses([("_sphinx_pss_probe.pss", _PROBE_SOURCE)])
    parser.link()

    def find_field(node):
        if type(node).__name__ == "Field":
            return node
        get_children = getattr(node, "getChildren", None)
        if get_children is None:
            return None
        for i in range(len(get_children())):
            found = find_field(node.getChild(i))
            if found is not None:
                return found
        return None

    for unit in parser.user_units():
        field = find_field(unit)
        if field is not None:
            getter = getattr(field, "getDocstring", None)
            return getter() if getter is not None else None
    return None


def check_pssparser() -> str:
    """Verify the installed ``pssparser`` extracts doc comments correctly.

    Returns the installed version string. Raises `PssParserCapabilityError` if
    the probe fails, or plain `ImportError` if ``pssparser`` is not importable.
    """
    global _verified
    if _verified is not None:
        return _verified

    try:
        version = installed_version()
    except ImportError as e:  # pragma: no cover - environment-specific
        raise ImportError(
            "sphinx-pss requires the 'pssparser' package, which could not be "
            "imported. pssparser is a C++/Cython extension and must be built, "
            "not merely downloaded; see docs/getting-started.md."
        ) from e

    try:
        doc = _probe_docstring()
    except Exception as e:  # noqa: BLE001 - any failure means "not capable"
        problem = f"parsing a doc-comment probe failed: {e}"
    else:
        if not doc:
            problem = (
                "doc comments on attributed fields ('rand int f;') come back "
                "empty"
            )
        elif doc != _PROBE_EXPECTED:
            problem = (
                "doc comments are not normalized: expected "
                f"{_PROBE_EXPECTED!r}, got {doc!r} ('*' markers or source "
                "indentation left in)"
            )
        else:
            _verified = version
            return version

    import pssparser

    raise PssParserCapabilityError(
        f"sphinx-pss cannot use the installed pssparser: {problem}.\n\n"
        f"  installed: pssparser {version} ({pssparser.__file__})\n\n"
        "This needs the doc-comment rework described in pssparser's "
        "CHANGELOG. If you are building pssparser from a working tree, check "
        "that it has been rebuilt since those changes landed."
    )
