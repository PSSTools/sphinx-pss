# `pssparser` Enhancement Plan — doc-comment support for sphinx-pss

**Status:** Releases A, B and C implemented (2026-08-13) — see §10 for the progress log
**Date:** 2026-08-13
**Target repo:** `psstools/pssparser` (a separate repo; every item here lands there, not in `sphinx-pss`)
**Consumers:** `design/sphinx-pss-design.md` §3–§5, `design/implementation-plan.md` Phase 0.5
**Principle:** the parser is the source of truth for doc comments. Everything below is a proper fix inside `pssparser` — no downstream re-scanning, no regex post-processing, no channel scraping in the extension.

---

## 1. Why this plan exists

The Phase-0.5 entry in `implementation-plan.md` proposed a contingency: if the parser's doc-comment support stayed broken, `sphinx-pss` would re-read source files and scan upward for comment blocks. **That contingency is withdrawn.** It would mean two independent implementations of comment association, guaranteed to disagree, with the wrong one winning silently. This plan fixes the parser instead.

Investigation also showed the problem is larger than the two gaps (G1, G2) recorded in the design doc. The doc-comment subsystem has **six additional defects**, and the output it produces today is not usable as reStructuredText even when it works. §2 catalogues what was found; §3 proposes replacing the subsystem rather than patching it.

### 1.1 What already works — do not disturb

Verified by spike (2026-08-13); these are the load-bearing behaviors:

- `AstBuilder::setCollectDocStrings(bool)` gates collection; **default `false`** (`AstBuilderInt.cpp:55`). Correct default — keep it.
- Every `ScopeChild` carries a `docstring` field (`ast/coretypes.yaml`), reaching Python as `getDocstring()`/`setDocstring()`.
- Doc comments attach correctly for packages, components, actions, structs/buffers, enums, function prototypes, constraint blocks, and **unqualified** fields.
- `Location{fileid, lineno, linepos, extent}` is populated; `Parser.file_map` maps `fileid → path`; synthesized members are identifiable by `lineno < 0`.
- **Extension provenance is already fully derivable** — a member merged from `extend action X` keeps its own `location` (extend-site file/line) and its `getParent()` still returns the `ExtendType`, because `TaskApplyTypeExtensions` appends non-owning references without reparenting (`TaskApplyTypeExtensions.cpp:358,403,425,455`). **No parser change is needed for provenance**, which removes a risk from `sphinx-pss` `P1-IMPL-6`.
- The AST is generated from `ast/*.yaml` by `scripts/gen_ast.py` (`gen-cpp` **and** `gen-pyext`), so a schema change propagates to C++ and the Python extension automatically. Schema additions are cheap.

---

## 2. Defect catalogue

Each entry has a verified reproduction. `Dn` numbering is used by the work items in §4. G-numbers cross-reference the design doc §4.3.

### 2.1 Blocking — doc comments are missing or wrong

| ID | Defect | Reproduction | Root cause |
|---|---|---|---|
| **D1** (G1) | No public API enables docstring collection. `Parser` never calls `setCollectDocStrings`, so the documented Python entry point cannot produce docstrings at all. | `Parser().parse([f]); link()` → every `getDocstring()` empty; the same source through `core.Factory` + `setCollectDocStrings(True)` works. | `Parser._mkBuilder` (`python/pssparser/parser.py`) omits the call. |
| **D2** (G2) | **Qualified fields lose their doc comment.** `rand int x;` gets nothing; `int y;` in the same scope works. | `component C { // doc\n int f1; action A { // doc\n rand int x; // doc\n int y; } }` → `f1` ✔, `x` ✘, `y` ✔ | `visitData_declaration` (`AstBuilderInt.cpp:2445`) anchors the lookup on `ctx->data_type()->start`. Under `attr_field`, the `rand` / `static const` token sits between the comment and that anchor, so `getHiddenTokensToLeft` sees only whitespace. |
| **D3** | Line-comment association **ignores the blank-line rule entirely** — a comment separated from the declaration by blank lines still attaches. Inconsistent with block comments, where the rule *is* enforced. | `// far away doc\n\n int f1;` → attaches (should not). | `processDocStringSingleLineComment` (`AstBuilderInt.cpp:3990`) accepts `ws_tokens` and **never uses it**. |
| **D4** | Unrelated line-comment blocks are **concatenated**. | `// block one\n\n// block two\nint f1;` → `' block one\n block two\n'` | Same function loops over every channel-11 token returned, with no run-boundary logic. |
| **D5** | Block-comment cleanup **fails on ordinary indentation**, leaving `*` markers and full source indentation in the body. Output is unusable as RST — leading whitespace turns prose into block quotes and literal blocks. | An 8-space-indented `/** * Line one. */` yields `'\n         * Line one.\n         *\n         *     indented code\n         '` | The `*`-stripping loop (`AstBuilderInt.cpp:3963`) only handles *exactly one* whitespace character before `*`. There is also **no dedent step** anywhere. |
| **D6** | A block comment **immediately adjacent** to the declaration is silently dropped. | `/** doc */int f1;` → empty | `processDocStringMultiLineComment` returns an empty string on the `last_ws_line < 0` path (no whitespace between comment and declaration) — the branch is a no-op with a stale comment. |
| **D7** | Copy-paste bug in the block-comment line counter: the loop is bounded by `comment.size()` while scanning `ws`. | latent; skews the gap calculation when whitespace is longer than the comment | `while (i < comment.size() && (i=ws.find('\n', i)) != npos)` (`AstBuilderInt.cpp:3946`) — should bound on `ws.size()`. |
| **D8** | Doc-comment **marker forms are not recognized**: `///`, `//!`, `/*! … */` leave marker residue in the body (`/ text`, `! text`). | `/// doc` → `' / doc'` | Both processors strip a fixed 2 characters (`substr(2)`, `substr(2, n-4)`). |

### 2.2 Coverage gaps

| ID | Gap | Impact |
|---|---|---|
| **D9** | `EnumItem`, `FunctionParamDecl`, and `TemplateParamDecl` never receive docstrings. All three derive from `ScopeChild`/`NamedScopeChild`, so the field exists and is simply never populated — they are built into typed lists (`getItems()`, `getParameters()`) rather than through `addChild`. | Enum values and function parameters cannot be documented. Both are routine in real PSS and both are called out in the `sphinx-pss` field vocabulary (`:param:`). |
| **D10** | No trailing/inline comment support (`rand int len; // bytes`). | A common style silently produces no documentation. |
| **D11** | `Location.extent` is `-1` on most nodes and `endLocation` exists only on `Scope`, not `ScopeChild`. | `[source]` links can target a line but not a range; no exact source slicing for viewcode. |
| **D12** | The standard-library `.pss` sources (`src/stdlib/*.pss`) are **not** in `setup.py`'s `package_data`, so an installed wheel does not ship them, and there is no API to locate them. | Blocks `sphinx-pss` Phase 3 (the annotated core-library reference and its reconciliation test). |

### 2.3 Annotation syntax — **in scope** (resolved §8)

| ID | Gap | Status |
|---|---|---|
| **D13** (G3) | `TOK_COMMENT_AT: '//@'` (`PSSLexer.g4:184`) is unreachable — `SL_COMMENT` (line 189) matches longer and wins, so `//@doc(…)` becomes comment text. The LRM defines **no** comment-form annotation, so this is a dead pssparser extension. | Release C — `E8`. |
| **D14** (G4) | Annotation application diverges from the LRM. Grammar implements `@doc(text = …)` with positional/named/mixed paren forms (`PSSParser.g4:2023-2047`). PSS 3.1 Syntax 20 specifies **literal braces with dot-prefixed named params only**: `annotation_params_list ::= { annotation_param_item {, …} }`, `annotation_param_item ::= . identifier = constant_expression` — confirmed against Example323 (`@code_doc {.text="Zero the target memory word" }`), where the outer braces are literal and the inner braces are BNF repetition. The LRM has **no positional form**. | Release C — `E9`. Resolved: implement the LRM mechanism now (§8). |

---

## 3. Design: replace the doc-comment subsystem

`addDocstring` + `processDocStringSingleLineComment` + `processDocStringMultiLineComment` (`AstBuilderInt.cpp:3845-4000`) should be **removed**, not patched. D3–D8 are not independent bugs; they are consequences of one structural mistake:

> The code fetches **three separate channel-filtered token lists** (WS=10, SLC=11, MLC=12) and then attempts to reconstruct their relative order by comparing line numbers.

Every ordering bug above follows from that. ANTLR's `BufferedTokenStream` already offers the right primitive — `getHiddenTokensToLeft(tokenIndex)` with no channel argument returns **all** off-channel tokens in source order (confirmed in `BufferedTokenStream.h:86`). One ordered list makes association a simple backward scan, and the line-number arithmetic disappears entirely.

### 3.1 New component: `DocCommentExtractor`

New files `src/DocCommentExtractor.{h,cpp}`, unit-testable in isolation from the builder.

```cpp
struct DocComment {
    std::string    raw;        // verbatim source, markers included
    std::string    text;       // normalized body (what getDocstring() returns)
    DocCommentForm form;       // Line, DocLine, Block, DocBlock
    ast::Location  location;   // first character of the comment block
    bool           trailing;   // same-line trailing comment (E5)
};

class DocCommentExtractor {
public:
    DocCommentExtractor(antlr4::BufferedTokenStream *toks,
                        int32_t file_id,
                        const DocCommentOptions &opts);

    // Leading doc comment for the declaration starting at `anchor`.
    bool extractLeading(antlr4::Token *anchor, DocComment &out) const;

    // Trailing same-line comment following `stop` (E5).
    bool extractTrailing(antlr4::Token *stop, DocComment &out) const;
};
```

### 3.2 Association algorithm (leading)

Deterministic, uniform for every comment form:

1. `getHiddenTokensToLeft(anchor->getTokenIndex())` — one list, source order.
2. Scan **backwards** from the anchor:
   - whitespace containing **0 or 1** newline → continue (the normal newline + indent between comment and declaration);
   - whitespace containing **≥2** newlines (a blank line) → **stop**. This is the single association rule, applied to line *and* block comments alike (fixes D3, and makes the existing block-comment behavior the specified behavior rather than an accident);
   - a comment token → add to the run and continue;
   - anything else → stop.
3. The run is the doc block. Consecutive line comments accumulate; a block comment terminates the run (a block comment is a complete block by itself). Fixes D4.
4. Zero whitespace between comment and declaration is a **valid** association, not a rejection. Fixes D6.
5. Reverse the run to source order and normalize (§3.3).

The whole gap computation of D7 disappears — newlines are counted in the whitespace token that is actually adjacent, never reconstructed from line numbers.

### 3.3 Normalization

Produces `text`; `raw` is always retained verbatim so downstream tools can implement other dialects (Doxygen, and the deferred annotation source) without re-lexing.

1. **Strip markers by form** — longest match first, so `///` and `//!` are recognized before `//`, and `/**`/`/*!` before `/*` (fixes D8):

   | Form | Opens | Per-line prefix | Closes |
   |---|---|---|---|
   | `Line` | `//` | — | EOL |
   | `DocLine` | `///`, `//!` | — | EOL |
   | `Block` | `/*` | optional `*` | `*/` |
   | `DocBlock` | `/**`, `/*!` | optional `*` | `*/` |

2. **Strip the continuation `*`** on block-comment lines: optional leading whitespace, then `*`, then an optional single space. Arbitrary indentation depth — fixes the half-working loop in D5.
3. **Dedent** — compute the longest common leading-whitespace prefix across all non-blank lines and remove it, ignoring the first line (Python `inspect.cleandoc` semantics). **Relative indentation must be preserved**, since the consumer parses the body as reStructuredText where indentation is syntax. This is the missing step that makes D5 fatal rather than cosmetic.
4. **Trim** leading and trailing blank lines; do not trim trailing whitespace inside the body.
5. Tabs are expanded to spaces before the common-prefix computation (tab width 4, configurable) so mixed indentation dedents predictably.

### 3.4 Anchor selection — fixing D2 properly

D2's real cause is that the doc anchor is chosen by whichever visitor happens to construct the node, so a wrapping grammar rule shifts it. The narrow fix ("also check `attr_field`") would leave every other wrapper rule broken in the same way.

Proper fix: **the anchor is always the start token of the outermost declaration context as written in source**, established with an explicit RAII scope:

```cpp
class DocAnchorScope {                 // src/DocAnchorScope.h
public:
    DocAnchorScope(AstBuilderInt *b, antlr4::Token *tok);   // push
    ~DocAnchorScope();                                      // restore
};
```

`visitAttr_field` (and every other wrapper identified by the E2.4 audit) opens a `DocAnchorScope(this, ctx->start)` before delegating; `addChild` uses the innermost active anchor, falling back to the token it is handed. Explicit, scope-safe, and it cannot leak across sibling declarations.

**E2.4 is the audit item**: every `addChild` call site in `AstBuilderInt.cpp` (~40 sites) is checked against its grammar rule, and any wrapper that can precede the anchor gets a `DocAnchorScope`. Known candidates beyond `attr_field`: `flow_ref_field_declaration`, `resource_ref_field_declaration`, `component_pool_declaration`, `object_bind_stmt`, and the `override`/`abstract` declaration forms. The audit is the deliverable, not the guess-list.

### 3.5 Trailing comments — the convention (resolved §8)

Two prior-art conventions, and they disagree:

| Tool | Rule |
|---|---|
| **Doxygen** | A trailing comment documents the preceding member **only** with an explicit `<` marker: `///<`, `//!<`, `/**< … */`, `/*!< … */`. An unmarked trailing comment is not documentation. |
| **sphinx-systemverilog** | An unmarked trailing comment on the same line attaches to the declaration it follows (`docs/usage/native-style.md`: *"A trailing inline comment documents the declaration on its own line"*), implemented as a same-line reassignment in `model/comments.py`. |

**Adopted: both, with the unmarked form primary.**

1. A comment beginning on the same line as the **end** of a declaration attaches to that declaration as its trailing doc comment — no marker required.
2. Doxygen's `<` marker forms are additionally recognized, and the `<` is stripped as part of marker removal (§3.3 step 1). They are accepted, not required.
3. **A leading doc comment always wins.** A trailing comment is used only when the declaration has no leading doc comment. Predictable, and it avoids inventing a merge rule that neither prior tool has.
4. **A trailing comment is never also a leading comment.** In the backward leading scan (§3.2), a candidate run is rejected if its last comment token begins on the same line as the preceding non-hidden token — i.e. it belongs to the previous declaration. This is the interaction that made E5 worth confirming before building.

Rationale for not requiring `<`: E2.5 resolves that *all* comment forms count as doc comments, so a plain `//` above a declaration documents it. Requiring a marker below a declaration but not above it would be internally inconsistent. Doxygen requires `<` because plain `//` is *not* a doc comment there — the premise does not hold for us. Accepting `<` anyway costs nothing and does the expected thing for Doxygen-trained authors.

This must be written up in the `pssparser` doc-comment reference (`E10`) and mirrored in `sphinx-pss`'s `docs/usage/native-style.md`.

### 3.6 Compatibility

- `getDocstring()` keeps returning normalized text. Existing consumers see **better** text (dedented, markers stripped) but the shape is unchanged.
- **Behavior changes that are intentional and could surprise:** line comments separated by a blank line no longer attach (D3), and adjacent blocks no longer merge (D4). Both make line comments behave the way block comments already do. Call these out in the changelog as a fix, not a break.
- Default `setCollectDocStrings(false)` is unchanged, so anything not asking for docstrings is unaffected.
- New AST fields are additive (`ast/*.yaml`), and `gen-pyext` regenerates the Python bindings, so no hand-written binding work.

---

## 4. Work items

IDs are referenced from `sphinx-pss`'s `implementation-plan.md` Phase 0.5.

### Release A — unblocks sphinx-pss Phase 1

| ID | Task | Done when |
|---|---|---|
| ☑ `E1` | `Parser(collect_docstrings: bool = False)`; thread through `_mkBuilder` → `setCollectDocStrings`. Default unchanged (D1) | **Done.** Set on every `_mkBuilder` call, not only on creation: `link()` drops the builder, so a `Parser` reused across a link boundary would otherwise come back with collection off. `collect_docstrings` property added |
| ☑ `E2.1` | Add `src/DocCommentExtractor.{h,cpp}` implementing §3.1–§3.3; no builder wiring yet | **Done.** 34 gtest cases in `tests/src/TestDocCommentExtractor.cpp`, run over a real `PSSLexer` stream but with no builder |
| ☑ `E2.2` | Replace `addDocstring` and both `processDocString*` functions with calls into the extractor; **delete the old implementations** (D3–D8) | **Done.** Both `processDocString*` deleted from `.cpp` and `.h`; `addDocstring` is now 12 lines |
| ☑ `E2.3` | `DocAnchorScope` (§3.4); apply to `visitAttr_field` (D2) | **Done.** `src/DocAnchorScope.{h,cpp}`; `push_scope` pushes a null sentinel so a nested declaration cannot inherit a wrapper's anchor |
| ☑ `E2.4` | **Audit every `addChild` call site** against its grammar rule; add `DocAnchorScope` wherever a wrapper rule can precede the anchor | **Done.** Audit table in §10.1. Eight wrapper sites, one test each |
| ☑ `E2.5` | `DocCommentOptions` — tab width, and a strict mode in which only `///`/`//!`/`/**`/`/*!` count. **Default: all forms count** (resolved §8; matches current behavior and the `native` style in design §3.1). Strict mode exists for projects that want ordinary comments ignored | **Done.** Exposed as `setDocCommentTabWidth()` / `setDocCommentStrictMarkers()` on `IAstBuilder` |
| ☑ `E3` | Populate docstrings for `EnumItem`, `FunctionParamDecl`, `TemplateParamDecl` via an `attachDocstring(node, tok)` helper at their construction sites (D9) | **Done.** Six construction sites. `attachDocstring` deliberately ignores the active anchor — these nodes sit inside a declaration that may have one, and each carries its own comment |
| ☑ `E10` | **Doc-comment reference** in `docs/` — the association rules (§3.2), supported forms and marker handling (§3.3), the trailing-comment convention (§3.5), and the behavior changes in §3.6. Prior art is cited so the choices are traceable. Without this, "be consistent with other doc tools" is unverifiable | **Done.** `docs/doc_comments.rst`, added to the toctree |
| ☑ `E-TEST-A` | Test suite per §6 for all of the above | **Done.** 34 gtest + 23 pytest cases; corpus check runs over the standard library. `ctest` added to the Forgejo CI workflow — the gtest target was being built and never run |
| ◐ `E-REL-A` | Version bump + changelog entry naming the behavior changes in §3.6 | Version bumped `3.0.2` → `3.1.0`; `CHANGELOG.md` created. **Tagging/publishing left to the maintainer**, as is pinning the floor in `sphinx-pss` |

> **Note on `//@`:** an earlier draft carried an `E2.6` item to strip a leading `@…` line from extracted comments, because the dead `TOK_COMMENT_AT` token (D13) lets `//@doc(…)` fall into the docstring as prose. It is **retired**. With D13 resolved by removing the token (`E8`), `//@…` is simply an ordinary comment, and silently deleting a line of a user's comment text would be exactly the kind of quiet special-case this plan is meant to avoid. Behavior in Release A is unchanged from today.

### Release B — completeness

| ID | Task | Done when |
|---|---|---|
| ☑ `E4` | Expose the full `DocComment` on the AST — `doc_raw`, `doc_form`, `doc_location` on `ScopeChild` | **Done.** `getDocRaw()` / `getDocForm()` / `getDocLocation()`; `docForm` is a generated `DocCommentForm` enum. Required a `pyastbuilder` fix — see §10.4 |
| ☑ `E5` | Trailing same-line comments (D10) per the **§3.5 convention** | **Done.** The trailing lookup needs the *statement's* stop token, not the declarator's: for a field the `;` sits between the declarator and the comment, so looking right from the declarator finds nothing |
| ☑ `E6` | Source extents (D11) — `endLocation` on `ScopeChild`, and `Location.extent` populated | **Done.** `endLocation` was *moved up* to `ScopeChild` rather than duplicated: `Scope`, `FunctionDefinition`, `ExecScope` and `ConstraintScope` each declared their own, and all four now inherit it |
| ☑ `E7` | Ship the standard library (D12) — `.pss` sources in the package, `get_stdlib_dir()` / `get_stdlib_files()` | **Done and verified from an installed wheel** in a clean venv, not just in the source tree. Note the trap in §10.3 |
| ☑ `E-TEST-B` | Tests for E4–E7 | **Done.** |
| ◐ `E-REL-B` | Version bump + changelog | Folded into the single 3.1.0 entry; tagging left to the maintainer |

### Release C — LRM annotation conformance

Promoted from "deferred" (resolved §8: implement the LRM 3.1 mechanism now). Independent of Releases A and B — it touches the grammar, not the doc-comment subsystem.

| ID | Task | Done when |
|---|---|---|
| ☑ `E9` (D14) | **Add the LRM Syntax-20 application form** — `@type {.name = expr, .name = expr}` | **Done.** Unambiguous against both the paren forms and a following declaration, since no body item begins with `{` |
| ☑ `E9.1` | **Retain the paren form** `@type(expr, name = expr)` as a documented `pssparser` extension | **Done.** Every existing annotation test passes unchanged; `docs/annotations.rst` marks the LRM form canonical |
| ☑ `E9.2` | Conformance check: **standalone annotations** (LRM 7.13) and the "error if no subsequent element" rule | **Done, and both were wrong.** See §10.5 |
| ☑ `E8` (D13) | **Remove `TOK_COMMENT_AT`** and its reference in the `annotation` rule | **Done.** `//@…` remains an ordinary comment, and is collected verbatim as a docstring — nothing edits the text |
| ☑ `E-TEST-C` | Tests per §6 | **Done.** `tests/python/parsing/test_annotations_lrm.py`, 14 cases including LRM Example323 verbatim |
| ◐ `E-REL-C` | Version bump + changelog | Folded into the single 3.1.0 entry; tagging left to the maintainer |

---

## 5. Explicitly rejected approaches

Recording these so they are not reintroduced:

- **Source-text re-scan in `sphinx-pss`.** The original Phase-0.5 contingency. Withdrawn: two implementations of comment association that will disagree, with no way to tell which is right. `implementation-plan.md` `P1-IMPL-5` and its `pss_recover_comments` config should be **deleted**, and the corresponding risk-register rows removed.
- **Patching `processDocString*` in place.** D3–D8 share one root cause (§3); patching them individually preserves the three-list ordering design that produced them.
- **Post-processing `getDocstring()` downstream** (dedent, marker-stripping, or `*` removal in `sphinx-pss`). Normalization belongs where the source text and its lexical form are both known.
- **Adding a doc-comment channel to the lexer.** Would require classifying `///` vs `//` at lex time, hard-coding one doc convention into the grammar. Form detection belongs in the extractor, where it is data-driven and testable.
- **Inferring provenance in the extension by matching locations against `ExtendType` extents.** Unnecessary — `getParent()` already answers it exactly (§1.1).

---

## 6. Test plan

All tests land in `pssparser`. Existing docstring tests live in `tests/python/source_references/test_docstrings.py`; the association tests there encode current behavior and must be reviewed against §3.6 (the D3/D4 fixes change line-comment outcomes).

**C++ unit tests** (`tests/`, gtest) — `DocCommentExtractor` in isolation:

| Area | Cases |
|---|---|
| Association | adjacent; 1 newline gap; blank-line gap rejected (D3); two blocks not merged (D4); zero whitespace accepted (D6); comment at buffer start; comment after another declaration |
| Forms | `//`, `///`, `//!`, `/* */`, `/** */`, `/*! */`; marker residue absent (D8) |
| Normalization | `*` continuation at 0/1/2/8 spaces of indent (D5); dedent preserving relative indent; tabs; blank-line trim; a nested indented code block survives round-trip into RST |
| Raw fidelity | `raw` is byte-identical to source for every form |

**Python integration tests** (`tests/python/source_references/`):

| ID | Case |
|---|---|
| `T-D1` | `Parser(collect_docstrings=True/False)` — on/off through the public API |
| `T-D2` | `rand`, `static const`, plain fields, in action / struct / component scope |
| `T-D2b` | One case per wrapper rule found by the E2.4 audit |
| `T-D3/4` | Blank-line gap rejected; adjacent blocks not merged — **for line comments**, mirroring the existing block-comment tests |
| `T-D5` | An indented `/** */` block yields dedented text with no `*` residue |
| `T-D9` | Enum items, function params, template params document |
| `T-D10` | Trailing comments per §3.5 (Release B): unmarked attaches to its own declaration and **not** the next; `///<`/`//!<`/`/**< */` accepted with the `<` stripped; leading+trailing → leading wins; trailing-only → trailing used |
| `T-D11` | `endLocation`/`extent` bound the declaration (Release B) |
| `T-D12` | `get_stdlib_dir()` returns real files from an installed wheel (Release B) |
| `T-D13` | `//@doc(…)` is an ordinary comment; no `TOK_COMMENT_AT` remains (Release C) |
| `T-D14` | LRM brace form `@doc {.text = "…"}` parses; produces the same `AnnotationParam` structure as the paren form; multiple params; the paren form still parses; **Example323 from the LRM parses verbatim** (Release C) |
| `T-D14b` | Standalone annotation terminated by `;`, and the "no subsequent element" error case (LRM 7.13) (Release C) |
| `T-REG` | Every existing docstring test still green, with §3.6 changes reviewed and re-baselined deliberately; every existing annotation test in `tests/python/parsing/test_annotations_31.py` green unchanged |

**Corpus check:** run the builder with docstring collection over the existing `tests/python/corpus` sources and the standard library; assert no crashes and no docstring containing a residual marker (`/*`, `*/`, a leading `*`, or `//`). This catches normalization escapes that unit tests miss.

---

## 7. Sequencing

1. **E1** first and alone — one-line change, immediately unblocks `sphinx-pss` `P1-IMPL-1` from having to drive the low-level `core.Factory` API.
2. **E2.1** (extractor + its unit tests) before any builder wiring, so the algorithm is validated in isolation.
3. **E2.2** swap, then re-baseline existing tests against §3.6.
4. **E2.3 → E2.4** — the single known anchor fix, then the systematic audit.
5. **E2.5, E3** — independent, parallelizable. **E10** (the doc-comment reference) is written alongside, not after, since it is what makes the §3.5 convention reviewable.
6. **Release A.** `sphinx-pss` Phase 1 proceeds against it.
7. **Release B** (E4–E7) can run concurrently with `sphinx-pss` Phase 1–2; only `E7` gates `sphinx-pss` Phase 3.
8. **Release C** (E8, E9) is independent of both — grammar work, no overlap with the doc-comment subsystem. It can land any time; nothing in `sphinx-pss`'s current phase plan waits on it.

`sphinx-pss` Phase 1 depends on Release A only. `E7` is the sole Release-B item on a `sphinx-pss` critical path.

---

## 8. Resolved (M. Ballance, 2026-08-13)

- **`E2.5` default — all comment forms count as doc comments.** Plain `//` and `/* */` document, alongside `///`, `//!`, `/**`, `/*!`. Preserves current behavior and keeps the `native` style (design §3.1) marker-free. A strict mode remains available as an option, not the default.
- **`E5` trailing comments — follow prior art, and document the choice.** Doxygen and sphinx-systemverilog disagree (marker-required vs. unmarked), so §3.5 adopts **both**: unmarked is primary, Doxygen's `<` markers are also accepted, leading always wins, and a trailing comment is excluded from the next declaration's leading scan. Requiring `<` would have contradicted the resolution above — plain `//` documents above a declaration, so it must document below one too. `E10` writes this up so the choice is traceable rather than folklore.
- **`E9`/D14 — implement the LRM 3.1 mechanism now.** Promoted out of "deferred" into **Release C**. The LRM form `@doc {.text = …}` (literal braces, dot-prefixed named params, no positional form) becomes canonical; the existing paren form is retained as a documented `pssparser` extension so current tests and models keep working. D13 (`//@`) is resolved by **removing** the dead token, since the LRM defines no comment-form annotation.
- **Re-baselining `test_docstrings.py` — accepted**, with consistency against other doc tools as the standard. The D3/D4 fixes make line comments behave like block comments, which is what Doxygen, Javadoc, and Python docstrings all do: association is adjacency, and a blank line breaks it. §3.5/§3.6 and `E10` record the rules and their prior art.
- **Version floor — hard requirement.** `sphinx-pss` requires the Release-A `pssparser` outright rather than degrading. Partially-working doc extraction is worse than a clear failure.

  > **Superseded in mechanism, not in intent — see `pssparser-followup-plan.md` §4.** `pssparser` versions as `<PSS major>.<PSS minor>.<patch>`, where the first two components name the *LRM revision targeted*, not any capability. A version floor therefore cannot express "has the doc-comment rework", and the `>=3.1.0` floor this resolution produced was additionally demanding PSS 3.1 language support. Replaced by a capability probe that fails just as hard — the "rather than degrading" half of this resolution stands unchanged.

### 8.1 Still open

- **Deprecating the paren annotation form (`E9.1`).** Retained without a warning for now. Whether it should eventually warn — or stay a permanent extension, since it offers a positional form the LRM lacks — is a `pssparser` API-policy call, not a blocker.
- **Effect on the `sphinx-pss` annotation deferral.** With `E9` scheduled, the `@doc`-as-doc-source work in `sphinx-pss` (design §3.2, §14 Q2) is **no longer blocked** — it was blocked only on the G4 syntax question. It remains *unscheduled* per that decision, but the reason has changed from "blocked" to "deprioritized", and design §3.2's status note should be updated to say so.

---

## 9. Impact on the `sphinx-pss` plan

Once this plan is accepted, `design/implementation-plan.md` needs these edits:

1. **§2 Phase 0.5** — replace `U-G1`/`U-G2` with references to `E1`/`E2`/`E3` here, and **delete the G2 source-text contingency** (§5 above).
2. **`P1-IMPL-5`** — drop the source-text fallback and the `pss_recover_comments` config.
3. **`P1-IMPL-10`** — drop the "strip a leading `@…` line" requirement. It mirrored the retired `E2.6`; with `E8` removing the dead token, `//@…` is an ordinary comment and must not be silently edited.
4. **`P0-TEST-3` / the `upstream` marker** — with a hard version floor (§8), the capability-probe fixture is unnecessary. Replace it with a version assertion at import.
5. **Risk register** — remove "G2 source-text fallback masks the real fix"; add "Release A slips", mitigated by `E1` alone being enough to *start* Phase 1.
6. **`docs/usage/native-style.md` (`P1-DOC-3`)** — must state the §3.5 trailing-comment convention and cite `pssparser`'s `E10` reference rather than restating the rules.

`design/sphinx-pss-design.md` needs one edit: **§3.2's deferral note** should say the `@doc` doc-source work is deprioritized rather than blocked, since `E9` settles the syntax question (§8.1).

Two risks also come **off** the `sphinx-pss` books as a result of the investigation: extension provenance needs no parser work (§1.1), and normalization/dedent is handled upstream rather than in `docparse`.

---

## 10. Progress log

Implemented in the `packages/pssparser` working clone (the editable-installed one,
which is ahead of the sibling `~/projects/psstools/pssparser` checkout).

**All three releases complete.** 2065 pytest cases pass (baseline 2017), plus 34
new C++ unit tests. No regressions at any step.

Files added: `src/DocCommentExtractor.{h,cpp}`, `src/DocAnchorScope.{h,cpp}`,
`tests/src/TestDocCommentExtractor.cpp`,
`tests/python/source_references/test_doc_comments.py`,
`tests/python/parsing/test_annotations_lrm.py`, `docs/doc_comments.rst`,
`docs/annotations.rst`, `CHANGELOG.md`.

Released as a single `3.1.0` rather than three versions, since nothing was
published between them. **Tagging and publishing are left to the maintainer**,
as is pinning the floor in `sphinx-pss`.

### 10.1 E2.4 audit result

The audit was run against the grammar rather than by inspection: for each of the
36 `addChild` call sites, find every rule that references the site's own rule and
report whatever precedes the reference within that alternative (paren-aware, so
alternatives inside a group are not mis-split).

Only three target rules turn out to be wrapped at all:

| Target rule | Wrapper | Tokens ahead of the anchor |
|---|---|---|
| `action_declaration` | `abstract_action_declaration` | `abstract` |
| `monitor_declaration` | `abstract_monitor_declaration` | `abstract` |
| `data_declaration` | `attr_field` | `access_modifier? rand? (static const)?` |
| `data_declaration` | `component_data_declaration` | `access_modifier? ((static const) \| mutable \| instance)?` |
| `data_declaration` | `const_field_declaration` | `static? const` |
| `data_declaration` | `annotation_attr_field` | `(static const)?` |
| `data_declaration` | `activity_data_field` | `action` |

Plus one class the plan did not anticipate: the `*_ann` rules
(`action_body_item_ann`, `component_body_item_ann`, `activity_stmt_ann`) wrap a
body item in `annotation*`, so an annotation written between a doc comment and
its declaration displaces the anchor. These are anchored only when an annotation
is actually present, which makes the override a strict no-op otherwise.

**The plan's guess-list was wrong in both directions.**
`flow_ref_field_declaration`, `resource_ref_field_declaration`,
`component_pool_declaration` and `object_bind_stmt` are *not* wrapped — each
carries its own leading keyword (`input`, `lock`, `pool`, `bind`) inside its own
rule, so `ctx->start` was already correct. They have regression tests
(`test_unwrapped_declarations_still_document`) rather than anchors. Conversely
the `*_ann` and `abstract_*` wrappers were missing from the list.

### 10.2 Deviations from the plan, and why

- **§3.2's blank-line rule needed line arithmetic after all.** The plan says the
  rule is "whitespace containing ≥2 newlines". That is wrong as stated, because
  `SL_COMMENT` consumes its own terminating newline (`PSSLexer.g4:189`) while
  `ML_COMMENT` does not: after a line comment, *one* newline in the following
  whitespace already means a blank line. The implementation compares the
  comment's last content line against the next token's line, which is uniform
  across both forms. The plan's real point — that the *ordering* must not be
  reconstructed from three channel-filtered lists — is honored: there is one
  ordered list, and whitespace tokens are not inspected at all.

- **§3.3's "ignore the first line" applies to block comments only.** For a block
  comment the first line follows the opening marker, so its indentation is
  meaningless and `inspect.cleandoc` semantics are right. In a run of line
  comments every line is a real content line; ignoring the first would compute
  the common prefix from the remainder and destroy the relative indentation the
  same section requires be preserved.

- **§3.5.4's trailing-comment exclusion carries an exception.** As literally
  stated ("reject if the last comment token begins on the same line as the
  preceding non-hidden token") it rejects
  `function void f(/** how many */ int len)` — the comment begins on the same
  line as `(`. That would silently undocument every parameter written in the
  usual one-line form, which is the main thing `E3` exists to enable. The rule
  now makes an exception when the comment also *ends* on the anchor's own line,
  where it is positionally leading whatever follows it. A line comment can never
  satisfy this, so the `int a; // x` / `int b;` case is unaffected.

- **The §3.5.4 exclusion landed in Release A, not Release B.** It is part of
  correct leading association, and staging it separately would have meant two
  behavior changes to the same rule in consecutive releases. It is recorded in
  `CHANGELOG.md` under the §3.6 behavior changes.

- **`E2.5` is exposed as two scalar setters** rather than a `DocCommentOptions`
  parameter, so `IAstBuilder` — a public header — does not have to expose an
  internal type.

### 10.3 Found along the way — not in this plan's scope

- **`SymbolTypeScope` hides the docstring.** Linking wraps a type declaration,
  and `getDocstring()` on the wrapper returns empty while the declaration holds
  the text. Consumers must go through `getTarget()`. This is a real trap for
  `sphinx-pss` and is called out in `docs/doc_comments.rst`; it is worth a
  convenience accessor in a later release.

- **`symtabAt()` segfaults on a missing name.** The generated binding does
  `map.find(key)` and dereferences the iterator without comparing it to `end()`
  (`ast.pyx`, every `symtabAt` overload). A lookup miss is undefined behavior
  rather than a reported miss. Unrelated to doc comments — it reproduces with
  `Parser()` and no comments in the source — but `sphinx-pss` will hit it, and
  the new tests avoid the API entirely. Worth filing separately.

- **`visitActivity_data_field` never visits its `data_declaration`**, so
  `action int x;` inside an activity appears to build nothing. Untouched here;
  the anchor was added so the site is correct if the body is ever fixed.

### 10.4 Release B required a `pyastbuilder` fix

E4 and E6 are both blocked without it, so this is not optional.

`Linker.visitTypeUserDef` set `t.target` only on a class's **first** reference
to a given type — the assignment sat inside the guard that exists to add the
type to `deps` once, for include generation. `ScopeChild` previously had exactly
one `Location` field (`location`); adding `docLocation` and `endLocation` gave
it three, so the second and third resolved to `None` and `pyext_accessor_gen`
died on `t.target.accept(self)` with an `AttributeError` naming neither the
class nor the field.

Fixed in `packages/pyastbuilder` (`src/astbuilder/linker.py`): the target is
resolved on every reference, and only the `deps` insertion stays guarded.

**This needs its own release before `pssparser` CI will build**, since
`ivpm.yaml` resolves `pyastbuilder` from git (`default-dev`) or PyPI
(`default`), not from the local checkout.

### 10.5 E9.2 found two real conformance bugs

The plan allowed for "fix or file as found". Both were fixable.

- **Standalone annotations were indistinguishable from element annotations.**
  LRM 7.13: an annotation terminated by `;` "is attached to a lexical location",
  while an unterminated one attaches to "the next PSS model element declared in
  the scope". The grammar reaches a standalone annotation as an `annotation`
  followed by the null-statement alternative, which the visitor never sees, so
  every annotation was queued as pending and a standalone one silently
  documented whatever came next. Now told apart lexically, by whether the next
  on-channel token is `;`.

- **An annotation with no subsequent element was silently discarded.** LRM 7.13
  makes it an error, and Example32 calls the case out explicitly. `pop_scope`
  deleted the pending annotations with only a debug message. It now reports
  them. Note this only fires where the grammar admits a bare `annotation`
  (package scope); inside a `component` or `action` body the same source is
  already a syntax error, because `component_body_item_ann` is
  `annotation* component_body_item` and there is no body item to prefix.

Two further changes were needed for `T-D14`'s "Example323 parses verbatim",
neither of which the plan anticipated:

- **Annotations were not allowed on procedural statements.** Example323 applies
  `@code_doc` to a call inside a function body, and LRM 21.6.1 says `code_doc`
  "may be applied to statements and other executable elements". `annotation` is
  now an alternative of `procedural_stmt`, matching how `package_body_item`
  already admits one.

- **`code_doc` was not declared in the standard library.** Added to
  `src/stdlib/std_pkg.pss` per LRM Syntax 124.

### 10.6 Remaining

- `E-REL-A/B/C`: version is bumped and the changelog written; **tagging,
  publishing, and the `pyastbuilder` release are the maintainer's call**.
- §9's edits to `sphinx-pss`'s own `implementation-plan.md` and
  `sphinx-pss-design.md` are not done — this pass covered the `pssparser` work
  only.
