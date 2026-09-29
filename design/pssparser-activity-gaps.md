# `pssparser` — activity-construction deficiencies

**Status:** Fixed upstream. `A1`–`A6` verified on 2026-09-29 against pssparser `1ec757b` (its `test_activity_gaps.py`, 49 tests, passes). Kept as the record of the findings. What remains is in `../pssparser/docs/design/sphinx-pss-requests-2026-09-28.md` (`R1`, `R2`) and `-2026-09-29.md` (`AC1`–`AC3`, comments in activities)
**Date:** 2026-09-07
**Scope:** `ActivityDecl` and its statement nodes, as produced by `AstBuilderInt`
**Consumer:** [`activity-diagrams-design.md`](activity-diagrams-design.md) — the static UML activity-diagram renderer
**Clone:** `packages/pssparser` (the working clone; ahead of `~/projects/psstools/pssparser`)

---

## 1. Summary

Six defects in activity construction. All six are **silent**: every fixture
below parses and links without a single marker, and the loss is only visible by
inspecting the resulting AST. Two of them (`A1`, `A2`) mean the AST cannot
represent a correct activity at all; two more (`A3`, `A4`) drop a construct in a
way that makes it *look like a different, valid construct*, which is worse than
dropping it visibly.

| ID | Defect | Severity | Est. |
|---|---|---|---|
| `A1` | `if`/`else` branches are silently discarded | **Blocking** — the AST cannot represent an `if` statement | ~5 lines + AST spec edit |
| `A2` | Join specifications are never constructed (`mkActivityJoinSpec` is a stub) | **Blocking** for `parallel`/`schedule` semantics | ~40 lines |
| `A3` | `replicate` produces a bare `ActivitySequence` — no visitor | High — a parallel expansion silently becomes a plain sequence | ~25 lines |
| `A4` | Scheduling constraints are dropped — no visitor | Medium — a `schedule` block loses its whole point | ~25 lines |
| `A5` | Activity statements carry no source location | Medium — no `[source]` links, no diagnostic anchors, and downstream synthesized-node filters discard them | ~20 lines |
| `A6` | `super;` in an activity produces nothing — no visitor | Low | ~10 lines |

`U-12` (labeled statements hoisted into the enclosing action's symbol scope) is
described in §5 but **not** proposed as a fix — see the reasoning there.

---

## 2. Reproducing

### 2.1 Precondition: the build tree needs regenerating

`ninja -C build` currently fails at HEAD:

```
build/pssparser_ast/src/ExecTargetTemplateParam.h:66:52: error:
  'class pssp::ast::IVisitor' has no member named 'visitExecTargetTemplateParam'
```

`ExecTargetTemplateParam` appears in **no** `ast/*.yaml`, and its generated
header is dated Aug 13 — `build/pssparser_ast/` is a stale generated tree from an
older AST spec, and `IVisitor.h` is no longer even present in it. Delete
`build/pssparser_ast/` (or reconfigure into a fresh build dir) so `pyastbuilder`
regenerates, then run the normal loop: `ninja -C build` →
`ninja -C build install` → `python setup.py build_ext --inplace` (the third step
is required here, since the AST spec is regenerating).

**Caveat on the evidence below.** The runtime observations were produced by the
*currently installed* extension, which was built from an earlier revision; the
Python package source has since moved ahead of it (`Parser.parse` now calls
`MarkerCollector.setMaxErrors`, which the installed `.so` does not have). Every
root cause in §3 was re-verified by reading the **current** `AstBuilderInt.cpp`
and `PSSParser.g4`, and the line numbers cited are current. Re-run §2.2 after
rebuilding to confirm the runtime behavior end-to-end before fixing.

### 2.2 Fixture and probe

`probe.pss` — one activity exercising every construct:

```pss
package probe_pkg {
  component C {
    action A { rand int x; }
    action B { rand int y; }

    action Top {
      A a1, a2;
      B b1;
      rand int c;
      rand int arr[4];

      activity {
        lbl_seq: sequence { a1; b1; }
        if (c > 1) { a1; } else { b1; }
        parallel join_none { a1; b1; }
        parallel join_first (1) { a1; b1; }
        parallel join_branch (a1, b1) { a1; b1; }
        schedule {
          s1: a1;
          s2: b1;
          constraint parallel { s1, s2 };
        }
        select { (c > 2) [3]: a1; b1; }
        match (c) { [0..3]: a1; default: b1; }
        repeat (c) { a1; }
        repeat { a1; } while (c > 0);
        foreach (i : arr) { a1; }
        replicate (i: 4) { a1; }
        atomic { a1; b1; }
        do A with { x == 1; };
        bind a1.x a2.x;
      }
    }
  }
}
```

`probe.py`:

```python
import sys
from pssparser import Parser

p = Parser(collect_docstrings=True)
p.parse([sys.argv[1]])
root = p.link()

def nm(n):
    g = getattr(n, 'getName', None)
    if g:
        try:
            v = g(); return str(v.getId()) if hasattr(v, 'getId') else str(v)
        except Exception: return ""
    return ""

def find(n, w):
    if nm(n) == w: return n
    ch = getattr(n, 'getChildren', None)
    if ch:
        for i in range(len(ch())):
            r = find(n.getChild(i), w)
            if r is not None: return r

top = find(root, "Top")
print("action children:", [type(top.getChild(i)).__name__ for i in range(len(top.getChildren()))])
act = [top.getChild(i) for i in range(len(top.getChildren()))
       if type(top.getChild(i)).__name__ == "ActivityDecl"][0]

def loc(n):
    l = n.getLocation()
    return (l.fileid, l.lineno) if l else None

for i in range(len(act.getChildren())):
    c = act.getChild(i); t = type(c).__name__
    extra = ""
    if t == "ActivityIfElse":
        extra = f" true_s={c.getTrue_s()} false_s={c.getFalse_s()}"
    if t in ("ActivityParallel", "ActivitySchedule"):
        js = c.getJoin_spec()
        extra = f" join_spec={type(js).__name__ if js else None} children={len(c.getChildren())}"
    print(f"{i:2d} {t:32s} loc={loc(c)}{extra}")
```

Two syntax notes that cost time when writing fixtures, neither of them a defect:
`repeat … while` is `repeat { … } while (expr);`, not `repeat while (expr) { … }`;
and a scheduling constraint is `constraint parallel { a, b };`, which is the LRM
form, not `a before b;`. Separately, an `action` declared directly at **package**
scope fails to parse ("unexpected 'action' in this context") — worth confirming
against the LRM, but out of scope here; every fixture wraps actions in a component.

---

## 3. The defects

### `A1` — `if`/`else` branches are silently discarded

**Symptom.** For a well-formed `if (c > 1) { a1; } else { b1; }`, both
`ActivityIfElse.getTrue_s()` and `getFalse_s()` are `None`. `getCond()` is
correctly populated (`ExprBin`). No marker is emitted.

**Root cause.** Not a binding gap — a type mismatch in the AST spec, made silent
by a `dynamic_cast`. `AstBuilderInt.cpp:2521`:

```cpp
ast::IScopeChild *true_body  = mkActivityStmt(ctx->activity_stmt_ann(0));
...
ast::IActivityIfElse *ife = m_factory->mkActivityIfElse(
    cond,
    dynamic_cast<ast::IActivityStmt*>(true_body),     // ← nullptr for a block body
    dynamic_cast<ast::IActivityStmt*>(false_body));
```

The comment above it asserts that the bodies "also implement `IActivityStmt` via
the generated hierarchy." They do not. From `ast/activity.yaml`:

```
ActivityIfElse  <- ActivityLabeledStmt   { cond: UP<Expr>, true_s: UP<ActivityStmt>, false_s: UP<ActivityStmt> }
ActivitySequence <- ActivityLabeledScope <- SymbolScope     # NOT ActivityStmt
```

Every block-shaped body (`sequence`, `parallel`, `schedule`) descends from
`SymbolScope`, so the cast yields `nullptr` and the branch is dropped. A
single-statement body (`if (c) a1;`) does derive from `ActivityStmt` and survives
— which is why this has gone unnoticed.

**Fix.** Retype `true_s` and `false_s` to `UP<ScopeChild>` in
`ast/activity.yaml` and drop both casts. This is exactly what
`ActivityRepeatCount.body` already does (`body: UP<ScopeChild>`), and repeat
bodies work correctly as a result. Requires an AST regeneration and therefore the
full three-step rebuild.

Introducing a common base instead would be a larger change to the generated
hierarchy for no gain here; `ScopeChild` is already the shared base and already
the precedent.

**Test.** `if` with a block body, an `else` with a block body, and the
single-statement forms of each — assert all four bodies are non-null and of the
expected type.

---

### `A2` — join specifications are never constructed

**Symptom.** `ActivityParallel.getJoin_spec()` and
`ActivitySchedule.getJoin_spec()` return `None` for every form, including
explicit `parallel join_none { … }`, `join_first(1)`, `join_select(n)` and
`join_branch(a, b)`.

**Root cause.** `AstBuilderInt.cpp:5915` — the factory helper is a stub:

```cpp
ast::IActivityJoinSpec *AstBuilderInt::mkActivityJoinSpec(PSSParser::Activity_join_specContext *ctx) {
    DEBUG_ENTER("mkActivityoinSpec");
    ast::IActivityJoinSpec *spec = 0;
    DEBUG("TODO: mkActivityJoinSpec");
    DEBUG_LEAVE("mkActivityoinSpec");
    return spec;
}
```

The call sites are correct and already guarded (`AstBuilderInt.cpp:2366` for
`parallel`, `:2395` for `schedule`), and all four AST classes exist
(`ActivityJoinSpecNone`, `First{count}`, `Select{count}`, `Branch{branches}`).
Only the construction is missing. (Note the misspelled `DEBUG_ENTER` label,
`mkActivityoinSpec` — worth fixing while there.)

**Fix.** Dispatch on the four grammar alternatives (`PSSParser.g4:867`):

| Grammar rule | Build |
|---|---|
| `activity_join_none_spec` | `mkActivityJoinSpecNone()` |
| `activity_join_first_spec: TOK_JOIN_FIRST ( expression )` | `mkActivityJoinSpecFirst(mkExpr(...))` |
| `activity_join_select_spec: TOK_JOIN_SELECT ( expression )` | `mkActivityJoinSpecSelect(mkExpr(...))` |
| `activity_join_branch_spec: TOK_JOIN_BRANCH ( label_identifier, … )` | `mkActivityJoinSpecBranch(...)` — see the mismatch below |

**Open question in the AST spec.** `ActivityJoinSpecBranch.branches` is typed
`list<UP<ExprRefPathContext>>`, but the grammar yields a list of
`label_identifier`. Either synthesize a single-element `ExprRefPathContext` per
label (keeps the spec, and lets a later pass resolve the label like any other
reference), or retype the field to `list<UP<ExprId>>` (simpler, honest about what
a join-branch spec actually names). **Decide this before implementing** — the
first option is preferable if label references are ever to be resolved, which is
the same question `U-12` raises.

**Test.** One assertion per join form, on both `parallel` and `schedule`,
including the no-spec case (which must stay `None`, meaning "default join-all",
and must be distinguishable from "not implemented").

---

### `A3` — `replicate` produces a bare `ActivitySequence`

**Symptom.** `replicate (i: 4) { a1; }` yields an `ActivitySequence` in the
activity's child list. The replication index, the optional label array, and the
fact that this is a replication at all are all lost. Nothing distinguishes the
result from a plain `sequence { a1; }`.

**Root cause.** There is no `visitActivity_replicate_stmt` in
`AstBuilderInt.cpp` (and no declaration in `AstBuilderInt.h`). The grammar rule
exists (`PSSParser.g4:940`) and so does the AST class
(`ActivityReplicate <- ActivityLabeledStmt { idx_id, it_label, body }`). ANTLR's
default `visitChildren` therefore descends straight into the nested
`labeled_activity_stmt`, and its result — the sequence — becomes the statement.

**Fix.** Add the visitor, following `visitActivity_foreach_stmt` as the model
(same shape: an index identifier, an expression, a body). Grammar:

```
activity_replicate_stmt:
    TOK_REPLICATE TOK_LPAREN (index_identifier TOK_COLON)? expression TOK_RPAREN
        ( identifier TOK_LSBRACE TOK_RSBRACE TOK_COLON)?
        labeled_activity_stmt
```

Note `ActivityReplicate` has no field for the replication *count* expression —
only `idx_id`, `it_label`, `body`. The count needs a field adding, or the AST
cannot represent `replicate (4)`. Confirm against the LRM and extend the spec.

**Test.** Assert the node type is `ActivityReplicate`, that `idx_id`/`it_label`
are populated when written, and — the regression that matters — that a
`replicate` never comes back as an `ActivitySequence`.

---

### `A4` — scheduling constraints are dropped

**Symptom.** `constraint parallel { s1, s2 };` inside a `schedule` block parses
cleanly and produces nothing. The `ActivitySchedule` has only its traversal
children.

**Root cause.** No visitor for `activity_scheduling_constraint`. The grammar rule
is at `PSSParser.g4:333` and is reachable from two places — `action_body_item`
(`:237`) and `activity_stmt` (`:795`) — and the AST class exists
(`ActivitySchedulingConstraint <- ScopeChild { is_parallel: bool, targets:
list<UP<ExprHierarchicalId>> }`).

**Fix.** Add the visitor. The grammar labels the discriminator directly
(`is_parallel=TOK_PARALLEL | is_sequence=TOK_SEQUENCE`), so `is_parallel` falls
straight out; `targets` is the `hierarchical_id` list. Both parent contexts must
attach it correctly — at action-body scope it is a child of the action, inside an
activity it is a child of the enclosing scope.

**Test.** Both keywords, both scopes, and a three-target list (the grammar
permits `hierarchical_id , hierarchical_id (, hierarchical_id)*`).

---

### `A5` — activity statements carry no source location

**Symptom.** Every activity statement reports `location == (-1, -1, -1)`.
`ActivityDecl` itself is correct (it has both a start location and an
`endLocation` spanning the block), and `ActivityBindStmt` and
`ActivityAtomicBlock` are correct; nothing else is.

**Root cause.** Most `visitActivity_*` methods never call `setLoc`. Audited
against the current file:

| Visitor | line | `setLoc` |
|---|---|---|
| `visitActivity_bind_stmt` | 718 | ✅ |
| `visitActivity_declaration` | 743 | ✅ |
| `visitActivity_atomic_block_stmt` | 2467 | ✅ |
| `visitActivity_action_traversal_stmt` | 2264 | ❌ |
| `visitActivity_sequence_block_stmt` | 2339 | ❌ |
| `visitActivity_parallel_stmt` | 2361 | ❌ |
| `visitActivity_schedule_stmt` | 2390 | ❌ |
| `visitActivity_repeat_stmt` | 2418 | ❌ |
| `visitActivity_select_stmt` | 2494 | ❌ |
| `visitActivity_if_else_stmt` | 2521 | ❌ |
| `visitActivity_match_stmt` | 2548 | ❌ |
| `visitActivity_foreach_stmt` | 2578 | ❌ |
| `visitActivity_data_field` | 980 | ❌ |

**Fix.** Add `setLoc(stmt, ctx->start)` to each, at the point the node is
assigned to `m_activity_stmt`. Mechanical. Setting `endLocation` on the
block-shaped statements as well (as `visitActivity_declaration` does via
`addChild(..., ctx->TOK_RCBRACE()->getSymbol())`) would additionally let a
consumer slice the source text of any nested block, which is worth doing while
the code is open.

**Why it matters downstream.** Beyond `[source]` links and diagnostic anchoring:
`sphinx-pss` treats `lineno < 0` as "compiler-injected, do not document"
(`model/locations.py:is_synthesized`, the same rule that `EnumItem` needed
exempting from as finding `U-2`). A consumer walking activities has to add every
`Activity*` type to that exemption set, which is a workaround for this defect and
can be removed when it lands.

**Test.** Assert a real `(fileid, lineno)` on one statement of each kind — a
loop over the fixture's activity children asserting `lineno > 0` is enough and
will not rot.

---

### `A6` — `super;` produces nothing

**Symptom.** `super;` inside an activity yields no node.

**Root cause.** No visitor for `activity_super_stmt` (`PSSParser.g4:946`), though
`ActivitySuper <- ActivityLabeledStmt` exists. Same failure mode as `A3`/`A4`,
but the rule has no children for the default visitor to descend into, so the
statement simply vanishes.

**Fix.** Add a three-line visitor constructing `ActivitySuper`, applying the
pending label and `setLoc`.

---

## 4. Sequencing

1. **Regenerate the build tree** (§2.1) — nothing below is testable until
   `ninja -C build` succeeds.
2. **`A1`** and **`A2`** — the two that block the activity-diagram work. `A1`
   changes `ast/activity.yaml`, so it forces the full three-step rebuild; do it
   first and let `A2` ride along on the same regeneration.
3. **`A3`**, **`A4`**, **`A6`** — the three missing visitors. Independent of one
   another and of the above; `A3` needs the AST-spec decision about the
   replication count field.
4. **`A5`** — mechanical, touches every visitor, so land it *last* to avoid
   conflicting with 2 and 3.

Two AST-spec decisions to settle before coding: `ActivityJoinSpecBranch.branches`
(§`A2`) and the missing `ActivityReplicate` count field (§`A3`).

---

## 5. Adjacent observations — not proposed as fixes

**Labeled statements are hoisted into the action's symbol scope.** A labeled
activity statement appears *both* as a child of the `ActivityDecl` and as a
direct child of the enclosing action's `SymbolTypeScope`. On the `probe.pss`
fixture, `Top`'s children include the labeled traversals alongside its fields and
the `ActivityDecl`. Whether a label belongs in the action's symbol table is a
linking decision with `bind`- and join-branch-resolution consequences (see the
open question in `A2`), so this is recorded rather than filed: a consumer can
filter `Activity*` at type-scope level for the cost of one line, and changing it
without settling label resolution would be premature. Revisit if `A2` resolves
join-branch labels through the symbol table.

**`do p;` where `p` is an action-typed field parses as a *type* traversal.**
`ActivityActionTypeTraversal` with a `DataTypeUserDefined` target, not
`ActivityActionHandleTraversal`. The bare `p;` form does produce a handle
traversal. This looks like an inherent grammar ambiguity resolvable only after
name resolution, not a defect — consumers must treat "type traversal whose name
matches a field of the enclosing action" as a handle traversal. Recorded so it is
not mistaken for one of the above.

**`SymbolRefPath` remains unusable from Python** (finding `U-3`).
`ExprRefPathContext.getTarget()` returned `None` outright for a type traversal.
Not filed here because `sphinx-pss` resolves traversal targets by name through
its own index by design, so activity work does not depend on it.

**Monitor activity construction is largely unimplemented.** Adjacent, and out of
scope for the activity-diagram work (a temporal language wants a different
diagram), but noted so it is not rediscovered:
`visitMonitor_activity_concat_stmt` carries `// TODO: Handle monitor activity
statements` with its statement loop commented out, and
`visitMonitor_activity_monitor_traversal_stmt` builds its traversal with
`target = 0` under `// TODO: Properly construct target reference path`.

---

## 6. Regression guards on the consumer side

`sphinx-pss` has an `upstream` pytest marker for exactly this situation —
"asserts a `pssparser` behavior sphinx-pss depends on; a failure, not a skip"
(`tests/test_upstream_guards.py`). Each of `A1`–`A6` should get a guard there
asserting the **current, broken** behavior, so that when a fix lands the guard
fails loudly and points at the degradation path that can now be deleted
(`activity-diagrams-design.md` §5.6). That is the mechanism that keeps the
workarounds from outliving their cause.
