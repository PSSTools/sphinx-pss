"""The ``autopss*`` directives, and the index they all share.

The index is built **once**, on ``builder-inited``, and every directive
resolves into it (design section 6.1). Nothing here re-parses, which is both
why a large model stays fast and why whole-model relationships are computable
at all.
"""

from __future__ import annotations

from typing import Any

from docutils.parsers.rst import directives
from docutils.statemachine import StringList
from sphinx.util import logging
from sphinx.util.docutils import SphinxDirective

from ..docparse import ValidationIssue
from ..model.index import PssIndex, build_index
from ..model.objects import PssObject
from ..model.parse import PssParseError
from .documenters import DocumenterOptions, document_object

logger = logging.getLogger(__name__)

#: Shared indexes, keyed by the build's source directory.
#:
#: Deliberately **not** stored on the build environment: Sphinx pickles the
#: environment between runs, and the index holds a live ``pssparser.Parser``
#: — a Cython object that cannot be pickled, and that must stay alive for the
#: whole build because the linked tree is owned by it.
#:
#: Keyed by ``srcdir`` rather than by the application object because a
#: directive can reach ``env.srcdir`` but not the application:
#: ``BuildEnvironment.app`` is deprecated for removal in Sphinx 11. One
#: source directory is one project, so the key is as specific as the
#: application would have been.
_INDEXES: dict[str, PssIndex | None] = {}

#: ``autopss<name>`` -> the kinds that directive accepts. A directive that
#: accepts several kinds exists because PSS's ``struct`` declaration covers all
#: five flow-object kinds, and a reader looking for ``autopssbuffer`` should
#: find it.
AUTO_DIRECTIVES = {
    "package": ("package",),
    "component": ("component",),
    "action": ("action",),
    "struct": ("struct",),
    "buffer": ("buffer",),
    "stream": ("stream",),
    "state": ("state",),
    "resource": ("resource",),
    "enum": ("enum",),
    "function": ("function",),
    # Accepts anything, for the cases where spelling the kind adds nothing.
    "object": (),
}


def get_index(env) -> PssIndex | None:
    """The shared index for this build, or ``None`` if there is no model."""
    return _INDEXES.get(str(env.srcdir))


def _flag_or_bool(argument: str | None) -> bool:
    """A directive option that is a flag but may also be given a value.

    ``:members:`` and ``:members: True`` both mean yes, so a project can write
    either without discovering that one of them silently does nothing.
    """
    if argument is None or not argument.strip():
        return True
    return argument.strip().lower() not in {"false", "no", "0", "off"}


class AutoPssDirective(SphinxDirective):
    """Base for every ``autopss*`` directive."""

    #: Kinds this directive accepts; empty means any.
    kinds: tuple[str, ...] = ()

    has_content = True
    required_arguments = 1
    optional_arguments = 0
    final_argument_whitespace = False

    option_spec = {
        "members": _flag_or_bool,
        "no-members": directives.flag,
        "undoc-members": _flag_or_bool,
        "inherited-members": _flag_or_bool,
        "exclude-members": directives.unchanged,
        "member-order": lambda a: directives.choice(a, ("source", "alpha", "groups")),
        "recursive": _flag_or_bool,
        "no-index": directives.flag,
        "doc-style": directives.unchanged,
        "show-extensions": _flag_or_bool,
    }

    def run(self) -> list[Any]:
        index = get_index(self.env)
        if index is None:
            return [
                self.state.document.reporter.error(
                    "sphinx-pss: no PSS model is available. Set pss_source_dirs "
                    "or pss_source_files in conf.py.",
                    line=self.lineno,
                )
            ]

        target = self.arguments[0].strip()
        obj = self._resolve(index, target)
        if obj is None:
            return [
                self.state.document.reporter.error(
                    self._not_found_message(index, target), line=self.lineno
                )
            ]

        options = DocumenterOptions.from_directive(
            self.options, self.config.pss_default_options
        )
        lines, issues = document_object(index, obj, options, events=self.env.events)
        self._report(issues)

        if self.content:
            # Directive-body content overrides the source documentation
            # (design section 5.4), so it is appended inside the object's body
            # after the generated prose.
            lines.extend(f"   {line}" for line in self.content)
            lines.append("")

        return self.parse_generated(lines, target)

    # --- helpers -----------------------------------------------------------

    def _resolve(self, index: PssIndex, target: str) -> PssObject | None:
        obj = index.get(target) or index.resolve(target)
        if obj is None:
            return None
        if self.kinds and obj.kind not in self.kinds:
            return None
        return obj

    def _not_found_message(self, index: PssIndex, target: str) -> str:
        candidates = [o.qualname for o in index.candidates(target.split("::")[-1])]
        message = f"sphinx-pss: no PSS object named {target!r}"
        if self.kinds:
            message += f" of kind {' or '.join(self.kinds)}"
        if candidates:
            message += "; did you mean " + ", ".join(sorted(candidates)[:5]) + "?"
        return message

    def _report(self, issues: list[tuple[PssObject, ValidationIssue]]) -> None:
        """Turn cross-validation findings into Sphinx warnings.

        Located at the *source* of the doc comment rather than at the directive,
        because the thing to fix is the comment in the ``.pss`` file.
        """
        for obj, issue in issues:
            location = None
            if obj.location is not None:
                line = obj.location.line + max(issue.line - 1, 0)
                location = f"{obj.location.path}:{line}"
            logger.warning(
                issue.message,
                location=location or f"{self.env.docname}:{self.lineno}",
                type="pss",
                subtype=issue.category,
            )

    def parse_generated(self, lines: list[str], source: str) -> list[Any]:
        """Parse generated reStructuredText into nodes.

        The generated text is attributed to a pseudo-file named for the object,
        so a syntax error inside a doc comment reports against something the
        author can find rather than against a line number in a temporary
        buffer.
        """
        content = StringList(lines, source=f"<autopss:{source}>")
        return self.parse_text_to_nodes(content, allow_section_headings=True)


def make_directive(name: str, kinds: tuple[str, ...]) -> type[AutoPssDirective]:
    label = ", ".join(kinds) if kinds else "object"
    return type(
        f"AutoPss{name.title()}Directive",
        (AutoPssDirective,),
        {
            "kinds": kinds,
            "__doc__": f"Documents a PSS {label} from source.",
        },
    )


def build_shared_index(app) -> None:
    """Build the one index this project's directives share.

    Connected to ``builder-inited``. A configuration with no sources is not an
    error here — a project may legitimately use the domain directives by hand
    — but a directive that then needs the index says so specifically.
    """
    if not app.config.pss_source_dirs and not app.config.pss_source_files:
        _INDEXES[str(app.srcdir)] = None
        return

    try:
        index = build_index(
            app.config.pss_source_dirs,
            app.config.pss_source_files,
            confdir=app.confdir,
            document_stdlib=app.config.pss_document_stdlib,
            tolerate_link_errors=app.config.pss_tolerate_link_errors,
        )
    except PssParseError:
        _INDEXES[str(app.srcdir)] = None
        raise

    for diagnostic in index.model.diagnostics:
        logger.warning(
            diagnostic.message,
            location=diagnostic.location(),
            type="pss",
            subtype="parser",
        )

    if not index.model.linked:
        logger.warning(
            "PSS sources did not link; documentation is degraded to "
            "declarations and doc comments only. Cross references, extension "
            "merging and diagrams are unavailable.",
            type="pss",
            subtype="degraded",
        )

    _INDEXES[str(app.srcdir)] = index
    logger.info("sphinx-pss: indexed %d PSS objects", len(index))


def setup(app) -> None:
    for name, kinds in AUTO_DIRECTIVES.items():
        app.add_directive(f"autopss{name}", make_directive(name, kinds))
    app.connect("builder-inited", build_shared_index)
