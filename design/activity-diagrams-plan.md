# Activity diagrams — Implementation, Test & Doc Plan

**Status:** AD0–AD5 done (2026-09-29). Steps in activities are built and tested through the
stand-in provider (`D4`), and wait on pssparser `AC1`–`AC3` to reach users.
**Companion to:** [`activity-diagrams-design.md`](activity-diagrams-design.md), revision 2. §-refs
point there unless marked otherwise.
**Purpose:** Turn the design into trackable work. Every item has an ID (`AD<milestone>-<area>-<n>`),
a checkbox and a done-condition. Implementation, tests and docs are planned together per milestone,
and a milestone isn't done until all three are. The conventions, Definition of Done and pytest
markers are those of [`implementation-plan.md`](implementation-plan.md) §0.

**Docs rule** (as in `programming-steps-plan.md`): every user-visible behavior ships with a worked
example in the published docs, in the milestone that adds it. Every example is kept honest by a
test: it is included from a test fixture, rendered live by the docs build (`-W`, in
`tests/test_docs_build.py`), or compared against output a test produces.

## Progress log

*(Newest first. Each entry: what shipped, test and doc counts, deviations from the plan.)*

- **2026-09-29 — AD0–AD5 done, in one pass.** Suite: 724 default, 1108 with every marker (was
  605 and 897).

  **Model.**
  - `model/activity.py`: the `ActivityTree` and `activity_for`/`has_activity`, cached on the
    model. Targets come from the linker's `SymbolRefPath`, so `do a1` on a handle is told apart by
    where it resolves.
  - `model/activity_steps.py`: `stepped`, which applies the reach rule and numbering; the
    prelude-traversal check; `unread_marker`; and `activity_steps`, which projects onto
    `StepsDoc`.
  - `model/activity_diagram.py`: the UML lowering.
  - `SourceText` gained `select_arm`, `between_keyword_and_brace`, `with_clause` and
    `braced_after`.
  - `graph.py` gained nine shapes, edge styles, cluster kinds and `caption_notes`. The existing
    flowchart text is byte-identical.
  - `steps.py` gained `Group`, the `select` branch and arm kinds, the `exec` expansion mode and
    `StepsDoc.activity`.

  **Rendering.**
  - `autodoc/activity.py`: `pss:activity-diagram`, with `:format:`, `:depth:`, `:steps:`,
    `:weights:` and `:caption:`. The figure carries a caption and caption notes. The outline is a
    nested list, folded into `<details>` for `both`.
  - `:activity-diagram:` and its `activity-*` options on `autopss{package,component,action,
    object}`, and in `pss_default_options`, validated in `config.py`.
  - The step table gained rows for `parallel`, `schedule`, `select`, `replicate`, `atomic` and
    the `exec` boundary, plus `:expand-exec:` and `:weights:`.

  **Probes and lint.**
  - `_capability.activity_comments_supported()`.
  - `steps_lint` now walks activity statements through the same two comment functions as the
    model.

  **Tests.**
  - The fixtures `activities/{activity_model,activity_ext,xfer_pkg,steps_xfer}.pss`.
  - The roots `test-activity`, `-errors`, `-autodoc`, `-steps` and `-steps-errors`.
  - The unit test files `test_activity`, `test_activity_lowering`, `test_activity_steps`,
    `test_activity_step_tree` and `test_geometric_comments`.
  - The Sphinx test files `test_activity_diagram`, `test_activity_flag`,
    `test_activity_steps_render` and `test_activity_steps_table`.
  - 7 `upstream` guards in `test_upstream_activity.py`, and the corpus sweep
    `test_corpus_activities.py`, which covers 24 activities in 55 linked files.
  - Mermaid output of every fixture activity was checked with Mermaid 11's parser, off-suite as
    in S4.

  **Docs.**
  - The new `docs/usage/activities.md`, with three live diagrams, a live outline and a live
    entry.
  - `docs/usage/steps.md`: "Steps in activities", and "The step table of a compound action",
    whose table a test compares with what the renderer produces through the provider.
  - `docs/usage/diagrams.md`.

  **Deviations.**
  - **A new edge style, `anchor`.** A `with` note was pulled to the top of the diagram by
    `constraint=false`. It is now dotted, undirected, and on the same rank as its node
    (`{ rank=same; … }`).
  - **Parameter nodes aren't placed at the top or bottom** (design 5.1): the `bind` doesn't say
    which way the data flows. They sit wherever `dot` puts them.
  - **Bars label their join specification with `xlabel`**, outside the bar.
  - **The outline unwraps braced bodies**, so an `if`'s `{ }` isn't a level of its own. A
    `sequence` that is a branch of a `parallel` stays.
  - **The diagram comes before a step table in an entry**, not after (design 7.2 corrected). The
    documenter emits it into the generated text; `attach_steps` then inserts the table before
    the members.
  - **An unguarded `select` arm reads "Or:"**, not "Otherwise:", in the table (design 4.4
    corrected).
  - **An abstract traversal is opaque**, with no "Traverse any" row (design 4.4 corrected).
  - **A new pssparser defect, `AC5`,** found while checking the stand-in against the parser: a
    trailing comment after `repeat { } while (c);` reaches no node, in procedural code today.
    Added to the request. There is an `upstream` guard, and a named exception in the agreement
    test.
  - **`pss:steps` on a marked compound action, with today's parser,** gives the
    `pss.step_unsupported` warning, not "has no step markers". The markers are there; the parser
    can't attach them.
  - **`docs/conf.py` suppresses `pss.step_unsupported`**, since the steps page shows markers in
    an activity and the page explains the requirement. The docs test asserts step regions
    exactly when the probe passes.
  - **Two test files were renamed to avoid pytest basename clashes:** `test_activity_lowering.py`
    (was `test_activity_diagram.py` in `tests/model`), and `test_activity_step_tree.py`.

## Decisions

Taken with the design on 2026-09-29 (design §11):

| ID | Decision |
|---|---|
| `D1` | `schedule` follows the `parallel` reach rule, and every output distinguishes the two: the table row, the outline label, and the diagram (hollow bars in a `schedule` cluster) |
| `D2` | `select` weights are omitted by default in the table and the diagram. `:weights:` shows them |
| `D3` | Traversals don't expand into an atomic action's `exec body` steps unless `:expand-exec:` is given, and then under a boundary row |
| `D4` | Steps in activities read comments only through `model/comments.py`, which is what the parser attaches. There is no sphinx-pss re-implementation of placement. Until pssparser `AC1`–`AC3` land, the step logic is tested through a **test-only** comment provider (below), and the build warns (`pss.step_unsupported`) instead of drawing regions |

**The test-only comment provider (`D4`).** `model/activity.py` reads comments through two
module-level functions, `statement_comments` and `block_comments`. They default to
`comments.comments_of` and `comments.closing_comments`. `tests/support.py` provides
`geometric_comments(model)`, which attaches doc-comment tokens to activity statements by source
geometry, following the parser's rules for procedural statements. Tests monkeypatch it in. When
`AC1` lands:
- the `upstream` guard `AD0-TEST-2` fails;
- the provider is deleted;
- the same tests run against the parser's own comments. Any difference between the provider and
  the parser is then a bug in one or the other, and the tests say which.

## Milestones

| Milestone | Theme | Visible to users | Blocked on |
|---|---|---|---|
| `AD0` | Pre-flight: guards, fixture, probes | no | — |
| `AD1` | The activity model: lift, resolve, text | no | — |
| `AD2` | Diagrams and outlines: `pss:activity-diagram` | yes | — |
| `AD3` | `:activity-diagram:` on `autopssaction`, and as a project default | yes | — |
| `AD4` | Steps in activities: regions, collapse, warnings | yes (warning only, until `AC1`) | pssparser `AC1`–`AC3` for end-to-end use |
| `AD5` | The step table of a compound action | yes (once `AC1` lands) | as `AD4` |

`AD4` and `AD5` are built and tested now, through the provider. Their docs describe the feature
and the pssparser it needs. Their live examples are rendered by the docs build, and they show
regions once the parser supports it: the docs test asserts regions **iff** the capability probe
passes.

---

## AD0 — Pre-flight

| ID | Item | Done when |
|---|---|---|
| ☑ `AD0-IMPL-1` | `activity_comments_supported()` in `_capability.py`: parse `action A { activity { /// Step: x\n do A; } }` from memory with `collect_comments=True`, and check that the traversal has a comment. Cached, and it never raises | returns False on today's parser |
| ☑ `AD0-TEST-1` | `tests/fixtures/pss/activities/activity_model.pss`: one activity per construct (design §5.1), several blocks through `extend` (`activity_ext.pss`), inheritance with `super`, placed and unplaced `bind`s, labels, `with` constraints, a context-action parameter `bind` | parses and links with no markers |
| ☑ `AD0-TEST-2` | `upstream` guards in `tests/test_upstream_activity.py`: activity statements carry no comments (`AC1`, flips on the fix); `R1` (`atomic` body unlocated); `R2` (`bind` has no end); labels listed in the action's scope; `do a1` is a type traversal resolving to the field | green today, and each names what to do when it fails |

## AD1 — The activity model

| ID | Item | Done when |
|---|---|---|
| ☑ `AD1-IMPL-1` | `model/activity.py`: the `ActivityTree` node types (design §3.2), with `activity_for(model, qualname)` cached on the model | types importable; `activity_for` on an unknown or non-action name raises `ActivityError` |
| ☑ `AD1-IMPL-2` | Lifting (§3.3): dispatch per kind, typed accessors, `Unknown` | every construct in the fixture lifts |
| ☑ `AD1-IMPL-3` | Resolution (§3.3): handle versus type from `getTarget()`, to qualnames through `SymbolIndex`, extended to action types; `has_activity`, `is_abstract` | every traversal in the fixture resolves; the unresolvable one gives an issue |
| ☑ `AD1-IMPL-4` | `SourceText` lookups (§3.3): arm prefix (guard, weight), join spec, `with` text; reuse `after_keyword`, `choice_label` and `after_body` | text exactly as written |
| ☑ `AD1-IMPL-5` | Which activity (§3.4): several blocks in link order with `is_extension`; inheritance through `extends_target`; `super` resolved to the base | fixture cases |
| ☑ `AD1-IMPL-6` | Remove `PssObject.activity` and `ActivityGraph`; the builder skips `Activity*` at type scope (already true by omission, now tested) | no member entries for labels |
| ☑ `AD1-TEST-1` | `tests/model/test_activity.py`: the tree as text (a `support.activity_outline` helper, like `steps_outline`) for each construct, resolution, several blocks, inheritance, `super`, `Unknown` | green |
| ☑ `AD1-TEST-2` | `tests/model/test_source_text.py` additions for the new lookups | green |

## AD2 — Diagrams and outlines

| ID | Item | Done when |
|---|---|---|
| ☑ `AD2-IMPL-1` | `graph.py`: shapes `action`, `initial`, `final`, `flow_final`, `bar`, `hollow_bar`, `merge`, `note`, `parameter`; `GraphEdge.style`/`directed`; `Cluster.kind`; `Graph.caption_notes` (§6.2) | the existing flowchart text is byte-identical (existing tests unchanged) |
| ☑ `AD2-IMPL-2` | Back-ends: dot and Mermaid for each addition (§6.2), plus `group` and `ordering` for bars (§6.3) | text tests per shape, edge style and cluster kind |
| ☑ `AD2-IMPL-3` | `model/activity_diagram.py`: lowering to `Graph` (§5.1) with single entry and exit, `join_none`, `bind` placement and caption notes, `:depth:` inlining with recursion cut (§5.3), `:weights:` | graph data per construct |
| ☑ `AD2-IMPL-4` | Outline renderer: a nested bullet list (§1, §7.1) | per-construct text |
| ☑ `AD2-IMPL-5` | `autodoc/activity.py`: `pss:activity-diagram` with `:format:`, `:depth:`, `:weights:` and `:caption:`; figure with caption and caption notes; alt text; degradation to the outline; errors (§7.4); `pss.activity` warnings once per activity | a Sphinx build of the fixture under `-W` |
| ☑ `AD2-TEST-1` | `tests/model/test_activity_lowering.py`: lowering, as readable edge and node lists (as in `test_steps_flowchart.py`) | green |
| ☑ `AD2-TEST-2` | `tests/autodoc/test_diagrams.py` additions: each new shape, edge style and cluster kind in both back-ends; `dot` accepts the text | green |
| ☑ `AD2-TEST-3` | `tests/autodoc/test_activity_diagram.py` (`sphinx`, root `test-activity`): diagrams, outline, `both`, errors, `off` and no `dot` degrade to the outline, links, determinism | green |
| ☑ `AD2-DOC-1` | `docs/usage/activities.md`: the UML mapping as a key, with live diagrams of the fixture-style example (`docs/pss/`), options, and what isn't drawn and why. `docs/usage/diagrams.md`: activity diagrams join the list | docs build `-W` |

## AD3 — `:activity-diagram:` on `autopssaction`

| ID | Item | Done when |
|---|---|---|
| ☑ `AD3-IMPL-1` | The documenter emits `.. pss:activity-diagram::` into an action's generated reStructuredText when `activity-diagram` is set, mapping the `activity-*` options (§7.2); nothing for an action with no activity | members of an `autopsscomponent :members:` get diagrams |
| ☑ `AD3-IMPL-2` | `pss_default_options` accepts `activity-diagram` and the `activity-*` options; values checked in `config.py` | a bad default is a config error that lists the values |
| ☑ `AD3-TEST-1` | Sphinx tests: the flag, the prefixed options, the project default, members, an atomic action (nothing) | green |
| ☑ `AD3-DOC-1` | `activities.md`: the flag and the project default, with a live example | docs build `-W` |

## AD4 — Steps in activities

| ID | Item | Done when |
|---|---|---|
| ☑ `AD4-IMPL-1` | `model/activity_steps.py`: the step pass (§4.2): the reach rule per block kind (`D1`), nesting, marked controls, empty steps, prelude traversals → `pss.step_prelude_call` with "traversal" in the message | the provider-based unit tests pass |
| ☑ `AD4-IMPL-2` | `steps_lint.py`: activity bodies become valid marker positions, and `step_syntax`/`step_empty` run there (§4.6); a marker above `activity` stays misplaced | lint tests |
| ☑ `AD4-IMPL-3` | Diagram: step clusters (`Cluster.kind = "step"`), the proper-nesting assertion (§4.3), `:steps: regions / collapsed / none` (§5.2), inlined steps numbered `c1 › 2.1` (§5.3) | graph tests |
| ☑ `AD4-IMPL-4` | Outline: steps as numbered list items that hold their range | text tests |
| ☑ `AD4-IMPL-5` | Gating (§4.7): with the probe false, no step pass; a token scan of the activity's span, and one `pss.step_unsupported` per build if it finds a marker | Sphinx test with the probe forced each way |
| ☑ `AD4-TEST-1` | `tests/support.py`: `geometric_comments` (`D4`), with its own tests on procedural code, where it must agree with the parser | green |
| ☑ `AD4-TEST-2` | `tests/model/test_activity_steps.py`: reach per block kind, including a `schedule` (`D1`); a sequence branch with a procedure; select arms; marked controls; prelude traversals; several blocks; proper nesting | green |
| ☑ `AD4-TEST-3` | Graph and Sphinx tests for regions, collapse, `none`, and `pss.step_unsupported` | green |
| ☑ `AD4-TEST-4` | Corpus: every activity in the parseable buckets lifts, lowers and step-passes with no `Unknown` node, exception or step warning | green nightly |
| ☑ `AD4-DOC-1` | `docs/usage/steps.md` "Steps in activities": the reach rule with a `parallel` and a `schedule` example; the pssparser requirement and the warning. `activities.md`: regions and collapse | docs build `-W`; regions asserted iff the probe passes |

## AD5 — The step table of a compound action

| ID | Item | Done when |
|---|---|---|
| ☑ `AD5-IMPL-1` | `steps_for` on an action with an activity and no `:exec:`: project the stepped `ActivityTree` to a `StepsDoc`, with new control kinds for `parallel`, `schedule`, `select`, `replicate`, `atomic` and `super` (§4.4) | the design §4.5 table, exactly |
| ☑ `AD5-IMPL-2` | Traversal expansion (§4.4): compound targets by default under `:expand-calls:`/`:depth:`; abstract targets as "Traverse any `A`"; recursion cut; `:expand-exec:` (`D3`) with the boundary row; `:weights:` (`D2`) | tests per mode |
| ☑ `AD5-IMPL-3` | Table rows for the new controls; `:format: flowchart`/`both` rejected for an activity, pointing at `pss:activity-diagram` | Sphinx tests |
| ☑ `AD5-TEST-1` | `tests/model/test_activity_step_tree.py` and `tests/autodoc/test_activity_steps_table.py` | green |
| ☑ `AD5-DOC-1` | `steps.md`: the step table of a compound action, with `:expand-exec:` | docs build `-W` |

---

## Tracker

| Milestone | Impl | Tests | Docs | Status |
|---|---|---|---|---|
| `AD0` | ☑ | ☑ | — | done |
| `AD1` | ☑ | ☑ | — | done |
| `AD2` | ☑ | ☑ | ☑ | done |
| `AD3` | ☑ | ☑ | ☑ | done |
| `AD4` | ☑ | ☑ | ☑ | done |
| `AD5` | ☑ | ☑ | ☑ | done |
