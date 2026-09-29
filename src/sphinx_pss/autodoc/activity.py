#****************************************************************************
#* activity.py
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
"""Activity diagrams and outlines: the ``pss:activity-diagram`` directive.

The diagram is `sphinx_pss.model.activity_diagram.activity_diagram`, drawn by
the shared back-end (`sphinx_pss.autodoc.diagrams`), in a figure whose caption
is the action's name, followed by what the diagram couldn't draw. The outline
is the same activity as a nested list: the diagram's text equivalent, and
what the page shows when the diagram can't be drawn (activity-diagrams design
sections 6 and 7).
"""

from __future__ import annotations

from typing import Any, Callable

from docutils import nodes
from docutils.parsers.rst import directives
from sphinx import addnodes
from sphinx.util import logging
from sphinx.util.docutils import SphinxDirective

from ..domain import GENERATED_REF
from .._capability import activity_comments_supported
from ..model import activity as a
from ..model.activity_diagram import MAX_DEPTH, STEP_MODES, activity_diagram
from ..model.activity_steps import stepped, unread_marker
from ..model.steps_flowchart import plain_text
from . import diagrams
from .steps import display_path, report_once

logger = logging.getLogger(__name__)

#: ``:format:`` values.
FORMATS = ("diagram", "outline", "both")


def _depth(argument: str | None) -> int:
    value = directives.positive_int(argument)
    if value > MAX_DEPTH:
        raise ValueError(f"at most {MAX_DEPTH}")
    return value


#: The options of ``pss:activity-diagram``. `ACTIVITY_OPTIONS_PREFIXED` is the
#: same set as the ``autopssaction`` flag takes them (design 7.2).
ACTIVITY_OPTIONS: dict[str, Callable[[str | None], Any]] = {
    "format": lambda arg: directives.choice(arg, FORMATS),
    "depth": _depth,
    "weights": directives.flag,
    "steps": lambda arg: directives.choice(arg, STEP_MODES),
    "caption": directives.unchanged,
}
ACTIVITY_OPTIONS_PREFIXED = {f"activity-{name}": spec for name, spec in ACTIVITY_OPTIONS.items() if name != "caption"}


def render_activity(directive: SphinxDirective, target: str, options: dict[str, Any]) -> list[nodes.Node]:
    """The diagram and/or outline of the action ``target``, or the error saying why not."""
    from .directives import get_index

    reporter = directive.state.document.reporter
    env = directive.env
    index = get_index(env)
    if index is None:
        return [
            reporter.error(
                "sphinx-pss: no PSS model is available. Set pss_source_dirs or pss_source_files in conf.py.",
                line=directive.lineno,
            )
        ]

    obj = index.get(target) or index.resolve(target)
    if obj is None or obj.kind != "action":
        message = f"sphinx-pss: no PSS action named {target!r}"
        if obj is not None:
            message = f"sphinx-pss: {obj.qualname!r} is a {obj.kind}, not an action, so it has no activity"
        else:
            candidates = sorted(o.qualname for o in index.candidates(target.split("::")[-1]) if o.kind == "action")
            if candidates:
                message += "; did you mean " + ", ".join(candidates[:5]) + "?"
        return [reporter.error(message, line=directive.lineno)]

    try:
        activity = a.activity_for(index.model, obj.qualname)
    except a.ActivityUnavailable as e:
        if report_once(env, "activity-unavailable"):
            logger.warning(
                f"sphinx-pss: {e}; activity diagrams are left out",
                location=(env.docname, directive.lineno),
                type="pss",
                subtype="activity",
            )
        return []
    except a.ActivityError as e:
        return [reporter.error(f"sphinx-pss: {e}", line=directive.lineno)]

    steps = options.get("steps", "regions")
    shown = activity if steps == "none" else stepped(index.model, activity)
    for issue in shown.issues:
        if report_once(env, (issue.code, issue.path, issue.line)):
            logger.warning(issue.message, location=issue.location(), type="pss", subtype=issue.code)
    if steps != "none" and not activity_comments_supported():
        _report_unread_markers(env, index.model, activity)

    fmt = options.get("format", "diagram")
    weights = "weights" in options
    outline = ActivityOutline(env, weights).build(shown)

    backend = None
    if fmt != "outline":
        backend = diagrams.backend(env, (env.docname, directive.lineno))
    if backend is None:
        # Nothing to draw with, or nothing asked for: the outline is the
        # activity, which every builder can show.
        return [outline]

    graph = activity_diagram(
        index.model,
        activity,
        depth=options.get("depth", 1),
        weights=weights,
        steps=steps,
        describe_source=lambda ref: f"{display_path(env, ref.path)}:{ref.line}",
    )
    figure = nodes.figure(classes=["pss-activity"])
    diagram = diagrams.diagram_node(graph, backend, _alt(shown), classes=["pss-activity-diagram"])
    diagram["pss:target"] = obj.qualname
    figure += diagram
    figure += nodes.caption(text=options.get("caption") or obj.qualname)
    if graph.caption_notes:
        legend = nodes.legend()
        for note in graph.caption_notes:
            legend += nodes.paragraph(text=note)
        figure += legend

    if fmt == "diagram":
        return [figure]
    # ``both``: the outline follows, folded away in HTML, where the diagram
    # says the same to a sighted reader; open elsewhere.
    return [
        figure,
        nodes.raw("", '<details class="pss-activity-outline"><summary>Outline</summary>', format="html"),
        outline,
        nodes.raw("", "</details>", format="html"),
    ]


def _report_unread_markers(env: Any, model: Any, activity: a.Activity) -> None:
    """One warning per build when step markers in activities can't be read (design 4.7).

    The installed pssparser attaches no comments to activity statements, so
    the markers are invisible to the model; the source text shows they are
    there, and the user should know why the diagram has no steps.
    """
    if any(isinstance(n, a.StepRegion) for n in stepped(model, activity).nodes()):
        return
    found = unread_marker(model, activity)
    if found is None or not report_once(env, "step-unsupported"):
        return
    logger.warning(
        "sphinx-pss: step markers in activities need a pssparser that attaches comments to "
        "activity statements, and the installed one doesn't, so activity steps aren't shown. "
        "Upgrade pssparser, or suppress this with suppress_warnings = ['pss.step_unsupported']",
        location=str(found),
        type="pss",
        subtype="step_unsupported",
    )


def _alt(activity: a.Activity) -> str:
    traversals = sum(1 for n in activity.nodes() if isinstance(n, a.Traversal))
    noun = "action" if traversals == 1 else "actions"
    text = f"Activity diagram of {activity.qualname}: {traversals} {noun} traversed"
    steps = sum(1 for n in activity.nodes() if isinstance(n, a.StepRegion))
    if steps:
        text += f", in {steps} step" + ("" if steps == 1 else "s")
    return text


class ActivityOutline:
    """An `Activity` as a nested bullet list."""

    def __init__(self, env: Any, weights: bool) -> None:
        self.env = env
        self.weights = weights

    def build(self, activity: a.Activity) -> nodes.Node:
        container = nodes.container(classes=["pss-activity-outline"])
        container["pss:target"] = activity.qualname
        if activity.inherited_from:
            container += nodes.paragraph(
                "", "", nodes.Text("Inherited from "), self.ref(activity.inherited_from)
            )
        if len(activity.blocks) == 1:
            container += self.items(activity.blocks[0].children)
            return container
        # Several blocks run as if in a schedule (design 3.4).
        top = nodes.bullet_list()
        head = self.item([nodes.Text("schedule (every activity block)")])
        blocks = nodes.bullet_list()
        for block in activity.blocks:
            where = f"{display_path(self.env, block.source.path)}:{block.source.line}" if block.source else ""
            title = f"activity (extend, {where})" if block.is_extension else "activity"
            item = self.item([nodes.Text(title)])
            item += self.items(block.children)
            blocks += item
        head += blocks
        top += head
        container += top
        return container

    def items(self, children: list) -> nodes.bullet_list:
        out = nodes.bullet_list()
        for child in children:
            out += self.node(child)
        return out

    def body(self, node: a.Node) -> nodes.bullet_list:
        """The items of an arm's or a loop's body: a braced body's statements, unwrapped."""
        if isinstance(node, a.Sequence) and not node.label:
            return self.items(node.children)
        return self.items([node])

    def item(self, content: list[nodes.Node], label: str | None = None) -> nodes.list_item:
        para = nodes.paragraph()
        if label:
            para += nodes.literal(text=f"{label}:")
            para += nodes.Text(" ")
        para.extend(content)
        return nodes.list_item("", para)

    def node(self, node: a.Node) -> nodes.list_item:
        label = getattr(node, "label", None)
        if isinstance(node, a.Traversal):
            content: list[nodes.Node] = []
            if node.handle:
                content.append(nodes.literal(text=node.handle))
                content.append(nodes.Text(" : "))
            elif node.is_abstract:
                content.append(nodes.Text("any "))
            content.append(self.ref(node.target) if node.target else nodes.literal(text=node.written))
            if node.with_text:
                content.append(nodes.Text(" with "))
                content.append(nodes.literal(text="{ " + node.with_text + " }"))
            return self.item(content, label)
        if isinstance(node, a.Sequence):
            # Only a branch of a parallel or a labeled block gets here: bodies
            # are unwrapped by `body`.
            item = self.item([nodes.Text("sequence")], label)
            item += self.items(node.children)
            return item
        if isinstance(node, (a.Parallel, a.Schedule)):
            text = "parallel" if isinstance(node, a.Parallel) else "schedule (an order the tool chooses)"
            content = [nodes.Text(text)]
            if node.join.text:
                content += [nodes.Text(", "), nodes.literal(text=node.join.text)]
            item = self.item(content, label)
            children = self.items(node.children)
            for sc in getattr(node, "constraints", []):
                names = ", ".join(sc.targets)
                relation = "in parallel" if sc.is_parallel else "in that order"
                children += self.item([nodes.Text("constraint: "), nodes.literal(text=names), nodes.Text(f" {relation}")])
            item += children
            return item
        if isinstance(node, a.Select):
            item = self.item([nodes.Text("select one of")], label)
            arms = nodes.bullet_list()
            for arm in node.arms:
                content = [nodes.Text("branch")]
                if arm.guard:
                    content += [nodes.Text(" if "), nodes.literal(text=arm.guard)]
                if self.weights and arm.weight:
                    content += [nodes.Text(" (weight "), nodes.literal(text=arm.weight), nodes.Text(")")]
                arm_item = self.item(content)
                arm_item += self.body(arm.body)
                arms += arm_item
            item += arms
            return item
        if isinstance(node, a.IfElse):
            item = self.item([nodes.Text("if "), nodes.literal(text=node.cond)], label)
            arms = nodes.bullet_list()
            then = self.item([nodes.Text("then")])
            then += self.body(node.then)
            arms += then
            if node.otherwise is not None:
                other = self.item([nodes.Text("else")])
                other += self.body(node.otherwise)
                arms += other
            item += arms
            return item
        if isinstance(node, a.Match):
            item = self.item([nodes.Text("match "), nodes.literal(text=node.expr)], label)
            arms = nodes.bullet_list()
            for arm in node.arms:
                arm_item = self.item([nodes.Text("default")] if arm.is_default else [nodes.literal(text=arm.guard or "")])
                arm_item += self.body(arm.body)
                arms += arm_item
            item += arms
            return item
        if isinstance(node, (a.Loop, a.Replicate, a.Atomic)):
            item = self.item(self.region_text(node), label)
            item += self.body(node.body)
            return item
        if isinstance(node, a.Super):
            content = [nodes.Text("super")]
            if node.base:
                content += [nodes.Text(" ("), self.ref(node.base), nodes.Text(")")]
            return self.item(content, label)
        if isinstance(node, a.Bind):
            return self.item([nodes.Text("bind "), nodes.literal(text=" ".join([node.lhs, *node.rhs]))], label)
        if isinstance(node, a.Constraint):
            return self.item([nodes.Text("constraint "), nodes.literal(text="{ " + node.text + " }")], label)
        if isinstance(node, a.StepRegion):
            item = self.item(
                [nodes.strong(text=node.number), nodes.Text(" "), nodes.Text(plain_text(node.title))]
            )
            item["classes"].append("pss-activity-step")
            item += self.items(node.children)
            return item
        return self.item([nodes.Text(f"(a {node.node_type} statement sphinx-pss doesn't show)")], label)

    def region_text(self, node: Any) -> list[nodes.Node]:
        if isinstance(node, a.Atomic):
            return [nodes.Text("atomic")]
        if isinstance(node, a.Replicate):
            var = f"{node.index} : " if node.index else ""
            return [nodes.Text("replicate "), nodes.literal(text=f"({var}{node.count})"), nodes.Text(", in parallel")]
        var = f"{node.variable} : " if node.variable else ""
        if node.kind == "repeat_while":
            return [nodes.Text("repeat while "), nodes.literal(text=node.header)]
        if node.kind == "foreach":
            return [nodes.Text("foreach "), nodes.literal(text=f"({var}{node.header})")]
        return [nodes.Text("repeat "), nodes.literal(text=f"({var}{node.header})")]

    def ref(self, qualname: str) -> nodes.Node:
        """The action's short name, linked to its entry when a page documents it."""
        xref = addnodes.pending_xref(
            "",
            nodes.literal(text=qualname.rsplit("::", 1)[-1]),
            refdomain="pss",
            reftype="action",
            reftarget=qualname,
            refspecific=True,
            **{"pss:scope": "", GENERATED_REF: True},
        )
        xref["refwarn"] = False
        return xref


class PssActivityDiagramDirective(SphinxDirective):
    """``.. pss:activity-diagram:: <action>``: the activity of one action (design 7.1)."""

    has_content = False
    required_arguments = 1
    optional_arguments = 0
    final_argument_whitespace = False
    option_spec = dict(ACTIVITY_OPTIONS)

    def run(self) -> list[nodes.Node]:
        return render_activity(self, self.arguments[0].strip(), self.options)


def setup(app) -> None:
    app.add_directive_to_domain("pss", "activity-diagram", PssActivityDiagramDirective)
