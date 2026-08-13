# sphinx-pss — Implementation, Test & Doc Plan

**Status:** In progress — Phases 0, 0.5 and 1 done; Phase 2 next
**Date:** 2026-08-13
**Companion to:** `design/sphinx-pss-design.md` (design decisions; §-refs below point there)
**Purpose:** Turn the approved design into a concrete, trackable build plan. Every work item has an ID (`P<phase>-<area>-<n>`), a checkbox, and a defined "done" condition. Implementation, tests, and docs are planned **together** per phase — a phase is not done until all three are.

## Progress log

*(Append newest-first as work lands. Each entry: what shipped, test/doc counts, deviations from plan.)*

- **2026-08-13 — Phase 1 complete.** The end-to-end vertical slice works: a single `autopssaction::` directive turns a `.pss` source file into a full doctree with linked types, index entries, permalinks and TOC entries. **311 tests green** (117 model, 73 docparse, 50 domain, 25 autodoc, 7 docs-build, the rest scaffolding/lexer/upstream); `docs/` builds under `-W` with `docs/examples/sample.md` rendering the fixture model — 40 object descriptions, all from source.
  *Shipped:* `model/{parse,objects,locations,builder,index}.py` (parse-once, provenance, source-faithful signatures, lexical type resolution); `docparse/{base,native,fields}.py` (the 13-field PSS vocabulary and its two-way AST cross-validation); `domain.py` (17 object directives, 15 roles, real `desc_parameterlist` nodes, TOC support); `autodoc/{documenters,directives}.py` (11 `autopss*` directives, both events); five doc pages.
  *Deviations and findings:*
  - Six further upstream gaps surfaced and are catalogued in §2.1 (`U-1`…`U-6`). Only `U-5` needed a workaround with any smell to it — one documented private-attribute read to make the degraded mode produce anything at all.
  - `pss_tolerate_link_errors` is implemented **now** rather than deferred to `P4-IMPL-8`: `P1-IMPL-2` requires per-file walking, and a failed `link()` leaves nothing walkable, so the builder grew a second dispatch table for pre-link declaration nodes. What P4 has left is hardening, not building.
  - `PssParseError` and `PssConfigError` both derive from `SphinxError`, so parser diagnostics reach the user instead of being re-wrapped as "Handler … threw an exception".
  - The shared index is keyed by `srcdir` in a module-level dict, not stored on the environment: Sphinx pickles the environment and the index holds a live Cython `Parser`. Events fire through `env.events` rather than `env.app`, which is deprecated for removal in Sphinx 11.
  - Signature rendering is a *quotation of the source* — `rand int size`, not `rand field size : int`. Two bugs were caught by writing the tests: the kind keyword printed twice, and `:qualname:` leaking into the displayed name.
  - Node ids preserve case (`pss-dma_pkg.DmaBuf`); `docutils.make_id` lowercases, which collides PascalCase types with snake_case members depending on what else a project declares.
  - The duplicate-object warning caught a real bug in the example page on its first build, which is the dogfooding working as intended.
- **2026-08-13 — Phase 0 complete.** Packaging (`pyproject.toml`, src-layout, editable install), the module skeleton of design §6.2, `config.py` with all eight `pss_*` values and a validator, the `pssparser>=3.1.0` import-time floor, `tests/` with the four markers, `docs/` building clean under `-W`, `cspell.json`, `ivpm.yaml` dep-sets, and Forgejo CI (PR workflow + nightly corpus workflow). **30 tests green.**
  *Not in the plan, added:* a **Pygments lexer for PSS** (`sphinx_pss/lexer.py`, 10 tests). It surfaced immediately — a ``pss`` code block warns under `-W` because Pygments ships no PSS lexer, which would hit every project documenting PSS, and Phase 3's `viewcode` needs the same lexer for its source listings. **Superseded 2026-08-13:** it moved to its own package, [`pygments-pss`](https://git.dvkit.org/psstools/pygments-pss.git), which `sphinx-pss` now depends on; the in-tree copy and its tests are gone, replaced by `tests/test_pygments_pss.py`.
  *Deviations:* `PssConfigError` derives from `sphinx.errors.ConfigError` rather than `Exception` — `EventManager.emit` re-wraps a plain exception as "Handler … threw an exception", burying the actual message. `P0-TEST-2` is partial: the `pss` domain assertion waits on `P1-IMPL-13`. Theme is `furo`, not `sphinx-rtd-theme`, which has no Sphinx 9 release.
- **2026-08-13 — plan reconciled with `pssparser-enhancement-plan.md` §9.** Phase 0.5 marked done (`pssparser` 3.1.0, Releases A/B/C). Source-text comment-recovery contingency withdrawn (`P1-IMPL-5`, `pss_recover_comments` deleted); `P1-IMPL-10` no longer strips a leading `@…` line; `P0-TEST-3` is now a hard version-floor assertion instead of a capability probe; `upstream` marker means fail, not skip. Two `pssparser` traps recorded for Phase 1 (`SymbolTypeScope.getTarget()` for docstrings; avoid `symtabAt()`). Risk register updated; design §3.2 restated as deprioritized rather than blocked.

---

## 0. Conventions & ground rules

- **Source** → `src/sphinx_pss/` (src-layout, importable as `sphinx_pss`). Package name **`sphinx-pss`** (design §13/§14 Q3).
- **Tests** → `tests/` (pytest). All tests live here, mirroring the package tree.
- **Docs** → `docs/` (Sphinx project). `design/` holds these design/plan docs; `docs/` root is the published doc set, which **dogfoods the extension on itself** (the sample model in Phase 1, the annotated PSS standard library from Phase 3).
- **Env:** the venv at `packages/python` — `source packages/python/bin/activate`. New deps go through `uv` **and** get recorded in `ivpm.yaml` (`dep-sets`).
- **Upstream repo:** `packages/pssparser` is a *separate* repo (`psstools/pssparser`). Items prefixed **`U-`** land there, not here. They are tracked in this plan because Phase 1 depends on them, but they need their own PRs.
- **Definition of Done (item):** code merged + tests green + relevant doc page builds with no new Sphinx warnings + box checked here with commit/PR ref.
- **Definition of Done (phase):** all phase items done + phase **acceptance test** passes in CI + `docs/` builds clean under `-W` + §9 status table updated.

### Test taxonomy (pytest markers)

| Marker | Scope | Speed |
|---|---|---|
| `unit` | Pure Python, no Sphinx app — model, docparse, flow/activity extraction. The bulk of coverage. | fast |
| `sphinx` | `@pytest.mark.sphinx` against a `tests/roots/` mini-project; asserts doctree nodes. | medium |
| `corpus` | Model run over the `pssparser` test corpus + PSS standard library; smoke + element-count floors. Opt-in (`-m corpus`), nightly CI. | slow |
| `upstream` | Asserts a `pssparser` behavior this project depends on (doc-comment extraction, extend provenance, stdlib shipping). A **failure**, not a skip — the version floor (`>=3.1.0`) is hard. | fast |

### Naming conventions used throughout

- PSS qualified names use `::` (`dma_pkg::Dma::Xfer`).
- Object kinds follow `PssObject.kind` (design §8).
- Fixture models live in `tests/fixtures/pss/`; Sphinx mini-projects in `tests/roots/<name>/`.

---

## 1. Milestone 0 — Scaffolding & tooling

Prerequisite for everything. No PSS logic yet.

### Implementation
| ID | Task | Done when |
|---|---|---|
| ☑ `P0-IMPL-1` | `pyproject.toml`: src-layout, dist `sphinx-pss`, package `sphinx_pss`, deps `sphinx`, `pssparser`; `py.typed` | `pip install -e .` succeeds in the venv |
| ☑ `P0-IMPL-2` | Package skeleton per design §6.2 — `__init__.py`, `config.py`, `model/{parse,builder,index,objects,flow,activity,locations}.py`, `docparse/{base,native,doxygen,fields,xref}.py`, `domain.py`, `autodoc/{documenters,directives,diagrams}.py`, `viewcode.py` (empty stubs) | `import sphinx_pss` works; `setup(app)` returns a metadata dict |
| ☑ `P0-IMPL-3` | `config.py`: register every `pss_*` value via `app.add_config_value` — `pss_source_dirs`, `pss_source_files`, `pss_doc_style`, `pss_document_stdlib`, `pss_tolerate_link_errors`, `pss_diagrams`, `pss_viewcode`, `pss_default_options` (design §7). **No `pss_recover_comments`** — the source-text contingency is withdrawn (enhancement-plan §5) | values readable from a built app; unknown `pss_doc_style` raises a clear config error |
| ☑ `P0-IMPL-4` | `README.md`: rename from `sphinxcontrib-pss-autodoc` → `sphinx-pss` (design §13) | README matches the dist name |

### Tests
| ID | Task | Done when |
|---|---|---|
| ☑ `P0-TEST-1` | `tests/conftest.py` + pytest config registering `unit`/`sphinx`/`corpus`/`upstream` markers; fixture dirs | `pytest -m unit` runs (0 tests OK) |
| ☑ `P0-TEST-2` | `tests/test_setup.py` — extension loads in a bare app, registers the `pss` domain and all config values | green; the `pss` domain assertion landed with `P1-IMPL-13` (`tests/domain/test_directives.py`) |
| ☑ `P0-TEST-3` | **Version floor**, not a capability probe (enhancement-plan §8): `sphinx_pss` asserts `pssparser >= 3.1.0` at import with an actionable message; `tests/test_version_floor.py` covers it | assertion fires on an older parser |

### Docs
| ID | Task | Done when |
|---|---|---|
| ☑ `P0-DOC-1` | `docs/conf.py`, `docs/index.md` (MyST), `docs/_static/`, build wiring | `sphinx-build -W docs docs/_build/html` succeeds |
| ☑ `P0-DOC-2` | `cspell.json` project word list — `pssparser`, `psstools`, `Accellera`, `autodoc`, `docparse`, `docstrings`, `stdlib`, `intersphinx`, `viewcode`, `covergroup`, `Graphviz`, `Xfer`, `qname`, `autopss*`, … | IDE diagnostics on `design/` clear |

### Ops
| ID | Task | Done when |
|---|---|---|
| ☑ `P0-OPS-1` | CI: `pytest -m "unit or sphinx"` + `sphinx-build -W docs` on PR; nightly adds `-m corpus`. Must build/install `pssparser` (it is a C++/Cython extension, not a pure wheel) — reuse the `ivpm` setup action | CI green on a trivial PR |
| ☑ `P0-OPS-2` | `ivpm.yaml` records added dev deps (`pytest`, `myst-parser`, `graphviz`, `beautifulsoup4`) | `ivpm.yaml` matches the installed set |

---

## 2. Phase 0.5 — Upstream `pssparser` fixes ⚠️ cross-repo — **DONE**

**Theme:** unblock Phase 1. Superseded by `design/pssparser-enhancement-plan.md`, which found the doc-comment subsystem carried eight defects rather than the two (G1/G2) recorded in the design doc, and replaced it rather than patching it. All three releases (A, B, C) are implemented in `packages/pssparser` and version-stamped `3.1.0`.

| ID | Repo | Task | State |
|---|---|---|---|
| ☑ `E1` (G1) | `pssparser` | `Parser(collect_docstrings: bool = False)` threaded through `_mkBuilder` | done — `Parser.collect_docstrings` property present |
| ☑ `E2` (G2 + D3–D8) | `pssparser` | `DocCommentExtractor` + `DocAnchorScope` replace `addDocstring`/`processDocString*`; anchor audit over all 36 `addChild` sites | done — 34 gtest cases |
| ☑ `E3` | `pssparser` | Docstrings on `EnumItem`, `FunctionParamDecl`, `TemplateParamDecl` | done |
| ☑ `E4`–`E7` | `pssparser` | `doc_raw`/`doc_form`/`doc_location`; trailing comments; `endLocation`/`extent`; stdlib shipped with `get_stdlib_dir()`/`get_stdlib_files()` | done |
| ☑ `E8`, `E9` | `pssparser` | `TOK_COMMENT_AT` removed; LRM Syntax-20 brace annotation form added, paren form retained | done |
| ☑ `E10` | `pssparser` | `docs/doc_comments.rst` — the association rules, marker forms, and the trailing-comment convention | done |
| ◐ `E-REL-*` | `pssparser` | Version bumped `3.0.2` → `3.1.0` + `CHANGELOG.md`; **tagging/publishing left to the maintainer** | pending maintainer |

**Consequences for this plan** (from enhancement-plan §9, applied below):

- The **source-text re-scan contingency is withdrawn**. Two independent implementations of comment association would disagree with no way to tell which is right. `P1-IMPL-5` no longer carries a fallback and `pss_recover_comments` does not exist.
- `P1-IMPL-10` no longer strips a leading `@…` line. With `E8` removing the dead `TOK_COMMENT_AT`, `//@…` is an ordinary comment and must not be silently edited.
- `P0-TEST-3`'s capability probe is replaced by a **hard version floor** (`pssparser>=3.1.0`) asserted at import. Partially-working doc extraction is worse than a clear failure.
- Extension provenance (`P1-IMPL-6`) needs **no** parser work — a member merged from `extend` keeps its own extend-site `location` and its `getParent()` still returns the `ExtendType`.
- Normalization (dedent, marker-stripping, `*` removal) happens upstream. `docparse` must **not** re-normalize.

**Traps carried over from enhancement-plan §10.3, which Phase 1 must handle:**

- **`SymbolTypeScope` hides the docstring.** Linking wraps a type declaration; `getDocstring()` on the wrapper is empty while the declaration holds the text. Consumers must go through `getTarget()`.
- **`symtabAt()` segfaults on a missing name** (generated binding dereferences `map.find()` without an `end()` check). `model/` must avoid the API.

### 2.1 Further upstream findings (this repo's Phase-1 spike, 2026-08-13)

> **Resolved into a plan.** These six findings and the dependency-pinning question they exposed are worked through in **`design/pssparser-followup-plan.md`** (the design), and broken into trackable items `F1`–`F5` / `G1` in **`design/pssparser-fixes-plan.md`** (the work plan). The table below is the summary; those documents are authoritative.
>
> The PSS Pygments lexer is **out of scope for both**: resolved 2026-08-13 as a separate package owned elsewhere. **Done** — `sphinx-pss` depends on [`pygments-pss`](https://git.dvkit.org/psstools/pygments-pss.git) and `sphinx_pss/lexer.py` is deleted.
>
> One correction it records is worth reading here: `pssparser` versions as `<PSS major>.<PSS minor>.<patch>`, so the `>=3.1.0` floor this plan adopted in §2 was asking for **PSS 3.1 language support** rather than for the doc-comment rework. The floor is interim at `>=3.0.3` and is to be replaced by a capability probe.

Four more gaps surfaced while grounding the builder against the real linked tree. None blocks Phase 1 — each has a contained, documented in-model handling — but all four are worth filing against `pssparser`, because in every case the parser *has* the information and the Python view does not.

| ID | Finding | Phase-1 handling |
|---|---|---|
| `U-1` | **`SymbolScope` (package) and `SymbolEnumScope` expose no declaration.** `getTarget()` is `None` for both, and their own `getDocstring()` is empty, so a package's and an enum's doc comment are unreachable from the linked tree — unlike `SymbolTypeScope`, where `getTarget()` works. The text *is* collected: `PackageScope` / `EnumDecl` reached through `Parser.user_units()` carry it. (For a package a single `target` is arguably wrong, since one package can be declared across several files — a doc-comment accessor that merges them is the likelier fix.) | `model/parse.py` builds a declaration index keyed on `(fileid, lineno)` from `user_units()`; the linked node's location joins to it exactly. This uses parser-provided docstrings through a supported traversal — it is **not** a second comment-association implementation, and so is not the contingency §5 of the enhancement plan withdrew. |
| `U-2` | **`EnumItem` locations are `(-1, -1)`.** The synthesized-member rule (`lineno < 0`) would therefore discard every enum value. `EnumItem` does carry its docstring correctly (`E3`). | The synthesized filter is applied by node kind, never blanket-wise; enum items are exempt and documented as such. |
| `U-3` | **`SymbolRefPath` is barely bound.** A `TypeIdentifier`'s `getTarget()` returns a `SymbolRefPath` exposing only `getPyref_idx()`, so a type reference cannot be resolved to its declaration from Python. | Type references render from the `TypeIdentifier` element names and resolve to a qualified name **through `PssIndex`**, which is the design's stated model (`PssObject.type_ref`) rather than a fallback. |
| `U-6` | **A line-comment run dedents to zero when any one line lacks a space after `//`.** `// a` / `//b` yields `"a"` and `" b"` — the common prefix across the run is 0, so the usual single space after `//` survives on every other line. Cosmetic in prose, but a one-space indent is a block quote in reStructuredText. Realistic triggers: `//@…`, `//---` rules, and ASCII diagrams. Stripping one optional space per line as part of marker removal (as the block form already does for `* `) would fix it before the dedent runs. | Accepted as-is. Re-normalizing downstream is explicitly rejected (enhancement plan §5), so `docparse` leaves the text alone and the test asserts content rather than exact whitespace. |
| `U-5` | **A failed `link()` leaves nothing walkable.** `link()` raises *before* it snapshots `file_map` and sets `_root`, so after a link error `user_units()` returns `[]` and `file_map` is empty — the per-file scopes the degraded mode is supposed to fall back to are unreachable through the public API. | `model/parse.py` recovers by parsing again into a parser that is **never linked**, whose per-file scopes it therefore still owns; reading `_files` / `_filenames` on that parser is safe for exactly that reason, and is the one documented private-attribute access in the codebase. A public pre-link `units()` accessor, or snapshotting `file_map` before the raise, would remove it. |
| `U-4` | **`FunctionPrototype` carries neither location nor docstring** (`lineno == -1`, `getDocstring() == ''`); `FunctionDefinition` holds both. | Functions are read through `SymbolFunctionScope.getTarget()`, with the prototype used only for the signature (name, parameters, return type). |

**Phase-0.5 acceptance (`P05-ACC`):** ☑ — Release A/B/C implemented; `P0-TEST-3` asserts the floor.

---

## 3. Phase 1 — MVP: index + `pss` domain + `native` docs

**Theme:** an end-to-end vertical slice on a hand-written sample model. Establishes the parse-once/reference-scope contract (`PssIndex`) from day one (design §6.1). No diagrams, no flow tables yet.

### Implementation
| ID | Task | Done when |
|---|---|---|
| ☑ `P1-IMPL-1` | `model/parse.py`: own the `pssparser` lifecycle — `Parser(collect_docstrings=True)`, parse all sources, `link()` once, return the linked root + `file_map`. **Holds the `Parser` alive for the index's lifetime** and reads scopes only via `user_units()`/the linked root (design §4.4 ownership risk) | a fixture model parses+links; docstrings present |
| ☑ `P1-IMPL-2` | `model/parse.py`: map parser markers → structured diagnostics; `pss_tolerate_link_errors=False` fails the build on link errors, `True` degrades to per-file `GlobalScope` walking | both modes covered |
| ☑ `P1-IMPL-3` | `model/objects.py`: `PssObject` + `SourceRef` + `Provenance` + `TemplateParam` dataclasses (design §8). `FlowSpec`/`ActivityGraph` fields declared, populated `None` until Phase 2/3 | typed, importable |
| ☑ `P1-IMPL-4` | `model/locations.py`: `Location{fileid,lineno,linepos,extent}` → `(path, line, col)` via `file_map`; **`is_synthesized()` = `lineno < 0`** (spike finding — filters `set_executor`, `comp`, etc.) | unit-tested both ways |
| ☑ `P1-IMPL-5` | `model/builder.py`: walk the **linked** symbol tree → `PssObject` for `package`, `component`, `action`, `struct`/`buffer`/`stream`/`state`/`resource` (via `StructKind`), `enum`, `field`, `flow_ref`, `resource_claim`, `constraint`, `function`. Filter synthesized. Capture `raw_doc` + `annotations` + location. Unwrap `SymbolTypeScope` via `getTarget()` before reading the docstring (enhancement-plan §10.3) | sample model → expected tree |
| ☑ `P1-IMPL-6` | `model/builder.py`: **extension provenance** — record `defined_in` (base declaration vs. which `extend` site) for every member. The linked tree merges extensions, so this is the only way a reader can tell where a member came from. **No parser work needed**: a merged member keeps its extend-site `location` and its `getParent()` is the `ExtendType` (enhancement-plan §1.1) | members from a separate `extend` carry the right provenance |
| ☑ `P1-IMPL-7` | `model/builder.py`: signature rendering per kind — action/component/struct declarations, function prototypes with params, field declarations with type + qualifiers (`rand`, `static const`) | signatures match expected strings |
| ☑ `P1-IMPL-8` | `model/index.py`: `PssIndex` built once on `builder-inited`; `qualname → PssObject`; stdlib parsed-but-not-documented unless `pss_document_stdlib` (design §4.4). Relation tables declared, populated in Phase 2 | one parse per build, shared across directives |
| ☑ `P1-IMPL-9` | `docparse/base.py`: `DocstringParser` ABC + `ParsedDoc(summary, rst_body, fields, xrefs)` + registry. **The ABC takes the whole `PssObject`**, not just `raw_doc` — this is the seam the deferred `annotation` parser needs (design §3.4) | ABC + registry usable |
| ☑ `P1-IMPL-10` | `docparse/native.py`: first paragraph → summary, remainder → RST body, field lists parsed. The text arrives already dedented and marker-stripped from the parser — **do not re-normalize** (enhancement-plan §5). A `//@…` line is ordinary comment text and is rendered as written | unit-tested incl. the `//@` case |
| ☑ `P1-IMPL-11` | `docparse/fields.py`: the PSS field vocabulary — `:param:`, `:input:`, `:output:`, `:lock:`, `:share:`, `:field:`, `:constraint:`, `:pool:`, `:exec:`, `:covers:`, `:req:`, `:group:`, `:realizes:` (design §3.1) | each field parses to a structured entry |
| ☑ `P1-IMPL-12` | `docparse/fields.py`: **AST cross-validation** — a field naming something the element does not declare emits a Sphinx warning with file:line; a declared flow ref / field with no entry is reportable under `:undoc-members:` (design §3.1). This is the feature that keeps docs honest, so it ships in Phase 1, not later | both directions warn correctly |
| ☑ `P1-IMPL-13` | `domain.py`: `PssDomain` with object directives `pss:package`, `pss:component`, `pss:action`, `pss:struct`, `pss:buffer`, `pss:stream`, `pss:state`, `pss:resource`, `pss:enum`, `pss:field`, `pss:constraint`, `pss:function` | directives render in a `sphinx` test |
| ☑ `P1-IMPL-14` | `domain.py`: `handle_signature` producing real `desc_parameterlist`/`desc_parameter` nodes, index entries, permalinks, and **`_object_hierarchy_parts` TOC support — stash the fullname during `handle_signature`**, since Sphinx calls it before target ids exist (design §10; the SV project's Phase-5 lesson, adopted up front) | objects appear in the sidebar TOC; args are real param nodes |
| ☑ `P1-IMPL-15` | `domain.py`: xref roles `:pss:pkg:`, `:pss:comp:`, `:pss:action:`, `:pss:struct:`, `:pss:buffer:`, `:pss:stream:`, `:pss:state:`, `:pss:resource:`, `:pss:func:`, `:pss:field:`, `:pss:constraint:`, `:pss:obj:` resolving against `PssIndex`; type references in signatures resolve to links | xrefs resolve; unknown warns with candidates |
| ☑ `P1-IMPL-16` | `autodoc/`: `Documenter` base + `autopsspackage`, `autopsscomponent`, `autopssaction`, `autopssstruct` with `:members:`/`:undoc-members:`/`:exclude-members:`/`:member-order:`; emit domain directives; nested-parse `rst_body` | full doctree from a single directive |
| ☑ `P1-IMPL-17` | Events `pss-autodoc-process-doc` / `pss-autodoc-skip-member` | events fire in a test |

### Tests
| ID | Task | Done when |
|---|---|---|
| ☑ `P1-TEST-1` | `tests/fixtures/pss/dma_pkg.pss` — the canonical sample: component with actions, flow refs (`input`/`output`), a resource + `lock`, buffer/stream/state/struct, enum, named constraints, a function, `rand` and plain fields, native doc comments throughout | committed fixture, parses clean |
| ☑ `P1-TEST-2` | `tests/fixtures/pss/dma_ext.pss` — a second file that `extend`s a type from `dma_pkg`, for provenance testing | committed fixture |
| ☑ `P1-TEST-3` | `tests/model/test_parse.py` — parse+link, marker mapping, `tolerate_link_errors` both modes, **parser kept alive** (assert no crash when walking after `link()`) | green |
| ☑ `P1-TEST-4` | `tests/model/test_builder.py` — tree shape, kinds, names, qualnames, signatures, `StructKind` → kind mapping | green |
| ☑ `P1-TEST-5` | `tests/model/test_synthesized.py` — `set_executor` / `comp` (`lineno == -1`) are filtered; a real member with the same name is not | green |
| ☑ `P1-TEST-6` | `tests/model/test_docstrings.py` — `//`-block, `/** */`, blank-line-gap breaks association, attributed `rand`/`static const` fields, trailing comments, `SymbolTypeScope` unwrapping | green |
| ☑ `P1-TEST-7` | `tests/model/test_provenance.py` — members from `dma_ext.pss` carry the extension provenance; base members carry base | green |
| ☑ `P1-TEST-8` | `tests/model/test_index.py` — qualified-name resolution incl. nested `pkg::comp::action`; **parse-once** (assert the parser runs once across N lookups); stdlib present in index but excluded from the documented set | green |
| ☑ `P1-TEST-9` | `tests/docparse/test_native.py` — summary/body split, edge cases (empty, single line, no blank line), leading `@…` line stripped | green |
| ☑ `P1-TEST-10` | `tests/docparse/test_fields.py` — the full field vocabulary matrix | green |
| ☑ `P1-TEST-11` | `tests/docparse/test_validation.py` — undeclared `:input:` warns; undocumented declared flow ref reported; warning carries file:line | green |
| ☑ `P1-TEST-12` | `tests/roots/test-basic/` + `tests/domain/test_directives.py` (`sphinx`) — manual `pss:*` directives render; index entries, permalinks, **TOC entries** present | green |
| ☑ `P1-TEST-13` | `tests/domain/test_signatures.py` (`sphinx`) — `desc_parameterlist`/`desc_parameter` nodes; type refs are links; unparseable signature degrades to plain text without failing the build | green |
| ☑ `P1-TEST-14` | `tests/autodoc/test_autopss.py` (`sphinx`) — the four `auto*` directives against the fixture; `:members:`/`:exclude-members:`/`:member-order:`; doctree assertions | green |
| ☑ `P1-TEST-15` | `tests/autodoc/test_xref.py` (`sphinx`) — roles resolve; unknown ref warns; ambiguous bare name lists candidates | green |
| ☑ `P1-TEST-16` | `tests/test_upstream_guards.py` (`upstream`) — one test per depended-on parser behavior (docstring collection via `Parser`, attributed-field anchors, dedent/marker normalization, extend provenance, `get_stdlib_files()`). **Fails** on regression; no skips | green |

### Docs
| ID | Task | Done when |
|---|---|---|
| ☑ `P1-DOC-1` | `docs/getting-started.md` — install (incl. the `pssparser` build prerequisite), minimal `conf.py`, first `autopssaction` | builds clean |
| ☑ `P1-DOC-2` | `docs/usage/directives.md` — reference for `pss:*` and `autopss*` (Phase-1 subset) + options | builds clean |
| ☑ `P1-DOC-3` | `docs/usage/native-style.md` — **the recommended PSS doc-comment style**: comment placement, the blank-line rule, the **trailing-comment convention** (enhancement-plan §3.5 — unmarked is primary, Doxygen `<` markers accepted, leading always wins), RST/MyST in bodies, the full field vocabulary with worked examples, and what cross-validation will warn about. **Cite `pssparser`'s `docs/doc_comments.rst` for the lexical rules rather than restating them**; this page owns the *vocabulary and conventions* (design §3.1) | builds clean |
| ☑ `P1-DOC-4` | `docs/examples/sample.md` — **dogfood**: run `autopsspackage` on `tests/fixtures/pss/dma_pkg.pss` in the published docs | rendered output visible in the build |
| ☑ `P1-DOC-5` | `design/implementation-plan.md` (this file) kept current; progress-log entry added | log entry present |

**Phase-1 acceptance (`P1-ACC`):** `docs/examples/sample.md` builds under `-W` and renders the sample package's components, actions, and members from source, with working cross-references and TOC entries; `pytest -m "unit or sphinx"` green in CI.

---

## 4. Phase 2 — The PSS differentiators

**Theme:** everything a general-purpose doc tool cannot do (design §9). This is what makes the extension worth adopting, so it lands before the whole-tree and dialect polish.

### Implementation
| ID | Task | Done when |
|---|---|---|
| ☐ `P2-IMPL-1` | `model/flow.py`: extract `FlowSpec` per action — `input`/`output` flow refs (`FieldRef`), `lock`/`share` claims (`FieldClaim`), with resolved type qualnames | fixture actions produce correct specs |
| ☐ `P2-IMPL-2` | `model/index.py`: **relation tables** — `produces[type]`, `consumes[type]`, `locks[type]`, `shares[type]`, `instantiates[comp]`, `extends[type]`, `derived[type]` (design §6.1). Built once with the index | tables correct on a multi-package fixture |
| ☐ `P2-IMPL-3` | Render flow on action pages: inputs/outputs/claims as a linked field list, driven by `FlowSpec` and reconciled with any `:input:`/`:output:` doc fields | action page shows its flow signature |
| ☐ `P2-IMPL-4` | Render **producer/consumer tables** on flow-object type pages; `:producers-consumers:` option and `autopssbuffer`/`autopssstream`/`autopssstate`/`autopssresource` directives (design §9.1) | buffer page lists producing/consuming actions with links |
| ☐ `P2-IMPL-5` | `autodoc/diagrams.py`: shared diagram backend — Graphviz via `sphinx.ext.graphviz`, `pss_diagrams` config (`graphviz`/`mermaid`/`off`), **graceful degradation** to a warning + skipped node when `dot` is absent | backend selectable; no `dot` does not fail the build |
| ☐ `P2-IMPL-6` | **Flow dataflow diagram** — bipartite actions/flow-objects graph, scoped to a package, component, or the neighborhood of one action; `:flow-diagram:` option + `pss:flow-diagram::` directive (design §9.2) | diagram node emitted with correct edges |
| ☐ `P2-IMPL-7` | **Component instance tree** — component-typed fields form the static hierarchy; annotate pools and `bind` statements on nodes; `:component-diagram:` (design §9.4) | tree diagram for the fixture top |
| ☐ `P2-IMPL-8` | **Extension provenance rendering** — "Added by `extend action Xfer` (`dma_ext.pss:14`)" labels on members; "Extended by" list on type pages; `:show-extensions:` (design §9.5) | labels and list render |
| ☐ `P2-IMPL-9` | Inheritance: `:show-inheritance:`, `:inherited-members:` climbing `super_t` via the index, inheritance diagrams | inherited members appear, attributed to their base |
| ☐ `P2-IMPL-10` | `domain.py`: add `pss:monitor`, `pss:covergroup`, `pss:pool`, `pss:exec`, `pss:typedef`, `pss:annotation` object directives (rendering only; coverage semantics in Phase 4) | directives render |

### Tests
| ID | Task | Done when |
|---|---|---|
| ☐ `P2-TEST-1` | `tests/fixtures/pss/flow_model/` — multi-file, multi-package model with several producers/consumers per buffer type, a shared resource, nested components, cross-file `extend`, and a 3-level inheritance chain | committed, parses+links clean |
| ☐ `P2-TEST-2` | `tests/model/test_flow.py` — `FlowSpec` extraction incl. arrays and inherited flow refs | green |
| ☐ `P2-TEST-3` | `tests/model/test_relations.py` — every relation table against hand-computed expected values on the fixture | green |
| ☐ `P2-TEST-4` | `tests/autodoc/test_flow_render.py` (`sphinx`) — producer/consumer tables, links resolve, ordering deterministic | green |
| ☐ `P2-TEST-5` | `tests/autodoc/test_diagrams.py` (`sphinx`) — flow, component, inheritance diagrams emit correct nodes; **skips cleanly without `dot`**; `pss_diagrams="off"` suppresses | green with and without Graphviz |
| ☐ `P2-TEST-6` | `tests/autodoc/test_extensions.py` (`sphinx`) — provenance labels, "Extended by" list, `:show-extensions:` off by default | green |
| ☐ `P2-TEST-7` | `tests/autodoc/test_inherited.py` (`sphinx`) — `:inherited-members:` over the 3-level chain, correct base attribution | green |
| ☐ `P2-TEST-8` | Determinism guard — build the same fixture twice, assert byte-identical doctrees (relation tables and diagram edges must not depend on dict/set ordering) | green |

### Docs
| ID | Task | Done when |
|---|---|---|
| ☐ `P2-DOC-1` | `docs/usage/flow.md` — documenting flow objects and resources; how producer/consumer tables are derived; what the `:input:`/`:output:`/`:lock:`/`:share:` fields add over the AST | builds clean |
| ☐ `P2-DOC-2` | `docs/usage/diagrams.md` — flow, component, inheritance diagrams; Graphviz prerequisite; degradation behavior; `pss_diagrams` | builds clean |
| ☐ `P2-DOC-3` | `docs/usage/extensions.md` — how `extend` is documented and why provenance matters | builds clean |
| ☐ `P2-DOC-4` | Extend `docs/examples/sample.md` (or add `docs/examples/flow.md`) with live flow tables and diagrams | rendered in the build |

**Phase-2 acceptance (`P2-ACC`):** the `flow_model` fixture documents end-to-end with correct producer/consumer tables, a flow diagram, a component tree, and correct extension provenance across files; docs build under `-W` with Graphviz present **and** absent.

---

## 5. Phase 3 — Activities, whole tree, and the core-library reference

**Theme:** activity graphs, the Exhale-analog whole-tree front-end, and the annotated PSS standard library — which becomes the project's example doc set and primary corpus (design §9.8, §14 Q4).

### Implementation
| ID | Task | Done when |
|---|---|---|
| ☐ `P3-IMPL-1` | `model/activity.py`: normalize `ActivityDecl` and its statements — `ActivitySequence`, `ActivityParallel`, `ActivitySchedule`, `ActivitySelect`, `ActivityRepeatCount`, `ActivityRepeatWhile`, `ActivityForeach`, `ActivityActionHandleTraversal`, `ActivityActionTypeTraversal`, `ActivityBindStmt`, `ActivityConstraint` → an `ActivityGraph` | fixture activities produce expected graphs |
| ☐ `P3-IMPL-2` | **Activity diagrams** — render `ActivityGraph`, with traversed actions linked to their pages; `:activity-diagram:` + `pss:activity-diagram::` (design §9.3) | diagram for a compound action |
| ☐ `P3-IMPL-3` | `autopsssummary` whole-tree directive — walk an index subtree, emit a structured API tree; scope narrowing by `:packages:`, `:components:`, `:kinds:`, name glob | tree page generated |
| ☐ `P3-IMPL-4` | `viewcode.py`: `[source]` links + generated highlighted per-file PSS listings; `pss_viewcode`. Note `Location.extent`/end-locations exist only on `Scope` nodes, so non-scope members link to a line, not a range (design §4.3) | links resolve to the right line |
| ☐ `P3-IMPL-5` | Objects inventory (`objects.inv`) export for intersphinx + search | intersphinx round-trip works |
| ☐ `P3-IMPL-6` | Member ordering and `:group:` rubrics (`:member-order: source|alpha|groups`) | grouped rendering |
| ☐ `P3-IMPL-7` | **Annotation metadata rendering** — `PssObject.annotations` rendered as a field list on the element (user-defined annotation types included). Explicitly *not* a doc source; `@doc` as documentation stays deferred (design §3.2, §14 Q2) | annotations visible; `@doc` does not become the summary |
| ☐ `P3-IMPL-8` | `scripts/extract_stdlib.py` — scripted extraction of the standard packages from the LRM markdown, repeatable across LRM revisions (design §9.8 step 1) | re-running reproduces the sources |
| ☐ `P3-IMPL-9` | `stdlib/` — the extracted `std_pkg`, `addr_reg_pkg`, `executor_pkg`, `sync_pkg`, **reconciled against `pssparser/src/stdlib/*.pss`**; divergences filed upstream as parser bugs (design §9.8 step 1) | reconciliation report produced; divergences filed |
| ☐ `P3-IMPL-10` | Annotate the extracted stdlib with LRM-derived doc comments, each carrying a clause citation (e.g. `PSS 3.1 §22.3.1`) (design §9.8 step 2). **Also the forcing function for the §3.1 field vocabulary against non-toy PSS** — expect vocabulary gaps to surface here and budget for them | every public type/field/function documented |
| ☐ `P3-IMPL-11` | `pss_document_stdlib=True` path — stdlib documented rather than merely indexed | stdlib pages render |

### Tests
| ID | Task | Done when |
|---|---|---|
| ☐ `P3-TEST-1` | `tests/fixtures/pss/activity_model.pss` — sequence, parallel, schedule, select, repeat, foreach, nested compound actions | committed fixture |
| ☐ `P3-TEST-2` | `tests/model/test_activity.py` — graph normalization per statement kind; nesting preserved | green |
| ☐ `P3-TEST-3` | `tests/autodoc/test_activity_diagram.py` (`sphinx`) — diagram nodes, action links | green |
| ☐ `P3-TEST-4` | `tests/autodoc/test_summary.py` (`sphinx`) — whole-tree output and each scope-narrowing option | green |
| ☐ `P3-TEST-5` | `tests/domain/test_viewcode.py` (`sphinx`) — source links present and line-correct | green |
| ☐ `P3-TEST-6` | `tests/domain/test_intersphinx.py` — `objects.inv` produced; external ref resolves | green |
| ☐ `P3-TEST-7` | `tests/model/test_annotations.py` — annotations captured and rendered as metadata; `@doc` explicitly does **not** become the summary (guards the deferral) | green |
| ☐ `P3-TEST-8` | `tests/stdlib/test_reconcile.py` — diffs the LRM-extracted sources against `pssparser/src/stdlib/*.pss`; **fails on divergence** so drift surfaces instead of accumulating (design §12) | green, or fails with a readable diff |
| ☐ `P3-TEST-9` | `tests/corpus/test_stdlib.py` (`corpus`) — the annotated stdlib builds end-to-end; element-count floors; bounded diagnostics | green nightly |
| ☐ `P3-TEST-10` | `tests/corpus/test_pssparser_corpus.py` (`corpus`) — model runs over `pssparser/tests/python/` corpus sources; no crashes | green nightly |

### Docs
| ID | Task | Done when |
|---|---|---|
| ☐ `P3-DOC-1` | `docs/usage/activities.md` — activity documentation and diagrams | builds clean |
| ☐ `P3-DOC-2` | `docs/usage/whole-tree.md` — `autopsssummary`, scope narrowing, recommended page structure | builds clean |
| ☐ `P3-DOC-3` | `docs/usage/cross-referencing.md` — roles, intersphinx, viewcode | builds clean |
| ☐ `P3-DOC-4` | `docs/examples/stdlib.md` — **the flagship**: a live, linked PSS core-library reference built by the extension (design §9.8 step 3) | stdlib reference builds under `-W` |
| ☐ `P3-DOC-5` | `docs/stdlib-maintenance.md` — how to re-extract and re-reconcile when the LRM revs; where the annotated copy lives and why it is separate from the parser's vendored sources | builds clean |

**Phase-3 acceptance (`P3-ACC`):** the annotated PSS standard library documents end-to-end and is published as `docs/examples/stdlib.md` under `-W`; the reconciliation test is green; `-m corpus` green in nightly CI.

---

## 6. Phase 4 — Traceability, coverage, polish

| ID | Task | Done when |
|---|---|---|
| ☐ `P4-IMPL-1` | **Requirements index** — reverse table from `:req:` ID to every action/coverpoint/constraint referencing it, as a generated page + `pss:requirements::` directive (design §9.6). *Blocked on the §14.2 open question about ID conventions* | index page generated, IDs link both ways |
| ☐ `P4-IMPL-2` | Covergroups/coverpoints/crosses rendered as verification intent; `pss:covergroup` members | rendered |
| ☐ `P4-IMPL-3` | Constraint source rendering — highlighted constraint body beside its doc comment (design §9.7) | rendered |
| ☐ `P4-IMPL-4` | `docparse/doxygen.py` + `auto` dialect detection | unit-tested |
| ☐ `P4-IMPL-5` | Template/generic types — `TypeScope.params`; document the generic declaration, specializations best-effort | parameterized fixture documents |
| ☐ `P4-IMPL-6` | Exec-block documentation (`body`, `run_start`, `init_down`, …) and imported/exported functions — the target-integration surface | rendered |
| ☐ `P4-IMPL-7` | Performance: in-process index cache keyed by input set + source mtimes | warm rebuild materially faster; measured in the log |
| ◐ `P4-IMPL-8` | `pss_tolerate_link_errors` degraded mode hardened — declarations + docstrings only, every marker surfaced as a warning. **The mode itself landed in Phase 1** (`P1-IMPL-2` requires per-file walking, and a failed `link()` leaves nothing walkable — see `U-5`), including the pre-link dispatch table and the "documentation is degraded" build warning. What remains here is hardening: degraded-mode `sphinx` tests, suppressing the cross-reference machinery that cannot work without a linked tree, and a per-file corpus check | degraded build succeeds and is visibly degraded |
| ☐ `P4-TEST-1` | Tests mirroring each `P4-IMPL-*` | green |
| ☐ `P4-DOC-1` | `docs/usage/traceability.md`, `docs/usage/coverage.md`, `docs/usage/doxygen-style.md`, `docs/usage/advanced.md` (templates, exec blocks, perf, degraded mode) | build clean |

**Phase-4 acceptance (`P4-ACC`):** requirements index renders from the stdlib + fixture models; all three dialect paths covered by green tests; warm-rebuild timing recorded in the progress log.

---

## 7. Deferred (no phase) — `@doc` annotations as a documentation source

Design §3.2 / §14 Q2. **No longer blocked** — `pssparser` `E9`/`E8` settled the syntax question (LRM `@doc {.text=…}` canonical, `@doc(text=…)` retained as an extension, `//@` removed). It remains *unscheduled* per the Q2 decision; the reason is now deprioritization rather than a blocker.

When it is picked up, the work is additive because the seams exist from Phase 1:

| ID | Task |
|---|---|
| ☑ `D-1` | Upstream: settle and implement G4 (and G3, the dead `//@` form) — **done**, `pssparser` `E9`/`E8` |
| ☐ `D-2` | `docparse/annotation.py` — `@doc`/`code_doc` as a `DocstringParser` reading `PssObject.annotations` |
| ☐ `D-3` | `pss_doc_source` config (`comment`/`annotation`/`both`) + `:doc-source:` directive option |
| ☐ `D-4` | `code_doc` rendered as a distinct "Generated-code note" block, never the summary |
| ☐ `D-5` | Tests + `docs/usage/annotation-style.md` |

---

## 8. Strategy detail

### 8.1 Testing

- **Pyramid:** heavy `unit` (model, docparse, flow/activity), focused `sphinx` integration via `tests/roots/`, thin slow `corpus`.
- **Fixtures:** small hand-authored `.pss` under `tests/fixtures/pss/`, each targeting one behavior; Sphinx mini-projects under `tests/roots/<name>/`.
- **Sphinx assertions:** prefer doctree/node assertions (`app.env.get_doctree`) over HTML string matching; a few BeautifulSoup HTML smoke checks for permalinks, TOC, and index.
- **Golden files** for verbose structures (`PssObject` trees, `ParsedDoc`, relation tables) under `tests/golden/`, regenerated via a documented `--update-golden` switch.
- **Corpus floors,** not exact counts, so upstream churn does not break CI; bound the allowed diagnostic count.
- **Determinism** is a first-class test concern here (`P2-TEST-8`): relation tables and diagram edges are derived from dict/set traversal and will produce unstable output if ordering is not pinned.
- **Coverage gate:** ≥90% on `model/` and `docparse/` (the parser-agnostic core); `domain.py`/`autodoc/` covered by `sphinx` tests.
- **Upstream-dependency tests** carry the `upstream` marker and skip with an explicit reason rather than failing, so the suite stays green while `U-G1`/`U-G2` are in flight.

### 8.2 Docs

- `docs/` is a real Sphinx site that **dogfoods the extension** — the sample model from Phase 1, the PSS standard library from Phase 3. Best regression signal available.
- Structure: `getting-started`, `usage/` (native style, directives, flow, diagrams, extensions, activities, whole-tree, cross-referencing, traceability, coverage, advanced), `examples/` (sample, stdlib), `design/` (design + this plan), `changelog`.
- Built with `-W` in CI so doc rot fails the build.
- MyST-Markdown for narrative; the extension's own directives for API content.
- **`docs/usage/native-style.md` is the project's most important page** — it defines a convention the PSS community does not yet have. Budget real writing time for it, and revisit it after `P3-IMPL-10` exercises the vocabulary against the standard library.

### 8.3 Risk register

| Risk | Phase | Mitigation |
|---|---|---|
| `pssparser` 3.1.0 is unreleased (tagging pending) | 0.5 → 1 | Development runs against the editable `packages/pssparser` clone; CI builds it from source via `ivpm`. The floor is asserted, not worked around |
| `symtabAt()` segfaults on a missing name (enhancement-plan §10.3) | 1 | `model/` avoids the API entirely; resolution goes through `SymbolScopeUtil.getQname` and child iteration |
| Models that do not link cleanly cannot be documented | 1+ | `pss_tolerate_link_errors` degraded mode (`P4-IMPL-8`), markers surfaced as warnings |
| `Parser` ownership fault (use-after-free after `link()`) | 1 | `model/parse.py` owns the lifecycle; `P1-TEST-3` asserts post-link traversal is safe |
| Stdlib annotation is larger than it looks | 3 | Scripted extraction; reconciliation test; scope is the four standard packages only |
| Stdlib doc set drifts from the LRM | 3+ | `P3-TEST-8` fails on divergence; `docs/stdlib-maintenance.md` documents the re-extraction procedure |
| Field vocabulary proves inadequate on real PSS | 3 | `P3-IMPL-10` is the deliberate stress test; budget vocabulary revisions and a `native-style.md` revision after it |
| Graphviz absent in user/CI environments | 2+ | Degrade to warning + skipped node; tested both ways (`P2-TEST-5`) |
| Diagram/table output non-deterministic | 2 | Explicit determinism test (`P2-TEST-8`) |

---

## 9. Status tracker

| Phase | Impl | Tests | Docs | Acceptance | State |
|---|---|---|---|---|---|
| P0 Scaffolding | ☑ | ☑ | ☑ | — | **done** (30 tests green; `docs/` builds under `-W`) |
| P0.5 Upstream parser fixes | ☑ | ☑ | ☑ | `P05-ACC` ☑ | **done** (`pssparser` 3.1.0; tagging pending) |
| P1 MVP (index + domain + native) | ☑ | ☑ | ☑ | `P1-ACC` ☑ | **done** (311 tests green; `docs/` builds under `-W`) |
| P2 PSS differentiators | ☐ | ☐ | ☐ | `P2-ACC` ☐ | not started |
| P3 Activities + whole tree + stdlib | ☐ | ☐ | ☐ | `P3-ACC` ☐ | not started |
| P4 Traceability + coverage + polish | ☐ | ☐ | ☐ | `P4-ACC` ☐ | not started |
| Deferred: `@doc` annotations | ☐ | ☐ | ☐ | — | unscheduled (deprioritized; G4 resolved) |

> Update this table and the per-item boxes as work lands; append PR/commit refs next to checked items.

---

## 10. Open items / decisions still needed

Carried from design §14.2, plus plan-level questions:

- **Requirements-ID convention** (blocks `P4-IMPL-1`) — free-form strings, or a house convention / external requirements tool to integrate with?
- ~~**G4 direction**~~ — **resolved.** `pssparser` `E9` implements the LRM brace form as canonical and retains the paren form as a documented extension. The `@doc`-as-doc-source work (§7) is therefore **deprioritized, not blocked**.
- **Minimum Sphinx version** — target 9.x; confirm the floor.
- **MyST vs reST** for `docs/` narrative — assume MyST unless objected.
- **Where the annotated stdlib lives** — `stdlib/` at repo root, or under `docs/examples/`? It is simultaneously source, test corpus, and published example. *(Lean: `stdlib/` at root, referenced by both.)*
- ~~**CI cost of building `pssparser`**~~ — **resolved.** CI runs in the `dvkit/pssparser-ci` container and builds the parser from source via `ivpm update -a`. No artifact plumbing between repos, and no cache: a cache keyed on a moving upstream branch goes stale silently, which is the failure this project can least afford. If build time becomes the bottleneck, the next step is consuming `pssparser`'s published wheel, not adding a cache.
- **`Config.__getattr__` on a `pss_*` typo** — Sphinx does not error on an unknown `conf.py` name, so `pss_source_dir` (singular) is silently ignored. Worth a `config-inited` check that warns on near-miss names; not scheduled.
