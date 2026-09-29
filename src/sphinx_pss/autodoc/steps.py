#****************************************************************************
#* steps.py
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
"""Step tables and flowcharts: the ``pss:steps`` directive and the ``:steps:`` flag.

Both render `sphinx_pss.model.steps.steps_for` as a table with the columns of
steps design section 7.2 (the generated number, the title, the detail, and the
source line), as a flowchart (section 7.3, through the shared back-end in
`sphinx_pss.autodoc.diagrams`), or both. In the table, nesting is shown by
indenting the title; control rows (``If `rmii`:``) take no number, and the
steps inside them continue the enclosing numbering.

A step's title and detail are reStructuredText written in a ``.pss`` comment,
so they are parsed with each line attributed to its ``.pss`` line, the same
way doc comments are (`AutoPssDirective.parse_generated`): a markup error is
reported where the author can fix it, not at the page that asked for the table.
"""

from __future__ import annotations

import os
from typing import Any, Callable

from docutils import nodes
from docutils.parsers.rst import directives
from docutils.statemachine import StringList
from sphinx import addnodes
from sphinx.util import logging
from sphinx.util.docutils import SphinxDirective, switch_source_input
from sphinx.util.parsing import nested_parse_to_nodes

from ..domain import GENERATED_REF
from ..model.objects import SourceRef
from ..model.steps_flowchart import steps_flowchart
from ..model.steps import (
    Arm,
    Branch,
    CallExpansion,
    ExtensionGroup,
    Group,
    Loop,
    Step,
    StepsDoc,
    StepsError,
    StepsUnavailable,
    steps_for,
)
from ..viewcode import source_link
from . import diagrams

logger = logging.getLogger(__name__)

#: ``:format:`` values.
FORMATS = ("table", "flowchart", "both")

#: The options that shape a step table or flowchart, shared by ``pss:steps``
#: and the ``autopss*`` directives that take ``:steps:``. Values are checked by
#: `render_steps` and `steps_for`, whose messages list what is valid.
STEP_OPTIONS: dict[str, Callable[[str | None], Any]] = {
    "format": directives.unchanged_required,
    "exec": directives.unchanged_required,
    "numbering": directives.unchanged_required,
    "expand-calls": directives.unchanged_required,
    "depth": directives.nonnegative_int,
    # For a compound action's activity (activity-diagrams design 4.4).
    "expand-exec": directives.flag,
    "weights": directives.flag,
}

#: Per build (keyed by source directory, like the shared index): what has
#: already been reported, so a warning about the model is given once however
#: many tables run into it.
_REPORTED: dict[str, set[Any]] = {}

#: The directory ``conf.py`` is in, per build, for showing source paths the
#: way the project wrote them.
_CONFDIRS: dict[str, str] = {}

#: Indentation per nesting level of the Step column: an em space, which every
#: builder keeps, where CSS would only reach HTML.
_INDENT = "\u2003\u2003"


def start_build(app) -> None:
    """Forget what was reported; called when a build starts."""
    _REPORTED[str(app.srcdir)] = set()
    _CONFDIRS[str(app.srcdir)] = str(app.confdir)


def display_path(env: Any, path: str) -> str:
    """``path`` relative to the source directory it was found under, else to ``conf.py``."""
    config = env.config
    confdir = _CONFDIRS.get(str(env.srcdir), str(env.srcdir))
    full = os.path.abspath(path)
    for d in config.pss_source_dirs:
        root = os.path.abspath(os.path.join(confdir, d))
        if full.startswith(root + os.sep):
            return os.path.relpath(full, root).replace(os.sep, "/")
    rel = os.path.relpath(full, confdir)
    if not rel.startswith(".."):
        return rel.replace(os.sep, "/")
    return os.path.basename(full)


def report_once(env: Any, key: Any) -> bool:
    """True the first time ``key`` is reported in this build."""
    return _report_once(env, key)


def _report_once(env: Any, key: Any) -> bool:
    seen = _REPORTED.setdefault(str(env.srcdir), set())
    if key in seen:
        return False
    seen.add(key)
    return True


# --- rendering ------------------------------------------------------------------


def render_steps(
    directive: SphinxDirective, target: str, options: dict[str, Any]
) -> list[nodes.Node]:
    """The step table or flowchart of ``target`` under ``options``, or the error saying why not.

    ``directive`` is the one asking: its state parses the reStructuredText in
    step titles and details, and errors are reported at its line.
    """
    from .directives import get_index

    reporter = directive.state.document.reporter
    index = get_index(directive.env)
    if index is None:
        return [
            reporter.error(
                "sphinx-pss: no PSS model is available. Set pss_source_dirs "
                "or pss_source_files in conf.py.",
                line=directive.lineno,
            )
        ]

    fmt = options.get("format", "table")
    if fmt not in FORMATS:
        return [
            reporter.error(
                f"sphinx-pss: unknown step format {fmt!r}; expected one of: {', '.join(FORMATS)}",
                line=directive.lineno,
            )
        ]

    obj = index.get(target) or index.resolve(target)
    qualname = obj.qualname if obj is not None else target
    if obj is not None and obj.kind != "function" and obj.kind not in _TYPE_KINDS:
        return [
            reporter.error(
                f"sphinx-pss: {qualname!r} is {_article(obj.kind)} {obj.kind}, which has no "
                "body: steps are shown for a function, or for a type's exec blocks",
                line=directive.lineno,
            )
        ]
    try:
        doc = steps_for(
            index.model,
            qualname,
            exec_kind=options.get("exec"),
            expand_calls=options.get("expand-calls", "inline"),
            depth=options.get("depth"),
            numbering=options.get("numbering", "decimal"),
            expand_exec="expand-exec" in options,
            weights="weights" in options,
        )
    except StepsUnavailable as e:
        if _report_once(directive.env, "unavailable"):
            logger.warning(
                f"sphinx-pss: {e}; step tables are left out",
                location=(directive.env.docname, directive.lineno),
                type="pss",
                subtype="steps",
            )
        return []
    except StepsError as e:
        # The model says "the exec option"; here it has a spelling.
        message = f"sphinx-pss: {e}".replace("the exec option", "the ':exec:' option")
        if obj is None:
            candidates = sorted(
                o.qualname
                for o in index.candidates(target.split("::")[-1])
                if o.kind == "function" or o.kind in _TYPE_KINDS
            )
            if candidates:
                message += "; did you mean " + ", ".join(candidates[:5]) + "?"
        return [reporter.error(message, line=directive.lineno)]

    if doc.activity and fmt != "table":
        # The activity diagram is the activity's flowchart (design 4.4).
        return [
            reporter.error(
                f"sphinx-pss: {qualname!r} is a compound action, whose steps are shown as a table "
                "only. Draw its activity with pss:activity-diagram, and ':steps: collapsed' for "
                "one box per step",
                line=directive.lineno,
            )
        ]

    for issue in doc.issues:
        if _report_once(directive.env, (issue.code, issue.path, issue.line)):
            logger.warning(issue.message, location=issue.location(), type="pss", subtype=issue.code)

    if not any(True for _ in doc.steps()):
        if doc.activity:
            from .._capability import activity_comments_supported
            from ..model.activity import activity_for
            from ..model.activity_steps import unread_marker

            if not activity_comments_supported() and unread_marker(index.model, activity_for(index.model, qualname)):
                # The markers are there; the parser can't attach them (design 4.7).
                from .activity import _report_unread_markers

                _report_unread_markers(directive.env, index.model, activity_for(index.model, qualname))
                return []
        logger.warning(
            f"sphinx-pss: {_describe(doc)} has no step markers, so there is no step table",
            location=(directive.env.docname, directive.lineno),
            type="pss",
            subtype="steps",
        )
        return []

    table = StepsTable(directive, doc)
    flowchart = None
    if fmt != "table":
        name = diagrams.backend(directive.env, (directive.env.docname, directive.lineno))
        if name is not None:
            graph = steps_flowchart(doc, lambda ref: f"{table.display_path(ref.path)}:{ref.line}")
            flowchart = diagrams.diagram_node(
                graph, name, f"Flowchart of {graph.title}", classes=["pss-steps-flowchart"]
            )
            flowchart["pss:target"] = doc.target

    # A flowchart that can't be drawn falls back to the table, which every
    # builder can show: the page still documents the procedure.
    out: list[nodes.Node] = []
    if fmt != "flowchart" or flowchart is None:
        out.append(table.build())
    if flowchart is not None:
        out.append(flowchart)
    return out


_TYPE_KINDS = frozenset({"component", "action", "struct", "buffer", "stream", "state", "resource", "monitor"})


def _article(word: str) -> str:
    return "an" if word[:1] in "aeiou" else "a"


def _describe(doc: StepsDoc) -> str:
    if doc.exec_kind is None:
        return f"{doc.target!r}"
    return f"'exec {doc.exec_kind}' of {doc.target!r}"


class StepsTable:
    """Turns one `StepsDoc` into a docutils table."""

    COLUMNS = (("#", 8), ("Step", 40), ("Details", 40), ("Source", 12))

    def __init__(self, directive: SphinxDirective, doc: StepsDoc) -> None:
        self.directive = directive
        self.state = directive.state
        self.env = directive.env
        self.doc = doc
        self.body = nodes.tbody()

    def build(self) -> nodes.table:
        table = nodes.table(classes=["pss-steps", "colwidths-auto"])
        table["pss:target"] = self.doc.target
        group = nodes.tgroup(cols=len(self.COLUMNS))
        table += group
        for _, width in self.COLUMNS:
            group += nodes.colspec(colwidth=width)
        head = nodes.thead()
        header = nodes.row()
        for name, _ in self.COLUMNS:
            header += nodes.entry("", nodes.paragraph(text=name))
        head += header
        group += head
        group += self.body

        for g in self.doc.groups:
            self.group(g)
        return table

    # --- rows ---------------------------------------------------------------------

    def row(
        self,
        level: int,
        number: str,
        title: list[nodes.Node],
        *,
        secondary: list[nodes.Node] | None = None,
        detail: list[nodes.Node] | None = None,
        source: SourceRef | None = None,
        kind: str,
    ) -> None:
        row = nodes.row(classes=[f"pss-steps-{kind}", f"pss-steps-level-{level}"])

        row += nodes.entry("", nodes.paragraph(text=number))

        step = nodes.entry()
        first = nodes.paragraph()
        if level:
            first += nodes.Text(_INDENT * level)
        first.extend(title)
        step += first
        if secondary:
            more = nodes.paragraph(classes=["pss-steps-condition"])
            if level:
                more += nodes.Text(_INDENT * level)
            more.extend(secondary)
            step += more
        row += step

        row += nodes.entry("", *(detail or []))
        row += nodes.entry("", *self.source(source))
        self.body += row

    def source(self, ref: SourceRef | None) -> list[nodes.Node]:
        """The Source column: a link once viewcode exists, ``file:line`` text until then (D2)."""
        if ref is None:
            return []
        text = f"{self.display_path(ref.path)}:{ref.line}"
        link = source_link(self.env, ref, text)
        return [nodes.paragraph("", "", link if link is not None else nodes.literal(text=text))]

    def display_path(self, path: str) -> str:
        return display_path(self.env, path)

    # --- nodes --------------------------------------------------------------------

    def group(self, group: ExtensionGroup) -> None:
        if group.is_extension:
            self.row(
                0,
                "",
                [nodes.emphasis(text="Added by an extension")],
                source=group.source,
                kind="extension",
            )
        self.walk(group.children, 0)

    def walk(self, children: list[Any], level: int) -> None:
        for node in children:
            if isinstance(node, Step):
                self.step(node, level)
            elif isinstance(node, Branch):
                self.branch(node, level)
            elif isinstance(node, Loop):
                self.row(level, "", self.loop_text(node), source=node.source, kind="control")
                self.walk(node.children, level + 1)
            elif isinstance(node, CallExpansion):
                self.call(node, level)
            elif isinstance(node, Group):
                self.row(level, "", self.group_text(node), source=node.source, kind="control")
                self.walk(node.children, level + 1)

    def step(self, step: Step, level: int) -> None:
        children = list(step.children)
        merged = None
        if children and isinstance(children[0], (Branch, Loop, Group)) and children[0].marked:
            merged = children.pop(0)

        secondary = None
        if isinstance(merged, Loop):
            secondary = self.loop_text(merged)
        elif isinstance(merged, Group):
            secondary = self.group_text(merged)
        elif isinstance(merged, Branch) and merged.kind == "select":
            secondary = [nodes.Text("One of:")]
        elif isinstance(merged, Branch):
            secondary = (
                self.match_text(merged) if merged.kind == "match" else self.arm_text(merged.arms[0])
            )

        self.row(
            level,
            step.number,
            self.title(step),
            secondary=secondary,
            detail=self.detail(step),
            source=step.source,
            kind="step",
        )

        # A marked control is drawn as the step's own row (design 4.3): what
        # it holds sits one level in, and only the arms after the first get
        # rows of their own.
        if isinstance(merged, (Loop, Group)):
            self.walk(merged.children, level + 1)
        elif isinstance(merged, Branch):
            if merged.kind in ("match", "select"):
                self.choices(merged, level + 1)
            else:
                arms = _shown_arms(merged)
                if arms:
                    self.walk(arms[0].children, level + 1)
                    for arm in arms[1:]:
                        self.arm(arm, level + 1)
        self.walk(children, level + 1)

    def branch(self, branch: Branch, level: int) -> None:
        if branch.kind in ("match", "select"):
            head = self.match_text(branch) if branch.kind == "match" else [nodes.Text("One of:")]
            self.row(level, "", head, source=branch.source, kind="control")
            self.choices(branch, level + 1)
            return
        for arm in _shown_arms(branch):
            self.arm(arm, level)

    def arm(self, arm: Arm, level: int) -> None:
        self.row(level, "", self.arm_text(arm), source=arm.source, kind="control")
        self.walk(arm.children, level + 1)

    def choices(self, branch: Branch, level: int) -> None:
        # Choices are independent of each other, so an empty one says nothing.
        for arm in branch.arms:
            if arm.children:
                self.arm(arm, level)

    def call(self, call: CallExpansion, level: int) -> None:
        if call.mode == "exec":
            # The boundary between the scenario and the implementation stays
            # visible (activity-diagrams D3).
            text = [nodes.Text("The "), nodes.literal(text="exec body"), nodes.Text(" of "), self.callee_ref(call.callee), nodes.Text(":")]
            self.row(level, "", text, source=call.source, kind="call-exec")
            self.walk(call.children, level + 1)
            return
        if call.mode == "inline":
            # The callee's steps are sub-steps of the calling step, numbered
            # from it, as a programming guide nests them.
            self.walk(call.children, level)
            return
        name = [self.callee_ref(call.callee)]
        if call.mode == "link":
            text = [nodes.Text("Follow the steps of "), *name]
        else:
            text = [nodes.Text("Repeat from step "), nodes.Text(call.see), nodes.Text(" ("), *name, nodes.Text(")")]
        self.row(level, "", text, source=call.source, kind=f"call-{call.mode}")

    # --- text -----------------------------------------------------------------------

    def arm_text(self, arm: Arm) -> list[nodes.Node]:
        if arm.kind == "select":
            # An unguarded arm isn't a fallback: it may be picked any time.
            text = _phrase("If ", arm.label, "") if arm.label else [nodes.Text("Or")]
            if arm.weight:
                text += [nodes.Text(" (weight "), nodes.literal(text=arm.weight), nodes.Text(")")]
            return text + [nodes.Text(":")]
        if arm.kind == "if":
            return _phrase("If ", arm.label, ":")
        if arm.kind == "else_if":
            return _phrase("Else if ", arm.label, ":")
        if arm.kind == "choice":
            label = arm.label
            if label.startswith("[") and label.endswith("]"):
                label = label[1:-1].strip()
            return _phrase("When ", label, ":")
        return [nodes.Text("Otherwise:")]

    def match_text(self, branch: Branch) -> list[nodes.Node]:
        return _phrase("Depending on ", branch.label, ":")

    def loop_text(self, loop: Loop) -> list[nodes.Node]:
        if loop.kind == "while":
            return _phrase("While ", loop.label, ":")
        if loop.kind == "repeat_while":
            return _phrase("Repeat until not ", loop.label, ":")
        if loop.kind == "repeat_count":
            return _phrase("Repeat ", loop.label, " times:")
        if loop.variable:
            return [nodes.Text("For each "), nodes.literal(text=loop.variable), *_phrase(" in ", loop.label, ":")]
        return _phrase("For each element of ", loop.label, ":")

    def group_text(self, group: Group) -> list[nodes.Node]:
        """The row of an activity's ``parallel``, ``schedule``, ``replicate`` or ``atomic`` (design 4.4)."""
        if group.kind == "atomic":
            return [nodes.Text("Without interleaving:")]
        if group.kind == "replicate":
            return [nodes.literal(text=group.label), nodes.Text(" copies, in parallel:")]
        if group.kind == "schedule":
            text: list[nodes.Node] = [nodes.Text("In an order the tool chooses")]
            for is_parallel, targets in group.constraints:
                names = [nodes.literal(text=name) for name in targets]
                text.append(nodes.Text(" ("))
                for i, name in enumerate(names):
                    if i:
                        text.append(nodes.Text(", " if is_parallel else " before " if len(names) == 2 else ", then "))
                    text.append(name)
                text.append(nodes.Text(" in parallel)" if is_parallel else ")"))
            return text + [nodes.Text(":")]
        spec = group.label
        argument = spec[spec.find("(") + 1 : spec.rfind(")")].strip() if "(" in spec else ""
        if spec.startswith("join_none"):
            return [nodes.Text("Start in parallel, without waiting:")]
        if spec.startswith("join_first"):
            return _phrase("In parallel, until the first ", argument, " finish:")
        if spec.startswith("join_select"):
            return _phrase("In parallel, until ", argument, " chosen at random finish:")
        if spec.startswith("join_branch"):
            return _phrase("In parallel, until ", argument, " finish:")
        return [nodes.Text("In parallel:")]

    def callee_ref(self, qualname: str) -> nodes.Node:
        """The callee's name, linked to its entry when a page documents it."""
        from .directives import get_index

        index = get_index(self.env)
        obj = index.get(qualname) if index is not None else None
        short = qualname.rsplit("::", 1)[-1]
        node = addnodes.pending_xref(
            "",
            nodes.literal(text=short),
            refdomain="pss",
            reftype="action" if obj is not None and obj.kind == "action" else "func",
            reftarget=qualname,
            refspecific=True,
            **{"pss:scope": "", GENERATED_REF: True},
        )
        node["refwarn"] = False
        return node

    # --- reStructuredText from the .pss file --------------------------------------

    def title(self, step: Step) -> list[nodes.Node]:
        """The title's inline markup, parsed at the marker's line."""
        parsed = self.parse([step.title], step.source.path, step.source.line)
        if len(parsed) == 1 and isinstance(parsed[0], nodes.paragraph):
            return list(parsed[0].children)
        # Not a single paragraph ("- a list", say): show it as written.
        return [nodes.Text(step.title)]

    def detail(self, step: Step) -> list[nodes.Node]:
        if not step.detail:
            return []
        return self.parse(list(step.detail), step.source.path, step.detail_line or step.source.line)

    def parse(self, lines: list[str], path: str, first_line: int) -> list[nodes.Node]:
        """``lines`` parsed as reStructuredText, line ``i`` attributed to ``path:first_line + i``."""
        content = StringList()
        for i, line in enumerate(lines):
            content.append(line, path, first_line - 1 + i)
        with switch_source_input(self.state, content):
            return nested_parse_to_nodes(self.state, content, allow_section_headings=False)


def _phrase(before: str, code: str, after: str) -> list[nodes.Node]:
    """``before`` + ``code`` as literal text + ``after``: a condition as written."""
    return [nodes.Text(before), nodes.literal(text=code or "…"), nodes.Text(after)]


def _shown_arms(branch: Branch) -> list[Arm]:
    """The arms of an ``if`` chain up to the last one with something in it.

    An arm's condition is only reached when the ones before it fail, so an
    empty arm before a full one still says something; a trailing empty
    ``else`` doesn't.
    """
    last = max((i for i, arm in enumerate(branch.arms) if arm.children), default=-1)
    return branch.arms[: last + 1]


# --- directives -----------------------------------------------------------------


class PssStepsDirective(SphinxDirective):
    """``.. pss:steps:: <function or type>``: the steps of a body (design 7.1)."""

    has_content = False
    required_arguments = 1
    optional_arguments = 0
    final_argument_whitespace = False
    option_spec = dict(STEP_OPTIONS)

    def run(self) -> list[nodes.Node]:
        return render_steps(self, self.arguments[0].strip(), self.options)


def attach_steps(directive: SphinxDirective, target: str, result: list[nodes.Node]) -> None:
    """Put ``target``'s steps into the entry an ``autopss*`` directive rendered.

    The table or flowchart goes after the entry's own prose and before its
    members, so it stays with the thing it describes.
    """
    table = render_steps(directive, target, directive.options)
    if not table:
        return
    desc = next((n for n in result if isinstance(n, addnodes.desc)), None)
    content = None
    if desc is not None:
        content = next(iter(desc.findall(addnodes.desc_content)), None)
    if content is None:
        result.extend(table)
        return
    position = next(
        (i for i, child in enumerate(content.children) if isinstance(child, (addnodes.desc, addnodes.index))),
        len(content.children),
    )
    for node in reversed(table):
        content.insert(position, node)


def setup(app) -> None:
    app.add_directive_to_domain("pss", "steps", PssStepsDirective)
