# Programming steps — Implementation, Test & Doc Plan

**Status:** S0–S5 done (2026-09-29): step tables, flowcharts and the migration checker ship.
**Companion to:** [`programming-steps-design.md`](programming-steps-design.md) (the design; §-refs
below point there unless marked otherwise)
**Purpose:** Turn the design into trackable work. Every item has an ID (`S<milestone>-<area>-<n>`),
a checkbox and a done-condition. Implementation, tests and docs are planned together per milestone,
and a milestone isn't done until all three are. The conventions, Definition of Done and pytest
markers are those of [`implementation-plan.md`](implementation-plan.md) §0.

**Docs rule (M. Ballance, 2026-09-28):** every user-visible behavior ships with a worked example in
the published docs, in the milestone that adds it, not later. Every example is kept honest by a
test: it's either included from a test fixture, rendered live by the docs build (which runs under
`-W` in `tests/test_docs_build.py`), or, for warnings, linted and compared against the output the
page shows (`tests/test_docs_step_examples.py`). An example that stops being true fails the suite.

## Progress log

*(Newest first. Each entry: what shipped, test/doc counts, deviations from the plan.)*

- **2026-09-29 — S5 done.** `sphinx_pss/checkers/steps.py`: `StepCommentChecker`
  (`sphinx-pss-steps`, marker `SPSS001`, severity warning, `runs_without_link`). It tokenizes each
  of `ctx.files`, and for every comment token that `doc_form` classes as plain, it matches
  `MARKER_RE` on each line `strip_markers` gives, so it shares rule 2 and the comment-form rules
  with the Sphinx side instead of restating them. `sphinx_pss/checkers/__init__.py` has
  `register()`, and `pyproject.toml` the `pssparser.extensions` entry point `sphinx-pss`. Nothing
  there imports Sphinx. 8 `unit` tests in `tests/checkers/test_step_checker.py`, run through
  `pssparser`'s own `main` so discovery goes through the installed entry point. Docs:
  "Migrating existing comments" in `docs/usage/steps.md`, whose config, source and complete
  output a test runs and compares. Suite: 605 default, 897 with every marker. Deviations:
  - **Position isn't checked.** A plain marker anywhere is reported, not only in a body: the
    checker has no parse to consult, and a converted marker in the wrong place is then
    `pss.step_misplaced` in the Sphinx build. Documented.
  - **The message names the form to write:** `'/// Step: ...'` for a line comment,
    `'/** Step: ... */'` for a block comment. The column is the `S` of `Step`, and the extent
    covers the line, so `pssparser` underlines it.
  - **`--checker sphinx-pss-steps` alone doesn't enable it.** Selecting a checker and enabling
    it are separate in pssparser; `enabled` is the switch, as decided in §1.3.

- **2026-09-29 — S4 done.** `model/graph.py` (the back-end-free diagram IR: nodes with a meaning
  rather than a drawing, nested clusters, links by qualified name), `model/steps_flowchart.py` (the
  lowering) and `autodoc/diagrams.py` (`P2-IMPL-5`: dot and Mermaid text, `pss_diagrams`, the
  one-warning degradation, and link resolution at `doctree-resolved`). `sphinx_pss` now loads
  `sphinx.ext.graphviz`. `:format: flowchart` and `both` are accepted by `pss:steps` and, through
  `STEP_OPTIONS`, by the `:steps:` flag. Test root `test-steps-flowchart`; 25 `unit` tests in
  `tests/model/test_steps_flowchart.py`, 16 in `tests/autodoc/test_diagrams.py` (text of both
  back-ends; Graphviz, `off`, missing `dot`, Mermaid with and without its extension, links in SVG
  and PNG, determinism for both back-ends), 3 more in `test_docs_build.py`. Mermaid output was
  checked with Mermaid 11's own parser (`mermaid.parse` under jsdom) for every fixture flowchart;
  not a test, since it needs Node. Docs: a live `set_speed` flowchart and the shape key in
  `docs/usage/steps.md`, `:format: both` on the Ethernet example, and the new
  `docs/usage/diagrams.md` with a Mermaid example a test regenerates. CI and nightly install
  Graphviz; `sphinxcontrib-mermaid` joins the test dependencies and a `mermaid` extra. Suite: 597
  default, 889 with every marker. Deviations:
  - **No PNG warning.** §5.3 of `activity-diagrams-design.md` expected a PNG build to lose every
    link. It doesn't: `sphinx.ext.graphviz` gives a PNG a client-side image map, and
    `test_png_output_keeps_links_in_an_image_map` checks it. The one-time warning was not built;
    the docs recommend SVG for sharpness, and the docs site uses it.
  - **A flowchart that can't be drawn is its table.** With `dot` missing, Mermaid unloaded or
    `pss_diagrams = "off"`, `:format: flowchart` renders the table instead of nothing, so the page
    still documents the procedure; `both` renders the table alone. The warning is once per build,
    at the first page that asks, as `pss.diagrams`.
  - **Loop symbols.** `while` and `repeat … while` are a diamond with the condition and a `yes`
    back-edge (before and after the body); `repeat (n)` and `foreach` are a hexagon, the flowchart
    loop-limit symbol, with an unlabelled back-edge and a `done` exit. The design's "back-edge
    labelled with the loop condition" became the condition on the diamond.
  - **No join nodes.** Each construct lowers to its open exits, so an empty arm is an edge past the
    branch, and an `if` without `else` falls through on `no`.
  - **Marked controls aren't merged** as they are in the table: the step's box comes first, then
    its diamond or hexagon.
  - **Linked and cut calls** are a double-bordered box (the predefined-process symbol) with the
    table's text. Inline expansions are dashed clusters linked to the callee (SVG only; Mermaid
    subgraphs can't link). Links need `securityLevel: 'loose'` in Mermaid; documented.
  - **Source links:** every node carries its `file:line` as hover text. Links to the source line
    wait on viewcode (`P3-IMPL-4`), as the table's Source column does.

- **2026-09-29 — S3 done.** `autodoc/steps.py`: the `pss:steps` directive, the table renderer
  (`StepsTable`) and `attach_steps` for the `:steps:` flag on `autopssfunction`, `autopssaction` and
  `autopsscomponent`; `pss_default_options` rejects `steps`; `viewcode.source_link` is the Source
  column's hook for `P3-IMPL-4`. Test roots `test-steps` (every form, clean under `-W`),
  `test-steps-errors`, `test-steps-warnings` and `test-steps-unlinked`; 17 `sphinx` tests in
  `tests/autodoc/test_steps_table.py`, 1 more in `test_setup.py`, 3 more in `test_docs_build.py`, 1
  more example in `test_docs_step_examples.py` (which now checks `pss.step_prelude_call` as well as
  lint). Docs: `docs/usage/steps.md` has five live tables and the prelude warning;
  `docs/examples/steps.md` renders the Ethernet fixture in both numberings; `directives.md`,
  `CHANGELOG.md` and `README.md` updated. Suite: 553 default, 845 with every marker. Deviations:
  - **An inline call expansion has no row.** The callee's steps are sub-steps of the calling step,
    numbered from it, as the FRM nests them; their Source column shows they come from the callee. A
    linked call is a row, "Follow the steps of `f`", whose name links to `f`'s entry when a page
    documents it. A cut call is a row, "Repeat from step 1 (`f`)".
  - **A marked `if`** is one row: the title, and under it the first arm's condition. That arm's
    steps sit one level in; later arms are rows at that level with their steps under them. A marked
    loop or `match` is the same, with the loop's label or "Depending on `e`:".
  - **Arms shown:** an `if` chain's arms up to the last one with steps (an empty arm before a full
    one still states a condition); a `match`'s choices only when they hold steps.
  - **Indentation is em spaces** in the Step column, so every builder keeps it, not CSS.
  - **Source paths** are relative to the `pss_source_dirs` entry the file was found under, else to
    `conf.py`'s directory, else the base name.
  - **A body with no markers** is a `pss.steps` warning at the directive, with no table. A
    target that is neither a function nor a type with `exec` blocks (an enum, say) is an error
    naming its kind. A bare or relative target name is resolved through the index first.
  - **The model's messages say "the exec option"**; the directive prints it as `':exec:'`.
  - A markup error in a step's detail is reported each time a table shows the step, like a doc
    comment rendered twice; only the prelude warning is de-duplicated per build.
  - **Outline numbering restarts at 1 below the fourth level** (S2), which reads as ambiguous; the
    docs' component example uses decimal. A candidate for a later refinement, not a blocker.

- **2026-09-28 — S2 done.** `model/steps.py` builds the numbered step tree of a function or a
  type's `exec` blocks (`steps_for`); `model/source_text.py` reads condition text from the token
  stream; `model/calls.py` resolves calls through `refs.occurrences()`. Fixture
  `tests/fixtures/pss/steps/` (Ethernet bring-up plus two extensions). Tests: 37 in
  `test_steps_tree.py`, 14 in `test_steps_calls.py`, 11 in `test_steps_prelude.py`, 5 in
  `test_steps_extend.py`, 19 in `test_source_text.py`, 1 more in `test_step_markers.py`, 1 more in
  `test_docs_step_examples.py`, and a new `corpus` sweep, `test_corpus_steps.py`, which builds a tree
  for all 128 bodies in the 55 corpus files that link (102 functions, 26 `exec` blocks) and bounds
  all 269 of their simple statements. Suite: 530 default, 822 with every marker. Deviations:
  - **A marker on a control statement flags the node instead of titling it.** The step keeps the
    title, and its first child is the `Branch` or `Loop`, with `marked=True`; a renderer draws the
    two as one row, the condition as secondary text. Design §5 had a `title` field on the control
    node, which would have left the rest of the step's range with no parent.
  - **The prelude check covers every statement outside every step**, not only those before the
    first: a call after a nested step's block but before the outer first step is left out of the
    table just the same. The message says "outside every step".
  - **A control statement is shown when it holds an expanding call**, not only a marker, so the
    callee's steps keep their condition (`if (n > 0) { pong(); }`).
  - **Calls expand from anywhere in a step's simple statements**: arguments, assignment right-hand
    sides, declaration initializers and `return` values, in source order. Never from conditions.
  - **A call's extent is found in the token stream** (its start to the `;` at depth 0), and the
    calls are the function occurrences inside it. No expression walk.
  - **Conditions are found from bodies, not by scanning forward from the `if`.** Clauses and match
    choices have no location, but their bodies do: the `)` just before a body closes its
    condition, which works the same for `if` and `else if`. `repeat … while` reads after its body.
  - **Targets are looked up in `SymbolIndex`** (the builder's naming walk), since
    `SymbolScopeUtil.getQname` raises on an unknown name. `ParsedModel.derived` / `cached()` hold
    the per-model indexes.
  - **`S2-IMPL-10` is the model half**: `steps_for` raises `StepsUnavailable` on a model that
    didn't link. The directive's single warning is part of `S3-IMPL-1`.
  - `Marker.detail_line` added for `S3-IMPL-3`'s per-line attribution. `:depth:` counts levels
    of calls (0 expands none); past it, calls are opaque. Outline numbering starts its cycle again
    below the fourth level. Every `if` arm and `match` choice is kept, empty ones included; the
    renderer decides what to draw.
  - **Docs:** nothing new is visible, but the steps page's claim about how the placements example
    nests is now checked by `test_docs_step_examples.py`.

- **2026-09-28 — S1 done.** `model/steps_markers.py` parses markers; `model/steps_lint.py` checks
  them across the whole model once per build, and `build_shared_index` reports each problem as a
  `pss.step_*` warning at the comment's `.pss` line. Tests: 25 in `test_step_markers.py`, 24 in
  `test_step_lint.py`, 3 `sphinx` tests in `tests/autodoc/test_step_warnings.py` (locations,
  `suppress_warnings`, once per build), 97 `corpus` files with **zero** step warnings, 5 in
  `tests/test_docs_step_examples.py`, and a `test_docs_build.py` check on the fixture excerpt. Suite: 443 default, 638 with every marker. Deviations:
  - **Docs moved forward from S3** at the user's request, with the docs rule above.
    `docs/usage/steps.md` now covers the marker rules, the placements and the three lint warnings,
    each with an example that a test checks. S3 extends the page rather than writing it.
  - **Near misses are only looked for inside bodies.** A declaration's doc comment is prose, where
    `/// Steps are generated by the tool.` is a sentence, not a typo. On declarations only an exact
    marker is reported (`pss.step_misplaced`). The plan said "in `///`/`/**` comments only", which
    would have warned on API prose.
  - **The near-miss pattern needs a separator after the word**: `steps?` followed by a space, colon,
    period, digit or the end of the line. `Stepper`, `Stepping` and `Step-by-step` are words.
  - **`pss.step_empty` also covers a step with no statements**: a marker another marker follows
    directly (in the same comment, or on the same statement), and a marker after a block's last
    statement. Design §3.5 listed only the no-title case. A bare `Step:` is reported once, as
    having no title.
  - **A trailing marker (`w(1); /// Step: …`) starts its step at the statement it trails.** So a
    leading marker on the same statement has nothing in it. S2's ranges must agree.
  - **The lint walks `user_units()`, not the linked tree**: comments are attached there, each file
    is visited once, and a model that didn't link is still checked.
  - **`parse_markers(lines)` returns every marker in a comment**, and `parse_marker` the first. The
    plan named only `parse_marker`. `Marker` is `(title, detail, number, line)`, with the detail
    dedented and trimmed.

- **2026-09-28 — S0 done.** Comment collection is on; `model/comments.py` is the one reader of the
  comments API; pss-corpus is wired in. Tests: 40 in `test_comments.py`, 6 in
  `test_comment_collection.py`, 14 `upstream` guards in `test_upstream_steps.py`, and 98 `corpus`
  tests (97 files compared on/off, plus the cost recording: **+2.0%**, matching design §5.1).
  Suite: 385 default + 97 corpus, all green. Deviations:
  - **A marker after a block's last statement is on the block, not a statement.** The parser keeps
    it on the enclosing scope's `getTrailing_comments()`. Found while probing; not in §1.1.
    `comments.closing_comments(scope)` reads it and a guard pins it. S1 must read it too, or an
    empty trailing step (`pss.step_empty`) goes unreported.
  - **`comments.py` API** is `comments_of(node)` (all attached, in source order: the parser lists a
    trailing comment first), `leading_comments(node)`, `closing_comments(scope)`, and
    `comment_runs(comments)`, which merges a `///` run (one `Comment` per line) back into one
    comment for rule 3. Items are `SourceComment(raw, lines, form, placement, is_block, fileid,
    line, col)`; `lines` maps one-to-one onto source lines.
  - **The corpus finder is `tests/corpus/corpus_finder.py`, not a `conftest.py`**, and the snapshot
    helper is `tests/support.py`: without `__init__.py` files, every `conftest` imports as
    `conftest`. A missing corpus fails only the selected corpus tests; collection never fails, so
    the default suite runs without a corpus.
  - **New fixture `tests/fixtures/pss/steps_pkg.pss`**, a small MAC driver with markers in
    functions, a callee, component and action `exec` blocks, and an `extend`. S1–S3 build on it.
  - Nightly now names `-d default-dev` explicitly, since that dep-set carries the corpus.
- **2026-09-28 — decisions confirmed.** D1–D6 (§2) accepted as proposed. S0 can start.
- **2026-09-28 — readiness review.** Every parser capability the design depends on was re-verified
  against pssparser `1ec757b`. The evidence is in §1, so implementation doesn't re-derive it. One
  gap was found and resolved (member-call resolution, §1.2), and six plan-level decisions were
  taken (§2).

---

## 1. Readiness review — verified 2026-09-28

### 1.1 What the parser provides (all verified with probes)

| Need | How | Evidence |
|---|---|---|
| Marker comments on statements, every placement | `Parser(collect_comments=True)`; `ScopeChild.getComment(i)` / `numComments()` | Leading, trailing, and blank-line-separated markers all captured, in function bodies and `exec` blocks (design §6.1) |
| Comment style and placement | `Comment.getRaw()` (verbatim, so `///` vs `//`), `getPlacement()` (0 leading, 1 trailing, 2 detached), `getIs_block()` | Probed per form. `getText()` leaves a stray `/` on `///`, so use `getRaw()` |
| **Turning on comment collection changes nothing existing** | `collect_comments=True` in `parse_model` | Object snapshot of the fixture plus 97 corpus units (41 degraded): **0 differences** against `collect_docstrings=True` |
| Function bodies | `SymbolScopeUtil(root).getQname(q)` → `SymbolFunctionScope`; `getTarget()` → `FunctionDefinition`; `getBody()` | Probed for package and component functions |
| `exec` blocks, including from `extend` | The linked `SymbolTypeScope`'s children include every `ExecBlock` (`getKind()` → `pssparser.ast.ExecKind`), the declaration's first, then each extension in **file order** | Swapping the file order swaps the extension blocks, as design §4.5 requires |
| Statement start positions | `getLocation()` on every procedural statement; `if` clause bodies are located | Probed |
| Condition text | `pssparser.tokens.tokenize` (lossless) plus the statement start position; take the tokens inside the keyword's parentheses | Prototyped: `if`, `while`, `repeat`, `match` return source text exactly, parentheses preserved |
| Statement kinds | `ProceduralStmtExpr` (call as a statement), `ProceduralStmtAssignment`, `ProceduralStmtDataDeclaration` (`getInit()`), `ProceduralStmtIfElse` (`numIf_then()`, `getIf_then(i)` → clause with `getCond()`/`getBody()`, `getElse_then()`), `ProceduralStmtWhile`, `ProceduralStmtRepeat`, `ProceduralStmtMatch` | Probed |

### 1.2 Call resolution — one gap, resolved

A call's `ExprRefPathContext.getTarget()` resolves **only the first path element**. `w(1)` and a bare
`comp_fn()` resolve to the function, but `comp.comp_fn()` and `sub.sub_fn()` resolve to the `comp`
or `sub` field. Per-element `ExprMemberPathElem.getTarget()` returns a plain integer.

**Resolution, verified:** `refs.occurrences()` binds every identifier, including member calls
(`comp.sub.sub_fn()` → `sub_fn`'s `FunctionPrototype`). The route is:

1. Take the call's **last** path element, `hier_id.getElem(n-1).getId()`, and its location
   `(fileid, lineno, linepos)`.
2. Look up the occurrence at that position.
3. Map `occurrence.decl` (a `FunctionPrototype`, which has no parent) to its `SymbolFunctionScope`,
   using a dict built by walking the linked tree and keying each `getPrototype(i)`. The wrappers
   hash and compare by node.

Verified on package calls, component calls from an action `exec`, `comp.sub.fn()`, and component
`exec init_down` calls. Standard-library calls (`comp.ctrl.write_val(5)`) resolve with resolution
`library` to a template prototype that isn't in the map. That's correct: library functions have no
steps and stay opaque.

### 1.3 What is not ready, and what that means

| Dependency | State | Consequence |
|---|---|---|
| `P2-IMPL-5` shared diagram back-end | Not built: `autodoc/diagrams.py` is a stub | Flowcharts need it first. Decided: this plan builds it (§2, D1) |
| `P3-IMPL-4` viewcode | Not built: `viewcode.py` is a stub | Source column shows `file:line` text until it lands (§2, D2) |
| pssparser `PERF-1` (always `fill()`) | Filed, not landed | Only `S0-TEST-4`, the performance guard, waits on it |
| pss-corpus in this repo | Not a dependency; the `corpus` marker has no tests | `S0-IMPL-3` wires it in |
| Checker plug-ins off by default | No such switch in the checker API; checkers declare `options_schema` with defaults | `S5` uses an `enabled` option defaulting to `false` |

---

## 2. Plan-level decisions

Taken while planning, with the recommended default. **All six were confirmed by M. Ballance on
2026-09-28.** Strike through and annotate if one changes later.

| ID | Question | Decision | Why |
|---|---|---|---|
| D1 | Who builds `P2-IMPL-5` (diagram back-end)? | **This plan (`S4-IMPL-1`)**, scoped to the implementation-plan item, plus the two shared-layer additions activity diagrams also need (clustering, node links) | Flowcharts are its first consumer; activity and flow diagrams then reuse it |
| D2 | Source column before viewcode exists | Plain `file:line`; a link once `P3-IMPL-4` lands | The table must not wait on viewcode |
| D3 | Does an **assignment** from a call count as a prelude call (`x = read_reg(STATUS);`)? | **Yes.** Only data declarations are exempt. Calls in `if`/loop *conditions* do not count | It's device activity missing from the table. The user exempted "variable initializations", which is declarations |
| D4 | Addressing `exec` blocks | **`:exec: <kind>` option** on a type target, **not** `type::kind` in the argument. Refines design §7.1 | `body` etc. are not reserved words, so `dma_c::start::body` is ambiguous with a nested member called `body` |
| D5 | Scope of marker lint (`pss.step_syntax`, `pss.step_misplaced`, `pss.step_empty`) | **Whole model**, once, at index build. `pss.step_prelude_call` only for bodies actually rendered | Marker typos are mistakes wherever they are, and the scan is cheap. Prelude calls matter only where a table is shown |
| D6 | Keyword configurable (design §8 Q6)? | **Fixed** `Step:` | Portable across projects; no configuration surface to test |

---

## 3. Milestone S0 — Foundations

**Theme:** comments available everywhere, with guards on every parser behavior this feature
depends on.

### Implementation
| ID | Task | Done when |
|---|---|---|
| ☑ `S0-IMPL-1` | `model/parse.py`: `Parser(collect_comments=True)`, in both the linked and degraded paths | existing 325 tests green; object snapshot unchanged (§1.1) |
| ☑ `S0-IMPL-2` | `model/comments.py`: ~~`leading_comments(node)` → `[(raw, text, placement, is_block, location)]`~~ `comments_of` / `leading_comments` / `closing_comments` / `comment_runs` → `SourceComment` (see progress log); `doc_form(raw)` → `line_doc` (`///`), `block_doc` (`/**`), `plain`; `strip_markers(raw)`. The only module that reads the comments API | unit-tested per form and placement |
| ☑ `S0-IMPL-3` | Wire pss-corpus in: `ivpm.yaml` `default-dev` dependency (`type: raw`); ~~`tests/corpus/conftest.py`~~ `tests/corpus/corpus_finder.py` finder following the corpus README contract (`$PSS_CORPUS`, then `packages/pss-corpus`, then the sibling checkout; **missing corpus fails, doesn't skip**); nightly CI fetches it | `-m corpus` finds it locally and in nightly |

### Tests
| ID | Task | Done when |
|---|---|---|
| ☑ `S0-TEST-1` | `upstream` guards, one per §1.1 row: comment placements, `getRaw()` forms, `ExecBlock` kinds and extension order, statement start positions, the token contract, and member-call resolution through `refs.occurrences()` | green; each names the design section that depends on it |
| ☑ `S0-TEST-2` | `tests/model/test_comments.py`: every form × placement, including a `///` run with a `Step:` line in the middle | green |
| ☑ `S0-TEST-3` | Snapshot regression: `collect_comments` on vs off over the fixtures gives identical objects | green |
| ◐ `S0-TEST-4` | Performance guard (`corpus`): parse + link with comment collection within 5% of doc-comments-only. **Blocked on pssparser `PERF-1`**; until then, record numbers without asserting | numbers recorded (`test_corpus_comment_cost.py`, +2.0% on 2026-09-28); the assertion is enabled once `PERF-1` lands (`PERF_1_LANDED`) |

### Docs
| ID | Task | Done when |
|---|---|---|
| ☑ `S0-DOC-1` | `CHANGELOG.md` Unreleased: comment collection is on (no user-visible change); pss-corpus becomes a dev dependency | entry present |

---

## 4. Milestone S1 — Markers and marker lint

### Implementation
| ID | Task | Done when |
|---|---|---|
| ☑ `S1-IMPL-1` | `model/steps_markers.py`: `parse_marker(comment_lines)` → `Marker(title, detail_lines, number, line)` or `None`. Rule 2's regex, exact; `Step N:` accepted and the number dropped; the lines of the same comment after the marker become the detail; lines before it are ignored (design §3.1) | unit-tested against the design's examples |
| ☑ `S1-IMPL-2` | Near-miss classifier for `pss.step_syntax`: in `///`/`/**` comments only, a first word matching `steps?` case-insensitively without a valid marker; `pss.step_empty` for a marker with no title | unit-tested; plain `//` never classified |
| ☑ `S1-IMPL-3` | Whole-model lint pass (D5): walk declarations and bodies once after linking, reading each block's `closing_comments` as well as its statements' (a marker after the last statement is `pss.step_empty`); `pss.step_misplaced` for a valid marker outside a function body or `exec` block. Diagnostics become Sphinx warnings, `type="pss"`, at the comment's `.pss` line | lint runs once per build; warnings located at the comment |

### Tests
| ID | Task | Done when |
|---|---|---|
| ☑ `S1-TEST-1` | `tests/model/test_step_markers.py`: valid forms (`Step:`, `Step 3:`, `Step 2.1:`, with detail, `/** */`), and invalid ones (`step:`, `STEP 3 Reset`, `Steps:`, `Step` with no colon, `Step:` with no title) | green |
| ☑ `S1-TEST-2` | `tests/model/test_step_lint.py`: misplaced on a struct, field, action and at package scope; nothing from plain `//` or `/* */`, including `// Step:` | green |
| ☑ `S1-TEST-3` | `corpus` sweep: **zero** step warnings across every parseable pss-corpus bucket, which contains no markers (design `STEP-T3`) | green |

### Docs
| ID | Task | Done when |
|---|---|---|
| ☑ `S1-DOC-1` | `docs/usage/steps.md` (was `S3-DOC-1`'s first half): why steps exist, the marker rules, where markers go, the three lint warnings with `suppress_warnings`. The first example is included from `steps_pkg.pss`; each warning example is linted by `tests/test_docs_step_examples.py` and must give exactly the output the page shows | builds under `-W`; examples checked |
| ☑ `S1-DOC-2` | `CHANGELOG.md` Unreleased: the marker lint | entry present |

---

## 5. Milestone S2 — The step tree

### Implementation
| ID | Task | Done when |
|---|---|---|
| ☑ `S2-IMPL-1` | `model/steps.py` node types (design §5): `StepsDoc(target, blocks)`, `Step`, `Branch`, `Loop`, `CallExpansion`, `ExtensionGroup` (provenance row, design §4.5) | dataclasses with `source: SourceRef` |
| ☑ `S2-IMPL-2` | Body lookup: a function qualname → `SymbolFunctionScope` → definition body; or a type qualname plus exec kind → every `ExecBlock` of that kind, in linked order, grouped by declaration vs `extend` site (§1.1, D4). The `ExecKind` name map lives here | fixture targets resolve; an unknown kind is an error listing the valid kinds |
| ☑ `S2-IMPL-3` | Ranges and nesting (design §4.1–§4.2): a marker covers statements to the next marker in its block; markers in nested blocks become sub-steps; a nested block in the prelude hangs off its control node | unit-tested on hand-built bodies |
| ☑ `S2-IMPL-4` | Control flow (design §4.3): `if`/`else if`/`else`, `while`, `repeat … while`, `repeat (n)`, `foreach`, `match`, shown only when they contain steps; a marker on the control statement becomes its title | each kind unit-tested |
| ☑ `S2-IMPL-5` | `model/source_text.py`: per-file token cache; `paren_text(file, line, col)` for conditions; `else if` found by scanning forward from the enclosing `if`; offsets from line and column via a per-file line table | exact text on every kind; parentheses preserved |
| ☑ `S2-IMPL-6` | Call resolution (§1.2): a lazily built, per-model occurrence index `(fileid, line, col) → Occurrence` and prototype → function map, cached on `ParsedModel` | package, component, `comp.sub.fn()` and component-`exec` calls resolve; library calls come back `None` |
| ☑ `S2-IMPL-7` | Call expansion (design §4.4): calls inside a step's range expand into the callee's steps; unmarked callees are opaque; recursion cut with a back-reference ("see step 2.1"); `:depth:`; `:expand-calls: inline\|link\|none` | recursion and depth unit-tested |
| ☑ `S2-IMPL-8` | Prelude check (design §4.1, D3): call statements and call-assignments before the first step, at any depth; declarations exempt; condition calls exempt; only for rendered bodies with at least one step; located at the statement | unit-tested |
| ☑ `S2-IMPL-9` | Numbering (design §4.6): `decimal` and `outline`; control rows unnumbered; numbering continues across extension groups | unit-tested |
| ☑ `S2-IMPL-10` | Degraded model (`pss_tolerate_link_errors` after a link failure): step output unavailable; the directive warns once and emits nothing | warns and doesn't fail the build |

### Tests
| ID | Task | Done when |
|---|---|---|
| ☑ `S2-TEST-1` | **Fixture** `tests/fixtures/pss/steps/`: `eth_mac.pss`, a PSS rewrite of Microchip PIC32 FRM §35.4.10 (controller init, MAC init, and `init_miim(rmii)` with an RMII conditional, a set-then-clear reset, and a divider write); polling loops; a `match`; a recursive pair; a component with `exec init_down`; `eth_ext_a.pss`/`eth_ext_b.pss` each adding an `exec body` to one action | parses and links with zero markers |
| ☑ `S2-TEST-2` | `tests/model/test_steps_tree.py`: expected trees for every fixture target, including ranges, nesting, each control kind, and marker-titled control | green |
| ☑ `S2-TEST-3` | `tests/model/test_steps_calls.py`: inline expansion through every call shape in §1.2; opaque unmarked and library callees; recursion cut; `:depth:` | green |
| ☑ `S2-TEST-4` | `tests/model/test_steps_prelude.py` (design `STEP-T4`): a call before the first step warns at its line, including nested in an `if`; `x = read(…)` warns (D3); `int x = read(…)` doesn't; a condition call doesn't; an unmarked function is never checked | green |
| ☑ `S2-TEST-5` | `tests/model/test_steps_extend.py` (design `STEP-T5`): declaration plus two extensions in order, with provenance groups; swapping the file order swaps the groups; continuous numbering | green |
| ☑ `S2-TEST-6` | `tests/model/test_source_text.py`: condition text for each kind; `else if`; parentheses; multi-line conditions | green |

### Docs
None: S2 changes nothing a user sees. The prelude warning is only reported for rendered bodies
(D5), so it is documented with the directive in S3. (Done anyway: the placements example's nesting
claim on the steps page is now test-checked.)

---

## 6. Milestone S3 — Step tables (first user-visible release)

### Implementation
| ID | Task | Done when |
|---|---|---|
| ☑ `S3-IMPL-1` | `autodoc/steps.py`: the `pss:steps` directive. The argument is a function or type qualname; options `:exec:` (required for a type, D4), `:format:` (`table`; `flowchart` and `both` rejected with a clear error until S4), `:numbering:`, `:expand-calls:`, `:depth:`. `StepsError` becomes a directive error; `StepsUnavailable` one warning per build and no output (the directive half of `S2-IMPL-10`). Report `StepsDoc.issues` (`pss.step_prelude_call`) once per location per build | directive registered; an invalid target or option is an error, not a crash |
| ☑ `S3-IMPL-2` | Table renderer: a docutils table with columns #, Step, Details, Source (design §7.2). Nesting by indentation; control rows unnumbered, with the condition in literal text; extension group rows | renders under `-W` |
| ☑ `S3-IMPL-3` | Details parsed as reST with **per-line source attribution**: each detail line's `StringList` entry points at its `.pss` line, parsed under `switch_source_input` (the same mechanism as doc comments) | a markup error in a step's detail reports at the `.pss` line |
| ☑ `S3-IMPL-4` | `:steps:` flag on the `autopss*` function, action and component documenters, with the same options, appending the table to the entry. Rejected in `pss_default_options` (design §7.1) | the flag works; the config validator rejects it with a message |
| ☑ `S3-IMPL-5` | Source column: `file:line` (D2); a hook for a viewcode link when `P3-IMPL-4` lands | column present |

### Tests
| ID | Task | Done when |
|---|---|---|
| ☑ `S3-TEST-1` | `tests/roots/test-steps/`: a Sphinx project over the S2 fixture using every directive form | builds clean under `-W` |
| ☑ `S3-TEST-2` | `tests/autodoc/test_steps_table.py` (`sphinx`): row order, numbering in both styles, control rows, extension groups, source column | green |
| ☑ `S3-TEST-3` | **Acceptance fixture**: `init_eth` under `:numbering: outline` reproduces Microchip §35.4.10's 1 → a) → i. structure | green |
| ☑ `S3-TEST-4` | Warning locations (`sphinx`): step-detail reST errors, lint and prelude warnings all point at `.pss` lines, never `index.rst` | green |
| ☑ `S3-TEST-5` | Option errors: unknown `:exec:` kind, a type without `:exec:`, `:format: flowchart` before S4, `:steps:` in `pss_default_options` | each is a clear error |

### Docs
| ID | Task | Done when |
|---|---|---|
| ☑ `S3-DOC-1` | `docs/usage/steps.md` (the page exists since `S1-DOC-1`): ranges, nesting, control flow and call expansion, `extend` order, the directive and `:steps:`, and `pss.step_prelude_call`. **Every one with a live example**: a `pss:steps` directive rendered by the docs build next to its source, not a pasted table. Remove the page's "still being built" note | builds under `-W`; `test_docs_build.py` asserts rows of each live table |
| ☑ `S3-DOC-2` | `docs/examples/steps.md`: the Ethernet fixture rendered live, beside its source, in both numbering styles | renders in the build; asserted in `test_docs_build.py` |
| ☑ `S3-DOC-3` | Warning reference: add `pss.step_prelude_call` to the page's warning table, with an example checked by `test_docs_step_examples.py` (the three lint codes are done in `S1-DOC-1`) | listed and checked |
| ☑ `S3-DOC-4` | `CHANGELOG.md` and `README.md` feature list | entries present |

**S3 acceptance (`S3-ACC`) ☑ 2026-09-29:** the Ethernet fixture renders as a step table matching the vendor
structure; the docs build under `-W`; the corpus sweep reports zero step warnings.

---

## 7. Milestone S4 — Flowcharts (includes `P2-IMPL-5`)

### Implementation
| ID | Task | Done when |
|---|---|---|
| ☑ `S4-IMPL-1` | **`P2-IMPL-5`**: `autodoc/diagrams.py`, the shared back-end. `pss_diagrams` (`graphviz`/`mermaid`/`off`); Graphviz via `sphinx.ext.graphviz`; Mermaid via `sphinxcontrib-mermaid` if installed, otherwise a clear warning; **graceful degradation** to one warning and a skipped node when `dot` is absent. Plus the two shared-layer additions from `activity-diagrams-design.md` §5.3: sub-graph clusters and node hyperlinks, with a one-time warning when `graphviz_output_format` isn't `svg` | tick `P2-IMPL-5` in `implementation-plan.md` too |
| ☑ `S4-IMPL-2` | Flowchart lowering (design §7.3): steps → boxes (number and title), branches → diamonds with conditions, loops → back-edges, inline expansions → clusters, linked expansions → linked boxes, extension groups → clusters | graph IR unit-tested, independent of the back-end |
| ☑ `S4-IMPL-3` | Enable `:format: flowchart` and `both` | options accepted |

### Tests
| ID | Task | Done when |
|---|---|---|
| ☑ `S4-TEST-1` | `tests/autodoc/test_diagrams.py`: the back-end emits nodes; `off` suppresses; missing `dot` → one warning, no failure (`P2-TEST-5` coverage) | green with and without Graphviz |
| ☑ `S4-TEST-2` | `tests/model/test_steps_flowchart.py`: the lowered graph for each fixture target (nodes, edges, clusters, labels) | green |
| ☑ `S4-TEST-3` | Determinism: build twice, byte-identical dot/Mermaid output | green |

### Docs
| ID | Task | Done when |
|---|---|---|
| ☑ `S4-DOC-1` | `docs/usage/steps.md`: flowchart section, with the Graphviz prerequisite and the degradation behavior, and a **live flowchart** of a fixture function; `docs/examples/steps.md` gains `:format: both` for the Ethernet fixture | builds clean; the flowchart node is asserted in `test_docs_build.py` |
| ☑ `S4-DOC-2` | `docs/usage/diagrams.md`: the shared back-end and `pss_diagrams` (`P2-DOC-2`, the parts that exist) | builds clean |

**S4 acceptance (`S4-ACC`) ☑ 2026-09-29:** the fixture's flowcharts render with Graphviz; the build is clean with
`dot` absent (one warning each); Mermaid output is valid. With `dot` absent the build gives one
`pss.diagrams` warning in all and shows tables (`test_a_missing_dot_is_one_warning`); Mermaid validity
was checked with Mermaid's parser (progress log).

---

## 8. Milestone S5 — Migration checker

### Implementation
| ID | Task | Done when |
|---|---|---|
| ☑ `S5-IMPL-1` | `sphinx_pss/checkers/steps.py`: a pssparser `CheckerBase` named `sphinx-pss-steps`, marker `SPSS001` ("plain comment looks like a step marker; write `/// Step:`"). It tokenizes `ctx.files` (`CHANNEL_SL_COMMENT` and `CHANNEL_ML_COMMENT`) and matches rule 2 on plain comments. `options_schema = {"enabled": {"type": "bool", "default": False}}`: a no-op unless enabled | `pssparser --list-checkers` shows it; silent by default |
| ☑ `S5-IMPL-2` | `pyproject.toml`: `[project.entry-points."pssparser.extensions"]` registration | `pssparser --list-extensions` shows sphinx-pss |

### Tests
| ID | Task | Done when |
|---|---|---|
| ☑ `S5-TEST-1` | Disabled: no markers on a file full of `// Step:`. Enabled via `.pssparser.toml`: one marker per plain step comment, none for `///` | green |

### Docs
| ID | Task | Done when |
|---|---|---|
| ☑ `S5-DOC-1` | `docs/usage/steps.md` "Migrating existing comments": enabling the checker, with an example `.pssparser.toml` and the output it gives, checked by a test like `test_docs_step_examples.py` | builds clean; example checked |

---

## 9. Sequencing

```
S0 ──► S1 ──► S2 ──► S3 (first release: tables)
                      │
                      └──► S4 (flowcharts; builds P2-IMPL-5)
S0 ──────────────────────► S5 (independent; can land any time after S0)
```

S3 is the first point worth releasing, since tables are the primary output (design §2.1). S4 and
S5 are independent of each other.

---

## 10. Status tracker

| Milestone | Impl | Tests | Docs | Acceptance | State |
|---|---|---|---|---|---|
| S0 Foundations | ☑ | ☑ (`S0-TEST-4` assertion waits on `PERF-1`) | ☑ | — | **done** 2026-09-28 |
| S1 Markers + lint | ☑ | ☑ | ☑ (moved from S3) | — | **done** 2026-09-28 |
| S2 Step tree | ☑ (`S2-IMPL-10` directive half moves to `S3-IMPL-1`) | ☑ | — | — | **done** 2026-09-28 |
| S3 Step tables | ☑ | ☑ | ☑ | `S3-ACC` ☑ | **done** 2026-09-29 |
| S4 Flowcharts (+ `P2-IMPL-5`) | ☑ | ☑ | ☑ | `S4-ACC` ☑ | **done** 2026-09-29 |
| S5 Migration checker | ☑ | ☑ | ☑ | — | **done** 2026-09-29 |

> Update this table and the per-item boxes as work lands; append PR or commit refs next to checked
> items.

---

## 11. Risks

| Risk | Mitigation |
|---|---|
| The occurrence-based call resolution (§1.2) is position-keyed and could drift with a parser change | `S0-TEST-1` guards it; a failure names this plan |
| Comment collection's +14% link cost on comment-dense models (design §5.1) | Worst case measured at about +4% overall; `S0-TEST-4` once `PERF-1` lands; design §5.1 option 3 is the fallback |
| The source-text scan (`else if`, conditions) meets syntax it doesn't expect (nested parentheses in strings, `compile if` regions) | The token stream is lossless and parenthesis depth counts only default-channel tokens; `S2-TEST-6` covers it; on failure, fall back to "condition" text with a warning, never a crash |
| `P2-IMPL-5` grows beyond what flowcharts need | Scope fixed to the implementation-plan item plus the two §5.3 additions; activity and flow diagrams add their own renderers later |
