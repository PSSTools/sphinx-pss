# Activity diagrams — design & research

**Status:** Draft for review
**Date:** 2026-09-07
**Covers:** design §9.3 (`P3-IMPL-1`, `P3-IMPL-2`), and the seam for a future runtime-elaboration view
**Depends on:** `P2-IMPL-5` (the shared diagram back-end), which is not yet built

---

## 1. What this is, and what it is not

PSS `activity` blocks are the one part of the language that people already draw
on whiteboards. Rendering them is design §9.3's promise — *"for a compound
action this is the single most useful artifact a reader can be handed"* — and
nothing in the tree implements it today: `model/activity.py` and
`autodoc/diagrams.py` are both one-line stubs.

Two distinct products are worth naming up front, because conflating them is the
main way this design could go wrong:

| | **Static view** (this document) | **Runtime elaboration view** (future) |
|---|---|---|
| Input | The `ActivityDecl` as written | A solved scenario from a PSS tool |
| Content | The activity of *one* action, with sub-actions as opaque nodes | The full elaborated action tree, all inferred bindings, one concrete resolution of every `select`/`repeat` |
| Cardinality | One diagram per action, fixed at doc-build time | One diagram per *scenario*, produced by a solver |
| Loops/selects | Rendered as control structure | Already unrolled and chosen |
| Source | `pssparser`, in-process | An external tool's output (PSS has no standard scenario interchange format) |

This document specifies the static view and **shapes the IR so the runtime view
is a second front-end onto the same renderer** (§6.4), not a second renderer.

---

## 2. Findings — a `pssparser` spike, run 2026-09-07

Everything below was verified against the in-tree `pssparser` by parsing and
linking fixtures with rich activities. This section is the load-bearing part of
the document: **the parser cannot currently express a correct activity diagram**,
and how much of §5 is buildable today depends entirely on which of §3's items
land.

### 2.1 What works

| Capability | Evidence |
|---|---|
| `ActivityDecl` is reachable from the **linked** tree, as an ordinary child of the action's `SymbolTypeScope` | Walk of `dma_pkg::Dma::Xfer` shows `Field p`, `Field m1`, …, `ActivityDecl` |
| Statement order inside the activity is preserved | `ActivityDecl` children came back in written order |
| Scope-shaped statements expose their bodies through `getChildren()` | `ActivitySequence` → `[ActivityActionHandleTraversal, ActivityParallel]` |
| Non-scope statements expose bodies through typed accessors | `ActivityRepeatCount.getBody()` → `ActivitySequence`; `ActivityForeach.getBody()`, `ActivityAtomicBlock.getBody()`, `ActivityRepeatWhile.getBody()` all populated |
| `select` branches, with guard and weight | `ActivitySelect.getBranches()` → 2 × `ActivitySelectBranch`; first has `getGuard()` = `ExprBin`, `getWeight()` = `ExprUnsignedNumber` |
| `match` choices, incl. `default` | `ActivityMatch.getChoices()` → `ActivityMatchChoice(is_default=False, cond=ExprOpenRangeList)` and `(is_default=True)` |
| Handle traversal target as a written path | `ActivityActionHandleTraversal.getTarget()` → `ExprRefPathContext`, `hier_id` renders `m1` / `comp.sub_action` |
| Type traversal target | `ActivityActionTypeTraversal.getTarget()` → `DataTypeUserDefined`, `getType_id()` renders `Mem2Mem` |
| Inline `with` constraint is attached | `getWith_c()` → `ConstraintScope` |
| `bind` inside an activity | `ActivityBindStmt.getLhs()` = `m1.dst`, `getRhs()` = `[m2.src]` — **and it carries a real source location** |
| Labels | `getLabel()` returns the `ExprId` for `setup:`, `a:`, `b:` |
| The activity block has a full source **span** | `ActivityDecl` location `(file 1, line 26)`, `endLocation` `(file 1, line 55)` |

That last row matters more than it looks: a real span means the raw activity
source can be sliced for a `viewcode` link and for the literal-source fallback
in §5.5, independent of everything below.

### 2.2 What is broken or missing upstream

Six findings, continuing the implementation plan's `U-n` numbering. Every one
was reproduced on a fixture that parses and links without markers — these are
silent losses, not diagnostics.

| ID | Finding | Evidence | Impact on diagrams |
|---|---|---|---|
| `U-7` | **`if`/`else` branches are silently dropped.** `ActivityIfElse.getTrue_s()` and `getFalse_s()` are both `None` for a well-formed `if (c > 1) { a1; } else { b1; }`. Root cause is not a binding gap: `AstBuilderInt.cpp:2533` does `dynamic_cast<ast::IActivityStmt*>(true_body)` on an `IScopeChild*`, and the body is an `ActivitySequence`, which derives from `ActivityLabeledScope` → `SymbolScope` and **not** from `ActivityStmt` (`ast/activity.yaml`). The cast yields `nullptr` and the branch is discarded. | Fixture `act2.pss`; `cond` is present (`ExprBin`), both branches `None` | **Blocking.** A decision node with no outgoing branches is not a diagram; it is a lie. |
| `U-8` | **Join specifications are never built.** `mkActivityJoinSpec` is a stub — `DEBUG("TODO: mkActivityJoinSpec")` at `AstBuilderInt.cpp:5918` — so `ActivityParallel.getJoin_spec()` / `ActivitySchedule.getJoin_spec()` return `None` even for `parallel join_none {…}` and `parallel join_first(1) {…}`. | Both forms parse cleanly; `join` is `None` for both | **High.** `join_none` vs `join_first(n)` vs default-join are *different diagrams* — a `join_none` fork has no join bar at all. Rendering them identically is wrong, and there is no way to detect it. |
| `U-9` | **`replicate` loses its wrapper.** There is no `visitActivity_replicate_stmt` in `AstBuilderInt.cpp` (the grammar has the rule at `PSSParser.g4:940`, and `ActivityReplicate` exists in the AST). `replicate (i: 4) { a1; }` arrives as a bare `ActivitySequence`. | Fixture `act3.pss`: activity children are `[ActivitySchedule, ActivitySequence]` | **High.** A replication region silently renders as an ordinary sequence — a 4-way parallel expansion shown as one action. |
| `U-10` | **Scheduling constraints are dropped.** `constraint parallel { sb, sc };` inside a `schedule` block parses (grammar `PSSParser.g4:333`, LRM form) but produces no `ActivitySchedulingConstraint`; there is no visitor for it. | Fixture `act3.pss`: `ActivitySchedule` children are three traversals, nothing else | **Medium.** A `schedule` block's *whole point* is its ordering constraints. Without them a schedule is indistinguishable from an unordered fork. |
| `U-11` | **No activity statement carries a source location.** Every statement node reports `location == (-1, -1, -1)` and an empty `endLocation` — `ActivityBindStmt` and `ActivityDecl` itself are the only exceptions. | Every node in `act.pss` except children 7 and the decl | **Medium.** Three consequences: (a) no per-node `[source]` links; (b) `locations.is_synthesized()` treats `lineno < 0` as compiler-injected, so a naive walk would **discard the entire activity** — activity nodes must be added to the exemption set alongside `EnumItem` (`U-2`); (c) a diagnostic about a node ("cannot resolve traversal target `foo`") has nowhere to point. |
| `U-12` | **Labeled statements are hoisted into the action scope.** A labeled traversal appears *both* inside the `ActivityDecl` and as a direct child of the enclosing action's `SymbolTypeScope`. | `Xfer`'s children include three `Activity*Traversal` nodes (labels `setup`, `a`, `b`) before `ActivityDecl` | **Low, but a trap.** Harmless today only because `_DISPATCH` has no `Activity*` handlers. The moment activity nodes get handlers, every labeled statement becomes a phantom action member. The builder must filter `Activity*` at the type-scope level explicitly, not by omission. |

**One more, not a bug but a modelling consequence.** `do p;` where `p` is a
field of action type parses as an `ActivityActionTypeTraversal`
(`DataTypeUserDefined`), not a handle traversal — the two are only
distinguishable after name resolution. `ActivityActionHandleTraversal` is
produced for the bare `p;` form. The renderer must therefore treat "type
traversal whose type name matches a field of the enclosing action" as a handle
traversal (§4.3), rather than trusting the node class.

**And `U-3` still applies.** `ExprRefPathContext.getTarget()` returns a
`SymbolRefPath` exposing only `getPyref_idx()` — for the type traversal it was
`None` outright. Traversal targets resolve **by name through `PssIndex`**,
exactly as `PssObject.type_ref` already does. This is the design's stated model,
not a workaround, and it means activity linking needs no parser change.

---

## 3. Upstream work items (`pssparser`)

Filed as `A1`–`A5`, in the style of `pssparser-fixes-plan.md`. `A1` and `A2` are
blocking; the rest degrade specific constructs.

> **Detail lives in [`pssparser-activity-gaps.md`](pssparser-activity-gaps.md)** —
> per-defect evidence, root causes, proposed fixes, the reproduction fixture, and
> the two AST-spec decisions that must be settled before coding. That document
> also adds `A6` (`super;` produces nothing), found after this table was written.
> The summary below is the diagram-side view; that one is the work order.

| ID | Item | Where | Size | Blocking? |
|---|---|---|---|---|
| `A1` | Fix `if`/`else` branch loss (`U-7`). The `dynamic_cast` is the symptom; the cause is that `ActivityIfElse.true_s`/`false_s` are typed `UP<ActivityStmt>` while every block-shaped body is a `SymbolScope`. Retype both fields to `UP<ScopeChild>` (matching `ActivityRepeatCount.body`, which is already `UP<ScopeChild>` and works), or introduce a common base. Prefer retyping — it is one `ast/activity.yaml` edit plus dropping the cast. | `ast/activity.yaml`, `AstBuilderInt.cpp:2521` | ~5 lines | **Yes** |
| `A2` | Implement `mkActivityJoinSpec` (`U-8`) — build `ActivityJoinSpecNone` / `First(count)` / `Select(count)` / `Branch(list)` from `activity_join_spec`. | `AstBuilderInt.cpp:5915` | ~40 lines | **Yes**, for correctness of `parallel`/`schedule` |
| `A3` | Add `visitActivity_replicate_stmt` (`U-9`) — the AST class and grammar rule both exist; only the visitor is absent. | `AstBuilderInt.cpp` | ~25 lines | No — degrade per §5.6 |
| `A4` | Build `ActivitySchedulingConstraint` (`U-10`) from `activity_scheduling_constraint`. | `AstBuilderInt.cpp` | ~25 lines | No — degrade per §5.6 |
| `A5` | Set locations on activity statement nodes (`U-11`). Every other `ScopeChild` gets one; activity statements are constructed without. Set at least `location` at the statement's start token. | `AstBuilderInt.cpp`, throughout `visitActivity_*` | ~20 lines | No |

`U-12` (label hoisting) is deliberately **not** filed upstream: whether a label
belongs in the action's symbol table is a linking decision with `bind`-resolution
consequences, and the doc side can filter cheaply. Revisit only if the runtime
view needs label lookup.

**Scheduling.** `A1` + `A2` should land before `P3-IMPL-2` starts. `A3`–`A5` can
land in parallel with it; §5.6 defines what the renderer does without them, and
each one landing simply removes a degradation.

---

## 4. The model layer — `model/activity.py`

### 4.1 Two representations, deliberately

The natural instinct is one tree. The design calls for **a structural tree
*and* a derived control-flow graph**, because they serve different consumers and
have different lifetimes:

```
ActivityDecl  ──lift──▶  ActivityTree  ──lower──▶  ActivityGraph  ──render──▶  diagram / outline
   (parser)              (structure,               (nodes + edges,
                          as written)               UML-shaped)
```

* **`ActivityTree`** mirrors what was written: nesting, labels, guards,
  inline constraints, `bind` statements. It is what the *text outline* (§5.5)
  and cross-reference extraction (§4.4) read, and it is stable against layout
  decisions.
* **`ActivityGraph`** is nodes and edges with UML semantics attached — forks,
  joins, decisions, merges, control edges, object flows. It is the **only**
  thing the renderer sees.

The split earns its keep in §6.4: a runtime-elaborated scenario has no tree at
all, only a graph. Making `ActivityGraph` the rendering contract means the
runtime view reuses every line of the back-end.

`PssObject.activity` (declared in Phase 1 as `ActivityGraph(root=None)`) becomes
the tree; the graph is computed on demand and cached, because most builds
document actions without ever drawing them.

### 4.2 `ActivityTree` node kinds

One frozen dataclass per kind, all carrying `label: str | None` and
`source: SourceRef | None` (usually `None` until `A5` — see `U-11`).

| Node | Fields | From |
|---|---|---|
| `Traversal` | `target_name`, `target_qualname`, `is_type_traversal`, `with_constraint: str \| None`, `initializers` | `ActivityActionHandleTraversal`, `ActivityActionTypeTraversal` |
| `Sequence` | `children` | `ActivitySequence`, and any implicit block |
| `Parallel` | `children`, `join: JoinSpec` | `ActivityParallel` |
| `Schedule` | `children`, `join: JoinSpec`, `constraints: list[SchedulingConstraint]` | `ActivitySchedule` |
| `Select` | `branches: list[Branch(guard, weight, body)]` | `ActivitySelect` |
| `IfElse` | `cond`, `true_body`, `false_body` | `ActivityIfElse` |
| `Match` | `expr`, `choices: list[Choice(ranges, is_default, body)]` | `ActivityMatch` |
| `RepeatCount` | `count`, `loop_var`, `body` | `ActivityRepeatCount` |
| `RepeatWhile` | `cond`, `body` | `ActivityRepeatWhile` |
| `Foreach` | `iter_var`, `index_var`, `target`, `body` | `ActivityForeach` |
| `Replicate` | `index_var`, `label_var`, `body` | `ActivityReplicate` (after `A3`) |
| `Atomic` | `body` | `ActivityAtomicBlock` |
| `Super` | — | `ActivitySuper` |
| `Bind` | `lhs`, `rhs: list[str]` | `ActivityBindStmt` |
| `Constraint` | `text` | `ActivityConstraint` |
| `Unknown` | `node_type`, `raw` | any unmapped node kind |

`JoinSpec` is `("all" | "none" | "first" | "select" | "branch", count, branches)`,
with `"all"` as the default and — until `A2` — `"unknown"` as a distinct value so
the renderer can mark the uncertainty rather than assert the default (§5.6).

`Unknown` is not defensive padding. `ast/activity.yaml` gains node kinds when the
LRM revs, and the alternative to an explicit unknown node is a silently
incomplete diagram. It renders as a labelled grey box and emits one warning.

### 4.3 Lifting from the parser

A recursive walk with a per-kind dispatch table, mirroring
`builder.py`'s `_DISPATCH`. Three rules, all forced by §2:

1. **Children come from two places.** Scope-shaped nodes (`Sequence`,
   `Parallel`, `Schedule`) use `iter_children()`; everything else uses its typed
   accessor (`getBody()`, `getBranches()`, `getChoices()`, `getTrue_s()`). There
   is no generic traversal that covers both — a generic `getChildren()` walk
   returns nothing for two-thirds of the statement kinds.
2. **Exempt activity nodes from the synthesized filter.** `U-11` means every
   statement looks compiler-injected. Add the `Activity*` names to
   `locations.UNLOCATED_NODE_TYPES` — the same fix shape as `EnumItem`/`U-2`.
3. **Handle-vs-type disambiguation.** For an `ActivityActionTypeTraversal`,
   check the written name against the enclosing action's fields *first*; a match
   means it is a handle traversal that the grammar could not distinguish. Only
   if there is no field match is it resolved as a type through `PssIndex`.

### 4.4 Resolving traversal targets

Per `U-3`, resolution is by name through `PssIndex.resolve(name, scope=…)`, with
`scope` the enclosing action's qualname. Three cases:

| Written | Resolution | Diagram node links to |
|---|---|---|
| `m1;` (handle) | field `m1` of the action → its `type_ref` → index | The **action type** page, labelled `m1 : Mem2Mem` |
| `do Mem2Mem;` (type) | index lookup in the action's scope | The action type page |
| `comp.sub_action;` | component-relative path; resolve the leaf against the component's members | The action type page |

Unresolvable targets render as an unlinked node and emit **one** warning per
activity (not per node — an unresolvable component path typically hits every
traversal in the block, and the `-W` builds this project targets should not be
buried). Warning location falls back to the `ActivityDecl` span until `A5`.

---

## 5. Rendering

### 5.1 The UML mapping

This is the substantive design decision: what a PSS activity *is* in UML terms.
UML 2.5 activity diagrams have a richer node vocabulary than PSS needs, and the
mapping is close to exact — which is why this artifact is worth producing at all.

| PSS | UML activity concept | Rendered as |
|---|---|---|
| activity block | Activity | The whole diagram, framed, titled with the action's qualname |
| — | Initial node | Filled circle at the top |
| — | Activity final | Bullseye at the bottom |
| traversal | **CallBehaviorAction** | Rounded rectangle, `label : Type`, hyperlinked to the action's page |
| `sequence` | Control flow chain | Vertical edges |
| `parallel` | Fork node → Join node | Two solid bars; branches between them |
| `parallel join_none` | Fork with no join | Fork bar; branches end in their own final nodes |
| `parallel join_first(n)` | Fork → join, annotated | Join bar labelled `join_first(n)` |
| `parallel join_select(n)` / `join_branch(a,b)` | Join with a selection guard | Join bar labelled with the spec |
| `schedule` | Fork/join, branches **unordered** | Fork/join drawn with a dashed frame marked `schedule` |
| scheduling constraint | Control flow between branches | Dashed edge labelled `sequence` / `parallel` inside the schedule frame |
| `select` | **DecisionNode** → MergeNode | Diamond; edges labelled `[guard]` and `(weight)` |
| `if`/`else` | DecisionNode → MergeNode | Diamond; edges `[cond]` / `[else]` |
| `match` | DecisionNode | Diamond; edges labelled with the range list, plus `[default]` |
| `repeat (n)` | **LoopNode** | Structured box titled `repeat (n)`, with a back edge |
| `repeat … while (c)` | LoopNode | Box with the back edge labelled `[c]` |
| `foreach (i : a)` | **ExpansionRegion** (iterative) | Dashed box titled `foreach (i : a)` |
| `replicate (i : n)` | ExpansionRegion (parallel) | Dashed box titled `replicate`, with the parallel-expansion marker |
| `atomic` | StructuredActivityNode | Solid box titled `atomic` |
| inline `with { … }` | Constraint note | Note attached to the traversal node, `{ … }` |
| `bind a.out b.in` | **ObjectFlow** | Dashed edge between the two traversal nodes, labelled with the flow-object type |
| action `input`/`output` (`:pins:` option) | Input/output pins | Small squares on the node edge, labelled with the flow-object type |
| `super` | CallBehaviorAction to the base activity | Rounded rectangle, `super`, linked to the base action |

The `bind` → object-flow row is the one that repays the whole exercise. PSS's
data-flow story is invisible in the source (`bind m1.dst m2.src;` sits at the
bottom of the block, unrelated to where those actions appear) and *visible* in
the diagram, drawn as an edge between the two nodes it actually connects.

### 5.2 Lowering to `ActivityGraph`

`ActivityTree` → nodes and edges, one pass:

* Each node gets a stable id derived from its **structural path**
  (`activity/1/parallel/0`), not from a counter — stable ids are what make
  doctree output byte-identical between builds (the `P2-TEST-8` determinism
  guard) and what a future runtime view uses to correlate a scenario node back
  to its declaration site.
* Every construct lowers to a subgraph with exactly one entry and one exit node,
  so composition is a matter of connecting `exit(prev) → entry(next)`.
  `join_none` is the sole exception — its branches have no shared exit — and is
  handled explicitly rather than by special-casing at every call site.
* `bind` statements are collected during lowering and emitted last, as object
  flows between already-placed nodes. A `bind` naming a path with no
  corresponding node in this activity is dropped with a warning.

### 5.3 Back-ends

`pss_diagrams` already exists (`graphviz` | `mermaid` | `off`, validated in
`config.py`); `autodoc/diagrams.py` implements none of it. Activity diagrams
consume `P2-IMPL-5`'s back-end rather than growing their own — but they need two
things flow diagrams do not, and those belong in the shared layer:

* **Sub-graph clustering** (`subgraph cluster_…` in dot, `subgraph` in Mermaid)
  for structured regions — `foreach`, `repeat`, `atomic`, `schedule`.
* **Node hyperlinks** (`URL=` in dot; `click` in Mermaid) so a traversal node
  navigates to the action's page. Requires `graphviz_output_format = "svg"`;
  a `png` build silently loses every link, and that deserves a one-time warning.
  *(Corrected 2026-09-29, programming-steps plan S4: a `png` build keeps its
  links, because `sphinx.ext.graphviz` writes a client-side image map for it,
  so no warning was built. Both clustering and links landed with `P2-IMPL-5`.)*

**Graphviz is primary.** `sphinx.ext.graphviz` ships with Sphinx, produces SVG
with working links, and `dot`'s ranked layout is the right shape for a mostly
top-down control-flow graph. Fork/join bars are `shape=box, height=0.05,
style=filled` — the standard dot idiom for a UML bar.

**Mermaid is secondary** (`flowchart TD`). It has no UML activity diagram type,
so forks/joins/decisions are approximated with `{ }` diamonds and thin nodes; it
renders client-side with no `dot` binary, which matters for Read-the-Docs-style
hosts. Accept the lower fidelity; do not try to close the gap.

### 5.4 Directives and options

Per design §7, extending what is already specified:

```rst
.. autopssaction:: dma_pkg::Dma::Xfer
   :activity-diagram:          # the diagram
   :activity-outline:          # the text outline (§5.5)
   :activity-source:           # the raw activity block, syntax-highlighted
   :activity-depth: 2          # inline sub-activities to this depth (default 1)
   :pins:                      # draw flow-object pins on traversal nodes

.. pss:activity-diagram:: dma_pkg::Dma::Xfer
   :depth: 2
   :caption: DMA transfer activity
```

`:activity-depth:` is the option worth arguing about. Depth 1 — sub-actions as
opaque nodes — is the honest default: it is what the action *declares*, and
deeper inlining silently mixes in decisions made by other types. Depth > 1
inlines the callee's activity into a cluster, is capped at 4, and stops at any
recursive cycle with a "recursion elided" marker.

`pss_default_options` gains `activity-diagram` so a project can turn it on
globally.

### 5.5 The text outline — not optional

Every diagram renders alongside (or instead of) an indented outline:

```
sequence
├─ setup : Prog
├─ parallel (join_none)
│  ├─ m1 : Mem2Mem
│  └─ m2 : Mem2Mem
├─ repeat (count)
│  └─ Mem2Mem  with { len == 4; }
└─ bind m1.dst → m2.src
```

Three reasons this is a first-class deliverable rather than a fallback: it is
the accessible form of the same information (a linked SVG is not readable by a
screen reader); it is what renders when `dot` is absent or `pss_diagrams="off"`,
which `P2-IMPL-5` already requires to be non-fatal; and it is far easier to
assert on in tests than generated SVG. The outline is generated from
`ActivityTree` directly — it is the reason §4.1 keeps the tree.

### 5.6 Degradation, per upstream gap

Because §3's items may land in any order, each degradation is specified now and
each is *visible* — a diagram that quietly omits a branch is worse than no
diagram:

| Gap | Behavior until fixed |
|---|---|
| `U-7` / `A1` (`if`/`else` bodies) | Decision node rendered with the condition, branches replaced by a single node reading **"branches unavailable"**; one warning per activity. Do **not** draw an empty diamond. |
| `U-8` / `A2` (join specs) | Join bar drawn unlabelled with a dotted outline, meaning "join semantics unknown"; noted once in the caption. No default is assumed. |
| `U-9` / `A3` (`replicate`) | Indistinguishable from a sequence at the AST level, so nothing detects it. **Mitigation:** a source-text scan of the activity's span (available per §2.1) for `replicate` when the tree contains none, raising a warning that the diagram is incomplete. Ugly, and correct — a silently wrong parallel-expansion is the worst failure in this list. |
| `U-10` / `A4` (scheduling constraints) | `schedule` renders as an unordered fork/join with a caption note that constraints are not shown; same source-span scan for `constraint parallel`/`constraint sequence`. |
| `U-11` / `A5` (locations) | No per-node `[source]` links; warnings point at the `ActivityDecl`. |
| `U-12` (label hoisting) | Builder filters `Activity*` nodes at the type-scope level explicitly. |

---

## 6. Consequences and follow-on

### 6.1 Interaction with flow diagrams (§9.2)

Both exist, and they answer different questions: the flow diagram is
*inter*-action ("what can follow `Xfer`?"), the activity diagram is
*intra*-action ("what does `Xfer` do?"). They share the back-end and the linking
convention, nothing else. Resist merging them.

### 6.2 Monitors

`ast/activity.yaml`'s sibling `MonitorActivity*` classes (`MonitorActivityDecl`,
`Concat`, `Eventually`, `Overlap`, …) are a *temporal* language, not a control-flow
one, and a UML activity diagram is the wrong picture for them. Out of scope here;
worth its own treatment, probably as a sequence/timing diagram.

### 6.3 Performance

Lifting is linear in statement count and trivial next to parsing. Diagram
*generation* is not — `dot` is a subprocess per diagram. Build the graph lazily
(only when a diagram or outline is actually requested) and cache the lowered
graph on the `PssObject`.

### 6.4 The seam for the runtime elaboration view

The static view leaves exactly three things in place for it:

1. **`ActivityGraph` is the renderer's only input.** A solver-produced scenario
   lowers to the same node/edge types — traversals, forks, joins, object flows —
   with no decisions or loops (they are already resolved). The entire back-end,
   the UML vocabulary, the linking, and the outline renderer transfer unchanged.
2. **Structural node ids** (§5.2) give a scenario node a stable key back to the
   declaration it came from, which is what a "show me where this came from" link
   between the two views needs.
3. **The tree/graph split** means the runtime view simply skips the lift step.

What it will additionally need, and what this design deliberately does *not*
prejudge: a scenario input format. PSS standardizes no scenario interchange, so
that is either a vendor-specific reader or a `pssparser`-side solver — a much
larger question than rendering.

---

## 7. Work items

Refining `P3-IMPL-1` / `P3-IMPL-2` in the implementation plan.

### Upstream (prerequisite)
| ID | Task | Blocking |
|---|---|---|
| `A1` | `if`/`else` branch loss (`U-7`) | Yes |
| `A2` | `mkActivityJoinSpec` (`U-8`) | Yes |
| `A3` | `visitActivity_replicate_stmt` (`U-9`) | No |
| `A4` | `ActivitySchedulingConstraint` (`U-10`) | No |
| `A5` | Activity statement locations (`U-11`) | No |

### Implementation
| ID | Task | Done when |
|---|---|---|
| `P3-IMPL-1a` | `model/activity.py`: `ActivityTree` node types (§4.2) + lift from `ActivityDecl` (§4.3); `Activity*` added to `UNLOCATED_NODE_TYPES`; `Activity*` filtered at type-scope level (`U-12`) | fixture activities lift to expected trees |
| `P3-IMPL-1b` | Traversal target resolution through `PssIndex` (§4.4), incl. handle-vs-type disambiguation, one warning per activity | targets resolve to qualnames on the fixture |
| `P3-IMPL-1c` | Lowering to `ActivityGraph` (§5.2) with structural ids and single-entry/single-exit composition | graph edges match hand-computed expectations |
| `P3-IMPL-2a` | Shared back-end additions: clustering + node hyperlinks (§5.3) — lands in `P2-IMPL-5` | clusters and links emitted in dot and Mermaid |
| `P3-IMPL-2b` | UML rendering of `ActivityGraph` (§5.1) — fork/join bars, decisions, regions, object flows | diagram for the fixture compound action |
| `P3-IMPL-2c` | Text outline renderer (§5.5) | outline for every fixture activity |
| `P3-IMPL-2d` | Directives and options (§5.4): `:activity-diagram:`, `:activity-outline:`, `:activity-source:`, `:activity-depth:`, `:pins:`, `pss:activity-diagram::` | options render; depth capping and cycle elision work |
| `P3-IMPL-2e` | Degradation paths (§5.6), incl. the source-span scans for `U-9`/`U-10` | each degradation produces its warning, none fails the build |

### Tests
| ID | Task |
|---|---|
| `P3-TEST-1a` | `tests/fixtures/pss/activity_model.pss` — one activity per construct in §5.1, plus a nested compound action, `bind`, labels, inline constraints |
| `P3-TEST-2a` | `tests/model/test_activity.py` — lift per statement kind; nesting; disambiguation; unknown-node handling |
| `P3-TEST-2b` | `tests/model/test_activity_graph.py` — lowering, structural ids stable across two builds, single-entry/exit invariant |
| `P3-TEST-3a` | `tests/autodoc/test_activity_diagram.py` (`sphinx`) — nodes, action links, clusters; skips cleanly without `dot`; `pss_diagrams="off"` yields the outline |
| `P3-TEST-3b` | `tests/autodoc/test_activity_outline.py` — outline text for each construct |
| `P3-TEST-4` | `tests/test_upstream_guards.py` additions — one guard per `A1`–`A5`, asserting the *current* broken behavior so the guard fails loudly when the fix lands and the degradation can be removed |

`P3-TEST-4` is the pattern this repo already uses (`upstream` marker: "asserts a
`pssparser` behavior sphinx-pss depends on; a failure, not a skip"), and it is
what keeps §5.6's degradations from outliving their cause.

### Docs
| ID | Task |
|---|---|
| `P3-DOC-1a` | `docs/usage/activities.md` — the UML mapping table (§5.1), options, depth semantics, what is not rendered and why |

---

## 8. Open questions

1. **Default on or off?** `:activity-diagram:` off by default (explicit opt-in),
   or on for any action that has an activity? Leaning **off**, with
   `pss_default_options` to flip it: `dot` is a build dependency and a surprise
   subprocess per action is a poor default.
2. **Outline always, or only without a diagram?** Rendering both by default is
   redundant for sighted readers; rendering only the diagram loses the accessible
   form. Leaning **both, with the outline in a collapsible block**.
3. **`:pins:` — worth it?** Flow-object pins make the diagram substantially
   busier and duplicate the flow table on the same page. Proposed: implement,
   default off, and decide after seeing it on the stdlib example.
4. **Do we block on `A1`/`A2`?** The alternative is shipping §5.6's degradations
   from day one. Leaning **block on `A1`** (a decision node with no branches has
   no value) but **ship with `A2` degraded**, since an unlabelled join still
   conveys the fork structure correctly.
