#****************************************************************************
#* graph.py
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
"""A diagram as data: nodes, edges and nested clusters, with no back-end in it.

Each diagram kind lowers to a `Graph` (flowcharts in `steps_flowchart`), and
`sphinx_pss.autodoc.diagrams` writes a `Graph` as Graphviz or Mermaid. Keeping
the two apart lets the lowering be tested without Sphinx or ``dot``, and gives
activity and flow diagrams the same back-end later.

Everything is kept in insertion order and identifiers are sequential, so the
same input always gives the same text: the output is part of the page, and a
rebuild must not change it.
"""

from __future__ import annotations

import dataclasses

#: Node shapes, named for what they mean rather than how a back-end draws them.
SHAPES = (
    "terminal",  # where the procedure starts or ends
    "process",  # a step
    "decision",  # a condition, with one edge out per outcome
    "loop",  # a count or foreach loop's header
    "subroutine",  # a call shown as one box: the callee's steps are elsewhere
)


@dataclasses.dataclass(eq=False)
class GraphNode:
    id: str
    label: str
    shape: str
    #: The `Cluster.id` the node is drawn in, if any.
    cluster: str | None = None
    #: The qualified name of the PSS object the node links to, resolved to a
    #: URL when the page is written.
    link: str | None = None
    #: Hover text: where the node comes from in the source.
    tooltip: str = ""


@dataclasses.dataclass(eq=False)
class GraphEdge:
    src: str
    dst: str
    label: str = ""
    #: A loop's edge back to its start. Back-ends keep it out of the ranking,
    #: so the diagram still reads top to bottom.
    back: bool = False


@dataclasses.dataclass(eq=False)
class Cluster:
    id: str
    label: str
    parent: str | None = None
    link: str | None = None
    tooltip: str = ""


@dataclasses.dataclass(eq=False)
class Graph:
    #: What the diagram shows, for alternative text.
    title: str
    nodes: list[GraphNode] = dataclasses.field(default_factory=list)
    edges: list[GraphEdge] = dataclasses.field(default_factory=list)
    clusters: list[Cluster] = dataclasses.field(default_factory=list)

    def add_node(self, label: str, shape: str, **kwargs) -> GraphNode:
        if shape not in SHAPES:
            raise ValueError(f"unknown node shape {shape!r}")
        node = GraphNode(f"n{len(self.nodes) + 1}", label, shape, **kwargs)
        self.nodes.append(node)
        return node

    def add_edge(self, src: GraphNode, dst: GraphNode, label: str = "", *, back: bool = False) -> GraphEdge:
        edge = GraphEdge(src.id, dst.id, label, back)
        self.edges.append(edge)
        return edge

    def add_cluster(self, label: str, **kwargs) -> Cluster:
        cluster = Cluster(f"c{len(self.clusters) + 1}", label, **kwargs)
        self.clusters.append(cluster)
        return cluster

    def node(self, node_id: str) -> GraphNode:
        return next(n for n in self.nodes if n.id == node_id)

    def links(self) -> list[str]:
        """Every object the diagram links to, once each, in order."""
        seen: dict[str, None] = {}
        for item in [*self.clusters, *self.nodes]:
            if item.link:
                seen.setdefault(item.link)
        return list(seen)
