# Programming steps — tables and flowcharts from marked PSS code

**Status:** Approved for implementation (2026-09-28); open question §8 Q6 decided in the plan (D6: fixed keyword)
**Date:** 2026-09-28
**Covers:** a new design §9.9 (proposed), next to activity graphs (§9.3)
**Plan:** [`programming-steps-plan.md`](programming-steps-plan.md) (decision D4 refines §7.1: `exec` blocks are addressed with an `:exec:` option)
**Depends on:** `P2-IMPL-5` (the shared diagram back-end) for flowcharts; `P3-IMPL-4` (viewcode)
for source links. The step table depends on neither.

---

## 1. What this is, and what it is not

PSS is used to write the code that programs a device: functions and `exec` blocks that write
registers, poll status and call one another. The same procedure is what a device's programming
guide describes to a human reader, as "reset the MAC, wait for the reset to complete, initialize
the MIIM interface, …". This feature generates that description from the PSS source: a numbered
**step table** and, optionally, a **flowchart**.

The author marks which code is a step. The tool derives the structure: conditions, loops, and the
expansion of called functions into sub-steps.

It is **not**:
- **An activity diagram (§9.3).** Activities schedule *actions*. Steps describe the procedural code
  inside functions and `exec` blocks. The two share a diagram back-end and nothing else.
- **A control-flow graph of every statement.** Only marked code, plus the control flow around it,
  is shown. A step list with one row per register write would be unreadable, and no vendor writes
  one.
- **Inference of what the steps are.** Deciding that three writes are one step called "Program the
  station address" is editorial, and only the author can make that call (§2.3).

---

## 2. Research

### 2.1 How device programming guides describe sequences

Surveyed 2026-09-28. Vendors use three forms:

| Form | Examples | Notes |
|---|---|---|
| **Numbered steps, often nested** (most common) | AMD/Xilinx PG021 (AXI DMA) "Programming Sequence"; Microchip PIC32 FRM §35.4.10 Ethernet initialization; ADI AN-1561 (ADuCM4050 DMA) | Microchip nests three levels: 2 "MAC Initialization" → e) "Initialize the MIIM interface" → i–iii. The prose carries control flow: "If desired, enable interrupts", "must be written last", "polling the ETHBUSY bit", "If the RMII operation is selected" |
| **Flowcharts**, where a procedure is mostly decisions and waits | ST RM0091 I²C master transmitter/receiver; Infineon AN220191 (TRAVEO DMA) "Setting procedure" figures; Microchip PIC24F DMA transfer flow | Infineon pairs each flowchart with numbered steps *and* a code listing. The flowcharts are what an implementer codes from |
| **Sequence / timing diagrams** for bus transactions | Renesas 8A3xxxx programming guide; PIC32 I²C timing figures | A different kind of diagram. Out of scope |

So the **table is the primary output** and the flowchart is the secondary one. Both are needed.

### 2.2 Precedent for generating these from code

| Precedent | What it does | Taken from it |
|---|---|---|
| **Agnisys IDesignSpec** | Generates a "Programmer's Reference Manual" with *tabular* and *flowchart* views from sequences written in PSS | The output is wanted, from PSS specifically |
| **Flowgen** (C++; *Computer Physics Communications* 196, 2015) | `//$ text` marks an action and produces one UML activity diagram / flowchart per function | Most of §4: a marker covers the code **up to the next marker**; `//$ [text]` labels an `if` or loop; unmarked control flow is still drawn; a marked call links to the callee's diagram; numeric levels (`//$1`) set detail |
| **ST STM32Cube examples** | `/*##-1- Configure the UART peripheral ###*/`, `##-2-`, … | Vendors already mark steps in driver code. The numbers are typed by hand and drift: one example file restarts `##-2-`/`##-3-` inside a second `#ifdef` branch. **The tool numbers steps, never the comment** |
| **Allure** (`with allure.step("…")`, `@allure.step`) | Explicit, nested steps rendered as a report | Explicit nested steps are what people expect in a step report |

### 2.3 Why explicit marking rather than inference

A vendor's step list is curated. One step stands for several writes, and plenty of code (address
arithmetic, logging, bookkeeping) is not a step at all. No analysis recovers "these three writes are
*Program the station address*". Structure, on the other hand, is mechanical and must be derived:
hand-maintained structure drifts, as ST's numbering shows.

---

## 3. The marker

### 3.1 Syntax

```pss
function void init_mac(bool rmii) {
    /// Step: Reset the MAC
    write_reg(MAC_CFG, 0x8000);

    /// Step: Wait for the reset to complete
    /// SOFTRESET self-clears once the MAC's clock domains are back.
    while ((read_reg(MAC_CFG) & 0x8000) != 0) { }

    /// Step: Initialize the MIIM interface
    init_miim(rmii);          // init_miim's own steps become 3.1, 3.2, ...
}
```

Rules:

1. **Only `///` and `/** */` comments are scanned.** Plain `//` and `/* */` never are.
2. A marker is a comment line (after the comment markers are stripped) matching exactly:
   `^Step(\s+\d+(\.\d+)*)?:\s*(?P<title>\S.*)$`. It's case-sensitive and the colon is required.
   A number (`Step 3:`) is accepted and ignored.
3. The **title** is the rest of that line. The following lines of the same comment are the step's
   **detail**, parsed as reStructuredText by the project's doc dialect, like any doc comment. Lines
   of the same comment *before* the marker line are ignored: they're the author's prose.
4. `Step:` is the only keyword. A line like `Note:` or `Warning:` is prose, never an "unknown
   directive". New keywords, if any are ever added, come from a closed list (§3.3).

### 3.2 Why this form

Other languages balance "little syntax" against "no false matches" with four levers (surveyed
2026-09-28):

| Lever | Precedent | Used here |
|---|---|---|
| Recognize directives only in a special comment form | Doxygen commands only in `///` and `/** */`; Sphinx `#:` attribute comments; Flowgen `//$` | **Yes, rule 1.** Ordinary comments can't cause a match or a warning |
| Strict lexical form, often namespaced | Go `//go:generate` (no space allowed; `//(line \|extern \|export \|[a-z0-9]+:[a-z0-9])`); `# fmt: off`; `# pylint: disable=`; `# pragma: no cover`; `// NOLINT` | **Yes, rule 2.** Exact keyword, case and colon |
| Position rules | TypeScript `///` directives only at the top of a file ("treated as regular single-line comments" elsewhere); PEP 263 encoding only in the first two lines; PEP 484 type comments only on specific lines | **Yes, §3.4.** A marker means something only inside a function body or `exec` block |
| Warn only once intent is unambiguous | PEP 484: "misplaced type comments will be flagged as errors" once `# type:` has matched; pylint validates only after `# pylint:`; GCC `-Wimplicit-fallthrough=0…5` makes the matching strictness configurable | **Yes, §3.5.** Warnings only inside `///` and `/** */`; strictness of the plain-`//` lint is opt-in |

The anti-pattern is Javadoc, where an unknown `@tag` is an error and projects must register custom
tags to keep builds quiet.

Rejected alternatives:

| Alternative | Why not |
|---|---|
| Plain `// Step:` | Driver code is full of `//` comments, including hand-written `// Step 1:` ones that aren't meant for this tool. Either near-misses are silently dropped, or warnings fire on prose |
| Go style `//step: …` | Just as unambiguous, but it rests on a whitespace rule nobody would guess: `// Step:` would silently not count. Go gets away with it because `gofmt` enforces it |
| Any `///` on a statement is a step | Implicit. It rules out any other use of statement doc comments later |
| reST field `/// :step: Reset the MAC` | Heavier to type, for no gain in precision over rule 2 |
| PSS 3.1 annotations `@step {.title = "…"}` | Valid PSS (`procedural_stmt ::= … \| annotation`), but verbose, and pssparser doesn't support it yet (§6.3). Kept as the future route: Python's type comments gave way to annotation syntax (PEP 526) in the same way. The step model (§5) doesn't depend on how steps are written, so an annotation front end can be added later |

### 3.3 Reading markers from the parser

Markers are read through the **comments API** (`Parser(collect_comments=True)`), not the
doc-comment API. The doc-comment rules drop exactly the placements a marker needs (§6.1). From each
statement's leading comments:

- `getRaw()` keeps the comment verbatim, so `///` is told apart from `//` and `/**` from `/*`.
  (`getText()` leaves a stray `/` on a `///` comment, so it isn't used.)
- `getPlacement()` gives 0 for a comment directly before the statement, 1 for a trailing comment,
  and 2 for one separated from it by a blank line.

### 3.4 Where a marker means something

- **Valid:** before a statement (placement 0), trailing a statement (placement 1), or separated from
  the next statement by a blank line (placement 2), anywhere inside a function body or an `exec`
  block, at any nesting depth.
- **Misplaced:** a `Step:` marker on a declaration (type, field, action, function prototype) or at
  package or component scope. It's reported (§3.5) and otherwise ignored.

### 3.5 Warnings

Warnings about markers are emitted **only for `///` and `/** */` comments**, and only when intent is
clear. `pss.step_prelude_call` is about code, not comments, and fires only in bodies that already
have steps:

| Code | When | Example |
|---|---|---|
| `pss.step_syntax` | Inside a function body or `exec` block, the first word matches `steps?` case-insensitively (followed by a space, colon, period, digit or line end), but the line doesn't match rule 2. Not checked on declarations, whose doc comments are prose | `/// step: reset`, `/// STEP 3 Reset`, `/// Steps: …` |
| `pss.step_misplaced` | A valid marker outside a function body or `exec` block | `/// Step: …` above a `struct` |
| `pss.step_empty` | A marker with no title, or a step with no statements: another marker follows it directly, or the block ends (refined in plan S1) | `/// Step:` |
| `pss.step_prelude_call` | A call statement before the first step of a body that has steps (§4.1) | `enable_clocks();` above the first `/// Step:` |

Nothing is ever reported for plain `//` and `/* */` comments. A migration aid for codebases that
already write `// Step: …` belongs in a **pssparser checker plugin, off by default**. It reports
plain-comment lines that would be markers if written with `///`. This is the GCC-levels idea:
strictness is the user's choice, and the default is silence.

Hand-written numbers (`Step 3:`) are ignored rather than checked. An opt-in check that they agree
with the generated number is possible, but that is the ST drift problem, not a feature.

---

## 4. Semantics

### 4.1 Range

A step covers the statements **from its marker up to the next marker in the same block**, or to the
end of the block (Flowgen's rule). One marker over several writes is the normal case.

Statements in a function or `exec` body that run before its first step, in source order, and belong
to no step's range make up the **prelude**. The prelude is not shown.

**A function call in the prelude is a warning** (`pss.step_prelude_call`, §3.5): it's device
activity that the step table would silently leave out. Variable declarations are fine, including
ones whose initializer calls a function (`int base = read_reg(CFG);`): setting up locals is not a
programming step. Precisely:

- The warning is reported for each call **statement** (a procedural expression statement whose
  expression is a call) in the prelude, at any depth: a call inside an `if` or loop that precedes
  the first step counts.
- It is not reported for calls within a data declaration's initializer.
- It is reported only for bodies that contain at least one step. Unmarked functions are never
  checked.
- It covers every statement outside every step's range, not only those before the first: a call
  after a nested step's block and before the outer first step is left out the same way (refined in
  plan S2).
- The location is the call statement's own line.

Calls in the prelude are not expanded (§4.4). Decided 2026-09-28 (was §8 Q1 and Q2).

### 4.2 Nesting

Markers in a nested block (an `if` branch, a loop body, a `match` choice, a bare `{ }`) are
**sub-steps of the step whose range contains that block**. If the nested block lies in the prelude,
where no step contains it, its steps hang off the control-flow node (§4.3) at the outer level.

### 4.3 Control flow

An `if`, `while`, `repeat`, `foreach` or `match` that contains steps, directly or transitively, is
shown **even if it is unmarked** (Flowgen does the same). Its label is the condition **as written in
the source**:

| Statement | Table row | Flowchart node |
|---|---|---|
| `if (c) … else if (d) … else …` | "If `c`:", "Else if `d`:", "Otherwise:" | a decision diamond per condition |
| `while (c)` / `repeat … while (c)` | "While `c`:" / "Repeat until not `c`:" | a loop, with a back-edge |
| `repeat (n)` | "Repeat `n` times:" | a loop, with a back-edge |
| `foreach (e : xs)` | "For each `e` in `xs`:" | a loop, with a back-edge |
| `match (e)` | "Depending on `e`:" plus one row per choice | a decision with one edge per choice |

A marker directly on the control statement **titles** it, and the condition becomes secondary text
(the analogue of Flowgen's `//$ [text]`):

```pss
/// Step: Reset the RMII module, if RMII is in use
if (rmii) { ... }
```

A control statement that contains no steps is part of its step's range, and isn't drawn. One that
contains an expanding call (§4.4) is drawn, so the callee's steps keep their condition (refined in
plan S2).

**Condition text is taken from the token stream, not the AST.** Expressions carry no location, and
the AST folds away parentheses the author wrote. `pssparser.tokens` is lossless and statements have
a start position: find the keyword token at the statement's start, then take the tokens between its
matching parentheses. Prototyped 2026-09-28 against `if`, `while`, `repeat` and `match`; it returns
`rmii && n > 2` and `(r(0) & 0x1) != 0` exactly as written. Clauses have no location of
their own, but their bodies do, so an `if` or `else if` condition is the parentheses just before
its body (refined in plan S2).

### 4.4 Calls

A step whose range contains a call to a function **that has steps** expands into that function's
steps as sub-steps. That's how Microchip's "2.e.i" nesting arises with nothing written by hand.
Calls are resolved by the linker (`ExprRefPathContext.getTarget()`, cross-checked with
`refs.occurrences()`), not by name.

- Only calls inside a step's range expand. Calls in the prelude are reported (§4.1), not expanded.
- Calls to functions with no markers are opaque: they're part of the step, not expanded.
- Several expanding calls in one step expand in call order.
- Recursion is cut at the first repeat, with a note ("see step 2.1").
- `:expand-calls: link` renders the call as a single node linking to the callee's own step table
  instead of inlining it. This is the better choice for widely shared helpers.

### 4.5 `exec` blocks contributed by `extend`

An `exec` kind can have blocks in the type's own declaration and in any number of `extend`
statements. The steps for `dma_c::start::body` are the steps of **every** `body` block of that type,
**in extension order**: the declaration's block first, then each `extend` in the order the linker
processes the extension statements, which follows file order and then source order within a file.

That order is arbitrary, since reordering files reorders the table, but it is the order the blocks
exist in the merged model, and it is the rule. Each block's steps are grouped under a provenance row
naming the `extend` site ("Added by an extension at `dma_ext.pss:12`"), as members are (§9.5), and
numbering continues across blocks. Decided 2026-09-28 (was §8 Q4).

### 4.6 Numbering

Numbering is always generated, never taken from the source:

| `:numbering:` | Result | Style |
|---|---|---|
| `decimal` (default) | 1, 1.1, 1.1.1 | ST, AMD |
| `outline` | 1, a), i. | Microchip FRM |

Control-flow rows (§4.3) are not numbered. Their children continue the enclosing numbering, so
"If `rmii`:" is followed by 2.1, not by a number of its own.

---

## 5. Model — `model/steps.py`

A tree, built per function or `exec` block:

| Node | Fields |
|---|---|
| `Step` | `title`, `detail` (lines), `detail_line`, `source: SourceRef`, `children`, `number` |
| `Branch` | `kind` (`if`, `match`), `arms: list[Arm(kind, label, children, source)]`, `label` (the `match` expression), `marked`, `source` |
| `Loop` | `kind` (`while`, `repeat_while`, `repeat_count`, `foreach`), `label`, `variable`, `children`, `marked`, `source` |
| `CallExpansion` | `callee: str` (qualified name), `mode` (`inline`, `link`, `cut`), `children`; a cut refers back with `see` |
| `ExtensionGroup` | `source` (the block), `is_extension`, `children`: one per function body or `exec` block (§4.5) |

A marker on a control statement (§4.3) stays on its `Step`, whose first child is the control node
with `marked` set; a renderer draws the two as one row. (Refined in plan S2: a `title` on the control
node left the rest of the step's range without a parent.)

Built lazily when a directive asks for it, not at index build: most projects mark a handful of
functions. It needs the parse to run with `collect_comments=True`. `parse_model` sets that flag
always, rather than only when a directive asks for steps: the index is built once, at
`builder-inited`, before any directive is read, and §5.1 shows the flag is cheap. Tokenization for
condition text is cached per file.

### 5.1 The cost of comment collection — measured 2026-09-28

Against pssparser `1ec757b`, single core (`taskset`), five interleaved rounds per configuration, with
the minimum reported (minimum and median agreed within 1%).

**Corpus** (97 units, each a separate parse including the standard library): no collection 436.5
ms, doc comments 447.0 ms, all comments 455.6 ms. So +1.9% over doc comments, and +0.7 MB.

**Synthetic, deliberately comment-dense models** (a `//` note on every statement, a `/// Step:` on a
third of them, a doc comment on every function). Largest shown: 8000 functions, 11.5 MiB.

| Configuration | Parse | Link | Parse + link | Peak memory |
|---|---|---|---|---|
| Doc comments (sphinx-pss today) | 2936 ms | 768 ms | 3704 ms | 1358 MB |
| All comments | 2608 ms | 664 ms | 3272 ms (**−12%**) | 1426 MB |

Collecting *more* is faster. The reason is one line in `AstBuilderInt::build`: comment collection
calls `m_tokens->fill()` so that trailing comments are buffered, and lexing the whole file up front
is faster than ANTLR's lazy token stream. Confirmed by making `fill()` unconditional in a scratch
build (reverted afterwards; the restored library is byte-identical):

| With `fill()` in every configuration | Parse | Link | Parse + link | Peak memory |
|---|---|---|---|---|
| No collection | 2429 ms (−13% vs lazy) | 578 ms (−24% vs lazy) | 3007 ms | 1339 MB (unchanged) |
| Doc comments | 2563 ms | 582 ms | 3145 ms | 1358 MB |
| All comments | 2608 ms | 664 ms | 3272 ms | 1426 MB |

The comment-free 2000-function model shows the same `fill()` effect (−13% parse, −18% link).

**So:**
- Today, turning on comment collection makes sphinx-pss about **12% faster**, as a side effect.
- The intrinsic cost of collecting all comments, with `fill()` held equal, is **+1.7% parse, +14%
  link, +5% memory** on this worst-case model: about **+4%** in total. On models without dense
  comments it is around 1%.

**Optimization paths:**
1. **Upstream, and for every pssparser user: call `fill()` unconditionally** — −13% parse,
   −18–24% link, no measured memory cost. Filed as `PERF-1` in pssparser's
   `docs/design/sphinx-pss-requests-2026-09-28.md`.
2. **Upstream, investigate the +14% link cost of comments.** The linker never reads comments, and
   the generated visitor skips them (`visit: false` on `ScopeChild.comments`), so this is not a
   traversal. The working hypothesis is memory locality: comment nodes are interleaved with AST
   nodes. This couldn't be profiled here (`perf_event_paranoid=4` blocks `perf` for non-root;
   `valgrind` is impractical at this size). It is worth pursuing only if a real project shows the
   cost; this model is an upper bound.
3. **In sphinx-pss, only if a real project ever needs it:** skip `collect_comments` and find markers
   by tokenizing only the files of requested functions (`pssparser.tokens`), attaching comments to
   statements by position. This costs nothing for projects that never ask for steps, but it
   duplicates the parser's attachment rules. Not proposed now.

The model is independent of the marker syntax. An annotation front end (§3.2) or a doxygen-dialect
`\step` command could produce the same tree.

---

## 6. Parser dependencies — verified 2026-09-28 against pssparser `1ec757b`

### 6.1 Present and sufficient

| Need | Evidence |
|---|---|
| Comments on procedural statements, in function bodies **and** `exec` blocks | `collect_comments=True`; every placement in §3.4 was captured, including the blank-line-separated and trailing forms. The doc-comment API drops those two, which is why §3.3 reads the comments API |
| Comment style and placement | `getRaw()`, `getPlacement()` |
| A marker after a block's last statement | Kept on the enclosing scope's `getTrailing_comments()`, not on any statement (found in `S0`, 2026-09-28). It opens a step with nothing in it: `pss.step_empty` |
| Statement start positions | `getLocation()` on every procedural statement; `if` clause bodies are located |
| Condition text | `pssparser.tokens`, prototyped (§4.3) |
| Call resolution | `refs.occurrences()` binds each call to its `FunctionPrototype`; `ExprRefPathContext.getTarget()` on the node |

### 6.2 Gaps — none blocking

| Gap | Effect | Workaround |
|---|---|---|
| Procedural statements have no end location (`getEndLocation()` is -1) | A `[source]` link goes to a line, not a range | Link to the start line, as `P3-IMPL-4` already plans for non-scope members |
| An `else if` clause has no location | The condition can't be found directly | Read back from the clause body's `{` in the tokens (§4.3; plan S2) |
| `getText()` on a `///` comment keeps a stray `/` | — | Read `getRaw()` |

### 6.3 Only if annotations are adopted later

Found while evaluating §3.2's annotation alternative:
- **Statement annotations are hoisted.** `@step {…}` before a procedural statement is attached to
  the enclosing `FunctionDefinition`, not the statement. Each keeps its own location, so it could be
  re-associated by position, but it shouldn't need to be.
- **Annotations in `exec` blocks fail to link.** pssparser reports "'step' was left unbound by
  pssparser, although the model declares it: a pssparser defect, please report it".

Neither needs fixing for this design. File them if the annotation route is taken.

---

## 7. Rendering

### 7.1 Directive

```rst
.. pss:steps:: drv_pkg::init_mac
   :format: table            # table (default) | flowchart | both

.. pss:steps:: drv_pkg::dma_c::start
   :exec: body               # required when the target is a type
   :numbering: decimal       # decimal (default) | outline
   :expand-calls: inline     # inline (default) | link | none
   :depth: 3                 # expansion depth; default unlimited, cut at recursion
```

The target is a function, or a type plus an `:exec:` kind (`body`, `run_start`, `init_down`, …).
~~An `exec` block was written `<type>::<exec kind>`, for example `dma_c::start::body`.~~ Replaced
by the `:exec:` option (plan decision D4, 2026-09-28): `body` and the other kinds aren't reserved
words, so the path form could clash with a member of the same name. The `autopss*` documenters get a `:steps:` flag that appends the table to a
function's or action's entry.

**Step output appears only on request**: through `pss:steps`, or `:steps:` given on a specific
`autopss*` directive. It is never generated automatically for functions that have markers, and
`:steps:` is not accepted in `pss_default_options`, so a project can't turn it on everywhere by
accident. Decided 2026-09-28 (was §8 Q3).

### 7.2 Table

| Column | Content |
|---|---|
| **#** | Generated number (§4.6); empty for control-flow rows |
| **Step** | Title; control-flow rows show "If `rmii`:" etc. |
| **Details** | The detail reST |
| **Source** | Link to the marker's line (viewcode, `P3-IMPL-4`); plain `file:line` until that exists |

Indentation shows nesting. The table is the accessible, always-available output, the same role the
text outline plays for activity diagrams (`activity-diagrams-design.md` §5.5).

As built in plan S3 (2026-09-29):

- **Calls.** An inline expansion has no row: the callee's steps are sub-steps of the calling step,
  and their Source column names the callee's file. A linked call is a row, "Follow the steps of
  `f`", linked to `f`'s entry when a page documents it; a cut call is "Repeat from step 1 (`f`)".
- **A marked control** is one row: the title, then the condition as a second line. For an `if`,
  the first arm's steps sit one level in, and later arms are rows at that level.
- **Arms.** An `if` chain shows its arms up to the last one with steps; a `match` shows only the
  choices that have steps.
- **Indentation** is em spaces in the Step column, which every builder keeps.
- **Source** paths are relative to the `pss_source_dirs` entry the file was found under.

### 7.3 Flowchart

Uses `P2-IMPL-5`'s back-end, with the two shared-layer additions activity diagrams already require:
sub-graph clustering and node hyperlinks.

- Steps are boxes, labelled with number and title. Detail text is not drawn.
- Branches are diamonds labelled with the condition; loops draw a back-edge labelled with the loop
  condition.
- An inline call expansion is a cluster labelled with the callee. A linked expansion is one box
  linking to the callee's steps.
- Every node links to its source line.
- Graphviz is primary and Mermaid (`flowchart TD`) secondary, as for activity diagrams. A flowchart
  has none of UML's fork/join vocabulary, so Mermaid loses nothing here.

As built in plan S4 (2026-09-29):

- **Loops.** `while` is a diamond before its body and `repeat … while` one after it, each with a
  `yes` back-edge; `repeat (n)` and `foreach` are a hexagon (the loop-limit symbol) with a back-edge
  and a `done` exit. The condition labels the diamond rather than the back-edge.
- **No join nodes.** Each construct leaves its open exits for the next to connect, so an empty arm
  is an edge past the branch, and an `if` without `else` falls through on `no`.
- **A marked control** is the step's box and then its diamond or hexagon, not one merged node as
  in the table.
- **Linked and recursive calls** are a double-bordered box (predefined process) with the table's
  text, linked to the callee's entry. Inline expansions and `extend` blocks are dashed clusters.
- **Source.** Each node shows its `file:line` on hover. The link to the line waits on viewcode, as
  the table's Source column does.
- **Degradation.** A flowchart that can't be drawn (no `dot`, Mermaid not loaded, or
  `pss_diagrams = "off"`) is rendered as its table.

---

## 8. Open questions

Questions 1–5 were decided on 2026-09-28. They're kept, struck through, with what replaced them.

1. ~~**The prelude.** Statements before a block's first marker are not shown. Should an unmarked
   prelude that contains an expanding call be shown as an implicit step, or reported?~~
   **Decided:** a call statement before the first step is a warning (`pss.step_prelude_call`);
   variable declarations, including ones with initializers that call functions, are fine. See §4.1.
2. ~~**Calls outside any step's range.** Should a prelude call to a function that has steps
   expand?~~ **Decided:** no. It's reported by Q1's warning instead. See §4.4.
3. ~~**Where the table appears by default.** Automatically on functions with markers, or opt-in,
   perhaps project-wide via `pss_default_options`?~~ **Decided:** only on request, per directive;
   not accepted in `pss_default_options`. See §7.1.
4. ~~**`exec` blocks contributed by `extend`.** Are their steps appended, and in what order?~~
   **Decided:** every block of the kind, in extension order. The order is arbitrary but it is the
   rule. See §4.5.
5. ~~**The cost of `collect_comments=True`.** Enable always, or only when a directive needs
   steps?~~ **Decided:** always. Measured at −12% today (a side effect of `fill()`), and about +4%
   worst case once `fill()` is unconditional upstream. See §5.1.
6. **The keyword.** `Step:` is English. Configurable (`pss_step_keyword`), or fixed? Fixed is simpler
   and keeps models portable between projects. Leaning towards fixed.

---

## 9. Work items

### Implementation

| ID | Item | Done when |
|---|---|---|
| `STEP-1` | Marker recognition: scan leading comments from the comments API, rules §3.1/§3.4, warnings §3.5 | unit tests over every placement and near-miss in §3; no warning from any plain `//` |
| `STEP-2` | `model/steps.py`: build the tree (§4.1–§4.5, §5), with ranges, nesting, control flow, call expansion, the prelude-call warning and `extend` ordering | fixture functions produce expected trees, including recursion, `exec` blocks and extension order |
| `STEP-3` | Condition text from tokens (§4.3), including `else if` | exact source text for each statement kind, parentheses preserved |
| `STEP-4` | `pss:steps` directive and the table renderer (§7.1–§7.2); `:steps:` on the `autopss*` documenters | table renders under `-W` for the fixtures |
| `STEP-5` | Flowchart renderer (§7.3) on `P2-IMPL-5` | graphviz and mermaid output for the fixtures; missing `dot` degrades to a warning |
| `STEP-6` | Checker plugin for plain `// Step:` migration (§3.5), off by default | ships in the pssparser extension set, disabled unless selected. Done in plan S5: `SPSS001`, enabled with `enabled = true` under `[checker.sphinx-pss-steps]` |

### Tests

| ID | Item |
|---|---|
| `STEP-T1` | A realistic fixture: the Microchip §35.4.10 Ethernet initialization, rewritten as PSS functions with markers. The generated table should reproduce its 1 → a) → i. structure under `:numbering: outline` |
| `STEP-T2` | `upstream` guards for every §6.1 dependency: comments API placements, `getRaw()`, statement start positions, token contract, call resolution |
| `STEP-T3` | Negative tests: a corpus sweep asserting **zero** step warnings on the pss-corpus parseable buckets, which contain no markers. This is what proves plain comments are never noise |
| `STEP-T4` | Prelude: a call statement before the first step warns at its own line, including one nested in an `if`; `int x = read_reg(0);` does not; a function with no markers is never checked |
| `STEP-T5` | `extend` order: an `exec body` in the declaration plus two extensions in two files renders the three blocks' steps in extension order, with provenance rows; swapping the file order swaps the extension blocks |
| `STEP-T6` | Performance guard: the corpus sweep's parse + link time with `collect_comments=True` stays within 5% of doc-comments-only, once pssparser `PERF-1` has landed (§5.1) |

### Docs

A "Documenting programming procedures" page in `docs/usage/`, with the marker rules, the directive
and a worked example.

---

## Sources

- AMD/Xilinx PG021 AXI DMA — <https://china.xilinx.com/content/dam/xilinx/support/documents/ip_documentation/axi_dma/v7_1/pg021_axi_dma.pdf>
- Microchip PIC32 FRM §35, Ethernet Controller — <https://ww1.microchip.com/downloads/aemDocuments/documents/OTH/ProductDocuments/ReferenceManuals/60001155D.pdf>
- ADI AN-1561, DMA programming for the ADuCM4050 — <https://www.analog.com/en/resources/app-notes/an-1561.html>
- ST RM0091 I²C flowcharts, as used in a bare-metal write-up — <https://hackaday.com/2022/05/11/bare-metal-stm32-using-the-i2c-bus-in-master-transceiver-mode/> (the RM0091 PDF itself could not be retrieved from this environment)
- Infineon AN220191, DMA in TRAVEO T2G — <https://documentation.infineon.com/traveo/docs/yjd1680597039789_2>
- Renesas 8A3xxxx programming guide — <https://www.renesas.com/en/document/gde/8a3xxxx-family-programming-guide-v487>
- Agnisys, PSS for sequence specification and generation — <https://www.agnisys.com/pss-for-sequence-specification-and-generation/>
- Flowgen — <https://github.com/jlopezvi/Flowgen>; paper: <https://arxiv.org/abs/1405.3240>
- STM32CubeF4 `UART_TwoBoards_ComPolling/Src/main.c` — <https://github.com/STMicroelectronics/STM32CubeF4>
- Allure steps — <https://allurereport.org/docs/steps/>
- Go doc comments (directives) — <https://go.dev/doc/comment>
- GCC `-Wimplicit-fallthrough` — <https://gcc.gnu.org/onlinedocs/gcc/Warning-Options.html>
- TypeScript triple-slash directives — <https://www.typescriptlang.org/docs/handbook/triple-slash-directives.html>
- PEP 484 (type comments) — <https://peps.python.org/pep-0484/>
