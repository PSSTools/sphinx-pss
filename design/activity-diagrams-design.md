# Activity diagrams — design

**Status:** Revision 2 (2026-09-29), open questions decided the same day (§11). Plan:
[`activity-diagrams-plan.md`](activity-diagrams-plan.md)
**Covers:** design §9.3 (`P3-IMPL-1`, `P3-IMPL-2`), programming steps in activities, and the seam for
a future runtime-elaboration view
**Depends on:** `P2-IMPL-5`, the shared diagram back-end (done in programming-steps plan S4), and
the programming-steps model (S0–S3)
**Upstream:** pssparser `AC1`–`AC3` for steps in activities
(`../pssparser/docs/design/sphinx-pss-requests-2026-09-29.md`). Everything else is buildable today.

> **What changed from revision 1 (2026-09-07).** Revision 1 was written when the parser couldn't
> express a correct activity, and half of it was about that: a spike (§2), upstream work items `A1`–`A5`
> (§3) and a degradation for each gap (§5.6). `A1`–`A6` have since been fixed upstream and
> re-verified (§2). So those sections are gone, along with everything built to work around them:
> resolving targets by name, exempting activity nodes from the synthesized-node filter, and
> scanning source text for `replicate`. Revision 1 is in git history.
>
> What's new:
> - `/// Step:` markers inside activities (§4). They draw as regions of the diagram and give a
>   compound action a step table.
> - The renderer now targets the shared `model/graph.py` IR rather than a separate
>   `ActivityGraph`, with the vocabulary it lacks added (§6.2).
> - Decisions on the options and defaults (§7).
>
> The UML mapping (§5), the tree/graph split and the runtime seam carry over.

---

## 1. What this is, and what it is not

PSS `activity` blocks are the one part of the language that people already draw on whiteboards.
Design §9.3 promises to render them: "for a compound action this is the single most useful artifact
a reader can be handed".

There are two different products here. Mixing them up is the main way this design could go wrong:

| | **Static view** (this document) | **Runtime elaboration view** (future) |
|---|---|---|
| Input | The `activity` blocks as written | A solved scenario from a PSS tool |
| Content | The activity of *one* action, with sub-actions as opaque nodes unless asked to inline them | The full elaborated action tree, all inferred bindings, one concrete resolution of every `select`/`repeat` |
| Cardinality | One diagram per action, fixed at doc-build time | One diagram per *scenario*, produced by a solver |
| Loops/selects | Drawn as control structure | Already unrolled and chosen |
| Source | `pssparser`, in-process | An external tool's output (PSS has no standard scenario interchange format) |

This document specifies the static view. It keeps the diagram IR free of anything static-only, so
the runtime view can be a second front end onto the same back-end (§9.3).

Three outputs come from one model:

| Output | What it shows | For |
|---|---|---|
| **Activity diagram** | Every construct, as UML, with steps as labelled regions | Seeing the shape of a scenario |
| **Activity outline** | The same content as a nested list | The diagram's accessible text equivalent, and its fallback when it can't be drawn |
| **Step table** | Only the steps, with their detail, numbered, as `pss:steps` shows a function's | Reading the activity as a procedure, and following it down into the sub-actions' own steps |

---

## 2. Parser status — verified 2026-09-29 against pssparser `1ec757b`

`pssparser`'s own `tests/python/parsing/test_activity_gaps.py` (49 tests, A1–A8) passes against the
installed build. The results were re-checked with probes from this repository, and
`../pssparser/docs/design/sphinx-pss-requests-2026-09-28.md` §1 records a sweep of 173 corpus
activity statements. The renderer can rely on:

| Construct | Available |
|---|---|
| Every statement kind | Sequence, parallel, schedule, select (guard, weight), if/else (both bodies), match (ranges, default), repeat count/while, foreach, replicate (count, index, label array), atomic, `super`, bind, traversal with `with` constraint, activity-scope constraint, scheduling constraint (`is_parallel`, targets) |
| Join specs | `join_none`, `join_first(n)`, `join_select(n)`, `join_branch(…)`; `None` means the default join-all |
| Locations | A start line on every statement. Start and end on every block statement and body, except `R1`/`R2` below |
| Resolution | Every reference in an activity resolves through `getTarget()`. Handle traversals resolve to the `Field`; `do A` resolves to the type's `SymbolTypeScope`; `join_branch` labels and scheduling-constraint targets resolve to the labeled statement |
| Several blocks | The declaration's `ActivityDecl` and each `extend`'s appear among the type's linked children in link order. The `own` versus `extend` test from `steps._exec_blocks` tells them apart |

Behaviors to build around, none of them defects:

- **Labels are listed in the action's scope.** An action's `getChildren()` includes its top-level
  labeled statements as non-owning entries, which is how label references resolve (LRM 11.8). The
  builder must skip `Activity*` nodes when collecting members.
- **`do a1;`, where `a1` is a field, is built as `ActivityActionTypeTraversal`.** Its type id
  resolves to the field, so a handle traversal is detected by where it resolves, not by node class.
- **A derived action doesn't carry its base's activity.** `Top2 : Base { }` has no `ActivityDecl`
  among its children. The base comes from `PssObject.extends_target`.
- **`select` branches and `match` choices have no location of their own.** Their bodies do, which
  is enough.

Still open upstream, with a fallback here:

| ID | Gap | Fallback |
|---|---|---|
| `R1` | `atomic` has no end location, and its body `ActivitySequence` has no location (both -1; re-checked 2026-09-29) | Use the `atomic` statement's start, and the body's first and last statements, for anything that needs a span. The body must not be filtered as compiler-injected |
| `R2` | `bind` has no end location | None needed: nothing slices a `bind`'s text except its own label, which comes from the AST |
| `AC1`–`AC3` | No comments on activity statements or blocks, so no steps (§4.7) | Diagrams and outlines without step regions. One warning if a marker is found (§4.7) |

---

## 3. The model — `model/activity.py`

### 3.1 Pipeline

```
ActivityDecl(s) ──lift──▶ ActivityTree ──steps──▶ ActivityTree ──lower──▶ Graph   ──▶ dot / Mermaid
   (parser)             (as written)          (+ step regions)     │     (graph.py)
                                                                   ├──▶ outline (nested list)
                                                                   └──▶ StepsDoc ──▶ step table
```

- **`ActivityTree`** mirrors what was written: nesting, labels, guards, join specs, inline
  constraints, `bind`s, source locations. The outline and the step projection read it.
- **`Graph`** is the existing diagram IR from `model/graph.py`, which already backs flowcharts. It
  becomes the only thing the back-end sees. Revision 1's separate `ActivityGraph` is dropped: the
  IR's node shapes are already "named for what they mean rather than how a back-end draws them",
  so UML's vocabulary belongs there (§6.2).

The tree is built lazily per request, as `steps_for` builds a step tree. `activity_for(model,
qualname)` caches the tree on the `ParsedModel`, since a page can ask for a diagram and a table of
the same action. The unused `PssObject.activity` field and its `ActivityGraph` placeholder are
removed: nothing is computed at index time.

### 3.2 `ActivityTree` node kinds

Every node is a frozen dataclass with `label: str | None` (the PSS label, `s1:`) and
`source: SourceRef`.

| Node | Fields | From |
|---|---|---|
| `Activity` | `blocks: list[Block]`, `inherited_from: str \| None` | the action's `ActivityDecl`s, or its base's (§3.4) |
| `Block` | `children`, `is_extension`, `source` | one `ActivityDecl` |
| `Traversal` | `handle: str \| None`, `target: str \| None` (qualname), `has_activity`, `is_abstract`, `with_text: str \| None` | `ActivityActionHandleTraversal`, `ActivityActionTypeTraversal` |
| `Sequence` | `children` | `ActivitySequence`, including a braced body |
| `Parallel` | `children`, `join: JoinSpec` | `ActivityParallel` |
| `Schedule` | `children`, `join: JoinSpec`, `constraints: list[SchedulingConstraint]` | `ActivitySchedule` and the scheduling constraints inside it |
| `Select` | `arms: list[Arm(guard, weight, body)]` | `ActivitySelect` |
| `IfElse` | `cond`, `then`, `otherwise: … \| None` | `ActivityIfElse` |
| `Match` | `expr`, `arms: list[Arm(ranges \| "default", body)]` | `ActivityMatch` |
| `Loop` | `kind` (`repeat_count`, `repeat_while`, `foreach`), `header`, `variable`, `body` | `ActivityRepeatCount`, `ActivityRepeatWhile`, `ActivityForeach` |
| `Replicate` | `count`, `index`, `label_array`, `body` | `ActivityReplicate` |
| `Atomic` | `body` | `ActivityAtomicBlock` |
| `Super` | `base: str \| None` | `ActivitySuper` |
| `Bind` | `lhs`, `rhs: list[str]` | `ActivityBindStmt` |
| `Constraint` | `text` | `ActivityConstraint` |
| `Unknown` | `node_type` | any node kind not listed |

The step pass (§4) adds one more:

| Node | Fields |
|---|---|
| `StepRegion` | `step` (`title`, `detail`, `number`, `source`), `children`, `marked` (the marker is on a single control statement, §4.3) |

`JoinSpec` is `("all" | "none" | "first" | "select" | "branch", count_text, branch_labels)`, with
`"all"` for an absent spec.

`Unknown` is not defensive padding. `ast/activity.yaml` gains node kinds when the LRM revs, and the
alternative is a diagram that silently leaves something out. It renders as a grey box labelled with
the node kind, and gives one `pss.activity` warning per activity.

### 3.3 Lifting

This is a recursive walk with a per-kind dispatch table. Two rules come from §2:

1. **Children come from two places.** Scope-shaped nodes (`Sequence`, `Parallel`, `Schedule`,
   `ActivityDecl`) use `iter_children()`. The others use their typed accessors: `getBody()`,
   `getBranches()`, `getChoices()`, `getTrue_s()`/`getFalse_s()`.
2. **Targets come from the linker.** A traversal is resolved through `getTarget()`. Resolving to a
   `Field` makes it a handle traversal: take the field's type, then that type's qualname through
   the `SymbolIndex` of `model/calls.py`, extended to action types. Resolving to a
   `SymbolTypeScope` makes it a type traversal. This applies whichever node class the parser built.
   A target that doesn't resolve is kept, unlinked, and gives one `pss.activity` warning per
   activity. That can happen with a standard-library type, or with a model that linked with errors.

**Text comes from tokens.** Conditions and headers are shown as written, as step conditions are
(`sphinx_pss.model.source_text`, programming-steps design §4.3). Each construct gets a lookup:

- the parentheses after `if`, `repeat`, `foreach`, `replicate` and `match`, and after `while` in the
  do-while form;
- the `( guard )` and `[ weight ]` before a `select` arm's body;
- the `[ ranges ]` before a `match` arm's body;
- the join spec between `parallel`/`schedule` and `{`;
- the `with { … }` of a traversal, from `with` to its matching `}`.

The arm lookups work because an arm's body is located and its prefix sits between the previous
arm's end (or the `{`) and that body. Each is a small addition to `SourceText`.

**`with` text is abbreviated for the diagram:** whitespace collapsed, and cut at 60 characters with
`…`. The outline and the node's hover text keep it whole.

### 3.4 Which activity an action has

LRM 11: "If more than one activity is specified in an action, the execution semantics are the same
as if the activity statements were combined in a schedule statement". An action inheriting from a
compound action shadows the base's activities if it declares any, and `super;` traverses them.

| The action has | `Activity` | Drawn as |
|---|---|---|
| One `activity` block | one `Block` | the block |
| Several, from its declaration and/or `extend`s | one `Block` each, in link order, with `is_extension` set | an implicit `schedule`: fork and join bars, each block a cluster labelled with where it was declared (`activity` / `activity (extend, dma_ext.pss:12)`) |
| None, but a base (transitively) that has one | the base's blocks, `inherited_from` set | as the base's; the caption says "Inherited from `Base`" |
| None at all | — | not an error for `autopssaction :activity-diagram:` on an atomic action: nothing is drawn. `pss:activity-diagram` on it is an error at the directive |

`super;` is a `Super` node linked to the base. With `:depth:` of 2 or more, it inlines the base's
activity like any traversal (§7.3).

---

## 4. Steps in activities

### 4.1 The marker

The marker is unchanged from functions (programming-steps design §3.1): a `///` or `/** */`
comment line matching `^Step(\s+\d+(\.\d+)*)?:\s*(?P<title>\S.*)$`, with the rest of the comment as
detail. It can go above an activity statement, after it on its line, or above it with a blank line
between (placements 0, 1 and 2), at any depth. It can also go after a block's last statement,
before its `}`, where it opens an empty step (`pss.step_empty`).

A marker above a `select` arm or `match` choice attaches to that arm's body (pssparser `AC3`).
That is where an author writes it:

```pss
select {
    /// Step: Take the fast path
    (fast) [3]: burst;
    /// Step: Take the safe path
    single;
}
```

A marker between `}` and `else` has no owner. Write it inside the `else` body instead.

### 4.2 Reach — the one new rule

In a function, a step covers the statements from its marker **to the next marker in the same
block** (programming-steps design §4.1). That rule assumes the statements in a block run one after
another. In an activity, only some blocks do:

| Block | Its statements | A marker covers |
|---|---|---|
| The `activity` body, `sequence { }`, and the braced bodies of `if`/`else`, `repeat`, `foreach`, `replicate` and `atomic` | run in order | **its statement up to the next marker in the block**, as in a function |
| `parallel { }`, `schedule { }` | are branches that run concurrently, or in an order the solver chooses | **its own statement only**, which is its branch |
| `select { }`, `match { }` | are alternatives: one runs | **its own arm only** |

The reason: in `parallel { /// Step: A  a1;  b1; }`, the function rule would put `b1` inside step
A, but `b1` runs *alongside* `a1`, not after it. Each branch of a concurrent block, and each arm of
a choice, is its own scope. That's also how an author thinks of it.

**`schedule` follows the `parallel` rule** (decided 2026-09-29). Its branches may run in sequence,
but in an order the solver picks, so an author can't know what "the next statement" is. Sharing
the reach rule doesn't mean sharing the rendering: **every output keeps a `schedule` distinct from
a `parallel`**:
- the step table's control row (§4.4);
- the outline's label;
- the diagram, which draws a `schedule`'s bars hollow inside a cluster titled `schedule`, where a
  `parallel`'s bars are solid (§5.1).

A reader must never have to guess whether branches are guaranteed to overlap.

A branch that is a braced `sequence` has its own sequential scope inside, so a branch can carry a
whole numbered procedure:

```pss
parallel {
    sequence {
        /// Step: Fill the source buffer
        fill;
        /// Step: Copy it
        m1;
    }
    /// Step: Poll the status register
    poll;
}
```

The rest of the step semantics carries over unchanged:

- **Nesting** (§4.2 there). Markers in a nested block are sub-steps of the step whose range holds
  the block.
- **Marked controls** (§4.3). A marker directly on `parallel`, `select`, a loop, etc. titles it. In
  the step tree the control is the step's first child, flagged `marked`.
- **Control nodes are shown only when they hold steps.** This applies in the step table. The
  diagram shows every construct anyway.
- **The prelude and its warning** (§4.1). A **traversal** outside every step's range, in an
  activity that has steps, is reported by the existing `pss.step_prelude_call`, with a message
  that says "traversal". A traversal is the activity's call, and the step table would silently
  leave it out. That includes an unmarked branch beside marked ones in a `parallel`. `bind`,
  constraints and declarations are exempt, as declarations are in functions.
- **Several blocks and `extend`** (§4.5). Each `Block` is a group with a provenance row, and
  numbering continues across the groups.

**Numbering.** Numbers in a concurrent block identify steps; they don't order them. The control row
above them ("In parallel:", §4.4) says so. Steps 2.1 and 2.2 in a `parallel` are two branches, not
two steps in sequence.

### 4.3 Steps and structure nest properly

A step's range is a run of consecutive statements in **one** block (§4.2). So it never straddles a
block boundary, and a step region always nests properly with the structural regions: inside the
block that holds it, and around the blocks its statements hold. This is what lets a step be drawn
as a cluster (§5.2) without a layout that cuts across a loop or a fork. It holds by construction,
and the lowering asserts it.

One subtlety: a marked control. `/// Step: Move the data` above a `parallel` gives a step region
that contains the whole fork/join, with the parallel's own branch steps nested inside as 2.1, 2.2.

### 4.4 The step table of a compound action

`pss:steps` (and `:steps:` on `autopssaction`) accepts a compound action with no `:exec:`. The table
is its activity's steps. Rows follow programming-steps design §7.2, with these control rows:

| Construct | Row |
|---|---|
| `parallel` | "In parallel:". `join_none`: "Start in parallel, without waiting:". `join_first(n)`: "In parallel, until the first `n` finish:". `join_select(n)`: "In parallel, until `n` chosen at random finish:". `join_branch(a, b)`: "In parallel, until `a`, `b` finish:" |
| `schedule` | "In an order the tool chooses:", plus "(`s1`, `s2` in parallel)" or "(`s1` before `s2`)" for each scheduling constraint |
| `select` | "One of:", each arm labelled with its guard: "If `fast`:", or ~~"Otherwise:"~~ "Or:" for an unguarded arm (as built in AD5: an unguarded arm isn't a fallback, it may be picked any time). Weights are left out unless `:weights:` is given, which adds "(weight 3)" |
| `if` / `match` / loops | As in functions: "If `c`:", "Depending on `c`:", "Repeat `n` times:", "For each `i` in `arr`:" |
| `replicate` | "`n` copies, in parallel:" |
| `atomic` | "Without interleaving:" |
| `super` | "Follow the steps of `Base`", expanded or linked as below |

**Traversals expand the way calls do** (§4.4 there), under the same `:expand-calls:` and `:depth:`
options. In an activity, a traversal *is* the call. A traversal of a **compound** action, inside a
step's range, expands into that action's activity steps.

**A traversal of an atomic action does not expand into its `exec body` steps by default**
(decided 2026-09-29). An activity says *what* runs and in what arrangement; an `exec` block says
*how* one action does its work. The table keeps the two apart unless asked. Without the option, an
atomic traversal is part of its step, like a call to a function with no markers.

`:expand-exec:` (a flag) asks for it:
- each atomic traversal whose `exec body` has steps expands into them;
- they sit under a row "The `exec body` of `configure`:", so the boundary between scenario and
  implementation stays visible;
- those steps expand their own calls in turn, so the table reaches down to the register writes at
  the leaves. That is the procedure a programming guide prints, generated.

Two limits:
- **An abstract or inferred target isn't expanded.** `do A`, where `A` is abstract, stands for
  whichever subtype the solver picks. ~~It is one row, "Traverse any `A`", linked to `A`.~~
  *(As built in AD5: it is opaque, like a call to a function with no markers. A row for every
  abstract traversal would be the only row an unexpanded traversal ever got, which is noise.)*
- **Recursion is cut at the first repeat**, as for calls. An action whose activity traverses its
  own type is legal PSS.

`:format: flowchart` and `both` are rejected for an activity, with an error that points at
`pss:activity-diagram` and its `:steps: collapsed` (§7.1). The activity diagram *is* the activity's
flowchart, and a second, different drawing of the same thing would confuse.

### 4.5 A worked example

```pss
component dma_c {
    action configure {
        exec body {
            /// Step: Write the descriptor
            write_desc();
            /// Step: Enable the channel
            write_reg(CH_CTRL, 1);
        }
    }
    action copy  { }
    action check { }

    action xfer {
        configure cfg;
        copy      c1, c2;
        check     chk;

        activity {
            /// Step: Configure the channel
            /// Both halves share one descriptor chain.
            cfg;
            /// Step: Move the data
            parallel {
                /// Step: Copy the first half
                c1;
                /// Step: Copy the second half
                c2;
            }
            /// Step: Check the result
            chk;
        }
    }
}
```

`.. pss:steps:: dma_c::xfer` gives:

| # | Step | Details |
|---|---|---|
| 1 | Configure the channel | Both halves share one descriptor chain. |
| 2 | Move the data | |
| | In parallel: | |
| 2.1 | Copy the first half | |
| 2.2 | Copy the second half | |
| 3 | Check the result | |

With `:expand-exec:`, step 1 reaches into `configure`'s `exec body` through the traversal of `cfg`:

| # | Step | Details |
|---|---|---|
| 1 | Configure the channel | Both halves share one descriptor chain. |
| | The `exec body` of `configure`: | |
| 1.1 | Write the descriptor | |
| 1.2 | Enable the channel | |
| 2 | Move the data | |
| … | | |

`.. pss:activity-diagram:: dma_c::xfer` draws the following. Regions are dashed clusters, and the
step regions are shaded (§6.2):

```
                ●
                │
   ┌─ 1 Configure the channel ─┐
   │     ( cfg : configure )   │
   └───────────────────────────┘
                │
   ┌─ 2 Move the data ─────────────────────────┐
   │              ━━━━━━━━━━━                   │
   │  ┌─ 2.1 Copy the first half ─┐ ┌─ 2.2 … ─┐ │
   │  │    ( c1 : copy )          │ │ (c2:copy)│ │
   │  └───────────────────────────┘ └─────────┘ │
   │              ━━━━━━━━━━━                   │
   └────────────────────────────────────────────┘
                │
   ┌─ 3 Check the result ─┐
   │   ( chk : check )    │
   └──────────────────────┘
                │
                ◉
```

The activity outline, as a nested list:

- 1 Configure the channel
  - `cfg : configure`
- 2 Move the data
  - parallel
    - 2.1 Copy the first half
      - `c1 : copy`
    - 2.2 Copy the second half
      - `c2 : copy`
- 3 Check the result
  - `chk : check`

### 4.6 Warnings

The existing codes carry over, and their scope widens from "function and `exec` bodies" to "function
bodies, `exec` blocks and activities":

| Code | In an activity |
|---|---|
| `pss.step_syntax` | Unchanged: a near-miss (`/// step: …`, `/// Steps: …`) on an activity statement |
| `pss.step_misplaced` | Activity statements become valid positions. A marker above the `activity` keyword itself is still misplaced: that comment documents the block, like one above a function |
| `pss.step_empty` | Unchanged |
| `pss.step_prelude_call` | Also reports a traversal outside every step (§4.2) |

There are two new codes, neither of them about markers:

| Code | When |
|---|---|
| `pss.activity` | An activity has an `Unknown` node kind, or a traversal target that doesn't resolve. Once per activity, at the activity's line |
| `pss.step_unsupported` | The installed pssparser can't attach comments in activities (§4.7), and an activity that a page draws or tabulates has a `///` or `/** */` marker in it. Once per build |

The `SPSS001` migration checker needs no change. It works on tokens, so it already reports a plain
`// Step:` inside an activity.

### 4.7 Until pssparser `AC1`–`AC3` land

Without comments on activity statements, the step pass finds no markers. So:

- **Capability probe.** At the first activity request, parse `action A { activity { /// Step: x
  do A; } }` in memory, with `collect_comments=True`, and check that the traversal has a comment.
  This is the shape of the existing `_capability` probes. No version floor is involved, in line
  with the versioning convention.
- **When the probe fails**, diagrams and outlines are drawn without step regions, and `pss:steps`
  on a compound action is an error that says why. Markers aren't silently lost: the activity's span
  is tokenized (`SourceText`, already cached per file), and one `pss.step_unsupported` warning is
  given if any doc-comment line in it matches the marker pattern.
- **An `upstream` guard** asserts that the parser attaches no activity comments today. It fails
  when `AC1` lands, which is the signal to delete the token-scan fallback.

Rejected: attaching comments to activity statements in sphinx-pss, from tokens and statement
locations. It would work, since every statement now has a location. But it would be a second
implementation of the parser's placement rules (leading, trailing, detached, the blank-line rule),
against `model/comments.py`'s principle that there is one reader of comments, and it would drift.

---

## 5. The UML mapping

### 5.1 Constructs

UML 2.5 activity diagrams have a richer node vocabulary than PSS needs, and the mapping is close to
exact, which is why this output is worth producing at all.

| PSS | UML concept | Drawn as |
|---|---|---|
| the action's activity | Activity | the whole diagram, titled with the action's qualified name |
| — | Initial node | filled circle at the top |
| — | Activity final | bullseye at the bottom |
| traversal `a1;` | CallBehaviorAction | rounded rectangle `a1 : A`, linked to `A`'s entry. A rake `⋔` after the name if `A` has an activity of its own, as UML marks a call to an activity |
| `do A;` | CallBehaviorAction | rounded rectangle `A`, linked; `«any» A` if `A` is abstract |
| labeled traversal `s1: a1;` | named action | `s1: a1 : A` |
| `sequence` | control flow chain | edges. A labeled sequence is a dashed cluster titled with its label, so `join_branch` and scheduling constraints that name it have something to point at |
| `parallel` | Fork → Join | two solid bars; branches between them |
| `parallel join_none` | Fork without a join | the fork bar has an edge to what follows, and each branch ends in a flow final (⊗) |
| `join_first(n)`, `join_select(n)`, `join_branch(…)` | Join with a join specification | the join bar labelled `{join_first(1)}` etc., in UML's `{joinSpec}` style |
| `schedule` | (none in UML) | two **hollow** bars (black outline, no fill) inside a dashed cluster titled `schedule`, so it is never mistaken for a `parallel` (§4.2) |
| scheduling constraint | — | a dotted edge between the two named nodes, inside the schedule: undirected and labelled `parallel`, or directed and labelled `sequence` |
| `select` | DecisionNode → MergeNode | diamond labelled `select`. Edges labelled `[guard]`; an unguarded arm is unlabelled. With `:weights:`, an edge with a weight adds ` (3)` |
| `if` / `else` | DecisionNode → MergeNode | diamond. Edges `[cond]` and `[else]`; with no `else`, the `[else]` edge goes straight to the merge |
| `match` | DecisionNode → MergeNode | diamond labelled with the expression; edges `[0..3]` etc. and `[default]` |
| `repeat (n)`, `repeat … while (c)` | LoopNode | dashed cluster titled `repeat (n)` / `repeat … while (c)` |
| `foreach (i : a)` | ExpansionRegion, iterative | dashed cluster titled `«iterative» foreach (i : a)` |
| `replicate (i : n)` | ExpansionRegion, parallel | dashed cluster titled `«parallel» replicate (i : n)` |
| `atomic` | StructuredActivityNode | dashed cluster titled `atomic` |
| inline `with { … }` | Constraint | note shape joined to its node by a dotted edge, with the abbreviated text (§3.3) |
| activity-scope `constraint` | Constraint | note inside the activity frame, unattached |
| `bind a.x b.y` | ObjectFlow | dashed edge between the two traversal nodes, labelled with the bound fields. A `bind` to the context action's own field (`bind in_buf sub.in_buf`) draws an ActivityParameterNode: a rectangle `in_buf : Buf` at the top for inputs, at the bottom for outputs |
| `super` | CallBehaviorAction to the base activity | rounded rectangle `super`, linked to the base, with the rake if the base has an activity |
| several activity blocks | (LRM: an implicit schedule) | as `schedule`, one cluster per block (§3.4) |
| step | StructuredActivityNode | a shaded cluster titled `2.1 Copy the first half`. Hovering shows the detail; it links to the marker's line when viewcode exists |

**Loops are drawn as regions, not back-edges.** A back-edge makes a flowchart read like code; UML
draws a LoopNode as a structured node. Keeping every construct single-entry and single-exit with
only forward edges also keeps `dot`'s ranking top-down, which matters more in activities (many
parallel branches) than in step flowcharts. Revision 1 had both; the back-edge is dropped.

**`bind` edges that can't be placed are listed, not drawn.** Two cases:
- a `bind` whose endpoint names no traversal node in this activity, which is legal when it binds
  through a nested sub-action;
- a handle traversed in two places, where the edge would be ambiguous.

These go in a caption line ("Also bound: `a.x` ↔ `sub.y`"). They aren't warnings, since the code
is valid. `-W` builds must not fail on valid PSS.

### 5.2 Steps in the drawing

- A step is a cluster. Its region holds the nodes its range lowers to (§4.3), including fork/join
  bars and decision/merge diamonds when the range holds a whole construct.
- Step clusters are **shaded and solid-edged**, and structural clusters are **dashed and
  unshaded**, so they stay apart when nested: `2 Move the data` around a `parallel` region around
  `2.1` and `2.2`.
- The detail is not drawn, as in step flowcharts. It is the cluster's hover text.
- With `:steps: collapsed` (§7.1), each outermost step's region becomes **one node**, a rounded
  rectangle titled with its number and title, and everything outside steps is drawn as usual. A
  step's range lowers to a single-entry, single-exit subgraph, so replacing it with one node keeps
  the rest of the graph valid. This is the step-level overview of a large activity. Steps in
  different branches of a `parallel` stay parallel nodes between the bars.

### 5.3 Inlining sub-activities

`:depth:` (default 1) controls how far traversals are opened:
- At depth 1 every traversal is an opaque node. That is what the action *declares*. Deeper
  inlining mixes in decisions made by other types.
- At depth *n* > 1, a traversal of a compound action is drawn as a dashed cluster titled `a1 : A`,
  holding `A`'s activity lowered at depth *n* − 1, with no initial or final node of its own.
- Recursion is cut at the first repeat with a node "`A` (recursive, see above)".
- The cap is 4.

Steps inside an inlined activity are drawn with their own numbering, prefixed by the traversal:
`c1 › 2.1`. Continuing the outer numbering would suggest the outer activity wrote them.

---

## 6. Rendering

### 6.1 Back-ends

Both come from `P2-IMPL-5` (`autodoc/diagrams.py`): `pss_diagrams = "graphviz" | "mermaid" | "off"`.
Diagrams warn once per build when they can't draw, and links are resolved at `doctree-resolved`.

- **Graphviz** is primary. It carries the full UML vocabulary through `dot` shapes (§6.2).
- **Mermaid** (`flowchart TD`) is secondary. It has no UML activity-diagram type, so bars, initial
  and final nodes are approximated with styled nodes. Accept the lower fidelity; don't try to close
  the gap. Its output must still pass Mermaid's own parser, as step flowcharts are checked.
- **A diagram that can't be drawn** is rendered as its outline. This matches the flowchart-to-table
  rule, so the page still shows the activity.

### 6.2 Additions to `model/graph.py` and the back-end

New shapes, named for meaning as the existing ones are:

| Shape | dot | Mermaid |
|---|---|---|
| `action` | `shape=box, style="rounded"` | `("…")` |
| `initial` | `shape=circle, style=filled, fillcolor=black, width=0.2, label=""` | `(( ))` with a `style` line filling it |
| `final` | `shape=doublecircle, style=filled, fillcolor=black, width=0.15, label=""` | `((( )))` |
| `flow_final` | `shape=circle, label="✕", width=0.2` | `(("✕"))` |
| `bar` | `shape=box, style=filled, fillcolor=black, height=0.05, width=1.5, label=""` | `[" "]` with a black-fill `style` line |
| `hollow_bar` | as `bar`, with `style=""` (outline only) and `height=0.08` | `[" "]` with a white-fill, black-stroke `style` line |
| `merge` | `shape=diamond, label="", width=0.25, height=0.25` | `{" "}` |
| `note` | `shape=note` | `>"…"]` (asymmetric) |
| `parameter` | `shape=box` | `["…"]` |

The existing `terminal` stays for flowcharts. Activities use `initial` and `final`.

Edge and cluster additions:

- **`GraphEdge.style`**: `control` (default, solid), `object` (dashed, for `bind`) and
  `constraint` (dotted, for notes and scheduling constraints). Plus `GraphEdge.directed` (default
  true), so a `parallel` scheduling constraint can be undirected.
  - dot: `style=dashed|dotted` and `dir=none`.
  - Mermaid: `-.->`, `-.-` and `~~~`. Mermaid has no dotted-versus-dashed distinction, so object
    flows use `-.->` and constraints `-.-`.
- **`Cluster.kind`**: `region` (default, today's rounded dashed style) and `step` (solid, light
  shading).
  - dot: `style="rounded,filled"; fillcolor="#80808020"`.
  - Mermaid: a `style <id> fill:#80808020` line per step subgraph.
  - The fill is semi-transparent grey rather than a light grey, so it reads on a dark-mode page
    as well as a light one.
- **`Graph.caption_notes`**: lines under the diagram, for unplaced binds (§5.1), "Inherited from
  `Base`" (§3.4) and similar. Rendered by the directive as the figure caption, not by the back-end.

These are additive. Step flowcharts' dot and Mermaid output must stay byte-identical, which the
existing determinism tests enforce.

### 6.3 Layout details that matter

- **Fork and join bars** need `group` attributes, or `dot` skews the branches: the fork, the join
  and the first node of each branch share a rank-aligned group. Branches get `ordering=out` so they
  are drawn in source order.
- **Scheduling-constraint and note edges** get `constraint=false`, so they don't distort the
  ranking.
- **Object flows** get `constraint=false`. A `bind` often points "backwards" in control order.
- **Determinism.** Node ids stay sequential in lowering order, which follows the source. Revision 1
  wanted structural path ids, so that a runtime view could map a scenario node back to its
  declaration. Source locations now do that (every statement is located), so sequential ids
  suffice.

---

## 7. Directives and options

### 7.1 `pss:activity-diagram`

```rst
.. pss:activity-diagram:: dma_pkg::dma_c::xfer
   :format: diagram          # diagram (default) | outline | both
   :steps: regions           # regions (default) | collapsed | none
   :depth: 1                 # 1 (default) .. 4
   :weights:                 # show select weights (default: left out)
   :caption: DMA transfer
```

| Option | Meaning |
|---|---|
| `:format:` | `diagram`, the outline alone, or the diagram with the outline in a collapsed `<details>` block below it. For HTML the outline is always in the page, so a screen reader has the text form. For non-HTML builders `both` renders the outline in the open |
| `:steps:` | Draw step regions, collapse each outermost step to one node, or ignore markers. With no markers, all three give the same diagram |
| `:depth:` | §5.3 |
| `:weights:` | Label `select` edges with their weights. Left out by default: a weight tunes test generation, and doesn't describe the scenario (decided 2026-09-29) |
| `:caption:` | Figure caption. The default is the action's qualified name. `Graph.caption_notes` lines follow it |

The alternative text for the SVG is a one-line summary, such as "Activity of `xfer`: 3 steps, 4
actions, 1 parallel block". The outline is the full text equivalent.

### 7.2 On `autopssaction`

`:activity-diagram:` puts the diagram in the action's entry, after its prose, before any step table
and its members. *(As built in AD3: the step table is inserted before the members afterwards, so it
follows the diagram.)* The options are prefixed so they can't clash with `:steps:`' `:format:` and
`:depth:`: `:activity-format:`, `:activity-steps:`, `:activity-depth:`, `:activity-weights:`.

The documenter emits the diagram as a `pss:activity-diagram` directive in the reStructuredText it
generates for the action. So the flag also works for actions documented as *members*, such as those
of an `autopsscomponent` with `:members:`, which is what makes a project-wide default useful.

**Unlike `:steps:`, `:activity-diagram:` is accepted in `pss_default_options`.** A step table on
every function is never wanted, since most functions are small. But a diagram on every compound
action is a reasonable reference-manual default, and on an atomic action the flag does nothing
(§3.4). Off unless set.

### 7.3 `pss:steps` on a compound action

This is §4.4. The target is an action, with no `:exec:`. `:expand-calls:` and `:depth:` govern
traversals as well as calls. `:expand-exec:` (a flag) expands atomic traversals into their `exec
body` steps, and `:weights:` adds `select` weights to arm rows. Both are accepted, and ignored, for
a function or an `exec` target. `:format:` accepts `table` only.

### 7.4 Errors and warnings at the directive

The rules of `pss:steps` apply:
- An unknown name, or an action with no activity (for `pss:activity-diagram`), is an error at the
  directive's line, naming what would have worked.
- A bad option value is an error that lists the valid values.
- An activity with nothing drawable, such as an empty `activity { }`, gives a `pss.activity`
  warning, and the diagram is just the initial and final nodes.

---

## 8. Tests

The work items (§10) carry these. The strategy follows programming steps.

- **Unit.** Lifting per statement kind. The reach rule (§4.2): a `parallel` with one marked
  branch; a `select` with markers per arm; a sequence branch with a procedure; a marked control.
  The proper-nesting assertion (§4.3). Lowering per construct, checked on `Graph` data rather than
  on dot text. Collapse. Inlining with recursion. Traversal expansion into activity steps and
  `exec body` steps.
- **Text back-ends.** Exact dot and Mermaid text for one fixture per construct family. Mermaid
  checked with Mermaid's parser off-suite, as in S4.
- **Sphinx.** A test root with a DMA-style fixture (§4.5), under `-W`, covering:
  - diagram, outline, `both` and collapsed forms;
  - `:activity-diagram:` through `pss_default_options`;
  - the degradation to an outline with `pss_diagrams = "off"`, and with no `dot`;
  - links in SVG and PNG;
  - determinism across two builds.
- **Upstream guards.**
  - Comments aren't attached in activities today (§4.7). It flips when `AC1` lands.
  - `R1`/`R2` (§2).
  - The label-listing behavior (§2), so a change there is noticed before members go wrong.
- **Corpus.** Every activity in the parseable pss-corpus buckets lifts and lowers without an
  `Unknown` node or an exception, and gives zero step warnings (the corpus has no markers). This
  is what proves the reach rule and the prelude warning are silent on unmarked code.
- **Docs.** Every example on the usage page is a live directive or a checked listing, per the
  docs-per-milestone rule.

---

## 9. Consequences and follow-on

### 9.1 Flow diagrams (§9.2)

Flow diagrams and activity diagrams answer different questions. The flow diagram is *inter*-action
("what can follow `xfer`?"). The activity diagram is *intra*-action ("what does `xfer` do?"). They
share the back-end and the linking convention, nothing else. Resist merging them.

### 9.2 Monitors

`MonitorActivity*` is a *temporal* language, not a control-flow one, and a UML activity diagram is
the wrong picture for it. It is out of scope, and worth its own treatment, probably as a sequence or
timing diagram. Upstream, monitor-activity construction also has open TODOs.

### 9.3 The runtime elaboration view

The static view leaves three things in place for it:

1. **`Graph` is the back-end's only input.** A solver-produced scenario lowers to the same shapes
   (actions, bars, object flows) and has no decisions or loops. The back-end, the linking, the
   outline and the step shading transfer unchanged.
2. **Source locations** on every statement give a scenario node a key back to the declaration it
   came from.
3. **The tree/graph split** means the runtime view skips the lift step and builds a `Graph`
   directly.

It will also need a scenario input format. This design deliberately doesn't prejudge that. PSS
standardizes no scenario interchange, so it is either a vendor-specific reader or a
`pssparser`-side solver, which is a much larger question than rendering.

### 9.4 Performance

Lifting is linear in statement count and trivial next to parsing. Each diagram is a `dot`
subprocess. Build lazily, only for requested diagrams, and cache the tree per action. Comment
collection is already on for every parse (programming-steps design §5.1), so steps in activities
add no parse cost.

---

## 10. Work items

These refine `P3-IMPL-1`/`-2`, `P3-TEST-1`–`3` and `P3-DOC-1`. A phased plan in the style of
`programming-steps-plan.md` will turn them into milestones.

### Implementation

| ID | Task | Done when |
|---|---|---|
| `P3-IMPL-1a` | `model/activity.py`: `ActivityTree` (§3.2); lifting (§3.3) with linker resolution; several blocks, inheritance, `super` (§3.4); `Activity*` skipped at type scope (§2); drop `PssObject.activity` | fixture activities lift to the expected trees |
| `P3-IMPL-1b` | `SourceText` lookups for headers, arm prefixes, join specs and `with` text (§3.3) | text exactly as written for each construct |
| `P3-IMPL-1c` | Step pass (§4): markers through `model/comments.py`, the reach rule, marked controls, prelude traversals, and the warning scope widened (§4.6) | reach and nesting match hand-computed expectations |
| `P3-IMPL-1d` | Capability probe and the token-scan fallback (§4.7) | with the probe forced false, one `pss.step_unsupported` per build, and diagrams without regions |
| `P3-IMPL-2a` | `graph.py` and back-end additions (§6.2), with flowchart output unchanged | new shapes, edge styles and cluster kinds in both back-ends; step flowchart text byte-identical |
| `P3-IMPL-2b` | Lowering to `Graph` (§5.1, §5.2, §6.3), including collapse and inlining (§5.3) | graph data for each construct as expected |
| `P3-IMPL-2c` | Outline renderer (§1, §7.1) | nested list for every fixture activity |
| `P3-IMPL-2d` | `pss:activity-diagram`, `:activity-diagram:` and its prefixed options, `pss_default_options` (§7) | options render; errors per §7.4 |
| `P3-IMPL-2e` | `pss:steps` on a compound action (§4.4, §7.3): the step projection, the new control rows, traversal expansion into activity and `exec body` steps | the §4.5 table, exactly |

### Tests

| ID | Task |
|---|---|
| `P3-TEST-1a` | `tests/fixtures/pss/activity_model.pss`: one activity per construct in §5.1, plus several blocks with `extend`, inheritance with `super`, `bind` (placed and unplaced), labels, inline constraints |
| `P3-TEST-1b` | `tests/fixtures/pss/activity_steps.pss`: the §4.5 DMA example and the reach-rule cases of §4.2 |
| `P3-TEST-2a` | `tests/model/test_activity.py`: lifting, resolution, several blocks, inheritance, `Unknown` |
| `P3-TEST-2b` | `tests/model/test_activity_steps.py`: reach, nesting, marked controls, prelude traversals, proper nesting |
| `P3-TEST-2c` | `tests/model/test_activity_graph.py`: lowering, collapse, inlining and recursion, determinism |
| `P3-TEST-3a` | `tests/autodoc/test_activity_diagram.py` (`sphinx`): directives, options, degradation, links, `pss_default_options` |
| `P3-TEST-3b` | `tests/autodoc/test_activity_steps_table.py` (`sphinx`): `pss:steps` on an action; `:format: flowchart` rejected |
| `P3-TEST-4` | `tests/test_upstream_guards.py`: activity comments absent (flips on `AC1`), `R1`, `R2`, label listing |
| `P3-TEST-5` | Corpus: every activity lifts and lowers with no `Unknown` node, and no step warnings |

### Docs

| ID | Task |
|---|---|
| `P3-DOC-1a` | `docs/usage/activities.md`: the UML mapping, the directives and options, depth, collapse, and what isn't drawn and why. Every example is live or checked |
| `P3-DOC-1b` | `docs/usage/steps.md`: "Steps in activities". The reach rule with a `parallel` example, the step table of a compound action, and the pssparser requirement (§4.7) |
| `P3-DOC-1c` | `docs/usage/diagrams.md`: activity diagrams join the list of kinds; the shape key |

---

## 11. Open questions

Revision 1's questions are settled:
- ~~Default on or off?~~ Off, but allowed in `pss_default_options` (§7.2).
- ~~Outline always, or only without a diagram?~~ `:format:` decides, and `both` puts the outline in
  a collapsed block (§7.1).
- ~~Block on `A1`/`A2`?~~ Moot: they're fixed.
- ~~`:pins:`?~~ Deferred. Parameter nodes for the context action's `bind`s cover the common
  case (§5.1). Pins on every node duplicate the flow table on the same page. Revisit after seeing
  the stdlib example.

Revision 2's questions were decided on 2026-09-29:

1. ~~**Should the reach rule apply to `schedule` as to `parallel`?**~~ **Decided:** yes, the
   `parallel` rule. But every output must keep a `schedule` distinguishable from a `parallel`
   (§4.2, §4.4, §5.1).
2. ~~**Should `select` weights appear in the step table?**~~ **Decided:** omitted by default, in
   the table and the diagram alike, with `:weights:` to show them (§4.4, §7.1).
3. ~~**Should traversals expand into an atomic action's `exec body` steps by default?**~~
   **Decided:** no. Activity and procedural `exec` are kept distinct. `:expand-exec:` opts in,
   under a row that marks the boundary (§4.4).
