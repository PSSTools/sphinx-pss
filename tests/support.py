"""Helpers shared across test directories.

A plain module rather than ``conftest.py``: every directory's ``conftest`` is
importable as ``conftest``, so importing helpers from one is ambiguous.
"""

from __future__ import annotations

import dataclasses


def model_snapshot(index) -> list[dict]:
    """Everything the object model says about a parse, as plain data.

    Two parses that document identically produce equal snapshots. Used to show
    that a parser option changes nothing the documentation reads.
    """
    return [dataclasses.asdict(root) for root in index.roots] + [
        dataclasses.asdict(index.relations)
    ]




def steps_outline(doc) -> list[str]:
    """A step tree as indented lines, one per node, for comparing whole trees.

    ``3.1 Title @19`` is a step (number, title, marker line); ``if n > 0`` and
    ``else`` are arms; ``[while c]`` is a loop and ``[match e]`` a branch, with
    a ``*`` when a marker titles it; ``-> f`` is an inline call, ``-> f (link)``
    a linked one, and ``-> f (see 1)`` a cut; ``== extension @7`` a group added
    by an ``extend``.
    """
    from sphinx_pss.model.steps import Branch, CallExpansion, ExtensionGroup, Loop, Step

    out: list[str] = []

    def walk(nodes, depth: int) -> None:
        pad = "  " * depth
        for node in nodes:
            if isinstance(node, Step):
                out.append(f"{pad}{node.number} {node.title} @{node.source.line}")
                walk(node.children, depth + 1)
            elif isinstance(node, Branch):
                star = "*" if node.marked else ""
                if node.kind == "match":
                    out.append(f"{pad}[match {node.label}]{star}")
                    star = ""
                for arm in node.arms:
                    head = f"{arm.kind} {arm.label}".strip()
                    out.append(f"{pad}{head}{star}")
                    star = ""
                    walk(arm.children, depth + 1)
            elif isinstance(node, Loop):
                var = f"{node.variable} : " if node.variable else ""
                out.append(f"{pad}[{node.kind} {var}{node.label}]{'*' if node.marked else ''}")
                walk(node.children, depth + 1)
            elif isinstance(node, CallExpansion):
                tail = {"inline": "", "link": " (link)", "cut": f" (see {node.see})"}[node.mode]
                out.append(f"{pad}-> {node.callee}{tail}")
                walk(node.children, depth + 1)
            elif isinstance(node, ExtensionGroup):
                if node.is_extension:
                    out.append(f"{pad}== extension @{node.source.line}")
                walk(node.children, depth)

    walk(doc.groups, 0)
    return out
