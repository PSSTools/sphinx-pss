#****************************************************************************
#* activity_diagram.py
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
"""An `Activity` as a UML activity diagram `Graph` (activity-diagrams design 5 and 6).

- The diagram starts at an initial node and ends at an activity final.
- A traversal is an action node, ``c1 : copy``, linked to the action type,
  with UML's rake (``⋔``) when the type has an activity of its own.
- ``parallel`` is a fork bar and a join bar; ``join_none`` has no join, and
  each branch ends in a flow final. ``schedule`` has hollow bars inside a
  cluster titled ``schedule``, so the two are never confused.
- ``select``, ``if`` and ``match`` are a decision and a merge.
- Loops, ``replicate`` and ``atomic`` are clusters titled with their header:
  UML draws them as structured nodes, not with back-edges.
- ``with`` constraints and activity-scope constraints are notes.
- ``bind`` is a dashed object flow between the nodes it names, or a line of
  the caption when it can't be placed.
- A programming step is a shaded cluster titled with its number and title
  (design 5.2); with ``steps="collapsed"`` each outermost step is one box.
  Steps of an inlined activity are numbered from its traversal, ``c1 › 2.1``.

Each construct is lowered to the edges still waiting for a successor (its
*exits*), and the next construct connects them to its entry, as step
flowcharts do; every construct has one entry and, except ``join_none``'s
branches, one way out.
"""

from __future__ import annotations

import os
from typing import Callable

from . import activity as a
from .activity_steps import stepped
from .graph import Cluster, Graph, GraphNode
from .objects import SourceRef
from .parse import ParsedModel

#: An edge that still needs a successor: where it starts, and its label.
Exit = tuple[GraphNode, str]

#: The deepest ``depth`` accepted (design 5.3).
MAX_DEPTH = 4

#: Longest ``with`` text drawn in a note; the full text is its hover text.
_NOTE_WIDTH = 60

#: How steps are drawn (design 5.2): as clusters, each outermost one as a
#: single box, or not at all.
STEP_MODES = ("regions", "collapsed", "none")


def default_source(ref: SourceRef) -> str:
    return f"{os.path.basename(ref.path)}:{ref.line}"


def activity_diagram(
    model: ParsedModel,
    activity: a.Activity,
    *,
    depth: int = 1,
    weights: bool = False,
    steps: str = "regions",
    describe_source: Callable[[SourceRef], str] = default_source,
) -> Graph:
    """The UML activity diagram of ``activity``.

    ``depth`` is how many levels of activity are drawn: 1 shows traversals
    as single nodes, and each level more opens the traversals of compound
    actions one level further. ``weights`` labels ``select`` arms with their
    weights. ``steps`` is one of `STEP_MODES`.
    """
    if not 1 <= depth <= MAX_DEPTH:
        raise a.ActivityError(f"depth must be from 1 to {MAX_DEPTH}, not {depth}")
    if steps not in STEP_MODES:
        raise a.ActivityError(f"unknown steps mode {steps!r}; expected one of: {', '.join(STEP_MODES)}")
    return _Lowering(model, depth, weights, steps, describe_source).run(activity)


class _Lowering:
    def __init__(
        self, model: ParsedModel, depth: int, weights: bool, steps: str, describe: Callable[[SourceRef], str]
    ) -> None:
        self.model = model
        self.depth = depth
        self.weights = weights
        self.steps = steps
        self.describe = describe
        #: Per activity being drawn: what its step numbers are prefixed with,
        #: and how many steps deep the lowering is.
        self.prefixes: list[str] = []
        self.step_depth: list[int] = []
        self.graph: Graph
        #: Actions being drawn, outermost first, for cutting recursion.
        self.stack: list[str] = []
        #: Per activity being drawn: action nodes by handle, and nodes by PSS label.
        self.handles: list[dict[str, list[GraphNode]]] = []
        self.labels: list[dict[str, GraphNode]] = []
        #: Per activity being drawn: its binds, placed once its nodes exist.
        self.binds: list[list[a.Bind]] = []

    def run(self, activity: a.Activity) -> Graph:
        self.graph = Graph(f"the activity of {activity.qualname}")
        if activity.inherited_from:
            self.graph.caption_notes.append(f"Inherited from {activity.inherited_from}")
        start = self.graph.add_node("", "initial")
        exits = self.activity(self.prepared(activity), [(start, "")], None, "")
        end = self.graph.add_node("", "final")
        self.connect(exits, end)
        return self.graph

    # --- helpers ----------------------------------------------------------------

    def node(self, label: str, shape: str, cluster: Cluster | None, source: SourceRef | None = None, **kwargs) -> GraphNode:
        return self.graph.add_node(
            label,
            shape,
            cluster=cluster.id if cluster else None,
            tooltip=kwargs.pop("tooltip", None) or (self.describe(source) if source else ""),
            **kwargs,
        )

    def cluster(self, label: str, parent: Cluster | None, source: SourceRef | None = None, **kwargs) -> Cluster:
        return self.graph.add_cluster(
            label,
            parent=parent.id if parent else None,
            tooltip=kwargs.pop("tooltip", None) or (self.describe(source) if source else ""),
            **kwargs,
        )

    def prepared(self, activity: a.Activity) -> a.Activity:
        """``activity`` with its steps, unless steps aren't drawn."""
        return activity if self.steps == "none" else stepped(self.model, activity)

    def connect(self, exits: list[Exit], target: GraphNode) -> None:
        for src, label in exits:
            self.graph.add_edge(src, target, label)

    def entry_of(self, mark: int) -> GraphNode | None:
        """The first node added since ``len(graph.nodes)`` was ``mark``: a construct's entry."""
        return self.graph.nodes[mark] if len(self.graph.nodes) > mark else None

    # --- an activity ----------------------------------------------------------------

    def activity(self, activity: a.Activity, exits: list[Exit], cluster: Cluster | None, prefix: str) -> list[Exit]:
        self.stack.append(activity.qualname)
        self.handles.append({})
        self.labels.append({})
        self.binds.append([])
        self.prefixes.append(prefix)
        self.step_depth.append(0)
        try:
            if len(activity.blocks) == 1:
                exits = self.seq(activity.blocks[0].children, exits, cluster)
            else:
                # LRM 11: several blocks run as if in a schedule (design 3.4).
                region = self.cluster("schedule", cluster)
                fork = self.node("", "hollow_bar", region)
                self.connect(exits, fork)
                ends: list[Exit] = []
                for block in activity.blocks:
                    where = self.describe(block.source) if block.source else ""
                    title = f"activity (extend, {where})" if block.is_extension else "activity"
                    inner = self.cluster(title, region, block.source)
                    ends += self.seq(block.children, [(fork, "")], inner)
                join = self.node("", "hollow_bar", region)
                self.connect(ends, join)
                exits = [(join, "")]
            self.place_binds()
        finally:
            self.stack.pop()
            self.handles.pop()
            self.labels.pop()
            self.binds.pop()
            self.prefixes.pop()
            self.step_depth.pop()
        return exits

    def seq(self, children: list, exits: list[Exit], cluster: Cluster | None) -> list[Exit]:
        for child in children:
            exits = self.lower(child, exits, cluster)
        return exits

    def lower(self, node: a.Node, exits: list[Exit], cluster: Cluster | None) -> list[Exit]:
        mark = len(self.graph.nodes)
        out = self._lower(node, exits, cluster)
        label = getattr(node, "label", None)
        entry = self.entry_of(mark)
        if label and entry is not None:
            self.labels[-1].setdefault(label, entry)
        return out

    def _lower(self, node: a.Node, exits: list[Exit], cluster: Cluster | None) -> list[Exit]:
        if isinstance(node, a.Traversal):
            return self.traversal(node, exits, cluster)
        if isinstance(node, a.Sequence):
            if node.label:
                cluster = self.cluster(node.label, cluster, node.source)
            return self.seq(node.children, exits, cluster)
        if isinstance(node, a.Parallel):
            return self.fork(node, exits, cluster, "bar")
        if isinstance(node, a.Schedule):
            region = self.cluster(_titled("schedule", node.label), cluster, node.source)
            out = self.fork(node, exits, region, "hollow_bar")
            self.scheduling_constraints(node)
            return out
        if isinstance(node, a.Select):
            arms = []
            for arm in node.arms:
                text = f"[{arm.guard}]" if arm.guard else ""
                if self.weights and arm.weight:
                    text = f"{text} ({arm.weight})".strip()
                arms.append((text, arm.body))
            return self.decision(_titled("select", node.label), arms, exits, cluster, node.source)
        if isinstance(node, a.IfElse):
            arms = [(f"[{node.cond}]", node.then), ("[else]", node.otherwise)]
            return self.decision(node.label or "", arms, exits, cluster, node.source)
        if isinstance(node, a.Match):
            arms = [("[default]" if arm.is_default else arm.guard or "", arm.body) for arm in node.arms]
            return self.decision(_titled(node.expr, node.label), arms, exits, cluster, node.source)
        if isinstance(node, a.Loop):
            return self.region(_loop_title(node), node.body, exits, cluster, node)
        if isinstance(node, a.Replicate):
            var = f"{node.index} : " if node.index else ""
            return self.region(f"«parallel» replicate ({var}{node.count})", node.body, exits, cluster, node)
        if isinstance(node, a.Atomic):
            return self.region("atomic", node.body, exits, cluster, node)
        if isinstance(node, a.Super):
            return self.super(node, exits, cluster)
        if isinstance(node, a.Bind):
            self.binds[-1].append(node)
            return exits
        if isinstance(node, a.Constraint):
            self.node("{" + _abbreviate(node.text) + "}", "note", cluster, node.source)
            return exits
        if isinstance(node, a.StepRegion):
            return self.step(node, exits, cluster)
        box = self.node(f"? {node.node_type}", "action", cluster, node.source)
        self.connect(exits, box)
        return [(box, "")]

    # --- constructs ---------------------------------------------------------------

    def step(self, region: a.StepRegion, exits: list[Exit], cluster: Cluster | None) -> list[Exit]:
        from .steps_flowchart import plain_text

        title = f"{self.prefixes[-1]}{region.number} {plain_text(region.title)}"
        where = self.describe(region.source)
        tooltip = "\n".join([where, *region.detail]).strip()
        if self.steps == "collapsed" and self.step_depth[-1] == 0:
            box = self.node(title, "process", cluster, region.source, tooltip=tooltip)
            self.connect(exits, box)
            return [(box, "")]
        if not region.children:
            # An empty step (pss.step_empty): nothing to draw around.
            return exits
        inner = self.cluster(title, cluster, region.source, kind="step", tooltip=tooltip)
        self.step_depth[-1] += 1
        try:
            return self.seq(region.children, exits, inner)
        finally:
            self.step_depth[-1] -= 1

    def traversal(self, t: a.Traversal, exits: list[Exit], cluster: Cluster | None) -> list[Exit]:
        name = f"«any» {t.type_name}" if t.is_abstract else t.type_name
        text = f"{t.handle} : {name}" if t.handle else name
        if t.label:
            text = f"{t.label}: {text}"
        opens = t.has_activity and t.target is not None and len(self.stack) < self.depth
        if opens and t.target not in self.stack:
            region = self.cluster(text, cluster, t.source, link=t.target)
            prefix = f"{self.prefixes[-1]}{t.handle or t.type_name} › "
            out = self.activity(self.prepared(a.activity_for(self.model, t.target)), exits, region, prefix)
            return self.with_note(t, out, region)
        if opens:
            text += " (recursive, see above)"
        elif t.has_activity:
            text += " ⋔"
        box = self.node(text, "action", cluster, t.source, link=t.target)
        self.connect(exits, box)
        if t.handle:
            self.handles[-1].setdefault(t.handle, []).append(box)
        self.with_note(t, [(box, "")], cluster, box)
        return [(box, "")]

    def with_note(self, t: a.Traversal, out: list[Exit], cluster: Cluster | None, box: GraphNode | None = None) -> list[Exit]:
        if t.with_text:
            note = self.node(
                "with {" + _abbreviate(t.with_text) + "}", "note", cluster, tooltip=f"with {{ {t.with_text} }}"
            )
            if box is not None:
                self.graph.add_edge(box, note, style="anchor", directed=False)
        return out

    def fork(self, node: a.Parallel | a.Schedule, exits: list[Exit], cluster: Cluster | None, bar: str) -> list[Exit]:
        if node.label and bar == "bar":
            cluster = self.cluster(node.label, cluster, node.source)
        fork = self.node("", bar, cluster, node.source)
        self.connect(exits, fork)
        if not node.children:
            return [(fork, "")]
        branches = [self.lower(child, [(fork, "")], cluster) for child in node.children]
        if node.join.kind == "none":
            # Nothing waits for the branches: each ends on its own, and what
            # follows starts as soon as they are started.
            for branch in branches:
                self.connect(branch, self.node("", "flow_final", cluster))
            return [(fork, "")]
        label = "" if node.join.kind == "all" else "{" + node.join.text + "}"
        join = self.node(label, bar, cluster)
        for branch in branches:
            self.connect(branch, join)
        return [(join, "")]

    def scheduling_constraints(self, node: a.Schedule) -> None:
        for sc in node.constraints:
            ends = [self.labels[-1].get(t) for t in sc.targets]
            if any(e is None for e in ends):
                continue
            kind = "parallel" if sc.is_parallel else "sequence"
            for src, dst in zip(ends, ends[1:]):
                self.graph.add_edge(src, dst, kind, style="constraint", directed=not sc.is_parallel)

    def decision(
        self,
        title: str,
        arms: list[tuple[str, a.Node | None]],
        exits: list[Exit],
        cluster: Cluster | None,
        source: SourceRef | None,
    ) -> list[Exit]:
        diamond = self.node(title, "decision", cluster, source)
        self.connect(exits, diamond)
        merge_exits: list[Exit] = []
        for text, body in arms:
            start = [(diamond, text)]
            merge_exits += self.lower(body, start, cluster) if body is not None else start
        merge = self.node("", "merge", cluster)
        self.connect(merge_exits, merge)
        return [(merge, "")]

    def region(self, title: str, body: a.Node, exits: list[Exit], cluster: Cluster | None, node: a.Node) -> list[Exit]:
        region = self.cluster(_titled(title, node.label), cluster, node.source)
        out = self.lower(body, exits, region)
        if out == exits:
            # An empty body: the region still needs something in it to be drawn.
            box = self.node("(empty)", "action", region)
            self.connect(exits, box)
            out = [(box, "")]
        return out

    def super(self, node: a.Super, exits: list[Exit], cluster: Cluster | None) -> list[Exit]:
        opens = node.has_activity and node.base is not None and len(self.stack) < self.depth
        if opens and node.base not in self.stack:
            short = node.base.rsplit("::", 1)[-1]
            region = self.cluster(f"super: {short}", cluster, node.source, link=node.base)
            prefix = f"{self.prefixes[-1]}super › "
            return self.activity(self.prepared(a.activity_for(self.model, node.base)), exits, region, prefix)
        text = "super ⋔" if node.has_activity else "super"
        box = self.node(text, "action", cluster, node.source, link=node.base)
        self.connect(exits, box)
        return [(box, "")]

    # --- binds ------------------------------------------------------------------------

    def place_binds(self) -> None:
        """Draw each ``bind`` of the activity being finished, or name it in the caption."""
        handles = self.handles[-1]
        parameters: dict[str, GraphNode] = {}
        for bind in self.binds[-1]:
            ends = []
            for path in [bind.lhs, *bind.rhs]:
                head = path.split(".", 1)[0]
                if head in handles:
                    found = handles[head]
                    ends.append(found[0] if len(found) == 1 else None)
                elif "." not in path:
                    # The context action's own field (design 5.1).
                    if path not in parameters:
                        parameters[path] = self.node(path, "parameter", None, bind.source)
                    ends.append(parameters[path])
                else:
                    ends.append(None)
            if any(e is None for e in ends):
                self.graph.caption_notes.append(f"Also bound: {' ↔ '.join([bind.lhs, *bind.rhs])}")
                continue
            lhs_field = _field(bind.lhs)
            for end, path in zip(ends[1:], bind.rhs):
                label = " ↔ ".join(f for f in (lhs_field, _field(path)) if f)
                self.graph.add_edge(ends[0], end, label, style="object", directed=False)


def _titled(title: str, label: str | None) -> str:
    return f"{label}: {title}" if label else title


def _loop_title(loop: a.Loop) -> str:
    var = f"{loop.variable} : " if loop.variable else ""
    if loop.kind == "repeat_while":
        return f"repeat … while ({loop.header})"
    if loop.kind == "foreach":
        return f"«iterative» foreach ({var}{loop.header})"
    return f"repeat ({var}{loop.header})"


def _abbreviate(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= _NOTE_WIDTH else text[: _NOTE_WIDTH - 1].rstrip() + "…"


def _field(path: str) -> str:
    """The field part of ``c1.src``; empty for a path with none."""
    return path.split(".", 1)[1] if "." in path else ""
