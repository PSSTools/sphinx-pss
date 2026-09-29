#****************************************************************************
#* steps_flowchart.py
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
"""A `StepsDoc` as a flowchart `Graph` (steps design section 7.3).

- A step is a box with its number and title. Detail text is not drawn.
- An ``if`` chain is a diamond per condition: "yes" into the arm, "no" on to
  the next condition. A ``match`` is one diamond with an edge per choice.
- ``while`` tests before its body and ``repeat … while`` after it; both are a
  diamond with a back-edge. A count or ``foreach`` loop is a hexagon, the
  flowchart symbol for a loop limit, with a back-edge from the end of the body
  and a "done" edge out.
- An inline call is a cluster labelled with the callee; a linked or cut call
  is one box, drawn as a predefined process, that links to the callee.
- The blocks an ``extend`` adds are clusters.

Each construct is lowered to the edges still waiting for a successor (its
*exits*, each with its label), and the next construct connects them to its
entry. So an arm with no steps is an edge straight past it, and there is no
join node to draw.
"""

from __future__ import annotations

import os
import re
from typing import Callable

from .graph import Cluster, Graph, GraphNode
from .objects import SourceRef
from .steps import Branch, CallExpansion, ExtensionGroup, Loop, Step, StepsDoc

#: An edge that still needs a successor: where it starts, and its label.
Exit = tuple[GraphNode, str]


def default_source(ref: SourceRef) -> str:
    return f"{os.path.basename(ref.path)}:{ref.line}"


def steps_flowchart(doc: StepsDoc, describe_source: Callable[[SourceRef], str] = default_source) -> Graph:
    """The flowchart of ``doc``. ``describe_source`` gives each node's hover text."""
    return _Lowering(doc, describe_source).run()


class _Entry(GraphNode):
    """A stand-in source for the start of a body whose entry isn't known yet.

    Connecting from it records the node the body starts at, instead of adding
    an edge; ``repeat … while`` needs that node for its back-edge.
    """

    def __init__(self) -> None:
        super().__init__("", "", "process")
        self.targets: list[GraphNode] = []


class _Lowering:
    def __init__(self, doc: StepsDoc, describe_source: Callable[[SourceRef], str]) -> None:
        self.doc = doc
        self.describe = describe_source
        title = f"the steps of {doc.target}"
        if doc.exec_kind:
            title = f"the steps of 'exec {doc.exec_kind}' of {doc.target}"
        self.graph = Graph(title)

    def run(self) -> Graph:
        start = self.graph.add_node("Start", "terminal")
        exits: list[Exit] = [(start, "")]
        for group in self.doc.groups:
            exits = self.group(group, exits)
        end = self.graph.add_node("End", "terminal")
        self.connect(exits, end)
        return self.graph

    # --- helpers ----------------------------------------------------------------

    def node(self, label: str, shape: str, cluster: Cluster | None, source: SourceRef | None, **kwargs) -> GraphNode:
        return self.graph.add_node(
            label,
            shape,
            cluster=cluster.id if cluster else None,
            tooltip=self.describe(source) if source else "",
            **kwargs,
        )

    def connect(self, exits: list[Exit], target: GraphNode, *, back: bool = False) -> None:
        for src, label in exits:
            if isinstance(src, _Entry):
                src.targets.append(target)
            else:
                self.graph.add_edge(src, target, label, back=back)

    # --- constructs ---------------------------------------------------------------

    def group(self, group: ExtensionGroup, exits: list[Exit]) -> list[Exit]:
        cluster = None
        if group.is_extension:
            cluster = self.graph.add_cluster(
                "Added by an extension",
                tooltip=self.describe(group.source) if group.source else "",
            )
        return self.seq(group.children, exits, cluster)

    def seq(self, children: list, exits: list[Exit], cluster: Cluster | None) -> list[Exit]:
        for child in children:
            if isinstance(child, Step):
                exits = self.step(child, exits, cluster)
            elif isinstance(child, Branch):
                exits = self.branch(child, exits, cluster)
            elif isinstance(child, Loop):
                exits = self.loop(child, exits, cluster)
            elif isinstance(child, CallExpansion):
                exits = self.call(child, exits, cluster)
        return exits

    def step(self, step: Step, exits: list[Exit], cluster: Cluster | None) -> list[Exit]:
        label = plain_text(step.title)
        if step.number:
            label = f"{step.number} {label}"
        box = self.node(label, "process", cluster, step.source)
        self.connect(exits, box)
        return self.seq(step.children, [(box, "")], cluster)

    def branch(self, branch: Branch, exits: list[Exit], cluster: Cluster | None) -> list[Exit]:
        out: list[Exit] = []
        if branch.kind == "match":
            diamond = self.node(branch.label or "…", "decision", cluster, branch.source)
            self.connect(exits, diamond)
            for arm in branch.arms:
                label = "otherwise" if arm.kind == "default" else _choice(arm.label)
                out += self.seq(arm.children, [(diamond, label)], cluster)
            return out

        pending = exits
        for arm in branch.arms:
            if arm.kind == "else":
                out += self.seq(arm.children, pending, cluster)
                pending = []
                continue
            diamond = self.node(arm.label or "…", "decision", cluster, arm.source or branch.source)
            self.connect(pending, diamond)
            out += self.seq(arm.children, [(diamond, "yes")], cluster)
            pending = [(diamond, "no")]
        return out + pending

    def loop(self, loop: Loop, exits: list[Exit], cluster: Cluster | None) -> list[Exit]:
        if loop.kind == "while":
            diamond = self.node(loop.label or "…", "decision", cluster, loop.source)
            self.connect(exits, diamond)
            body = self.seq(loop.children, [(diamond, "yes")], cluster)
            self.connect(body, diamond, back=True)
            return [(diamond, "no")]

        if loop.kind == "repeat_while":
            entry = _Entry()
            mark = len(self.graph.edges)
            body = self.seq(loop.children, [(entry, "")], cluster)
            diamond = self.node(loop.label or "…", "decision", cluster, loop.source)
            self.connect(body, diamond)
            if not entry.targets:
                # Nothing drawn in the body: the test repeats on its own.
                entry.targets.append(diamond)
            first = entry.targets[0]
            # The way in is known only now; it goes before the body's edges,
            # so the text reads in the order the loop runs.
            after = self.graph.edges[mark:]
            del self.graph.edges[mark:]
            self.connect(exits, first)
            self.graph.edges.extend(after)
            self.graph.add_edge(diamond, first, "yes", back=True)
            return [(diamond, "no")]

        if loop.kind == "repeat_count":
            label = f"Repeat {loop.label} times"
        elif loop.variable:
            label = f"For each {loop.variable} in {loop.label}"
        else:
            label = f"For each element of {loop.label}"
        header = self.node(label, "loop", cluster, loop.source)
        self.connect(exits, header)
        body = self.seq(loop.children, [(header, "")], cluster)
        self.connect(body, header, back=True)
        return [(header, "done")]

    def call(self, call: CallExpansion, exits: list[Exit], cluster: Cluster | None) -> list[Exit]:
        short = call.callee.rsplit("::", 1)[-1]
        if call.mode == "inline":
            if not call.children:
                return exits
            inner = self.graph.add_cluster(
                short,
                parent=cluster.id if cluster else None,
                link=call.callee,
                tooltip=self.describe(call.source) if call.source else "",
            )
            return self.seq(call.children, exits, inner)
        if call.mode == "link":
            label = f"Follow the steps of {short}"
        else:
            label = f"Repeat from step {call.see} ({short})"
        box = self.node(label, "subroutine", cluster, call.source, link=call.callee)
        self.connect(exits, box)
        return [(box, "")]


def _choice(label: str) -> str:
    label = label.strip()
    if label.startswith("[") and label.endswith("]"):
        label = label[1:-1].strip()
    return label


_ROLE = re.compile(r":[\w.+-]+(?::[\w.+-]+)*:`((?:[^`\\]|\\.)*)`")
_LITERAL = re.compile(r"``(.+?)``")
_STRONG = re.compile(r"\*\*(.+?)\*\*")
_EMPHASIS = re.compile(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])")
_INTERPRETED = re.compile(r"`((?:[^`\\]|\\.)+)`_{0,2}")
_ESCAPE = re.compile(r"\\(.)")


def plain_text(title: str) -> str:
    """A step title's inline reStructuredText as the text a reader sees.

    A diagram label is plain text, so markup is dropped rather than drawn:
    ``:pss:func:`init_miim``` is ``init_miim``, ``*now*`` is ``now``.
    """

    def role(match: re.Match) -> str:
        text = match.group(1)
        explicit = re.fullmatch(r"(.*?)\s*<[^<>]*>", text, re.S)
        if explicit:
            return explicit.group(1)
        if text.startswith("~"):
            # As Sphinx shows it: the last component only.
            return re.split(r"::|\.", text[1:])[-1]
        return text.lstrip("!")

    # Escaped characters are set aside, so no pattern below takes them as markup.
    text = _ESCAPE.sub(lambda m: f"\x00{ord(m.group(1))}\x00", title)
    text = _ROLE.sub(role, text)
    text = _LITERAL.sub(r"\1", text)
    text = _STRONG.sub(r"\1", text)
    text = _EMPHASIS.sub(r"\1", text)
    text = _INTERPRETED.sub(lambda m: re.sub(r"\s*<[^<>]*>$", "", m.group(1)), text)
    return re.sub("\x00(\\d+)\x00", lambda m: chr(int(m.group(1))), text)
