# sphinx-pss — Design & Approach

**Status:** Draft for review
**Date:** 2026-08-13
**Companion project:** `fvutils/sphinx-systemverilog` (the SystemVerilog/`pyslang` analog)
**Front-end:** `psstools/pssparser` (ANTLR4 → C++ AST + linker, with Cython Python bindings)
**Goal:** A Sphinx extension that autodocuments Accellera PSS source the way `sphinx.ext.autodoc` documents Python — pulling declarations and doc comments directly from PSS source via `pssparser`, and rendering PSS-specific structure (flow, activity, component hierarchy) that no general-purpose doc tool can produce.

---

## 1. Executive summary / recommendation

Build a **custom Sphinx domain (`pss`) plus a bespoke autodoc layer**, backed by a **parse-once, project-wide index** built from `pssparser`'s *linked* symbol tree. This is the same architecture that `sphinx-systemverilog` validated against `pyslang`, and it transfers cleanly.

Three things make the PSS case *better* than the SystemVerilog case, and they should shape the product:

1. **The parser already extracts doc comments.** `pssparser`'s `AstBuilder` has a `setCollectDocStrings(bool)` mode and every `ScopeChild` carries a `docstring` field (`ast/coretypes.yaml`). We do not need a trivia-scraping layer at all — unlike `pyslang`, where comment recovery was the hard part of the spike. §4 reports what works and the four concrete gaps to close.
2. **PSS has a *standard*, machine-readable doc mechanism.** PSS 3.1 §21.6.2 defines `std_pkg::doc { string text; }` — an annotation, not a comment — for model-level documentation, alongside `code_doc` for implementation-level text. This is a first-class doc source that survives macro/template expansion and code generation. **Resolved: annotation support is deferred** (§14 Q2) — the parser's annotation-application syntax does not yet match the LRM, and settling that is `pssparser` grammar work we do not want on the critical path. The design keeps a clean seam for it (§3.2) so it can land later without rework.
3. **PSS carries semantics worth rendering that SV does not have.** Actions declare `input`/`output` flow objects, `lock`/`share` resource claims, `activity` graphs, pools and binds, and cross-file `extend`. From a whole-project index we can compute and render **producer/consumer tables** and **dataflow graphs** per flow-object type, **activity graphs** per action, and **component instance trees**. This is the headline feature — see §9.

**Why not extend `sphinx.ext.autodoc`?** Same reasoning as the SV project: `autodoc` is wired to Python's runtime object model (it `import`s the module and introspects live objects). PSS has no runtime to import. We reuse autodoc's *ideas* — a documenter registry, `:members:`/`:undoc-members:` options, docstring→RST processing, event hooks — against `pssparser`.

**Why not Doxygen/Breathe?** Doxygen has no PSS front-end and its object model has no concept of a flow object or an activity. The XML round-trip would also discard exactly the structure we most want to render.

---

## 2. Landscape

| Tool | Approach | Lesson |
|---|---|---|
| `sphinx.ext.autodoc` (Python) | Runtime introspection, `Documenter` registry emits `py` directives | Reuse the architecture, not the code |
| `sphinx-systemverilog` (sibling) | `pyslang` → normalized model → custom `sv` domain + auto* directives | **Direct template.** Proven through 5 phases on real UVM; reuse its module layout, docparse contract, and index/scope model |
| Built-in `c`/`cpp` domains | Hand parser + domain, no autodoc | A domain alone is viable but tedious |
| Breathe / Exhale | Doxygen XML → domain; Exhale generates the whole tree | Validates "external front-end → domain"; Exhale is the model for `autopsssummary` |
| PSS vendor tools | Proprietary HTML/model browsers, per-tool | No portable, source-of-truth doc path exists for PSS today — that is the gap |

**Conclusion:** the proven pattern is *language front-end → normalized model → custom Sphinx domain*. `pssparser` is the front-end. The novelty for PSS is (a) an in-process parse with docstrings already attached, and (b) rendering PSS's flow/activity semantics rather than just declarations.

---

## 3. Documentation style for PSS

PSS has **no entrenched doc-comment convention** — there is no UVM-style NaturalDocs legacy to accommodate. That is an opportunity to be opinionated. We define three doc sources unified into one `ParsedDoc`, of which **two ship** (`native`, `doxygen`) and one (`annotation`) is **designed now and deferred** per §14 Q2.

### 3.1 `native` — doc comments (default, recommended)

The immediately-preceding `//` block or `/** … */` block is the documentation. Exactly what `pssparser` already collects. The body is **reStructuredText/MyST**, so authors get the full Sphinx toolbox with no invented markup:

```pss
// Program a single DMA transfer.
//
// Claims the DMA engine for the duration of the transfer and produces a
// filled buffer for a downstream consumer.
//
// :output out_b: the filled destination buffer
// :input  in_b:  the source buffer to read from
// :lock   eng:   exclusive claim on the DMA engine
// :param  len:   transfer length in bytes; must be word-aligned
// :req:   DMA-014, DMA-015
action Xfer {
    input  DmaBuf in_b;
    output DmaBuf out_b;
    lock   DmaEngine eng;
    rand int len;

    // Transfers are word-aligned and never empty.
    constraint c_len { len > 0 && len % 4 == 0; }
}
```

First paragraph is the summary; the rest is the body; field lists are structured metadata.

**PSS-specific field-list vocabulary.** This is the substantive design work — the doc style has to name things PSS has and Python/SV do not. Proposed canonical roles:

| Field | Applies to | Meaning |
|---|---|---|
| `:param X:` | action, component, struct, function | template parameter or function argument |
| `:input X:` / `:output X:` | action | flow-object reference; renders with a link to the object type |
| `:lock X:` / `:share X:` | action | resource claim |
| `:field X:` | any type scope | attribute field (when not documented at its own declaration) |
| `:constraint C:` | any type scope | intent of a named constraint (when the constraint has no own comment) |
| `:pool P:` | component | pool declaration / bind intent |
| `:exec K:` | action, component | what a `body`/`run_start`/`init_down`/… exec block does |
| `:covers C:` | action, covergroup | coverage intent |
| `:req:` / `:requirement:` | anything | traceability IDs — PSS is a verification-*intent* language, and requirement traceability is the single most-requested artifact in that space |
| `:group:` | member | logical grouping, rendered as a rubric |
| `:realizes:` | action | the target-side operation this action stands for |

Every one of `:input:`/`:output:`/`:lock:`/`:share:`/`:field:`/`:constraint:` is **cross-checked against the AST**: a field list naming something the action does not declare is a Sphinx warning, and a declared flow ref with no field-list entry is reported under `:undoc-members:`. This makes the docs verifiably in sync with the model — a property prose comments alone cannot give you.

### 3.2 `annotation` — the LRM `@doc` annotation — **DEFERRED**

> **Status: deferred (resolved 2026-08-13, §14 Q2) — *deprioritized*, no longer blocked.** Not implemented in Phases 1–4. It is specified here because the seam it needs — a `DocstringParser` that reads `PssObject.annotations` rather than `raw_doc` — costs nothing to preserve now and is expensive to retrofit. The original blocker was G4 (§4.3), the divergence between the parser's application syntax and the LRM's. **That is settled**: `pssparser` `E9` (see `pssparser-enhancement-plan.md` Release C) implements the LRM's `@doc {.text = …}` brace form as canonical and retains `@doc(text = …)` as a documented extension, and `E8` removes the dead `//@` token. The work is therefore additive whenever it is picked up; it stays unscheduled by priority, not by dependency.

PSS 3.1 §21.6.2 (Syntax 125):

```pss
package std_pkg {
    annotation doc { string text; }
}
```

Applied — note the syntax caveat in §4.4 — as:

```pss
@doc(text = "Program a single DMA transfer.")
action Xfer { ... }
```

`pssparser` already parses annotation applications and attaches them to the annotated element (`ScopeChild.annotations`, verified in §4.2). This source matters because:

- it is **standardized**, so it is portable across PSS tools in a way comments are not;
- it **survives generation** — a model emitted by a generator can carry documentation without a comment-emission pass;
- it is **structured** — user-defined annotation types (`annotation requirement { string id; }`) give typed metadata, and we can render arbitrary annotation types as field lists automatically.

`code_doc` (§21.6.1) is *implementation*-level, intended to land as a comment in generated target code. We surface it as a distinct, collapsible "Generated-code note" block, never as the element's summary.

**Precedence (when this lands).** `pss_doc_source` config: `"comment"` (default), `"annotation"`, or `"both"`. Under `"both"`, an `@doc` annotation supplies the summary/body when present and the comment supplements it; a `:no-index:`-style directive body always wins over both. Rationale: the annotation is the explicit, deliberate act.

**What Phases 1–4 must still do.** The model captures `PssObject.annotations` from the parser regardless (§8) — it is free, since `pssparser` already attaches them — and annotations are *rendered* as a metadata field list on the element. What is deferred is treating `@doc` as a **documentation source** (summary/body). So an annotated model loses nothing today; it simply shows its annotations rather than having them become the prose.

### 3.3 `doxygen` — migration path

`@brief`/`@param`/`@return`/`@note`/`@see`, `\`-variants, `///` and `//!` line forms. Purely for teams arriving from a C/C++ or Doxygen-documented SV codebase. Lowest priority; the `sphinx-systemverilog` implementation is directly portable.

### 3.4 Strategy

A `DocstringParser` ABC with `native` and `doxygen` implementations (plus `annotation`, deferred), selected by `pss_doc_style` and overridable per-directive and per-comment (`auto` sniffing: `/**` + `@brief` → doxygen, else native). Each parser's contract is identical to the SV project's: **raw text → `(summary, rst_body, fields, xrefs)`**. Cross-reference normalization is unified downstream, so `:pss:action:`Xfer`` and a Doxygen `@see Xfer` produce the same node.

The ABC takes the whole `PssObject`, not just `raw_doc`, precisely so the deferred `annotation` parser can read `annotations` through the same interface later. That is the entire cost of keeping the seam open.

---

## 4. Technical validation of `pssparser` (spike run 2026-08-13)

Environment: `packages/pssparser` built in `packages/python` (`pssparser.core` / `pssparser.ast` Cython extensions, Python 3.12).

### 4.1 What works today

- **Docstrings are collected by the parser.** `AstBuilder.setCollectDocStrings(True)` (exposed in `python/core.pyx:147`) makes `AstBuilderInt::addDocstring` (`src/AstBuilderInt.cpp:3845`) pull `SL_COMMENT` (channel 11) / `ML_COMMENT` (channel 12) hidden tokens to the left of a declaration and store them on the node. Verified on packages, components, actions, structs/buffers, enums, function prototypes, constraint blocks, and component fields:

  ```
  PackageScope                  doc=''
    Struct       MemBuf         doc=' A packet buffer object. '
    EnumDecl     Kind           doc=' An address-space enum\n'
    Component    Mem            doc=' Reusable memory-write behavior.\n\n :param addr: target address\n'
      Action     Write          doc=' Writes a word to memory.\n'
        ConstraintBlock         doc=' Address must be word-aligned\n'
      FunctionPrototype helper  doc=' A helper function\n'
  ```

  Both the `//`-block and `/** … */` forms work, and multi-line blocks including blank lines are captured intact.
- **Association is adjacency-based with a whitespace guard.** A blank-line gap between comment and declaration breaks the association (`tests/python/source_references/test_docstrings.py::test_comment_not_attached_when_spacing_breaks_association`). Correct default behavior; matches Python/`native` expectations.
- **Annotations are parsed and attached.** `@doc(text = "…")` on a field yields `Annotation` with `getType() → TypeIdentifier` and `getParameters() → [AnnotationParam(name='text', value=ExprString)]`. Verified.
- **The linker merges `extend` into the base type.** `Parser.link()` returns a `RootSymbolScope`; `SymbolScopeUtil.getQname("p::Dma::Xfer")` resolves to a `SymbolTypeScope` whose children include members contributed by a separate `extend action p::Dma::Xfer { rand int prio; }` — `prio` appears alongside the original members. **This makes the linked tree the correct documentation view**, and it is what the index will be built from.
- **Source locations resolve.** Every `ScopeChild` carries `Location { fileid, lineno, linepos, extent }`; `Parser.file_map` maps `fileid → path` after `link()`, and `Parser.user_units()` returns per-file `GlobalScope`s excluding the standard library.
- **Diagnostics are structured.** `Parser.markers` yields `{severity, message, file, line, col}` dicts — mapped directly onto Sphinx warnings.
- **A Python visitor exists.** `pssparser.ast.VisitorBase` provides `visitX` for every node type, so traversal need not be hand-rolled per kind.
- **Synthesized members are identifiable.** Compiler-injected members (`FunctionPrototype set_executor`, `FieldCompRef comp`) carry `lineno == -1`. **Filter rule:** drop any node whose location `lineno < 0`. Directly analogous to the bogus-`SourceLocation` filter the SV project needed.

### 4.2 Worked example (abridged from the spike)

```python
from pssparser import Parser
from pssparser.utils import SymbolScopeUtil

pr = Parser()                      # see gap G1 — needs collect_docstrings
pr.parse(["dma.pss"])
root = pr.link()

xfer = SymbolScopeUtil(root).getQname("dma_pkg::Dma::Xfer")
for i in range(len(xfer.getChildren())):
    c   = xfer.getChild(i)
    loc = c.getLocation()
    if loc.lineno < 0:             # synthesized — skip
        continue
    doc = c.getDocstring()
    src = pr.file_map[loc.fileid]
    # -> (type(c).__name__, name, f"{src}:{loc.lineno}", doc) ==> DocstringParser
```

### 4.3 Gaps to close in `pssparser` (blocking, all small)

Each is a contained change in the parser repo, and all should be tracked as upstream work items rather than worked around in the extension. **G1 and G2 block Phase 1. G3 and G4 are deferred alongside annotation support (§14 Q2)** — they only matter once `@doc` becomes a documentation source.

| ID | Gap | Evidence | Fix |
|---|---|---|---|
| **G1** | `Parser` never enables docstring collection — there is no way to get docstrings through the public Python API. `Parser._mkBuilder` (`python/pssparser/parser.py`) does not call `setCollectDocStrings`, and the C++ default is `false` (`AstBuilderInt.cpp:55`). | Spike via `Parser` returned empty docstrings; the same source via `core.Factory` + `setCollectDocStrings(True)` returned them. | Add `Parser(collect_docstrings: bool = False)` and pass it through in `_mkBuilder`. |
| **G2** | **Fields with attribute qualifiers lose their docstring.** `rand int x;` inside an action/struct gets `doc=''`, while `int f1;` in a component works. Cause: `visitData_declaration` (`AstBuilderInt.cpp:2445`) passes `ctx->data_type()->start` as the doc-comment anchor token; when the declaration is wrapped by `attr_field`, the `rand` / `static const` token sits between the comment and `data_type`, so `getHiddenTokensToLeft` sees only whitespace. | Verified: `// slc field doc` → `Field f1 doc=' slc field doc\n'`; `// slc rand field` → `Field x doc=''`. | Anchor on the enclosing `attr_field` start token when present. This is the highest-impact fix — action and struct attribute fields are the most commonly documented elements in real PSS. |
| **G3** *(deferred)* | `//@`-form annotations are dead. The lexer defines `TOK_COMMENT_AT: '//@'` (`PSSLexer.g4:184`) but `SL_COMMENT` (line 189) matches longer and wins, so `//@doc(text="…")` lands in the *docstring* as literal text rather than parsing as an annotation. | Verified: field `f4` received `doc='@doc(text = "comment-form annotation")\n'`. | Either fix the lexer ordering/predicate, or remove `TOK_COMMENT_AT` and the `annotation` rule's reference to it. **One consequence bites Phase 1:** a `//@…` line silently becomes docstring text, so the `native` parser should strip a leading `@…` line from a comment block rather than render it as prose. |
| **G4** *(deferred)* | **Annotation-application syntax diverges from the LRM.** PSS 3.1 Syntax 20/125 specifies braces with dot-prefixed names — `@doc {.text = "…"}` — while the grammar implements parentheses with bare names — `@doc(text = "…")` (`PSSParser.g4:2023-2047`). | `@doc {.text=…}` is a syntax error; `@doc(text=…)` parses. | Reconcile with the LRM (accepting both during a transition is reasonable). This is the reason §3.2 is deferred: sphinx-pss must not publish a doc convention built on the non-conforming form. Until it is settled, annotations are *rendered as metadata* but are not a doc source. |

Non-blocking, worth noting: there is no trailing/inline comment support (`rand int len; // bytes`) — the SV project needed a same-line reassignment heuristic and PSS will want the same eventually; and `Location.extent` is populated but end-locations exist only on `Scope` nodes, which bounds how precisely `viewcode` can slice source for non-scope members.

### 4.4 Risks

- **Elaboration requires a complete, linkable model.** Unlike the SV project, there is no meaningful "syntax-only" fallback that still gives cross-references: `extend` merging, inheritance, and flow-object typing all come from the linker. A project whose sources do not link cleanly cannot be fully documented. **Mitigation:** a `pss_tolerate_link_errors` mode that falls back to per-file `GlobalScope` walking (declarations + docstrings, no cross-refs, no diagrams), plus surfacing every marker as a Sphinx warning so the failure is visible rather than silent.
- **The standard library is always parsed.** `Parser` loads `std_pkg`/`addr_reg_pkg`/`executor_pkg`/`sync_pkg` as `fileid 0`. It must be excluded from the documented set by default (`pss_document_stdlib = False`) but retained in the index so references into it resolve. Documenting it is a **confirmed goal** — see §9.8 and Phase 3.
- **Parser ownership semantics.** `Parser.link()` transfers ownership of the `GlobalScope`s to the linked root and clears `_files`; holding Python wrappers past that point is a double-ownership fault (documented in `parser.py`). The index must read through `Parser.user_units()` / the linked root only, and must hold the `Parser` alive for the life of the index.
- **Template/generic types.** `action A<T>` (`TypeScope.params`) — the SV project found parameterized classes needed a separate best-effort path. Expect the same: document the generic declaration, and specializations best-effort.

---

## 5. Comment-to-element association

1. **Adjacency (default)** — handled by the parser; the extension consumes `getDocstring()`. Blank-line gap breaks association.
2. **Annotation (`@doc`)** — *(deferred, §3.2)* attached structurally to the element; no heuristics needed. This is the robust path and the reason §3.2 remains worth doing later.
3. **Extension provenance** — when a member arrives via `extend`, its doc comes from the `extend` site. The model records `defined_in` (file + whether it came from the base declaration or an extension) and rendering labels it — *"Added by `extend action Xfer` (`dma_ext.pss:14`)"*. Idiomatic PSS spreads a type across files; hiding that would be actively misleading.
4. **Explicit** — directive-body content overrides the source doc.

---

## 6. Architecture

```
                      ┌──────────────────────────────────────────────┐
   .pss  ───────────► │  model  (pssparser front-end)                 │
                      │  - Parser.parse(...) + link()                 │
                      │  - walk linked RootSymbolScope (ext-merged)   │
                      │  - filter synthesized (loc.lineno < 0)        │
                      │  - collect docstrings + annotations + loc     │
                      │  - emit normalized PssObject tree             │
                      └───────────────────┬──────────────────────────┘
                                          │  PssObject (kind, name, sig,
                                          │  raw_doc, annotations, flow,
                                          │  loc, defined_in, children)
                      ┌───────────────────▼──────────────────────────┐
                      │  docparse  (DocstringParser registry)         │
                      │  native | doxygen  (annotation: deferred)     │
                      │  raw -> (summary, rst_body, fields, xrefs)    │
                      │  + field-list/AST cross-validation (§3.1)     │
                      └───────────────────┬──────────────────────────┘
                                          │
   ┌──────────────────────────────────────▼───────────────────────────────┐
   │  sphinx_pss  (the extension)                                          │
   │                                                                       │
   │  domain.py    PssDomain(Domain)                                       │
   │               directives: pss:package pss:component pss:action        │
   │                 pss:monitor pss:struct pss:buffer pss:stream           │
   │                 pss:state pss:resource pss:enum pss:field              │
   │                 pss:constraint pss:covergroup pss:function pss:exec    │
   │                 pss:pool pss:annotation pss:typedef                    │
   │               roles: pss:action pss:comp pss:buffer pss:obj ...        │
   │               index + inventory (intersphinx-ready)                    │
   │                                                                       │
   │  autodoc/     Documenter registry + auto* directives                  │
   │               :members: :undoc-members: :inherited-members:            │
   │               :extensions: :flow: :activity: :recursive: ...           │
   │                                                                       │
   │  diagrams.py  flow graph | activity graph | component tree |          │
   │               inheritance graph   (Graphviz / Mermaid)                 │
   │                                                                       │
   │  events       pss-autodoc-process-doc, pss-autodoc-skip-member         │
   └───────────────────────────────────────────────────────────────────────┘
```

### 6.1 Parse wide, reference scope

Same contract as `sphinx-systemverilog` §6.1, and it is if anything more important here because PSS's cross-element relationships are *global*:

- **One index per build.** On `builder-inited`, parse everything in `pss_source_dirs` / `pss_source_files` in a single `Parser`, `link()` once, and build a `PssIndex` — qualified name → `PssObject` — plus the **derived relation tables** that make PSS docs valuable: `produces[type] → [actions]`, `consumes[type] → [actions]`, `locks/shares[resource] → [actions]`, `instantiates[component] → [components]`, `extends[type] → [extensions]`, `derived[type] → [subtypes]`. These are computable only with the whole model in hand.
- **Directives reference into it.** `.. autopssaction:: dma_pkg::Dma::Xfer` resolves a qualified name; roles resolve the same way; no directive re-parses.
- **Whole-tree front-end.** `.. autopsssummary::` walks an index subtree and emits a structured API tree, scoped by package/component/kind/glob.
- **Caching.** Memoize the index in-process keyed by input set + source mtimes (the SV project measured cold ~4s / warm ~0.4ms on UVM-scale input; PSS models are far smaller).

### 6.2 Module layout

```
src/sphinx_pss/
  __init__.py            # setup(app): domain, directives, config, events
  config.py              # pss_source_dirs, pss_doc_style, pss_document_stdlib, ...
  model/
    builder.py           # pssparser -> PssObject tree (the §4 engine)
    index.py             # PssIndex + derived relation tables (§6.1)
    objects.py           # PssObject dataclasses
    flow.py              # flow/resource relation extraction
    activity.py          # ActivityDecl -> normalized activity graph
    locations.py         # Location -> file:line, viewcode support
  docparse/
    base.py              # DocstringParser ABC, ParsedDoc
    native.py
    annotation.py        # @doc / @code_doc as a doc source — DEFERRED (§3.2)
    doxygen.py
    fields.py            # PSS field-list vocabulary + AST cross-validation
    xref.py
  domain.py
  autodoc/
    documenters.py
    directives.py        # auto* incl. autopsssummary
    diagrams.py
  viewcode.py
tests/
  pss/                   # fixture .pss sources
  roots/                 # sphinx test projects
  test_model.py test_docparse_*.py test_domain.py test_autodoc.py test_flow.py
```

---

## 7. Directives, roles, config

**Manual domain directives** (autodoc emits these; always available):

```rst
.. pss:component:: Dma

   The DMA controller.

   .. pss:action:: Xfer
      :input: in_b : DmaBuf
      :output: out_b : DmaBuf
      :lock: eng : DmaEngine

      Program a single DMA transfer.
```

**Autodoc directives:**

```rst
.. autopsspackage:: dma_pkg
   :members:
   :recursive:

.. autopsscomponent:: dma_pkg::Dma
   :members:
   :actions:
   :component-diagram:

.. autopssaction:: dma_pkg::Dma::Xfer
   :members:
   :flow-diagram:
   :activity-diagram:
   :show-extensions:

.. autopssbuffer:: dma_pkg::DmaBuf
   :producers-consumers:

.. autopsssummary::
   :packages: dma_pkg
   :kinds: action, buffer, component
```

**Options.** `:members:` `:undoc-members:` `:inherited-members:` `:exclude-members:` `:recursive:` `:member-order: (source|alpha|groups)` `:doc-style:` `:no-index:` — plus PSS-specific: `:show-extensions:` (annotate members with their `extend` provenance), `:flow-diagram:`, `:activity-diagram:`, `:component-diagram:`, `:show-inheritance:`, `:producers-consumers:`, `:constraints:` (render constraint bodies), `:exec-blocks:`.

**Roles.** `:pss:action:` `:pss:comp:` `:pss:buffer:` `:pss:stream:` `:pss:state:` `:pss:resource:` `:pss:struct:` `:pss:func:` `:pss:field:` `:pss:constraint:` `:pss:pkg:` `:pss:obj:` (generic). Inventory exported for intersphinx.

**Config (`conf.py`):**

```python
extensions = ["sphinx_pss"]
pss_source_dirs     = ["../model"]
pss_source_files    = []                    # explicit ordered build unit, if needed
pss_doc_style       = "native"              # native | doxygen | auto
                                            #   ("annotation" deferred — §3.2)
pss_document_stdlib = False                 # True publishes the core-library reference (§9.8)
pss_tolerate_link_errors = False
pss_diagrams        = "graphviz"            # graphviz | mermaid | off
pss_viewcode        = True
pss_default_options = {"members": True, "member-order": "source"}
```

---

## 8. Object model (`PssObject`)

```python
@dataclass
class PssObject:
    kind: str              # 'package'|'component'|'action'|'monitor'|'struct'
                           #  |'buffer'|'stream'|'state'|'resource'|'enum'
                           #  |'field'|'flow_ref'|'resource_claim'|'constraint'
                           #  |'covergroup'|'function'|'exec'|'pool'|'annotation'
                           #  |'typedef'|'activity'
    name: str
    qualname: str                       # pkg::comp::action
    qualifiers: list[str]               # abstract, rand, static, const, pure, ...
    signature: str                      # rendered declaration
    type_ref: str | None                # declared type, resolved to a qualname
    extends: str | None                 # super_t
    template_params: list[TemplateParam]
    raw_doc: str | None                 # untouched comment text
    annotations: list[Annotation]       # captured from Phase 1; rendered as
                                        #   metadata, not (yet) a doc source
    doc_style: str | None
    location: SourceRef                 # file, line, col
    defined_in: Provenance              # base declaration vs. which extend site
    flow: FlowSpec | None               # inputs/outputs/locks/shares (actions)
    activity: ActivityGraph | None      # normalized activity (actions)
    group: str | None
    children: list["PssObject"]
```

All `pssparser` specifics live in `model/builder.py`; everything downstream is stable against parser API churn. `FlowSpec` and `ActivityGraph` are the PSS-specific additions with no SV analog — they are what §9 renders.

---

## 9. PSS-specific capabilities (the differentiator)

These are the reason this is not just "sphinx-systemverilog with a different parser."

**9.1 Flow documentation and producer/consumer tables.** Every action declares `input`/`output` flow-object refs and `lock`/`share` resource claims. From the index we render, on each **flow-object type page**, a *Produced by* / *Consumed by* table linking to the actions, and on each **action page**, its flow signature with links to the object types. This is the PSS model's actual composition contract, and today it exists only in people's heads.

**9.2 Flow dataflow diagrams.** A Graphviz/Mermaid bipartite graph — actions as boxes, flow objects as ellipses, edges by direction — scoped to a package, a component, or the transitive closure around one action. Answers "what can follow `Xfer`?" directly from the model.

**9.3 Activity graphs.** `ActivityDecl` and its statement nodes (`ActivitySequence`, `ActivityParallel`, `ActivitySchedule`, `ActivitySelect`, `ActivityRepeatCount`, `ActivityForeach`, `ActivityActionHandleTraversal`, …) normalize into an `ActivityGraph` rendered as a diagram, with each traversed action linked. For a compound action this is the single most useful artifact a reader can be handed.

**9.4 Component instance trees.** Component fields that are component types form the static instance hierarchy — render it as a tree diagram, with pool declarations and `bind` statements annotated on the nodes.

**9.5 Extension provenance.** Because the linked view merges `extend`, docs must say where each member came from (§5.3). Additionally, each type page lists *"Extended by"* with links to every `extend` site.

**9.6 Coverage and requirements traceability.** Covergroups/coverpoints render as verification intent, and the `:req:` field builds a **requirements index page** — a reverse table from requirement ID to every action/coverpoint/constraint that references it. For a language whose whole purpose is portable verification intent, this is the artifact that sells the tool.

**9.7 Constraint rendering.** Named constraint blocks render with their source text (syntax-highlighted) plus their doc comment, so the documented intent sits beside the actual expression.

**9.8 Core-library reference — a confirmed deliverable.** With `pss_document_stdlib = True`, the same machinery publishes a browsable reference for `std_pkg`, `addr_reg_pkg`, `executor_pkg`, and `sync_pkg`. Resolved (§14 Q4) as a goal in its own right, and it doubles as the project's realistic example doc set. Concretely:

1. **Extract the standard-package source from the LRM.** Note that `pssparser` already ships copies at `src/stdlib/{std_pkg,addr_reg_pkg,executor_pkg,sync_pkg}.pss` — these are the parser's working definitions, not necessarily a faithful transcription of PSS 3.1. The task is to extract from the LRM text and **reconcile against those files**, reporting any divergence back to `pssparser` as a bug. Extraction should be scripted (`scripts/extract_stdlib.py`) against the LRM markdown so it is repeatable when the LRM revs, not a one-time hand copy.
2. **Add doc comments derived from the LRM prose.** Each type, field, and function gets a `native` doc comment written from the corresponding LRM clause, with a clause citation (`PSS 3.1 §22.3.1`). This is also the forcing function that exercises the §3.1 field-list vocabulary against real, non-toy PSS.
3. **Publish it as the example.** The annotated stdlib becomes both `docs/examples/stdlib.md` — a live, linked reference built with the extension — and the corpus the tests build against. Two things fall out for free: a public PSS core-library reference that does not exist today, and a large real-world dogfooding target of exactly the kind the SV project got from UVM.

The maintenance cost is real (it must track the LRM), which is why the extraction is scripted and the doc comments live in a separate annotated copy under version control rather than being hand-edited into vendored parser sources.

---

## 10. Rendering & integration

- Each `PssObject` → a domain directive node; signatures via `handle_signature` producing real `desc_parameterlist`/`desc_parameter` nodes, with type references resolved to links (the SV project's Phase-5 lesson: do this from the start, and stash the fullname in `handle_signature` because Sphinx calls `_object_hierarchy_parts()` before target ids exist, or objects get no TOC entries).
- `ParsedDoc.rst_body` goes through nested-parse, so authors write full RST/MyST in comments.
- `viewcode`-style `[source]` links from `Location`.
- Objects inventory exported → intersphinx + search.
- `pss-autodoc-process-doc` / `pss-autodoc-skip-member` events for user post-processing.
- Parser markers → Sphinx warnings, severity-mapped; errors surfaced, info summarized.

---

## 11. Phased delivery plan

**Phase 0 — spike (DONE, §4).** Proven: docstring collection, annotation attachment, extension merging through the linker, qualified-name lookup, location/fileid resolution, synthesized-member filtering. Four upstream gaps identified (G1–G4).

**Phase 0.5 — upstream `pssparser` fixes.** G1 (`Parser(collect_docstrings=…)`) and G2 (attributed-field docstrings) are **blocking** — without G2 the most commonly documented elements in PSS have no docs. Land both in `pssparser` with tests before Phase 1 depends on them. G3 and G4 are **deferred** with annotation support and are not on this critical path.

**Phase 1 — MVP: index + domain + `native`.**
- `model/builder.py`: linked-tree walk → `PssObject` for package, component, action, struct/buffer/stream/state/resource, enum, field, constraint, function.
- `model/index.py`: project-wide `PssIndex` built once on `builder-inited` — establishes the parse-wide/reference-scope contract from day one.
- `native` docparse with the PSS field-list vocabulary (§3.1), including AST cross-validation.
- `pss` domain: object directives + roles + index.
- `autopsspackage`, `autopsscomponent`, `autopssaction`, `autopssstruct` with `:members:`.
- **Deliverable:** document a hand-written sample DMA package end-to-end, dogfooded in this repo's own docs, building clean under `-W`.

**Phase 2 — the PSS differentiators.**
- Flow relation tables + producer/consumer rendering (§9.1).
- Flow dataflow diagrams and component instance trees (§9.2, §9.4).
- Extension provenance and "Extended by" (§9.5).
- Inheritance diagrams; `:inherited-members:`.
- **Acceptance:** a realistic multi-file, multi-package PSS model with cross-file `extend` documents end-to-end with correct flow tables and provenance.

**Phase 3 — activities, whole tree, and the core-library reference.**
- Activity graph extraction and diagrams (§9.3).
- `autopsssummary` whole-tree front-end with scope narrowing.
- `viewcode`, intersphinx inventory, member ordering/groups.
- **Core-library reference (§9.8)** — the three-step stdlib work: scripted LRM extraction + reconciliation against `pssparser/src/stdlib`, LRM-derived doc comments with clause citations, and publication as `docs/examples/stdlib.md`. Promoted from Phase 4 because it is the project's realistic example and corpus, and everything after it benefits from having a non-toy model to build against. Annotation rendering as element metadata (not as a doc source) lands here too, since the stdlib declares annotation types.
- **Acceptance:** the PSS standard library documents end-to-end, clean under `-W`, and is published as the reference example.

**Phase 4 — traceability, coverage, polish.**
- Requirements index (§9.6), covergroup/coverpoint rendering (§9.6), constraint source rendering (§9.7).
- `doxygen` dialect + `auto` detection.
- Template/generic type handling.
- Performance caching; `pss_tolerate_link_errors` degraded mode.

**Deferred (no phase) — `@doc` annotations as a doc source (§3.2).** Blocked on the G4 syntax decision in `pssparser`. Re-plan once that is settled; the `DocstringParser` seam (§3.4) and `PssObject.annotations` (§8) are in place from Phase 1 so this is additive when it happens.

---

## 12. Testing

- **Unit:** each `DocstringParser` (raw → `ParsedDoc`), table-driven per dialect; the field-list vocabulary and its AST cross-validation warnings.
- **Model:** fixture `.pss` → expected `PssObject` tree, explicitly covering synthesized-member filtering (`lineno < 0`), extension merging and provenance, flow-ref extraction, and — once G2 lands — attributed-field docstrings.
- **Relations:** producer/consumer, lock/share, instance-tree and inheritance tables from a fixture model with known-correct expected tables.
- **Integration:** `sphinx-build` on `tests/roots/` mini-projects, asserting the doctree via `sphinx.testing` (`@pytest.mark.sphinx`).
- **Corpus smoke:** run the model over the `pssparser` test corpus and the PSS standard library; assert no crashes and an element-count floor. This is what will surface parser gaps early, exactly as the UVM corpus did for the SV project. From Phase 3, the **annotated stdlib** (§9.8) becomes the primary corpus and is built end-to-end under `-W`.
- **Stdlib reconciliation:** a test that diffs the LRM-extracted standard packages against `pssparser/src/stdlib/*.pss`, so divergence surfaces as a failure rather than drifting silently.
- **Regression guard for G1 and G2:** a test per gap that fails if the upstream fix regresses. Plus one for G3's consequence: a `//@…` line must not appear as prose in rendered output.

---

## 13. Dependencies / packaging

- Runtime: `sphinx`, `pssparser` (already in `ivpm.yaml`). Graphviz via `sphinx.ext.graphviz` (optional at runtime; diagrams degrade to a skipped node with a warning when unavailable).
- Package name: **`sphinx-pss`** (resolved, §14 Q3) — consistent with the sibling `sphinx-systemverilog`. The repo README currently says `sphinxcontrib-pss-autodoc` and needs updating.
- `src/` layout, `pyproject.toml`, entry via `setup(app)` in `src/sphinx_pss/__init__.py`.
- Any new dev tooling installed via `uv` **and** recorded in `ivpm.yaml` `dep-sets`.

---

## 14. Key decisions for review

1. **Custom `pss` domain + bespoke autodoc layer**, not an `sphinx.ext.autodoc` extension. Mirrors the validated SV design. — §1
2. **Document the *linked* tree, not per-file ASTs**, so `extend` merging, inheritance, and type resolution are available; per-file walking is the degraded fallback only. — §4.1, §4.4
3. **`native` doc comments are the shipping convention** (with `doxygen` as a migration path), carrying a PSS-specific field-list vocabulary that is cross-validated against the AST. LRM `@doc` annotations are designed but deferred. — §3
4. **PSS-specific rendering (flow tables, dataflow/activity/instance diagrams, extension provenance, requirements traceability) is the product**, not a phase-4 extra; it is what a general doc tool cannot do. — §9
5. **G1 and G2 are upstream blockers** in `pssparser` and should land before Phase 1. G3 and G4 are deferred with annotation support. — §4.3
6. **The annotated PSS standard library is the reference example and test corpus**, extracted from the LRM and published in Phase 3. — §9.8

### 14.1 Resolved (M. Ballance, 2026-08-13)

- **Q1 — Phase ordering: confirmed as planned.** PSS differentiators (flow/diagrams) stay ahead of annotation support. Reinforced by Q2 — annotations now sit outside the phase plan entirely.
- **Q2 — Annotation support (`@doc`) is deferred.** Not in Phases 1–4; blocked on the G4 syntax reconciliation in `pssparser`. §3.2 keeps the specification and marks it deferred; §3.4 keeps the `DocstringParser` seam open (the ABC takes the whole `PssObject`, not just `raw_doc`) so it is additive later. Annotations are still captured in the model and rendered as element metadata from Phase 3 — only their use as a *documentation source* is deferred. G3/G4 dropped from the Phase-0.5 blocking set. One consequence carried into Phase 1: because G3 makes `//@…` lines fall into the docstring as literal text, the `native` parser must strip a leading `@…` line rather than render it as prose.
- **Q3 — Package name: `sphinx-pss`.** README to be updated from `sphinxcontrib-pss-autodoc`.
- **Q4 — Standard-library reference: yes, and it becomes the project's example.** Three steps, now §9.8 and a Phase-3 deliverable: (1) extract the standard-package source from the LRM — scripted, and reconciled against the copies `pssparser` already ships at `src/stdlib/`, with any divergence reported upstream; (2) add doc comments derived from LRM prose, with clause citations; (3) publish as `docs/examples/stdlib.md` and use as the test corpus. This also becomes the forcing function for the §3.1 field-list vocabulary against non-toy PSS.

### 14.2 Still open

- **Requirements-traceability vocabulary.** `:req:` (§3.1, §9.6) assumes free-form IDs. If there is a house convention or an external requirements tool to integrate with, that should shape the field's syntax and the index page before Phase 4.
- **G4 direction, when it is picked up.** Deferring the feature does not settle the grammar question: whether `pssparser` moves to the LRM's `@doc {.text=…}`, keeps `@doc(text=…)`, or accepts both during a transition. That call is `pssparser`'s to make; sphinx-pss follows it.
