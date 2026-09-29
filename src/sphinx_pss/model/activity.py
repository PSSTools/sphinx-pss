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
"""The activity of an action, as written (activity-diagrams design section 3).

`activity_for` lifts an action's ``ActivityDecl``\\ s into an `Activity`: a
tree that mirrors the source, one node kind per statement kind, with labels,
guards, join specifications, ``with`` constraints, binds and source locations.
The diagram, the outline and the step table all read it.

- **Children come from two places** (3.3). Scope-shaped statements
  (``sequence``, ``parallel``, ``schedule``) hold their statements as
  children; the rest hold a body behind a typed accessor.
- **Targets come from the linker** (3.3). A traversal is resolved through
  ``getTarget()``: to a ``Field`` it is a handle traversal, whatever class
  the parser built (``do a1`` is built as a type traversal); to a type it is
  a type traversal.
- **Text is as written** (3.3): conditions, guards and join specifications
  come from the token stream (`sphinx_pss.model.source_text`).
- **Which activity** (3.4): every block of the action, the declaration's first
  and then each ``extend``'s in link order; or, with none, the nearest base's.

A statement kind this module doesn't know becomes an `Unknown` node and an
issue, never a silently incomplete tree.

**Comments** (design 4) are read here, and only through `statement_comments`
and `block_comments`, which are the parser's comments
(`sphinx_pss.model.comments`). The step markers found are kept on the
`Activity`, keyed by node, for `sphinx_pss.model.activity_steps`. Until
pssparser attaches comments to activity statements (its ``AC1``-``AC3``)
there are none; tests put a stand-in in place of the two functions
(activity-diagrams plan decision D4).
"""

from __future__ import annotations

import dataclasses
from typing import Any, Iterator, Union

from .calls import source_text, symbol_index
from .comments import CommentForm, closing_comments, comment_runs, comments_of
from .locations import node_source_ref, node_type_name
from .objects import SourceRef
from .parse import ParsedModel, iter_children, unwrap
from .steps_lint import StepIssue
from .steps_markers import Marker, parse_markers

__all__ = [
    "Activity",
    "ActivityError",
    "ActivityUnavailable",
    "Arm",
    "Atomic",
    "Bind",
    "Block",
    "Constraint",
    "IfElse",
    "JoinSpec",
    "Loop",
    "Match",
    "Parallel",
    "Replicate",
    "Schedule",
    "SchedulingConstraint",
    "Select",
    "Sequence",
    "StepRegion",
    "Super",
    "Traversal",
    "Unknown",
    "activity_for",
    "walk",
]

#: The issue code for an activity that can't be shown completely.
ACTIVITY_ISSUE = "activity"


def statement_comments(node: Any) -> list:
    """The comments on an activity statement, as `comments.comments_of` gives them."""
    return comments_of(node)


def block_comments(node: Any) -> list:
    """The comments before an activity block's ``}``, as `comments.closing_comments` gives them."""
    return closing_comments(node)


class ActivityError(Exception):
    """A target that has no activity to show. The message is for the user."""


class ActivityUnavailable(ActivityError):
    """The model didn't link, so traversals can't be resolved."""


# --- the tree ---------------------------------------------------------------------


@dataclasses.dataclass(eq=False)
class Traversal:
    """``a1;``, ``do A;`` or ``do A with { ... };``."""

    #: The action handle, or None for a traversal of a type.
    handle: str | None
    #: The traversed action type's qualified name, or None when it didn't resolve.
    target: str | None
    #: The target as written, for display when it didn't resolve.
    written: str = ""
    #: The target has an activity of its own (UML's rake).
    has_activity: bool = False
    #: The target is abstract: the solver picks a subtype.
    is_abstract: bool = False
    #: The text inside ``with { }``, as written.
    with_text: str | None = None
    label: str | None = None
    source: SourceRef | None = None

    @property
    def type_name(self) -> str:
        """The target's short name, or the name as written."""
        if self.target:
            return self.target.rsplit("::", 1)[-1]
        return self.written


@dataclasses.dataclass(eq=False)
class Sequence:
    """``sequence { }``, or a braced body."""

    children: list["Node"] = dataclasses.field(default_factory=list)
    label: str | None = None
    source: SourceRef | None = None


@dataclasses.dataclass(frozen=True)
class JoinSpec:
    """How a ``parallel`` or ``schedule`` ends.

    ``kind`` is ``all`` (no specification), ``none``, ``first``, ``select`` or
    ``branch``; ``text`` is the specification as written, ``join_first (1)``.
    """

    kind: str = "all"
    text: str = ""


@dataclasses.dataclass(eq=False)
class Parallel:
    children: list["Node"] = dataclasses.field(default_factory=list)
    join: JoinSpec = JoinSpec()
    label: str | None = None
    source: SourceRef | None = None


@dataclasses.dataclass(frozen=True)
class SchedulingConstraint:
    """``constraint parallel { s1, s2 };`` or ``constraint sequence { ... };``."""

    is_parallel: bool
    targets: tuple[str, ...]
    source: SourceRef | None = None


@dataclasses.dataclass(eq=False)
class Schedule:
    children: list["Node"] = dataclasses.field(default_factory=list)
    join: JoinSpec = JoinSpec()
    constraints: list[SchedulingConstraint] = dataclasses.field(default_factory=list)
    label: str | None = None
    source: SourceRef | None = None


@dataclasses.dataclass(eq=False)
class Arm:
    """One way through a `Select` or `Match`.

    For a ``select`` arm, ``guard`` and ``weight`` as written, either may be
    None. For a ``match`` choice, ``guard`` is the choice label as written
    (``[0..3]``) and ``is_default`` marks ``default``.
    """

    body: "Node"
    guard: str | None = None
    weight: str | None = None
    is_default: bool = False


@dataclasses.dataclass(eq=False)
class Select:
    arms: list[Arm] = dataclasses.field(default_factory=list)
    label: str | None = None
    source: SourceRef | None = None


@dataclasses.dataclass(eq=False)
class IfElse:
    cond: str
    then: "Node"
    otherwise: "Node | None" = None
    label: str | None = None
    source: SourceRef | None = None


@dataclasses.dataclass(eq=False)
class Match:
    expr: str
    arms: list[Arm] = dataclasses.field(default_factory=list)
    label: str | None = None
    source: SourceRef | None = None


@dataclasses.dataclass(eq=False)
class Loop:
    """``repeat (n)``, ``repeat (i : n)``, ``repeat { } while (c)`` or ``foreach (e : xs)``.

    ``kind`` is ``repeat_count``, ``repeat_while`` or ``foreach``; ``header``
    is the count, the condition or the collection, as written; ``variable``
    is the loop or iterator variable, if one is named.
    """

    kind: str
    header: str
    body: "Node"
    variable: str = ""
    label: str | None = None
    source: SourceRef | None = None


@dataclasses.dataclass(eq=False)
class Replicate:
    """``replicate (n)``, ``replicate (i : n)``, optionally ``lbl[]:``."""

    count: str
    body: "Node"
    index: str = ""
    label_array: str = ""
    label: str | None = None
    source: SourceRef | None = None


@dataclasses.dataclass(eq=False)
class Atomic:
    body: "Node"
    label: str | None = None
    source: SourceRef | None = None


@dataclasses.dataclass(eq=False)
class Super:
    """``super;``: the base action's activity."""

    #: The base action's qualified name, or None when it didn't resolve.
    base: str | None
    #: The base has an activity to traverse.
    has_activity: bool = False
    label: str | None = None
    source: SourceRef | None = None


@dataclasses.dataclass(eq=False)
class Bind:
    """``bind a.x b.y;``: the paths as written."""

    lhs: str
    rhs: list[str] = dataclasses.field(default_factory=list)
    label: str | None = None
    source: SourceRef | None = None


@dataclasses.dataclass(eq=False)
class Constraint:
    """An activity-scope ``constraint { ... }``: its text as written."""

    text: str
    label: str | None = None
    source: SourceRef | None = None


@dataclasses.dataclass(eq=False)
class StepRegion:
    """A programming step in an activity: a marker and the statements it covers (design 4.2).

    Made by `sphinx_pss.model.activity_steps.stepped`, never by lifting.
    """

    title: str
    source: SourceRef
    detail: tuple[str, ...] = ()
    #: The source line of ``detail[0]``.
    detail_line: int = 0
    children: list["Node"] = dataclasses.field(default_factory=list)
    #: Set when the activity is numbered.
    number: str = ""
    #: The marker is on a control statement, which is the step's only child
    #: (design 4.3): a table draws the two as one row.
    marked: bool = False
    label: str | None = None


@dataclasses.dataclass(eq=False)
class Unknown:
    """A statement kind this module doesn't know."""

    node_type: str
    label: str | None = None
    source: SourceRef | None = None


Node = Union[
    Traversal,
    Sequence,
    Parallel,
    Schedule,
    Select,
    IfElse,
    Match,
    Loop,
    Replicate,
    Atomic,
    Super,
    Bind,
    Constraint,
    Unknown,
    StepRegion,
]

#: A step marker found on a node: the comment it is in, and the marker.
Found = tuple[Any, Marker]


@dataclasses.dataclass(eq=False)
class Block:
    """One ``activity { }`` block."""

    children: list[Node] = dataclasses.field(default_factory=list)
    #: The block comes from an ``extend``, not the action's declaration.
    is_extension: bool = False
    source: SourceRef | None = None
    #: The line of the block's ``}``, or 0 when the parser didn't say.
    end_line: int = 0


@dataclasses.dataclass(eq=False)
class Activity:
    """What an action does: its activity blocks (design 3.4)."""

    #: The action's qualified name.
    qualname: str
    blocks: list[Block] = dataclasses.field(default_factory=list)
    #: The base whose blocks these are, when the action has none of its own.
    inherited_from: str | None = None
    #: Problems met while lifting, for ``pss.activity``: at most one per activity.
    issues: list[StepIssue] = dataclasses.field(default_factory=list)
    #: Step markers on each node (by ``id``), and before each block's ``}``.
    markers: dict[int, list[Found]] = dataclasses.field(default_factory=dict, repr=False)
    closing: dict[int, list[Found]] = dataclasses.field(default_factory=dict, repr=False)

    def nodes(self) -> Iterator[Node]:
        """Every node, depth first, in source order."""
        for block in self.blocks:
            yield from walk(block.children)


def children_of(node: Any) -> list[Any]:
    """The nodes directly inside ``node``, in source order."""
    if isinstance(node, (Sequence, Parallel, Schedule, Block, StepRegion)):
        return list(node.children)
    if isinstance(node, (Select, Match)):
        return [arm.body for arm in node.arms]
    if isinstance(node, IfElse):
        return [node.then] + ([node.otherwise] if node.otherwise is not None else [])
    if isinstance(node, (Loop, Replicate, Atomic)):
        return [node.body]
    return []


def walk(nodes: Any) -> Iterator[Node]:
    """``nodes`` and everything inside them, depth first."""
    for node in nodes:
        yield node
        yield from walk(children_of(node))


# --- building ---------------------------------------------------------------------


def activity_for(model: ParsedModel, qualname: str) -> Activity:
    """The activity of the action ``qualname``, lifted once per model and cached.

    Raises `ActivityError`, with a message for the user, when ``qualname``
    isn't an action or has no activity, and `ActivityUnavailable` when the
    model didn't link.
    """
    if not model.linked or model.root is None:
        raise ActivityUnavailable(
            "activities are unavailable: the PSS model did not link, so traversals can't be resolved"
        )
    cache = model.cached("activity", dict)
    if qualname not in cache:
        cache[qualname] = _Lifter(model).activity(qualname)
    return cache[qualname]


def has_activity(model: ParsedModel, qualname: str) -> bool:
    """True when the action ``qualname`` has an activity, its own or inherited."""
    scope = symbol_index(model).scopes.get(qualname)
    return scope is not None and _Lifter(model).blocks_of(scope, qualname)[0] != []


#: Statement kinds whose children are statements.
_SCOPES = {"ActivitySequence": "sequence", "ActivityParallel": "parallel", "ActivitySchedule": "schedule"}
_HANDLE = "ActivityActionHandleTraversal"
_TYPE = "ActivityActionTypeTraversal"
_JOIN_KINDS = {
    "ActivityJoinSpecNone": "none",
    "ActivityJoinSpecFirst": "first",
    "ActivityJoinSpecSelect": "select",
    "ActivityJoinSpecBranch": "branch",
}


class _Lifter:
    def __init__(self, model: ParsedModel) -> None:
        self.model = model
        self.text = source_text(model)
        self.symbols = symbol_index(model)
        self.issues: list[StepIssue] = []
        self.markers: dict[int, list[Found]] = {}
        self.closing: dict[int, list[Found]] = {}
        #: The action whose blocks are being lifted: ``super`` is its base.
        self.owner: str | None = None

    def ref(self, node: Any) -> SourceRef | None:
        ref = node_source_ref(node, self.model.file_map)
        return ref if ref is not None and ref.line > 0 else None

    # --- the action ------------------------------------------------------------

    def activity(self, qualname: str) -> Activity:
        scope = self.symbols.scopes.get(qualname)
        if scope is None:
            raise ActivityError(f"no PSS action named {qualname!r}")
        if node_type_name(unwrap(scope)) != "Action":
            raise ActivityError(f"{qualname!r} is not an action, so it has no activity")
        decls, owner = self.blocks_of(scope, qualname)
        if not decls:
            raise ActivityError(f"action {qualname!r} has no activity")
        activity = Activity(qualname, inherited_from=owner if owner != qualname else None)
        self.owner = owner
        for decl, is_extension in decls:
            end = decl.getEndLocation()
            block = Block(is_extension=is_extension, source=self.ref(decl), end_line=max(end.lineno, 0) if end else 0)
            block.children = self.statements(decl)
            self.read_closing(block, decl)
            activity.blocks.append(block)
        activity.issues = self.issues[:1]
        activity.markers = self.markers
        activity.closing = self.closing
        return activity

    def blocks_of(self, scope: Any, qualname: str) -> tuple[list[tuple[Any, bool]], str | None]:
        """The ``ActivityDecl``\\ s of ``scope``, or of its nearest base that has some.

        Each is paired with whether an ``extend`` added it. Also returns the
        qualified name of the action they belong to.
        """
        seen: set[str] = set()
        while scope is not None and qualname not in seen:
            seen.add(qualname)
            own = [c for c in iter_children(unwrap(scope)) if node_type_name(c) == "ActivityDecl"]
            decls = [(c, c not in own) for c in iter_children(scope) if node_type_name(c) == "ActivityDecl"]
            if decls:
                return decls, qualname
            base = self.base_of(scope)
            if base is None:
                break
            qualname = base
            scope = self.symbols.scopes.get(base)
        return [], None

    def base_of(self, scope: Any) -> str | None:
        """The qualified name of the action ``scope`` inherits from."""
        get_super = getattr(unwrap(scope), "getSuper_t", None)
        super_t = get_super() if get_super is not None else None
        if super_t is None:
            return None
        _, qualname = self.follow(super_t.getTarget())
        return qualname

    # --- references ------------------------------------------------------------

    def follow(self, ref: Any) -> tuple[Any, str | None]:
        """The node a linker ``SymbolRefPath`` leads to, and the qualified name of its scope path.

        Only paths of plain child steps are followed; anything else (a
        template specialization, ``this``) gives ``(None, None)``.
        """
        if ref is None or not hasattr(ref, "numPath"):
            return None, None
        from pssparser.ast import SymbolRefPathElemKind

        node = self.model.root
        names: list[str] = []
        for i in range(ref.numPath()):
            elem = ref.getPath(i)
            if elem.kind != SymbolRefPathElemKind.ElemKind_ChildIdx:
                return None, None
            node = node.getChild(elem.idx)
            if node is None:
                return None, None
            if node_type_name(node) in ("SymbolScope", "SymbolTypeScope"):
                name = _name(node)
                if name:
                    names.append(name)
        return node, "::".join(names) or None

    def type_of_field(self, field: Any) -> str | None:
        data_type = getattr(field, "getType", lambda: None)()
        type_id = getattr(data_type, "getType_id", lambda: None)() if data_type is not None else None
        if type_id is None:
            return None
        node, qualname = self.follow(type_id.getTarget())
        return qualname if node is not None and node_type_name(node) == "SymbolTypeScope" else None

    # --- statements ------------------------------------------------------------

    def statements(self, scope: Any) -> list[Node]:
        out = []
        for stmt in iter_children(scope):
            # Declarations in an activity (handles, data fields) aren't steps
            # of it; scheduling constraints belong to their schedule.
            if not node_type_name(stmt).startswith("Activity") or node_type_name(stmt) == "ActivitySchedulingConstraint":
                continue
            out.append(self.statement(stmt))
        return out

    def statement(self, stmt: Any) -> Node:
        node = self._statement(stmt)
        found = _markers(statement_comments(stmt))
        if found:
            self.markers[id(node)] = found
        if isinstance(node, (Sequence, Parallel, Schedule, Select, Match)):
            self.read_closing(node, stmt)
        return node

    def read_closing(self, node: Any, scope: Any) -> None:
        found = _markers(block_comments(scope))
        if found:
            self.closing[id(node)] = found

    def _statement(self, stmt: Any) -> Node:
        kind = node_type_name(stmt)
        label = _label(stmt)
        source = self.ref(stmt)
        loc = stmt.getLocation() if hasattr(stmt, "getLocation") else None

        if kind in (_HANDLE, _TYPE):
            return self.traversal(stmt, kind, label, source)
        if kind == "ActivitySequence":
            return Sequence(self.statements(stmt), label, source)
        if kind == "ActivityParallel":
            return Parallel(self.statements(stmt), self.join(stmt), label, source)
        if kind == "ActivitySchedule":
            constraints = [
                SchedulingConstraint(
                    bool(c.getIs_parallel()),
                    tuple(_path_text(c.getTarget(i)) for i in range(c.numTargets())),
                    self.ref(c),
                )
                for c in iter_children(stmt)
                if node_type_name(c) == "ActivitySchedulingConstraint"
            ]
            return Schedule(self.statements(stmt), self.join(stmt), constraints, label, source)
        if kind == "ActivitySelect":
            arms = []
            for i in range(stmt.numBranches()):
                branch = stmt.getBranche(i)
                body = branch.getBody()
                guard, weight = self.text.select_arm(body.getLocation()) or (None, None)
                arms.append(Arm(self.statement(body), guard=guard, weight=weight))
            return Select(arms, label, source)
        if kind == "ActivityIfElse":
            otherwise = stmt.getFalse_s()
            return IfElse(
                self.text.after_keyword(loc) or "",
                self.statement(stmt.getTrue_s()),
                self.statement(otherwise) if otherwise is not None else None,
                label,
                source,
            )
        if kind == "ActivityMatch":
            arms = []
            for i in range(stmt.numChoices()):
                choice = stmt.getChoice(i)
                body = choice.getBody()
                is_default = bool(choice.getIs_default())
                guard = None if is_default else self.text.choice_label(body.getLocation())
                arms.append(Arm(self.statement(body), guard=guard, is_default=is_default))
            return Match(self.text.after_keyword(loc) or "", arms, label, source)
        if kind == "ActivityRepeatCount":
            header, variable = _split_variable(self.text.after_keyword(loc) or "", _id(stmt.getLoop_var()))
            return Loop("repeat_count", header, self.statement(stmt.getBody()), variable, label, source)
        if kind == "ActivityRepeatWhile":
            body = stmt.getBody()
            header = self.text.after_body(body.getLocation()) or ""
            return Loop("repeat_while", header, self.statement(body), "", label, source)
        if kind == "ActivityForeach":
            header, variable = _split_variable(self.text.after_keyword(loc) or "", _id(stmt.getIt_id()))
            return Loop("foreach", header, self.statement(stmt.getBody()), variable, label, source)
        if kind == "ActivityReplicate":
            count, index = _split_variable(self.text.after_keyword(loc) or "", _id(stmt.getIdx_id()))
            return Replicate(count, self.statement(stmt.getBody()), index, _id(stmt.getIt_label()), label, source)
        if kind == "ActivityAtomicBlock":
            return Atomic(self.statement(stmt.getBody()), label, source)
        if kind == "ActivitySuper":
            return self.super(stmt, label, source)
        if kind == "ActivityBindStmt":
            return Bind(
                _path_text(stmt.getLhs()),
                [_path_text(stmt.getRh(i)) for i in range(stmt.numRhs())],
                label,
                source,
            )
        if kind == "ActivityConstraint":
            return Constraint(self.text.braced_after(loc) or "", label, source)

        self.issue(source, f"the activity has a statement sphinx-pss doesn't know ({kind}); it is shown as a grey box")
        return Unknown(kind, label, source)

    def traversal(self, stmt: Any, kind: str, label: str | None, source: SourceRef | None) -> Traversal:
        target_expr = stmt.getTarget()
        if kind == _HANDLE:
            written = _path_text(target_expr)
            ref = target_expr.getTarget() if target_expr is not None else None
        else:
            type_id = target_expr.getType_id() if target_expr is not None else None
            written = _type_text(type_id)
            ref = type_id.getTarget() if type_id is not None else None

        node, qualname = self.follow(ref)
        handle = None
        target = None
        if node is not None and node_type_name(node) == "Field":
            handle = written
            target = self.type_of_field(node)
        elif node is not None and node_type_name(node) == "SymbolTypeScope":
            target = qualname

        t = Traversal(handle, target, written, label=label, source=source)
        if target is None:
            self.issue(source, f"the traversal of {written!r} doesn't resolve, so it isn't linked")
            return t
        scope = self.symbols.scopes.get(target)
        t.is_abstract = bool(getattr(unwrap(scope), "getIs_abstract", lambda: False)()) if scope is not None else False
        t.has_activity = scope is not None and bool(self.blocks_of(scope, target)[0])
        if stmt.getWith_c() is not None:
            t.with_text = self.text.with_clause(stmt.getLocation())
        return t

    def super(self, stmt: Any, label: str | None, source: SourceRef | None) -> Super:
        holder = self.symbols.scopes.get(self.owner) if self.owner else None
        base = self.base_of(holder) if holder is not None else None
        scope = self.symbols.scopes.get(base) if base else None
        has = scope is not None and bool(self.blocks_of(scope, base)[0])
        return Super(base, has, label, source)

    def join(self, stmt: Any) -> JoinSpec:
        spec = stmt.getJoin_spec()
        if spec is None:
            return JoinSpec()
        kind = _JOIN_KINDS.get(node_type_name(spec), "all")
        text = self.text.between_keyword_and_brace(stmt.getLocation()) or kind
        return JoinSpec(kind, text)

    def issue(self, source: SourceRef | None, message: str) -> None:
        if source is None:
            return
        self.issues.append(StepIssue(ACTIVITY_ISSUE, f"sphinx-pss: {message}", source.path, source.line))


# --- small helpers -------------------------------------------------------------------


def _markers(comments: list) -> list[Found]:
    """The step markers in ``comments``: ``///`` and ``/** */`` runs only (steps design 3.1)."""
    found = []
    for comment in comment_runs(comments):
        if comment.form is CommentForm.PLAIN:
            continue
        for marker in parse_markers(comment.lines, comment.line):
            found.append((comment, marker))
    return found


def _name(node: Any) -> str | None:
    getter = getattr(node, "getName", None)
    if getter is None:
        return None
    name = getter()
    while name is not None and hasattr(name, "getId"):
        name = name.getId()
    return str(name) if name is not None else None


def _id(expr_id: Any) -> str:
    """The text of an ``ExprId``, or empty for None."""
    if expr_id is None:
        return ""
    value = expr_id.getId() if hasattr(expr_id, "getId") else expr_id
    return str(value)


def _label(stmt: Any) -> str | None:
    get_label = getattr(stmt, "getLabel", None)
    label = get_label() if get_label is not None else None
    return _id(label) or None


def _path_text(ref_ctx: Any) -> str:
    """``a.b.c`` for an ``ExprRefPathContext`` (or an ``ExprHierarchicalId``)."""
    if ref_ctx is None:
        return ""
    hier = ref_ctx.getHier_id() if hasattr(ref_ctx, "getHier_id") else ref_ctx
    if hier is None or not hasattr(hier, "numElems"):
        return ""
    parts = []
    for i in range(hier.numElems()):
        elem = hier.getElem(i)
        parts.append(_id(elem.getId()) if hasattr(elem, "getId") else str(elem))
    return ".".join(parts)


def _type_text(type_id: Any) -> str:
    """``A`` or ``pkg::A`` for a ``TypeIdentifier``."""
    if type_id is None or not hasattr(type_id, "numElems"):
        return ""
    parts = []
    for i in range(type_id.numElems()):
        elem = type_id.getElem(i)
        parts.append(_id(elem.getId()) if hasattr(elem, "getId") else str(elem))
    return "::".join(parts)


def _split_variable(header: str, variable: str) -> tuple[str, str]:
    """``i : 4`` with variable ``i`` gives ``("4", "i")``; otherwise the header as is."""
    head, sep, rest = header.partition(":")
    if sep and variable and head.strip() == variable:
        return rest.strip(), variable
    return header, variable

