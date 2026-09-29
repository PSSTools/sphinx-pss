#****************************************************************************
#* activity_steps.py
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
"""Programming steps in an activity (activity-diagrams design section 4).

`stepped` regroups an `Activity`'s statements into `StepRegion`\\ s, from the
step markers `sphinx_pss.model.activity` found on them. How far a marker
reaches depends on the block it is in (design 4.2):

- In a block whose statements run in order (the ``activity`` body,
  ``sequence``, and the braced bodies of ``if``, loops, ``replicate`` and
  ``atomic``), a step covers its statement up to the next marker in the
  block, as in a function.
- In ``parallel`` and ``schedule``, whose statements are concurrent
  branches, and in the arms of ``select`` and ``match``, which are
  alternatives, a step covers its own statement only (decision D1).

The rest is the procedural rule set (programming-steps design 4):
- several markers on one statement start several steps there, all but the
  last empty;
- a marker on a control statement titles it (``marked``);
- steps are numbered, 1, 1.1, 1.1.1, continuing across blocks, with control
  structure transparent;
- in an activity that has steps, a traversal outside every step is reported
  (``pss.step_prelude_call``), since the step table leaves it out.

A step's range is a run of statements in one block, so a region nests
properly inside the structure around it (design 4.3); the diagram relies on
that to draw steps as clusters.

`activity_steps` projects a stepped activity onto the step tree of
`sphinx_pss.model.steps`, for the step table of a compound action (design
4.4). Control structure is kept only where it holds steps. A traversal inside
a step expands like a call: into the traversed action's activity steps, or,
with ``expand_exec`` only (decision D3), into an atomic action's ``exec
body`` steps.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from . import activity as a
from .comments import CommentForm, doc_form, strip_markers
from .objects import SourceRef
from .parse import ParsedModel
from .steps import STEP_PRELUDE_CALL
from .steps_lint import StepIssue
from .steps_markers import MARKER_RE

__all__ = ["activity_steps", "has_steps", "stepped", "unread_marker"]

#: Statements a marker titles, rather than starts a range at (design 4.3).
_CONTROLS = (a.Parallel, a.Schedule, a.Select, a.IfElse, a.Match, a.Loop, a.Replicate, a.Atomic)


def stepped(model: ParsedModel, activity: a.Activity) -> a.Activity:
    """``activity`` with its statements grouped into numbered steps.

    Cached per activity. An activity with no markers comes back with the
    same statements. The copy's ``issues`` are the lifting issues plus the
    traversals outside every step.
    """
    cache = model.cached("activity_steps", dict)
    key = id(activity)
    if key not in cache or cache[key][0] is not activity:
        cache[key] = (activity, _Pass(model, activity).run())
    return cache[key][1]


def has_steps(activity: a.Activity) -> bool:
    return any(isinstance(n, a.StepRegion) for n in activity.nodes())


class _Pass:
    def __init__(self, model: ParsedModel, activity: a.Activity) -> None:
        self.model = model
        self.activity = activity

    def run(self) -> a.Activity:
        blocks = [
            dataclasses.replace(block, children=self.sequential(block.children, block))
            for block in self.activity.blocks
        ]
        out = dataclasses.replace(self.activity, blocks=blocks, issues=list(self.activity.issues))
        _number(out)
        if has_steps(out):
            out.issues += self.outside(out)
        return out

    # --- regrouping --------------------------------------------------------------

    def region(self, found: a.Found) -> a.StepRegion:
        comment, marker = found
        return a.StepRegion(
            title=marker.title,
            source=SourceRef(
                path=self.model.file_map.get(comment.fileid, f"<file {comment.fileid}>"),
                line=marker.line,
                fileid=comment.fileid,
            ),
            detail=marker.detail,
            detail_line=marker.detail_line,
        )

    def closing(self, scope: Any) -> list[a.StepRegion]:
        return [self.region(f) for f in self.activity.closing.get(id(scope), [])]

    def sequential(self, children: list, scope: Any) -> list:
        """A block whose statements run in order: a step reaches to the next marker."""
        out: list = []
        current: a.StepRegion | None = None
        for child in children:
            found = self.activity.markers.get(id(child), [])
            new = self.rebuild(child)
            out.extend(self.region(f) for f in found[:-1])
            if found:
                current = self.region(found[-1])
                current.marked = isinstance(child, _CONTROLS)
                out.append(current)
            (current.children if current is not None else out).append(new)
        return out + self.closing(scope)

    def concurrent(self, children: list, scope: Any) -> list:
        """Branches of a ``parallel`` or ``schedule``: a step covers its own branch only (D1)."""
        out: list = []
        for child in children:
            out.extend(self.wrapped(child))
        return out + self.closing(scope)

    def body(self, node: Any) -> Any:
        """A body that is one statement: an arm, a branch of ``if``, a loop's body."""
        if node is None:
            return None
        parts = self.wrapped(node)
        return parts[0] if len(parts) == 1 else a.Sequence(parts)

    def wrapped(self, node: Any) -> list:
        """``node``, rebuilt, inside the step its markers start, if any."""
        found = self.activity.markers.get(id(node), [])
        new = self.rebuild(node)
        if not found:
            return [new]
        last = self.region(found[-1])
        last.children = [new]
        last.marked = isinstance(node, _CONTROLS)
        return [self.region(f) for f in found[:-1]] + [last]

    def rebuild(self, node: Any) -> Any:
        """A copy of ``node`` whose blocks are regrouped. Leaves are shared."""
        if isinstance(node, a.Sequence):
            return dataclasses.replace(node, children=self.sequential(node.children, node))
        if isinstance(node, (a.Parallel, a.Schedule)):
            return dataclasses.replace(node, children=self.concurrent(node.children, node))
        if isinstance(node, (a.Select, a.Match)):
            arms = [dataclasses.replace(arm, body=self.body(arm.body)) for arm in node.arms]
            return dataclasses.replace(node, arms=arms)
        if isinstance(node, a.IfElse):
            return dataclasses.replace(node, then=self.body(node.then), otherwise=self.body(node.otherwise))
        if isinstance(node, (a.Loop, a.Replicate, a.Atomic)):
            return dataclasses.replace(node, body=self.body(node.body))
        return node

    # --- the prelude check -----------------------------------------------------------

    def outside(self, activity: a.Activity) -> list[StepIssue]:
        """A traversal outside every step (design 4.2), reported at its line."""
        issues: list[StepIssue] = []

        def walk(nodes: list) -> None:
            for node in nodes:
                if isinstance(node, a.StepRegion):
                    continue
                if isinstance(node, (a.Traversal, a.Super)) and node.source is not None:
                    name = "super" if isinstance(node, a.Super) else (node.handle or node.type_name)
                    issues.append(
                        StepIssue(
                            STEP_PRELUDE_CALL,
                            f"sphinx-pss: traversal of {name!r} is outside every step, so the step "
                            "table leaves it out: move it into a step, or mark a step above it",
                            node.source.path,
                            node.source.line,
                        )
                    )
                walk(a.children_of(node))

        for block in activity.blocks:
            walk(block.children)
        return issues


def _number(activity: a.Activity) -> None:
    """Number the steps: 1, 1.1, 1.1.1, continuing across blocks, controls transparent."""

    def level(nodes: list, parent: str) -> None:
        count = 0

        def visit(nodes: list) -> None:
            nonlocal count
            for node in nodes:
                if isinstance(node, a.StepRegion):
                    count += 1
                    node.number = f"{parent}.{count}" if parent else str(count)
                    level(node.children, node.number)
                else:
                    visit(a.children_of(node))

        visit(nodes)

    level([child for block in activity.blocks for child in block.children], "")


def unread_marker(model: ParsedModel, activity: a.Activity) -> SourceRef | None:
    """The first step marker written in ``activity``'s blocks, found in the source text.

    For a parser that attaches no comments to activity statements (design
    4.7): the markers are there, but the model can't see them, and the user
    should be told rather than left wondering.
    """
    from .calls import source_text

    text = source_text(model)
    for block in activity.blocks:
        if block.source is None or block.source.fileid < 0:
            continue
        ft = text.file(block.source.fileid)
        if ft is None:
            continue
        last = block.end_line or block.source.line
        for tok in ft.toks:
            if not tok.trivia or tok.line < block.source.line or tok.line > last:
                continue
            if doc_form(tok.text) is CommentForm.PLAIN or not tok.text.lstrip().startswith("/"):
                continue
            for i, line in enumerate(strip_markers(tok.text)):
                if MARKER_RE.match(line.strip()):
                    return SourceRef(block.source.path, tok.line + i, fileid=block.source.fileid)
    return None


# --- the step table of a compound action (design 4.4) ---------------------------------


def activity_steps(
    model: ParsedModel,
    target: str,
    *,
    expand_calls: str = "inline",
    depth: int | None = None,
    numbering: str = "decimal",
    expand_exec: bool = False,
    weights: bool = False,
) -> Any:
    """The numbered step tree of the compound action ``target``'s activity."""
    from .steps import ExtensionGroup, StepsDoc, number_steps

    activity = stepped(model, a.activity_for(model, target))
    projection = _Projection(model, expand_calls, depth, expand_exec, weights)
    groups = [ExtensionGroup(block.source, block.is_extension) for block in activity.blocks]
    # A cut back to this action refers to its first step, in the first group.
    projection.holders[target] = groups[0]
    projection.stack.append(target)
    for group, block in zip(groups, activity.blocks):
        group.children = projection.nodes(block.children)
    projection.stack.pop()
    doc = StepsDoc(target=target, exec_kind=None, groups=groups, activity=True)
    doc.issues = [i for i in activity.issues if i.code == STEP_PRELUDE_CALL]
    number_steps(doc, numbering)
    return doc


class _Projection:
    def __init__(self, model: ParsedModel, expand: str, depth: int | None, expand_exec: bool, weights: bool) -> None:
        self.model = model
        self.expand = expand
        self.depth = depth
        self.expand_exec = expand_exec
        self.weights = weights
        #: Actions being expanded, outermost first, and what holds each one's steps.
        self.stack: list[str] = []
        self.holders: dict[str, Any] = {}
        self.level = 0

    def nodes(self, nodes: list, in_step: bool = False) -> list:
        out = []
        for node in nodes:
            out.extend(self.node(node, in_step))
        return out

    def node(self, node: Any, in_step: bool) -> list:
        from . import steps as s

        if isinstance(node, a.StepRegion):
            step = s.Step(
                title=node.title,
                source=node.source,
                detail=node.detail,
                detail_line=node.detail_line,
            )
            step.children = self.nodes(node.children, True)
            if node.marked and step.children and hasattr(step.children[0], "marked"):
                step.children[0].marked = True
            return [step]
        if isinstance(node, a.Traversal):
            return self.traversal(node) if in_step else []
        if isinstance(node, a.Super):
            if not in_step or not node.has_activity or node.base is None:
                return []
            return self.expansion(node.base, node.source, "activity")
        if isinstance(node, a.Sequence):
            return self.nodes(node.children, in_step)
        if isinstance(node, (a.Parallel, a.Schedule, a.Replicate, a.Atomic)):
            children = self.nodes(a.children_of(node), in_step)
            if not children:
                return []
            if isinstance(node, a.Replicate):
                return [s.Group("replicate", node.source, children, label=node.count)]
            if isinstance(node, a.Atomic):
                return [s.Group("atomic", node.source, children)]
            constraints = tuple((c.is_parallel, c.targets) for c in getattr(node, "constraints", []))
            kind = "parallel" if isinstance(node, a.Parallel) else "schedule"
            return [s.Group(kind, node.source, children, label=node.join.text, constraints=constraints)]
        if isinstance(node, a.Select):
            arms = [
                s.Arm(
                    "select",
                    arm.guard or "",
                    self.nodes([arm.body], in_step),
                    weight=(arm.weight or "") if self.weights else "",
                )
                for arm in node.arms
            ]
            return [s.Branch("select", node.source, arms)] if any(arm.children for arm in arms) else []
        if isinstance(node, a.IfElse):
            arms = [s.Arm("if", node.cond, self.nodes([node.then], in_step))]
            if node.otherwise is not None:
                arms.append(s.Arm("else", "", self.nodes([node.otherwise], in_step)))
            return [s.Branch("if", node.source, arms)] if any(arm.children for arm in arms) else []
        if isinstance(node, a.Match):
            arms = [
                s.Arm("default" if arm.is_default else "choice", "" if arm.is_default else arm.guard or "", self.nodes([arm.body], in_step))
                for arm in node.arms
            ]
            if not any(arm.children for arm in arms):
                return []
            return [s.Branch("match", node.source, arms, label=node.expr)]
        if isinstance(node, a.Loop):
            children = self.nodes([node.body], in_step)
            return [s.Loop(node.kind, node.header, node.source, children, variable=node.variable)] if children else []
        return []

    # --- expansion -------------------------------------------------------------------

    def traversal(self, t: a.Traversal) -> list:
        if t.target is None or t.is_abstract:
            # The solver picks what an abstract type becomes: nothing to expand.
            return []
        if t.has_activity:
            return self.expansion(t.target, t.source, "activity")
        if self.expand_exec:
            return self.expansion(t.target, t.source, "exec")
        return []

    def expansion(self, target: str, source: SourceRef | None, what: str) -> list:
        from . import steps as s

        if self.expand == "none":
            return []
        children = None
        if target in self.stack:
            return [s.CallExpansion(target, source, mode="cut", target=self.holders.get(target))]
        if self.depth is not None and self.level >= self.depth:
            return []
        if what == "activity":
            activity = stepped(self.model, a.activity_for(self.model, target))
            if not has_steps(activity):
                return []
            if self.expand == "link":
                return [s.CallExpansion(target, source, mode="link")]
            node = s.CallExpansion(target, source)
            self.holders[target] = node
            self.stack.append(target)
            self.level += 1
            try:
                children = [c for block in activity.blocks for c in self.nodes(block.children)]
            finally:
                self.level -= 1
                self.stack.pop()
            node.children = children
            return [node]

        # An atomic action's exec body, only when asked for (D3).
        try:
            doc = s.steps_for(
                self.model,
                target,
                exec_kind="body",
                expand_calls=self.expand,
                depth=None if self.depth is None else self.depth - self.level - 1,
            )
        except s.StepsError:
            return []
        children = [c for group in doc.groups for c in group.children]
        if not any(isinstance(c, s.Step) for c in _all(children)):
            return []
        return [s.CallExpansion(target, source, mode="exec", children=children)]


def _all(nodes: list):
    for node in nodes:
        yield node
        yield from _all(getattr(node, "children", []))
