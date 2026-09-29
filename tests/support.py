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
    by an ``extend``. In an activity, ``<parallel>`` is a group (``*`` when
    a marker titles it), ``[select]`` a ``select`` with its arms, and
    ``-> f (exec)`` an ``exec body`` expansion.
    """
    from sphinx_pss.model.steps import Branch, CallExpansion, ExtensionGroup, Group, Loop, Step

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
                tail = {"inline": "", "link": " (link)", "cut": f" (see {node.see})", "exec": " (exec)"}[node.mode]
                out.append(f"{pad}-> {node.callee}{tail}")
                walk(node.children, depth + 1)
            elif isinstance(node, Group):
                label = f" {node.label}" if node.label else ""
                out.append(f"{pad}<{node.kind}{label}>{'*' if node.marked else ''}")
                walk(node.children, depth + 1)
            elif isinstance(node, ExtensionGroup):
                if node.is_extension:
                    out.append(f"{pad}== extension @{node.source.line}")
                walk(node.children, depth)

    walk(doc.groups, 0)
    return out


def activity_outline(activity) -> list[str]:
    """An activity tree as indented lines, one per node, for comparing whole trees.

    ``c1 : copy`` is a handle traversal, ``do configure`` a type traversal
    (``*`` when abstract, ``⋔`` when the target has an activity, ``with {…}``
    when constrained); ``seq1: `` prefixes a label. Blocks are ``== block``
    or ``== extension``; arms are ``[guard] (weight)``, ``[0..3]`` or
    ``default``; ``# 2.1 Title @12`` is a step, with ``*`` when it titles a
    control statement.
    """
    from sphinx_pss.model import activity as a

    out: list[str] = []

    def line(depth: int, text: str, node) -> None:
        label = f"{node.label}: " if getattr(node, "label", None) else ""
        out.append(f"{'  ' * depth}{label}{text}")

    def walk(node, depth: int) -> None:
        if isinstance(node, a.Traversal):
            text = f"{node.handle} : {node.type_name}" if node.handle else f"do {node.type_name}"
            if node.target is None:
                text += " (unresolved)"
            if node.is_abstract:
                text += " *"
            if node.has_activity:
                text += " ⋔"
            if node.with_text:
                text += f" with {{{node.with_text}}}"
            line(depth, text, node)
        elif isinstance(node, a.Sequence):
            line(depth, "sequence", node)
            for c in node.children:
                walk(c, depth + 1)
        elif isinstance(node, (a.Parallel, a.Schedule)):
            head = "parallel" if isinstance(node, a.Parallel) else "schedule"
            if node.join.text:
                head += f" {node.join.kind}: {node.join.text}"
            line(depth, head, node)
            for c in node.children:
                walk(c, depth + 1)
            for sc in getattr(node, "constraints", []):
                kind = "parallel" if sc.is_parallel else "sequence"
                out.append(f"{'  ' * (depth + 1)}constraint {kind} {{{', '.join(sc.targets)}}}")
        elif isinstance(node, (a.Select, a.Match)):
            line(depth, "select" if isinstance(node, a.Select) else f"match {node.expr}", node)
            for arm in node.arms:
                if arm.is_default:
                    head = "default"
                else:
                    head = arm.guard if isinstance(node, a.Match) else f"[{arm.guard or ''}]"
                    if arm.weight:
                        head += f" ({arm.weight})"
                out.append(f"{'  ' * (depth + 1)}{head}")
                walk(arm.body, depth + 2)
        elif isinstance(node, a.IfElse):
            line(depth, f"if {node.cond}", node)
            walk(node.then, depth + 1)
            if node.otherwise is not None:
                out.append(f"{'  ' * depth}else")
                walk(node.otherwise, depth + 1)
        elif isinstance(node, a.Loop):
            var = f"{node.variable} : " if node.variable else ""
            line(depth, f"{node.kind} ({var}{node.header})", node)
            walk(node.body, depth + 1)
        elif isinstance(node, a.Replicate):
            var = f"{node.index} : " if node.index else ""
            line(depth, f"replicate ({var}{node.count})", node)
            walk(node.body, depth + 1)
        elif isinstance(node, a.Atomic):
            line(depth, "atomic", node)
            walk(node.body, depth + 1)
        elif isinstance(node, a.Super):
            line(depth, f"super -> {node.base}" + (" ⋔" if node.has_activity else ""), node)
        elif isinstance(node, a.Bind):
            line(depth, f"bind {node.lhs} {' '.join(node.rhs)}", node)
        elif isinstance(node, a.Constraint):
            line(depth, f"constraint {{{node.text}}}", node)
        elif isinstance(node, a.Unknown):
            line(depth, f"? {node.node_type}", node)
        elif isinstance(node, a.StepRegion):
            line(depth, f"# {node.number} {node.title}{' *' if node.marked else ''} @{node.source.line}", node)
            for c in node.children:
                walk(c, depth + 1)
        else:  # pragma: no cover - a node kind this helper doesn't know
            line(depth, f"?? {type(node).__name__}", node)

    for block in activity.blocks:
        out.append("== extension" if block.is_extension else "== block")
        for c in block.children:
            walk(c, 1)
    return out


def geometric_comments(model):
    """A stand-in for pssparser ``AC1``-``AC3``: comments on activity statements, by geometry.

    Returns ``(statement_comments, block_comments)`` to monkeypatch over
    `sphinx_pss.model.activity`'s (activity-diagrams plan decision D4). It
    follows the parser's placement rules for procedural statements and the
    anchoring the request asks for:

    - a statement's comments are those between the previous statement (or the
      ``{``) and its first token, where a label or a ``select``/``match`` arm
      prefix counts as part of the statement; the run ending on the line above
      is ``LEADING``, anything before a blank line ``DETACHED``;
    - a comment after a statement on its last line is ``TRAILING``;
    - a block's closing comments are those after its last statement's line and
      before its ``}``.

    DELETE THIS when ``test_ac1_activity_statements_carry_no_comments_yet``
    fails: the parser does it, and the tests should run against the parser.
    """
    from pssparser import tokens as ptokens

    from sphinx_pss.model.comments import Placement, SourceComment, doc_form, strip_markers

    files: dict[int, list] = {}

    def toks(fileid: int) -> list:
        if fileid not in files:
            with open(model.file_map[fileid], "rb") as f:
                stream = ptokens.tokenize(f.read())
            out = []
            for t in stream.tokens:
                if t.channel == ptokens.CHANNEL_BOM:
                    continue
                kind = "code"
                if t.channel in (ptokens.CHANNEL_SL_COMMENT, ptokens.CHANNEL_ML_COMMENT):
                    kind = "comment"
                elif t.channel != ptokens.CHANNEL_DEFAULT:
                    kind = "ws"
                out.append((t.text, t.line, t.col + 1, kind))
            files[fileid] = out
        return files[fileid]

    def code_before(ts, i):
        j = i - 1
        while j >= 0 and ts[j][3] != "code":
            j -= 1
        return j

    def code_after(ts, i):
        j = i + 1
        while j < len(ts) and ts[j][3] != "code":
            j += 1
        return j

    def match_back(ts, i):
        close = ts[i][0]
        opening = {")": "(", "]": "["}[close]
        depth = 0
        for j in range(i, -1, -1):
            if ts[j][3] != "code":
                continue
            if ts[j][0] == close:
                depth += 1
            elif ts[j][0] == opening:
                depth -= 1
                if depth == 0:
                    return j
        return i

    def start_of(node):
        loc = node.getLocation() if hasattr(node, "getLocation") else None
        if loc is None or loc.lineno < 0:
            return None, None
        ts = toks(loc.fileid)
        i = next((k for k, t in enumerate(ts) if t[1] == loc.lineno and t[2] == loc.linepos), None)
        if i is None:
            return None, None
        # A label, or a select/match arm's prefix, is part of the statement.
        j = code_before(ts, i)
        if j >= 0 and ts[j][0] == ":":
            k = code_before(ts, j)
            if k >= 0 and ts[k][0] in (")", "]"):
                while k >= 0 and ts[k][0] in (")", "]"):
                    k = code_before(ts, match_back(ts, k))
                i = code_after(ts, k)
            elif k >= 0:
                i = k
        return loc.fileid, i

    def end_of(ts, i):
        depth = 0
        k = i
        while k < len(ts):
            text, kind = ts[k][0], ts[k][3]
            if kind == "code":
                if text in ("{", "(", "["):
                    depth += 1
                elif text in ("}", ")", "]"):
                    depth -= 1
                    if depth == 0 and text == "}":
                        nxt = code_after(ts, k)
                        if nxt >= len(ts) or ts[nxt][0] not in ("else", "while", ";"):
                            return k
                elif text == ";" and depth == 0:
                    return k
            k += 1
        return len(ts) - 1

    def comment(fileid, t, placement):
        return SourceComment(
            raw=t[0],
            lines=tuple(strip_markers(t[0])),
            form=doc_form(t[0]),
            placement=placement,
            is_block=t[0].startswith("/*"),
            fileid=fileid,
            line=t[1],
            col=t[2],
        )

    def gap(ts, lo, hi):
        """Comments strictly between code tokens ``lo`` and ``hi``, less ``lo``'s trailing one."""
        found = []
        for k in range(lo + 1, hi):
            t = ts[k]
            if t[3] != "comment":
                continue
            if lo >= 0 and ts[lo][0] in (";", "}") and t[1] == ts[lo][1]:
                continue
            found.append(t)
        return found

    def statement_comments(node):
        fileid, i = start_of(node)
        if i is None:
            return []
        ts = toks(fileid)
        before = gap(ts, code_before(ts, i), i)
        out = []
        expect = ts[i][1] - 1
        leading = set()
        for t in reversed(before):
            last = t[1] + t[0].rstrip("\n").count("\n")
            if last == expect:
                leading.add(id(t))
                expect = t[1] - 1
            else:
                break
        for t in before:
            out.append(comment(fileid, t, Placement.LEADING if id(t) in leading else Placement.DETACHED))
        end = end_of(ts, i)
        k = end + 1
        while k < len(ts) and ts[k][3] != "code" and ts[k][1] == ts[end][1]:
            if ts[k][3] == "comment":
                out.append(comment(fileid, ts[k], Placement.TRAILING))
                break
            k += 1
        return out

    def block_comments(node):
        fileid, i = start_of(node)
        if i is None:
            return []
        ts = toks(fileid)
        close = end_of(ts, i)
        if ts[close][0] != "}":
            return []
        # The parser gives a closing comment placement 2, as for a detached one.
        return [comment(fileid, t, Placement.DETACHED) for t in gap(ts, code_before(ts, close), close)]

    return statement_comments, block_comments


def use_geometric_comments(monkeypatch, model) -> None:
    """Put `geometric_comments` in place for ``model``, and forget cached activities."""
    from sphinx_pss.model import activity

    statement, block = geometric_comments(model)
    monkeypatch.setattr(activity, "statement_comments", statement)
    monkeypatch.setattr(activity, "block_comments", block)
    model.derived.pop("activity", None)
    model.derived.pop("activity_steps", None)
