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
"""The step tree of a function or ``exec`` block (steps design sections 4 and 5).

`steps_for` builds it on request, for one target, from the linked model:

- **Ranges (4.1).** A marker starts a step at the statement it is attached to,
  above it or trailing it, and the step runs to the next marker in the same
  block. Several markers on one statement start several steps there, and all
  but the last are empty.
- **Nesting (4.2).** Markers in a nested block are sub-steps of the step whose
  range holds the block. A nested block outside every step hangs off its
  control node at the outer level.
- **Control flow (4.3).** An ``if``, loop or ``match`` is a node only when it
  holds steps or expanded calls. Its label is the condition as written
  (`sphinx_pss.model.source_text`). A marker on the statement itself makes the
  control node the step's first child, flagged ``marked``, which a renderer
  shows as one row.
- **Calls (4.4).** A call inside a step's range, to a function that has
  markers, expands into that function's steps. Calls are followed by the
  linker's bindings (`sphinx_pss.model.calls`), never by name. Recursion is
  cut at the first repeat, with a reference back.
- **extend (4.5).** A type's ``exec`` blocks of one kind, declaration first,
  then each extension in link order, each in its own group.
- **Numbering (4.6).** Generated. Control rows, call expansions and groups
  are transparent: their steps continue the enclosing count.

A call statement or call assignment outside every step is left out of the
table, so it is reported (``pss.step_prelude_call``, D3). Declarations are
exempt, even when their initializer calls, and so are conditions. It is only
checked in bodies that have steps.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Iterator, Union

from .calls import Call, Callee, call_index, function_body, source_text, symbol_index
from .comments import CommentForm, closing_comments, comment_runs, comments_of
from .locations import node_source_ref, node_type_name
from .objects import SourceRef
from .parse import ParsedModel, iter_children, unwrap
from .steps_lint import StepIssue, _sub_blocks
from .steps_markers import Marker, parse_markers

__all__ = [
    "Arm",
    "Branch",
    "CallExpansion",
    "EXEC_KINDS",
    "EXPAND_MODES",
    "ExtensionGroup",
    "Group",
    "Loop",
    "NUMBERING_STYLES",
    "STEP_PRELUDE_CALL",
    "Step",
    "StepsDoc",
    "StepsError",
    "StepsUnavailable",
    "number_steps",
    "steps_for",
]

STEP_PRELUDE_CALL = "step_prelude_call"

#: ``:exec:`` names and the parser's kinds. Only the procedural kinds: the
#: target-template kinds (``header``, ``declaration``, ``file``) hold text,
#: not statements.
EXEC_KINDS = {
    "body": "ExecKind_Body",
    "init_down": "ExecKind_InitDown",
    "init_up": "ExecKind_InitUp",
    "post_solve": "ExecKind_PostSolve",
    "pre_body": "ExecKind_PreBody",
    "pre_solve": "ExecKind_PreSolve",
    "run_end": "ExecKind_RunEnd",
    "run_start": "ExecKind_RunStart",
}

#: ``:expand-calls:`` values.
EXPAND_MODES = ("inline", "link", "none")
#: ``:numbering:`` values.
NUMBERING_STYLES = ("decimal", "outline")


class StepsError(Exception):
    """A target or option that can't give steps. The message is for the user."""


class StepsUnavailable(StepsError):
    """The model didn't link, so bodies and calls can't be followed."""


# --- the tree -------------------------------------------------------------------


@dataclasses.dataclass(eq=False)
class Step:
    """A marked step and what its range holds."""

    title: str
    source: SourceRef
    detail: tuple[str, ...] = ()
    #: The source line of ``detail[0]``; see `Marker.detail_line`.
    detail_line: int = 0
    children: list[Node] = dataclasses.field(default_factory=list)
    #: Set by `number_steps`.
    number: str = ""


@dataclasses.dataclass(eq=False)
class Arm:
    """One way through a `Branch`."""

    #: ``if``, ``else_if``, ``else``, ``choice`` or ``default``; in an
    #: activity also ``select`` (a ``select`` arm, ``label`` its guard, empty
    #: for none).
    kind: str
    #: The condition or choice label as written; empty for ``else`` and ``default``.
    label: str
    children: list[Node] = dataclasses.field(default_factory=list)
    source: SourceRef | None = None
    #: A ``select`` arm's weight, when the table shows weights (activity-diagrams D2).
    weight: str = ""


@dataclasses.dataclass(eq=False)
class Branch:
    """An ``if`` chain, a ``match`` or an activity's ``select`` that holds steps."""

    #: ``if``, ``match`` or ``select``.
    kind: str
    source: SourceRef | None
    arms: list[Arm] = dataclasses.field(default_factory=list)
    #: For ``match``, the expression matched on.
    label: str = ""
    #: The enclosing step's marker is on this statement (design 4.3).
    marked: bool = False

    @property
    def children(self) -> list[Node]:
        return [node for arm in self.arms for node in arm.children]


@dataclasses.dataclass(eq=False)
class Loop:
    """A loop that holds steps."""

    #: ``while``, ``repeat_while``, ``repeat_count`` or ``foreach``.
    kind: str
    #: The condition, the count, or the collection, as written.
    label: str
    source: SourceRef | None
    children: list[Node] = dataclasses.field(default_factory=list)
    #: ``i`` in ``repeat (i : n)`` or ``foreach (i : xs)``.
    variable: str = ""
    marked: bool = False


@dataclasses.dataclass(eq=False)
class Group:
    """An activity's ``parallel``, ``schedule``, ``replicate`` or ``atomic`` that holds steps.

    ``label`` is the join specification of a ``parallel`` or ``schedule`` as
    written, or a ``replicate``'s count; ``constraints`` a ``schedule``'s
    scheduling constraints as ``(is_parallel, targets)``.
    """

    kind: str
    source: SourceRef | None
    children: list[Node] = dataclasses.field(default_factory=list)
    label: str = ""
    constraints: tuple[tuple[bool, tuple[str, ...]], ...] = ()
    marked: bool = False


@dataclasses.dataclass(eq=False)
class CallExpansion:
    """A call to a function with steps, or in an activity a traversal of an action with steps.

    ``mode`` is ``inline`` (its steps are the children), ``link`` (a reference
    to the callee's own steps) or ``cut`` (recursion: the callee is already
    being expanded further up, and `see` names where). ``exec`` is a
    traversal of an atomic action expanded into its ``exec body`` steps
    (activity-diagrams D3), drawn under a row marking the boundary.
    """

    callee: str
    source: SourceRef | None
    mode: str = "inline"
    children: list[Node] = dataclasses.field(default_factory=list)
    #: For ``cut``: the expansion or group whose steps this call repeats.
    target: Any = dataclasses.field(default=None, repr=False)

    @property
    def see(self) -> str:
        """The number of the first step the cut call refers back to."""
        if self.target is None:
            return ""
        first = next(_steps(self.target.children), None)
        return first.number if first is not None else ""


@dataclasses.dataclass(eq=False)
class ExtensionGroup:
    """The steps of one block: a function body, or one ``exec`` block of a type."""

    source: SourceRef | None
    #: The block comes from an ``extend``, not the type's own declaration.
    is_extension: bool = False
    children: list[Node] = dataclasses.field(default_factory=list)


Node = Union[Step, Branch, Loop, CallExpansion, Group]


@dataclasses.dataclass(eq=False)
class StepsDoc:
    """The steps of one target."""

    target: str
    #: The ``:exec:`` kind, for a type target.
    exec_kind: str | None
    groups: list[ExtensionGroup]
    #: ``pss.step_prelude_call`` problems in the bodies shown.
    issues: list[StepIssue] = dataclasses.field(default_factory=list)
    #: The steps are a compound action's activity's (activity-diagrams design 4.4).
    activity: bool = False

    def steps(self) -> Iterator[Step]:
        """Every step, depth first, in table order."""
        return _steps(self.groups)


def _steps(nodes: Any) -> Iterator[Step]:
    for node in nodes:
        if isinstance(node, Step):
            yield node
        yield from _steps(node.children)


# --- building ---------------------------------------------------------------------


def steps_for(
    model: ParsedModel,
    target: str,
    *,
    exec_kind: str | None = None,
    expand_calls: str = "inline",
    depth: int | None = None,
    numbering: str = "decimal",
    expand_exec: bool = False,
    weights: bool = False,
) -> StepsDoc:
    """The numbered step tree of ``target``.

    ``target`` is a function's qualified name, or a type's with ``exec_kind``
    naming the blocks, or a compound action's with no ``exec_kind``: then
    the steps are its activity's (activity-diagrams design 4.4), and
    ``expand_exec`` and ``weights`` apply. ``depth`` limits how many levels of calls expand;
    ``None`` is no limit. Raises `StepsError` with a message for the user when
    the target or an option is wrong, and `StepsUnavailable` when the model
    didn't link.
    """
    if not model.linked or model.root is None:
        raise StepsUnavailable(
            "programming steps are unavailable: the PSS model did not link, so "
            "function bodies and calls can't be followed"
        )
    if expand_calls not in EXPAND_MODES:
        raise StepsError(f"unknown expand-calls mode {expand_calls!r}; expected one of: {', '.join(EXPAND_MODES)}")
    if numbering not in NUMBERING_STYLES:
        raise StepsError(f"unknown numbering {numbering!r}; expected one of: {', '.join(NUMBERING_STYLES)}")
    if depth is not None and depth < 0:
        raise StepsError(f"depth must not be negative, not {depth}")

    scope = symbol_index(model).scopes.get(target)
    if scope is None:
        raise StepsError(f"no PSS function or type named {target!r}")

    builder = _Builder(model, expand_calls, depth)
    kind = node_type_name(scope)
    if kind == "SymbolFunctionScope":
        if exec_kind is not None:
            raise StepsError(f"{target!r} is a function; the exec option names an exec block of a type")
        body = function_body(scope)
        if body is None:
            raise StepsError(f"function {target!r} has no body, only a declaration")
        group = ExtensionGroup(source=node_source_ref(scope, model.file_map))
        builder.fill(group, [body], root=target)
        groups = [group]
    elif kind == "SymbolTypeScope" and exec_kind is None and _has_activity(model, target):
        from .activity_steps import activity_steps

        return activity_steps(
            model,
            target,
            expand_calls=expand_calls,
            depth=depth,
            numbering=numbering,
            expand_exec=expand_exec,
            weights=weights,
        )
    elif kind == "SymbolTypeScope":
        groups = []
        for block, is_extension in _exec_blocks(scope, target, exec_kind):
            group = ExtensionGroup(node_source_ref(block, model.file_map), is_extension)
            builder.fill(group, [block])
            groups.append(group)
    else:
        raise StepsError(f"{target!r} is not a function or a type")

    doc = StepsDoc(target=target, exec_kind=exec_kind, groups=groups, issues=builder.issues)
    number_steps(doc, numbering)
    return doc


def _has_activity(model: ParsedModel, target: str) -> bool:
    from .activity import has_activity

    return has_activity(model, target)


def _exec_blocks(scope: Any, target: str, exec_kind: str | None) -> list[tuple[Any, bool]]:
    """The ``exec`` blocks of ``exec_kind``, in link order, each flagged when an ``extend`` added it."""
    valid = ", ".join(EXEC_KINDS)
    if exec_kind is None:
        raise StepsError(f"{target!r} is a type: name its exec block with the exec option, one of: {valid}")
    if exec_kind not in EXEC_KINDS:
        raise StepsError(f"unknown exec kind {exec_kind!r}; expected one of: {valid}")

    from pssparser import ast

    wanted = getattr(ast.ExecKind, EXEC_KINDS[exec_kind])
    own = [c for c in iter_children(unwrap(scope)) if node_type_name(c) == "ExecBlock"]
    blocks = [
        (c, c not in own)
        for c in iter_children(scope)
        if node_type_name(c) == "ExecBlock" and c.getKind() == wanted
    ]
    if not blocks:
        raise StepsError(f"{target!r} has no 'exec {exec_kind}' block")
    return blocks


#: Statements whose nested blocks can hold steps.
_IF = "ProceduralStmtIfElse"
_MATCH = "ProceduralStmtMatch"
_LOOPS = {
    "ProceduralStmtWhile": "while",
    "ProceduralStmtRepeatWhile": "repeat_while",
    "ProceduralStmtRepeat": "repeat_count",
    "ProceduralStmtForeach": "foreach",
}
#: A ``{ }`` block, and an ``exec`` block: their children are statements.
_BLOCKS = frozenset({"ExecScope", "ExecBlock"})
#: Statements whose calls, outside every step, are reported (D3).
_CALL_STATEMENTS = frozenset({"ProceduralStmtExpr", "ProceduralStmtAssignment"})


class _Builder:
    def __init__(self, model: ParsedModel, expand: str, depth: int | None) -> None:
        self.model = model
        self.text = source_text(model)
        self.calls = call_index(model)
        self.expand = expand
        self.depth = depth
        self.issues: list[StepIssue] = []
        self._reported: set[tuple[str, int]] = set()
        #: Functions being expanded, outermost first, and the node holding
        #: each one's steps, for cutting recursion.
        self._stack: list[str] = []
        self._holders: dict[str, Any] = {}
        #: Per body being built: the calls outside every step.
        self._outside: list[list[StepIssue]] = []
        self._has_markers: dict[str, bool] = {}
        #: How many calls deep the expansion being built is.
        self._level = 0

    def ref(self, node: Any) -> SourceRef | None:
        return node_source_ref(node, self.model.file_map)

    # --- bodies ----------------------------------------------------------------

    def fill(self, holder: Any, blocks: list[Any], root: str | None = None) -> None:
        """Build the steps of ``blocks`` into ``holder.children``."""
        if root is not None:
            self._holders[root] = holder
            self._stack.append(root)
        for block in blocks:
            holder.children.extend(self.body(block))
        if root is not None:
            self._stack.pop()

    def body(self, block: Any) -> list[Node]:
        """One function body or ``exec`` block, with its prelude check."""
        self._outside.append([])
        nodes = self.block(block, outside=True)
        outside = self._outside.pop()
        if any(True for _ in _steps(nodes)):
            for issue in outside:
                key = (issue.path, issue.line)
                if key not in self._reported:
                    self._reported.add(key)
                    self.issues.append(issue)
        return nodes

    def block(self, block: Any, outside: bool) -> list[Node]:
        """The nodes of a block, or of a single statement used as one.

        ``outside`` is true when the block is outside every step's range, so
        its statements before its own first marker are too.
        """
        is_block = node_type_name(block) in _BLOCKS
        statements = list(iter_children(block)) if is_block else [block]
        out: list[Node] = []
        current: Step | None = None
        for stmt in statements:
            markers = self.markers(comments_of(stmt))
            for marker in markers[:-1]:
                out.append(self.step(marker))
            if markers:
                current = self.step(markers[-1])
                out.append(current)
            content = self.statement(stmt, outside=outside and current is None)
            if markers and _is_control(stmt) and content:
                content[0].marked = True
            (current.children if current is not None else out).extend(content)
        if is_block:
            out.extend(self.step(m) for m in self.markers(closing_comments(block)))
        return out

    def statement(self, stmt: Any, outside: bool) -> list[Node]:
        kind = node_type_name(stmt)
        if kind in _BLOCKS:
            return self.block(stmt, outside)
        if kind == _IF:
            return self.if_chain(stmt, outside)
        if kind == _MATCH:
            return self.match(stmt, outside)
        if kind in _LOOPS:
            return self.loop(stmt, _LOOPS[kind], outside)

        calls = self.calls.calls_in(stmt)
        if outside:
            if kind in _CALL_STATEMENTS and calls:
                self.outside_call(stmt, calls[0])
            return []
        return [node for node in map(self.expansion, calls) if node is not None]

    # --- control flow ------------------------------------------------------------

    def if_chain(self, stmt: Any, outside: bool) -> list[Node]:
        arms = []
        for i in range(stmt.numIf_then()):
            body = stmt.getIf_then(i).getBody()
            arms.append(
                Arm(
                    kind="if" if i == 0 else "else_if",
                    label=self.text.before(body.getLocation()) or "",
                    children=self.block(body, outside),
                    source=self.ref(body),
                )
            )
        other = stmt.getElse_then()
        if other is not None:
            arms.append(Arm("else", "", self.block(other, outside), self.ref(other)))
        if not any(arm.children for arm in arms):
            return []
        return [Branch("if", self.ref(stmt), arms)]

    def match(self, stmt: Any, outside: bool) -> list[Node]:
        arms = []
        for i in range(stmt.numChoices()):
            choice = stmt.getChoice(i)
            body = choice.getBody()
            is_default = bool(choice.getIs_default())
            arms.append(
                Arm(
                    kind="default" if is_default else "choice",
                    label="" if is_default else self.text.choice_label(body.getLocation()) or "",
                    children=self.block(body, outside),
                    source=self.ref(body),
                )
            )
        if not any(arm.children for arm in arms):
            return []
        label = self.text.after_keyword(stmt.getLocation()) or ""
        return [Branch("match", self.ref(stmt), arms, label=label)]

    def loop(self, stmt: Any, kind: str, outside: bool) -> list[Node]:
        body = stmt.getBody()
        children = self.block(body, outside) if body is not None else []
        if not children:
            return []
        loc = stmt.getLocation()
        variable = ""
        if kind == "repeat_while":
            label = self.text.after_body(body.getLocation()) or ""
        else:
            label = self.text.after_keyword(loc) or ""
            it_id = getattr(stmt, "getIt_id", lambda: None)()
            if it_id is not None:
                variable = str(it_id.getId())
                # ``repeat (i : n)`` and ``foreach (e : xs)``: the variable is
                # its own field, and the label is what it ranges over.
                head, sep, rest = label.partition(":")
                if sep and head.strip() == variable:
                    label = rest.strip()
        return [Loop(kind, label, self.ref(stmt), children, variable=variable)]

    # --- markers, calls ----------------------------------------------------------

    def markers(self, comments: list) -> list[tuple[Any, Marker]]:
        found = []
        for comment in comment_runs(comments):
            if comment.form is CommentForm.PLAIN:
                continue
            for marker in parse_markers(comment.lines, comment.line):
                found.append((comment, marker))
        return found

    def step(self, found: tuple[Any, Marker]) -> Step:
        comment, marker = found
        return Step(
            title=marker.title,
            source=SourceRef(
                path=self.model.file_map.get(comment.fileid, f"<file {comment.fileid}>"),
                line=marker.line,
                fileid=comment.fileid,
            ),
            detail=marker.detail,
            detail_line=marker.detail_line,
        )

    def outside_call(self, stmt: Any, call: Call) -> None:
        ref = self.ref(stmt)
        if ref is None or not self._outside:
            return
        self._outside[-1].append(
            StepIssue(
                STEP_PRELUDE_CALL,
                f"call to {call.name!r} is outside every step, so the step table leaves it "
                "out: move it into a step, or mark a step above it",
                ref.path,
                ref.line,
            )
        )

    def expansion(self, call: Call) -> CallExpansion | None:
        callee = call.callee
        if self.expand == "none" or callee is None or not self.has_markers(callee):
            return None
        where = SourceRef(
            path=self.model.file_map.get(call.fileid, f"<file {call.fileid}>"),
            line=call.line,
            col=call.col,
            fileid=call.fileid,
        )
        if callee.qualname in self._stack:
            return CallExpansion(
                callee.qualname, where, mode="cut", target=self._holders.get(callee.qualname)
            )
        if self.depth is not None and self._level >= self.depth:
            return None
        if self.expand == "link":
            return CallExpansion(callee.qualname, where, mode="link")
        node = CallExpansion(callee.qualname, where)
        self._holders[callee.qualname] = node
        self._stack.append(callee.qualname)
        self._level += 1
        try:
            node.children = self.body(callee.body())
        finally:
            self._level -= 1
            self._stack.pop()
        return node

    def has_markers(self, callee: Callee) -> bool:
        """True when ``callee`` has a body with at least one marker in it."""
        if callee.qualname not in self._has_markers:
            body = callee.body()
            self._has_markers[callee.qualname] = body is not None and self._any_marker(body)
        return self._has_markers[callee.qualname]

    def _any_marker(self, node: Any) -> bool:
        if self.markers(comments_of(node)) or self.markers(closing_comments(node)):
            return True
        return any(self._any_marker(sub) for sub in _sub_blocks(node))


def _is_control(stmt: Any) -> bool:
    kind = node_type_name(stmt)
    return kind in (_IF, _MATCH) or kind in _LOOPS


# --- numbering ---------------------------------------------------------------------


def number_steps(doc: StepsDoc, style: str = "decimal") -> None:
    """Number every step of ``doc`` in place (design 4.6).

    ``decimal`` gives 1, 1.1, 1.1.1. ``outline`` gives 1, a), i., the
    Microchip FRM style, and starts the cycle again below that. Control
    nodes, call expansions and groups take no number; the steps inside them
    continue the count of the level they are at.
    """
    if style not in NUMBERING_STYLES:
        raise StepsError(f"unknown numbering {style!r}; expected one of: {', '.join(NUMBERING_STYLES)}")

    def level(nodes: list, parent: str, depth: int) -> None:
        count = 0

        def visit(nodes: list) -> None:
            nonlocal count
            for node in nodes:
                if isinstance(node, Step):
                    count += 1
                    node.number = _label(style, parent, depth, count)
                    level(node.children, node.number, depth + 1)
                else:
                    visit(node.children)

        visit(nodes)

    level(doc.groups, "", 0)


def _label(style: str, parent: str, depth: int, n: int) -> str:
    if style == "decimal":
        return f"{parent}.{n}" if parent else str(n)
    form = depth % 3
    if form == 0:
        return str(n)
    if form == 1:
        return f"{_alpha(n)})"
    return f"{_roman(n)}."


def _alpha(n: int) -> str:
    out = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        out = chr(ord("a") + r) + out
    return out


def _roman(n: int) -> str:
    out = ""
    for value, digits in (
        (1000, "m"), (900, "cm"), (500, "d"), (400, "cd"), (100, "c"), (90, "xc"),
        (50, "l"), (40, "xl"), (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i"),
    ):
        while n >= value:
            out += digits
            n -= value
    return out
