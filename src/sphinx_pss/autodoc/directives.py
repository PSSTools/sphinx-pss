#****************************************************************************
#* directives.py
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
from sphinx.util.docutils import SphinxDirective, switch_source_input
from sphinx.util.parsing import nested_parse_to_nodes

from ..docparse import ValidationIssue
from ..model.index import PssIndex, build_index
from ..model.objects import PssObject
from ..model.parse import PssParseError
from ..model.steps_lint import lint_markers
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
            # after the generated prose -- keeping its own .rst source lines.
            for source, offset, line in self.content.xitems():
                lines.append(f"   {line}", source, offset)
            lines.append("", f"<autopss:{target}>", len(lines))

        result = self.parse_generated(lines)
        if "steps" in self.options:
            from .steps import attach_steps

            attach_steps(self, obj.qualname, result)
        return result

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
        because the thing to fix is the comment in the ``.pss`` file: a field
        issue at the field's line, anything else at the declaration.
        """
        for obj, issue in issues:
            location = None
            if issue.line > 0 and obj.doc_source is not None:
                line = obj.doc_source.line_of(issue.line - 1)
                location = f"{obj.doc_source.path}:{line}"
            elif obj.location is not None:
                location = str(obj.location)
            logger.warning(
                issue.message,
                location=location or f"{self.env.docname}:{self.lineno}",
                type="pss",
                subtype=issue.category,
            )

    def parse_generated(self, content: StringList) -> list[Any]:
        """Parse generated reStructuredText into nodes.

        ``content`` carries a source for every line (see
        `PssDocumenter.document`). Two things are needed for docutils to use
        it: an offset of 0, so line numbers index ``content`` rather than the
        host document, and `switch_source_input`, because the reporter maps
        line numbers through the *host* document's state machine otherwise --
        which is how a doc-comment error used to be reported as
        ``index.rst:91`` in a six-line file.
        """
        with switch_source_input(self.state, content):
            return nested_parse_to_nodes(
                self.state, content, allow_section_headings=True
            )


#: Directives that take ``:steps:``: the kinds with a body to show steps of
#: (programming-steps design 7.1).
STEPS_DIRECTIVES = frozenset({"function", "action", "component"})


#: Directives that take ``:activity-diagram:``: those that can render an
#: action, themselves or as a member (activity-diagrams design 7.2).
ACTIVITY_DIRECTIVES = frozenset({"package", "component", "action", "object"})


def make_directive(name: str, kinds: tuple[str, ...]) -> type[AutoPssDirective]:
    label = ", ".join(kinds) if kinds else "object"
    attrs: dict[str, Any] = {
        "kinds": kinds,
        "__doc__": f"Documents a PSS {label} from source.",
    }
    option_spec = dict(AutoPssDirective.option_spec)
    if name in STEPS_DIRECTIVES:
        from .steps import STEP_OPTIONS

        option_spec.update({"steps": directives.flag, **STEP_OPTIONS})
    if name in ACTIVITY_DIRECTIVES:
        from .activity import ACTIVITY_OPTIONS_PREFIXED

        option_spec.update({"activity-diagram": _flag_or_bool, **ACTIVITY_OPTIONS_PREFIXED})
    if option_spec != AutoPssDirective.option_spec:
        attrs["option_spec"] = option_spec
    return type(f"AutoPss{name.title()}Directive", (AutoPssDirective,), attrs)


def build_shared_index(app) -> None:
    """Build the one index this project's directives share.

    Connected to ``builder-inited``. A configuration with no sources is not an
    error here — a project may legitimately use the domain directives by hand
    — but a directive that then needs the index says so specifically.
    """
    from .steps import start_build

    start_build(app)
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

    # Step markers are checked across the whole model, once, whether or not a
    # page asks for steps: a mistyped marker is a mistake wherever it is
    # (programming-steps plan, decision D5).
    for issue in lint_markers(index.model):
        logger.warning(
            issue.message,
            location=issue.location(),
            type="pss",
            subtype=issue.code,
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
