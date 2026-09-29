#****************************************************************************
#* diagrams.py
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
"""The shared diagram back-end (implementation plan ``P2-IMPL-5``).

A diagram kind lowers to a `sphinx_pss.model.graph.Graph`; this module draws
it with the back-end ``pss_diagrams`` names:

- ``graphviz``, the default, through ``sphinx.ext.graphviz``, which ships with
  Sphinx and is loaded with this extension. It needs Graphviz's ``dot``.
- ``mermaid`` (``flowchart TD``) through ``sphinxcontrib-mermaid``, which
  renders in the browser, so a host with no ``dot`` can still draw diagrams.
  The project has to add ``sphinxcontrib.mermaid`` to its extensions.
- ``off`` draws nothing.

A back-end that can't draw is **one warning per build** (``pss.diagrams``),
given when a page first asks for a diagram, and the diagram is left out: a
missing ``dot`` never fails a build on its own.

Links are resolved when the page is written, not when it is read: a diagram
can link to an object documented on a page that hasn't been read yet. The
directive leaves a `pss_diagram` node holding the graph, and `resolve_diagrams`
replaces it with the back-end's node once every object is known.
"""

from __future__ import annotations

import posixpath
import shutil
import textwrap
from typing import Any

from docutils import nodes
from sphinx.util import logging

from ..model.graph import UNLABELLED_SHAPES, Graph

logger = logging.getLogger(__name__)

#: The Graphviz shape attributes for each `Graph` shape.
_DOT_SHAPES = {
    "terminal": 'shape=box, style="rounded"',
    "process": "shape=box",
    "decision": "shape=diamond",
    "loop": "shape=hexagon",
    "subroutine": "shape=box, peripheries=2",
    "action": 'shape=box, style="rounded"',
    "initial": "shape=circle, style=filled, fillcolor=black, width=0.2, fixedsize=true",
    "final": "shape=doublecircle, style=filled, fillcolor=black, width=0.15, fixedsize=true",
    "flow_final": "shape=circle, width=0.25, fixedsize=true",
    "bar": "shape=box, style=filled, fillcolor=black, height=0.05, width=1.5, fixedsize=true, ordering=out",
    "hollow_bar": "shape=box, height=0.08, width=1.5, fixedsize=true, ordering=out",
    "merge": "shape=diamond, width=0.25, height=0.25, fixedsize=true",
    "note": "shape=note",
    "parameter": "shape=box",
}

#: The Graphviz attributes of each edge style.
_DOT_EDGE_STYLES = {
    "control": [],
    # Object flows and constraints relate nodes already placed by control
    # flow: they mustn't move them.
    "object": ["style=dashed", "constraint=false"],
    "constraint": ["style=dotted", "constraint=false"],
    # Drawn beside its node: both ends share a rank (see `to_dot`).
    "anchor": ["style=dotted"],
}

#: The Graphviz attributes of each cluster kind.
_DOT_CLUSTER_STYLES = {
    "region": 'style="rounded,dashed"',
    # Semi-transparent, so it reads on a light page and a dark one.
    "step": 'style="rounded,filled"; fillcolor="#80808020"',
}

#: Mermaid's node delimiters for each shape.
_MERMAID_SHAPES = {
    "terminal": ("([", "])"),
    "process": ("[", "]"),
    "decision": ("{", "}"),
    "loop": ("{{", "}}"),
    "subroutine": ("[[", "]]"),
    "action": ("(", ")"),
    "initial": ("((", "))"),
    "final": ("(((", ")))"),
    "flow_final": ("((", "))"),
    "bar": ("[", "]"),
    "hollow_bar": ("[", "]"),
    "merge": ("{", "}"),
    "note": (">", "]"),
    "parameter": ("[", "]"),
}

#: Mermaid ``style`` lines for the shapes it has no drawing of.
_MERMAID_STYLES = {
    "initial": "fill:#000,stroke:#000",
    "final": "fill:#000,stroke:#000",
    "bar": "fill:#000,stroke:#000",
    "hollow_bar": "fill:#fff,stroke:#000",
}

#: Characters per label line. Diamonds grow with the square of their text, so
#: they wrap sooner.
_WRAP = 32
_WRAP_DECISION = 22

#: Per build (keyed by source directory): whether each back-end can draw, and
#: what was already reported.
_STATE: dict[str, dict[str, Any]] = {}


class pss_diagram(nodes.General, nodes.Element):
    """A diagram waiting for its links: replaced by `resolve_diagrams`.

    Holds the `Graph` in ``graph``, the back-end in ``backend`` and the
    alternative text in ``alt``.
    """


def start_build(app) -> None:
    """Note which back-ends can draw; called when a build starts."""
    _STATE[str(app.srcdir)] = {
        "mermaid": "sphinxcontrib.mermaid" in app.extensions,
        "reported": set(),
    }


def backend(env, location: Any) -> str | None:
    """The back-end that will draw a diagram, or None to leave it out.

    ``location`` is where the first warning goes when the configured back-end
    can't draw; a ``pss_diagrams = "off"`` build says nothing.
    """
    choice = env.config.pss_diagrams
    if choice == "off":
        return None
    state = _STATE.setdefault(str(env.srcdir), {"mermaid": False, "reported": set()})
    if choice == "graphviz":
        dot = env.config.graphviz_dot
        if "dot" not in state:
            state["dot"] = shutil.which(dot) is not None
        if state["dot"]:
            return "graphviz"
        problem = (
            f"Graphviz's {dot!r} command was not found (graphviz_dot), so diagrams are "
            "left out. Install Graphviz, or set pss_diagrams = 'mermaid' or 'off'"
        )
    else:
        if state["mermaid"]:
            return "mermaid"
        problem = (
            "pss_diagrams is 'mermaid', but sphinxcontrib-mermaid isn't loaded, so "
            "diagrams are left out. Install it and add 'sphinxcontrib.mermaid' to "
            "extensions in conf.py"
        )
    if choice not in state["reported"]:
        state["reported"].add(choice)
        logger.warning(f"sphinx-pss: {problem}", location=location, type="pss", subtype="diagrams")
    return None


def diagram_node(graph: Graph, backend_name: str, alt: str, *, classes: list[str] | None = None) -> pss_diagram:
    """A diagram of ``graph`` for ``backend_name``; ``alt`` describes it for readers who can't see it."""
    node = pss_diagram()
    node["graph"] = graph
    node["backend"] = backend_name
    node["alt"] = alt
    node["classes"] = ["pss-diagram", *(classes or [])]
    return node


# --- text ---------------------------------------------------------------------------


def _lines(label: str, width: int) -> list[str]:
    return textwrap.wrap(label, width, break_long_words=False, break_on_hyphens=False) or [""]


def _dot_string(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _dot_label(label: str, width: int) -> str:
    escaped = [line.replace("\\", "\\\\").replace('"', '\\"') for line in _lines(label, width)]
    return '"' + "\\n".join(escaped) + '"'


def to_dot(graph: Graph, urls: dict[str, str] | None = None) -> str:
    """``graph`` in Graphviz's dot language. ``urls`` maps a link to its URL."""
    urls = urls or {}
    out = [
        "digraph pss {",
        '    graph [rankdir=TB, fontname="sans-serif", fontsize=10, nodesep=0.3, ranksep=0.3];',
        '    node [fontname="sans-serif", fontsize=10, margin="0.15,0.05"];',
        '    edge [fontname="sans-serif", fontsize=9];',
    ]

    def node_line(n, indent: str) -> str:
        width = _WRAP_DECISION if n.shape == "decision" else _WRAP
        if n.shape in UNLABELLED_SHAPES:
            # A bar's label is its join specification, written beside it.
            attrs = ['label=""', _DOT_SHAPES[n.shape]]
            if n.label:
                attrs.append(f"xlabel={_dot_label(n.label, width)}")
        else:
            attrs = [f"label={_dot_label(n.label, width)}", _DOT_SHAPES[n.shape]]
        if n.link and n.link in urls:
            attrs.append(f"URL={_dot_string(urls[n.link])}")
            attrs.append('target="_top"')
        if n.tooltip:
            attrs.append(f"tooltip={_dot_string(n.tooltip)}")
        return f"{indent}{n.id} [{', '.join(attrs)}];"

    def emit(cluster_id: str | None, indent: str) -> None:
        for c in graph.clusters:
            if c.parent != cluster_id:
                continue
            out.append(f"{indent}subgraph cluster_{c.id} {{")
            inner = indent + "    "
            out.append(f"{inner}label={_dot_label(c.label, _WRAP)}; {_DOT_CLUSTER_STYLES[c.kind]}; fontsize=9;")
            if c.link and c.link in urls:
                out.append(f'{inner}URL={_dot_string(urls[c.link])}; target="_top";')
            if c.tooltip:
                out.append(f"{inner}tooltip={_dot_string(c.tooltip)};")
            emit(c.id, inner)
            out.append(f"{indent}}}")
        for n in graph.nodes:
            if n.cluster == cluster_id:
                out.append(node_line(n, indent))

    emit(None, "    ")
    for e in graph.edges:
        attrs = []
        if e.label:
            attrs.append(f"label={_dot_string(e.label)}")
        if e.back:
            attrs.append("constraint=false")
        attrs.extend(_DOT_EDGE_STYLES[e.style])
        if not e.directed:
            attrs.append("dir=none")
        suffix = f" [{', '.join(attrs)}]" if attrs else ""
        out.append(f"    {e.src} -> {e.dst}{suffix};")
    for e in graph.edges:
        if e.style == "anchor":
            out.append(f"    {{ rank=same; {e.src}; {e.dst}; }}")
    out.append("}")
    return "\n".join(out) + "\n"


def _mermaid_text(text: str) -> str:
    """``text`` for a quoted Mermaid label: markup characters as entity codes."""
    text = text.replace("#", "#35;")
    for ch, code in (('"', "#34;"), ("<", "#60;"), (">", "#62;"), ("&", "#38;")):
        text = text.replace(ch, code)
    return text


def _mermaid_label(label: str, width: int) -> str:
    return '"' + "<br/>".join(_mermaid_text(line) for line in _lines(label, width)) + '"'


def to_mermaid(graph: Graph, urls: dict[str, str] | None = None) -> str:
    """``graph`` as a Mermaid ``flowchart TD``. ``urls`` maps a link to its URL."""
    urls = urls or {}
    out = ["flowchart TD"]

    def emit(cluster_id: str | None, indent: str) -> None:
        for c in graph.clusters:
            if c.parent != cluster_id:
                continue
            out.append(f"{indent}subgraph {c.id}[{_mermaid_label(c.label, _WRAP)}]")
            emit(c.id, indent + "    ")
            out.append(f"{indent}end")
        for n in graph.nodes:
            if n.cluster == cluster_id:
                width = _WRAP_DECISION if n.shape == "decision" else _WRAP
                opening, closing = _MERMAID_SHAPES[n.shape]
                # Mermaid draws no node without text: a space stands in.
                label = _mermaid_label(n.label, width) if n.label else '" "'
                out.append(f"{indent}{n.id}{opening}{label}{closing}")

    emit(None, "    ")
    for e in graph.edges:
        if e.style == "control":
            arrow = "-->"
        else:
            arrow = "-.->" if e.directed and e.style != "anchor" else "-.-"
        if e.label:
            arrow = f'{arrow}|"{_mermaid_text(e.label)}"|'
        out.append(f"    {e.src} {arrow} {e.dst}")
    for n in graph.nodes:
        if n.shape in _MERMAID_STYLES:
            out.append(f"    style {n.id} {_MERMAID_STYLES[n.shape]}")
    for c in graph.clusters:
        if c.kind == "step":
            out.append(f"    style {c.id} fill:#80808020")
    for n in graph.nodes:
        if n.link and n.link in urls:
            # A URL is taken as written: entity codes would break its fragment.
            url = urls[n.link].replace('"', "%22")
            tip = ' "' + n.tooltip.replace('"', "'") + '"' if n.tooltip else ""
            out.append(f'    click {n.id} href "{url}"{tip}')
    return "\n".join(out) + "\n"


# --- writing ---------------------------------------------------------------------------


def resolve_diagrams(app, doctree: nodes.document, docname: str) -> None:
    """Turn each `pss_diagram` into the back-end's node, with its links resolved.

    Connected to ``doctree-resolved``, when every object in the project has
    its page.
    """
    for node in list(doctree.findall(pss_diagram)):
        graph: Graph = node["graph"]
        urls = _urls(app, graph, docname) if app.builder.format == "html" else {}
        if node["backend"] == "mermaid":
            from sphinxcontrib.mermaid import mermaid

            new = mermaid()
            new["code"] = to_mermaid(graph, urls)
            new["options"] = {}
        else:
            from sphinx.ext.graphviz import graphviz

            new = graphviz()
            new["code"] = to_dot(graph, urls)
            new["options"] = {"docname": docname}
        new["alt"] = node["alt"]
        new["classes"] = list(node["classes"])
        node.replace_self(new)


def _urls(app, graph: Graph, fromdoc: str) -> dict[str, str]:
    """Each link's URL, relative to ``fromdoc``, for the objects a page documents."""
    domain = app.env.get_domain("pss")
    builder = app.builder
    found = {}
    for qualname in graph.links():
        entry = domain.objects.get(qualname)
        if entry is None:
            continue
        docname, node_id, _ = entry
        # Never a bare fragment: a Graphviz SVG is its own file, and
        # sphinx.ext.graphviz rebases its links as paths from the page.
        uri = builder.get_relative_uri(fromdoc, docname) or posixpath.basename(builder.get_target_uri(docname))
        found[qualname] = f"{uri}#{node_id}"
    return found


def setup(app) -> None:
    app.setup_extension("sphinx.ext.graphviz")
    app.add_node(pss_diagram)
    app.connect("doctree-resolved", resolve_diagrams)
    app.connect("builder-inited", start_build)
