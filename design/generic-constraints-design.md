# Generic constraints — design & research

**Status:** Draft for review
**Date:** 2026-09-09
**Covers:** PSS 3.1 §13.1.2 (`generic_constraint_declaration`, Syntax 58) — how `sphinx-pss` models, documents and renders it. Refines design §9.7 / `P4-IMPL-3`.
**Depends on:** nothing already built; the model and domain layers from Phase 1 are sufficient for the declaration slice. One upstream `pssparser` defect (`C1`) blocks documenting any model that *uses* the construct.

---

## 1. What this is, and why it needs its own design

PSS 3.1 added **generic constraints**: a named, optionally parameterized,
optionally value-yielding constraint that does *not* hold until something
references it.

```pss
action send_pkt {
    rand bit[16] pkt_sz;
    constraint pkt_sz_c        { pkt_sz > 0; }                          // fixed — always holds
    constraint small_pkt_c()   { pkt_sz <= 100; }                       // generic — holds when referenced
    constraint jumbo_pkt_c()   { pkt_sz > 1500; }
    constraint interesting_sz_c{ small_pkt_c() || jumbo_pkt_c(); }      // reference from a fixed constraint
}
constraint numeric max(numeric a, numeric b) (a < b) ? b : a;           // value-yielding, package scope
```

Three properties make this a documentation problem rather than "one more member
kind":

1. **It is a callable contract, not a statement.** A generic constraint has a
   name, a parameter list, optionally a result type, and callers. That is the
   same shape as a function — and this project already treats functions as
   first-class documented objects with real `desc_parameterlist` nodes. A
   generic constraint rendered the way `constraint c { … }` is rendered today
   (name only, body as prose) throws away everything a caller needs.
2. **Its meaning is "available", not "true".** A reader who sees
   `small_pkt_c()` beside `pkt_sz_c` and is not told the difference will read
   both as invariants of `send_pkt`, and be wrong about the model. The rendering
   has to make *conditional applicability* visible at a glance.
3. **Reference sites are the interesting half.** `pkt_sz_c` documents itself;
   `small_pkt_c` is only meaningful together with the answer to "who applies
   this, and where?" — a fixed constraint, an in-line `with`, or an activity
   branch (§13.4.11). That reverse relation is exactly the kind of whole-model
   artifact this project exists to produce (design §9.1's producer/consumer
   tables are the same idea for flow objects).

**In scope:** the declaration (both forms), its parameters, static-ness,
scoping, inheritance/shadowing, the reference index, the doc-comment
convention, and the rendering. **Out of scope:** solving or evaluating
constraints, expression pretty-printing beyond what §5.4 specifies, and the
runtime/elaboration view (same boundary the activity design draws).

---

## 2. What the LRM says

Condensed from PSS 3.1 Public Review Draft (2026.08.28); clause numbers are the
ones the doc comments should cite.

| Clause | Rule | Consequence for documentation |
|---|---|---|
| 13.1.1 | Two kinds of member constraint: **fixed** (always holds) and **generic** (holds only when referenced, directly or indirectly, from a fixed constraint) | The kind distinction is semantic and must be rendered, not inferred from the parentheses |
| 13.1.1 (NOTE) | `dynamic` constraints are **deprecated**; replaced by a generic constraint with no parameters | `dynamic constraint c {…}` renders with a deprecation note pointing at `constraint c() {…}` |
| 13.1.2, Syntax 58 | `generic_constraint_bool ::= [static] constraint id (params) constraint_set`; `generic_constraint_value ::= [static] constraint <type> id (params) expr ;` | Two shapes, one kind. The value form's signature carries a result type and its body is a single expression |
| 13.1.2 | `generic_constraint_data_type ::= numeric \| data_type`; a param may be `const` | `numeric` is a *category*, not a type — it never resolves to a page, and must not emit a broken cross-reference |
| 13.1.2 | Declarable in struct, action and component scopes, **and in package scopes where they are always static** | Package-scope declarations render as `static` regardless of the keyword (see `U-17`) |
| 13.1.2 a) | May not declare local variables | — |
| 13.1.2 b) | A generic constraint with a result type is a single expression and may be used anywhere an expression of that type is legal | The value form is documented like a function: signature, result type, params |
| 13.1.2 c) | A generic constraint that shadows one from a base type must match in return and parameter types | Shadowing is renderable as an override relation, and a mismatch is a legitimate warning |
| 13.1.2 d) | Recursion is allowed when gated by a non-random expression | Recursive references must not send the reference index into a loop (§5.5) |
| 13.1.3 | A named fixed **or** generic constraint in a subtype shadows the same name from the supertype | `:inherited-members:` must show the override, not two entries |
| 13.4.11 | A generic constraint may be **traversed in an activity**; it then holds for that branch and the remainder of the activity | An activity node can name a constraint rather than an action (§7.1) |
| 13.1.9 (Example 150) | `forall` is legal inside a generic constraint | Nothing special for us; noted because it parses and is worth a fixture |

Worked LRM examples used as fixtures below: 137 (declaration), 138 (reference
from a fixed constraint), 139 (value-yielding `max`), 140 (recursive), 150
(`forall`), 185 (activity traversal).

---

## 3. Findings — a `pssparser` spike, run 2026-09-09

Everything in this section was produced by parsing and linking fixtures with the
in-tree `packages/pssparser`, freshly rebuilt.

> **Build note.** `ninja -C build` failed at HEAD exactly as
> [`pssparser-activity-gaps.md`](pssparser-activity-gaps.md) §2.1 describes.
> The fix is narrower than deleting the generated tree: `ExecTargetTemplateParam.{h,cpp}`
> are orphans from an older AST spec, and the `AST-build` sub-project's ninja
> file still globs them. Delete those two files, re-run `cmake .` in
> `build/pssparser_ast/src/AST-build`, then the normal three-step loop. Done as
> part of this spike, so the evidence below is runtime-verified against current
> sources, not read off the C++.

### 3.1 What works

| Capability | Evidence |
|---|---|
| Both declaration forms build AST nodes | `GenericConstraintDeclBool` (`super: ConstraintBlock`) and `GenericConstraintDeclValue` (`super: ScopeChild`), `ast/constraint.yaml` |
| **Doc comments attach to both forms** | `GenericConstraintDeclBool 'small_pkt_c' doc='A small packet.\n\n:when: MTU-limited links'`; `GenericConstraintDeclValue 'max' doc='The larger of two values.…'` — the `attr_field` anchor problem (`G2`) does not recur here |
| Parameters are fully described | `GenericConstraintParam` exposes `getName()`, `getIs_const()`, `getIs_numeric()`, `getType()`. `numeric a` → `is_numeric=True, type=None`; `const bit[64] idx` → `is_const=True, type=DataTypeInt` |
| The value form's result type is available | `getIs_return_numeric()` / `getReturn_type()`; `constraint bit[8] clamp(…)` → `rtype=DataTypeInt`, `constraint numeric max(…)` → `is_return_numeric=True` |
| `static` is recorded | `getIs_static()` — `True` for `static constraint jumbo_pkt_c()` |
| **Declarations carry a real start location** | `small_pkt_c` at line 25, `max` at line 6 — unlike activity statements (`U-11`), so `[source]` links and precise diagnostics work |
| Declarations survive linking, in the right scope | Linked `SymbolTypeScope 'A'` contains `GenericConstraintDeclBool 'small_c'`; package scope contains `GenericConstraintDeclValue 'clamp'` |
| `extend` merging works | `extend action C::A { constraint ext_c() {…} }` appears among `A`'s linked children with its own docstring and `fileid` — provenance (design §5.3) needs no new machinery |
| Shadowing is representable | `base_s.lim(bit[8])` and `derived_s.lim(bit[8])` both present in their own scopes |
| Reference sites are recoverable by name | `ExprRefPathContext.getElems()` → `ExprMemberPathElem`, with `getId().getId()` = `max` and a **non-`None` `getParams()`** exactly when the element is a call. That pair is the discriminator the reference index needs (§5.5) |
| `forall` inside a generic constraint parses | Example 150 fixture builds `ConstraintStmtForall` under the declaration's `ConstraintScope` |

### 3.2 What is broken or missing upstream

Continuing the `U-n` numbering (`U-12` was the last, in the activity design).

| ID | Finding | Evidence | Impact |
|---|---|---|---|
| `U-13` | **Every reference to a generic constraint fails to link.** The declaration is added to the symbol tree as an *unnamed* child — `TaskBuildSymbolTree::visitConstraintBlock` calls `addChild(i, false)`, and there is no `visitGenericConstraintDecl*` override — so no name is registered and `TaskResolveRefs` cannot find one. `TaskResolveRefs` already tracks generic-constraint *parameter* names (`m_generic_constraint_params`), so the body resolves; only the reference site does not. | `constraint interesting_sz_c { small_pkt_c() \|\| jumbo_pkt_c(); }` → `Error: unknown identifier 'small_pkt_c'`; `j == max(k,l)` → `unknown identifier 'max'; did you mean 'map'?`; `do A with { small_c(); };` → `unknown identifier 'small_c'`; recursive `gt_elem(...)` → `unknown identifier 'gt_elem'`. All at **error** severity | **Blocking, and wider than this feature.** `Parser.link()` raises, so a model that uses generic constraints cannot be documented at all except under `pss_tolerate_link_errors` — no cross-references, no flow tables, no diagrams, for the *whole project*, not just the constraint |
| `U-14` | **An activity traversal of a generic constraint reports nothing to the marker stream.** `select { d1; d2; }` (LRM Example 185) prints `TaskResolveRef: Failed to find root element (d1)` on the console and produces **no marker**; `Parser.markers` contains only the unrelated error from another line | **High.** Sphinx warnings are generated from markers, so this failure is invisible to a doc build. It is also the one reference form that silently *keeps going* |
| `U-15` | **No end location on either declaration form.** `getEndLocation()` is `(-1,-1)` and `location.extent` is `-1`, though `ConstraintScope` inherits an `endLocation` field | **Medium.** No source span → no source-slice rendering of the body (§5.4 fallback), no `viewcode` range. Start line is available, so `[source]` links to the first line still work |
| `U-16` | **Parameters are hoisted into the enclosing symbol scope.** The linked scope containing a generic constraint also contains sibling `GenericConstraintParam` and `DataTypeInt` nodes — the same shape as the label hoisting in `U-12` | **Low, but a trap.** Harmless today only because they carry `lineno == -1` and the builder's synthesized-member filter drops them. A builder that stops relying on that filter emits phantom members named `v`, `hi`, … |
| `U-17` | **Package-scope declarations report `is_static == False`.** LRM 13.1.2 says package-scope generic constraints "are always static" | **Low.** Renderer must derive `static` from scope, not only from the flag (§5.3) |

`U-16` is deliberately **not** filed upstream, for the same reason `U-12` was
not: whether a parameter belongs in the enclosing symbol table is a linking
decision, and filtering it costs us nothing.

---

## 4. Upstream work items (`pssparser`)

Filed as `C1`–`C3`, in the style of `pssparser-fixes-plan.md` and the `A1`–`A6`
activity items.

| ID | Item | Where | Size | Blocking? |
|---|---|---|---|---|
| `C1` | **Resolve references to generic constraints** (`U-13`). Two halves: (a) register the declaration as a named symbol — add `visitGenericConstraintDeclBool` / `…Value` to `TaskBuildSymbolTree` using the named `addChild(c, name, …)` overload rather than inheriting `visitConstraintBlock`'s unnamed one; (b) teach `TaskResolveRefs` that a path element with a parameter list may denote a constraint symbol, in three positions — boolean reference inside a constraint, value reference in an expression, and bare-name traversal in an activity. Arity and parameter-type checking, the 13.1.2 c) shadow-signature rule, and 13.1.2 d) recursion gating are the semantic follow-ons; **a first cut may resolve without checking**, which is all the doc side needs | `TaskBuildSymbolTree.cpp`, `TaskResolveRefs.cpp` | Substantial — this is name-resolution work, not a patch. The registration half is ~30 lines; the resolution half is the real cost | **Yes**, for any model that uses the construct |
| `C2` | **Emit a marker for an unresolvable activity traversal root** (`U-14`) instead of a console print. Independent of `C1` and worth having regardless — it is the generic "activity names something that does not exist" diagnostic | `TaskResolveRefs.cpp` | ~10 lines | No, but cheap and it removes a silent failure |
| `C3` | **Set `endLocation` on `GenericConstraintDeclBool`/`Value`** (`U-15`), at the closing brace / statement terminator. Same class as `A5` | `AstBuilderInt.cpp:3334,3361` | ~5 lines | No — degrade per §6.5 |

**Sequencing.** `C1` gates the corpus and example work, not the declaration
rendering. Everything in §5 and §6 except the reference index (§5.5) is
buildable today, against a model that *declares* generic constraints without
referencing them — which is not a realistic model, so the honest position is:
ship the declaration rendering, keep the reference index behind `C1`, and treat
`C1` as the highest-priority upstream item this project has open.

---

## 5. The model layer

### 5.1 A new kind, not a qualifier on `constraint`

`PssObject.kind` gains **`generic_constraint`**, added to `MEMBER_KINDS`. The
alternative — `kind="constraint"` with a `generic` qualifier — was rejected:

- The directive name is the kind (`PssDomain.directives = {kind: make_directive(kind) …}`), so a distinct kind is what gives `pss:generic_constraint::` a signature renderer that emits a parameter list, without a conditional inside the fixed-constraint one.
- Filtering (`:exclude-members:`, `GROUP_ORDER`, the object index) becomes a kind test rather than a qualifier test.
- The index and the role can still treat them together: `:pss:constraint:` resolves to `("constraint", "generic_constraint")`, exactly as `:pss:field:` already spans `field`/`flow_ref`/`resource_claim`/`enum_item`.

The deprecated `dynamic constraint c {…}` stays `kind="constraint"` with its
existing `dynamic` qualifier — it is a fixed-constraint node in the AST
(`ConstraintBlock.is_dynamic`), and re-homing it would misrepresent the source.
Rendering adds the deprecation note (§6.3).

### 5.2 Mapping

| `PssObject` field | Value |
|---|---|
| `kind` | `"generic_constraint"` |
| `name` / `qualname` | declaration name; `qualname` = enclosing scope + `::` + name. Names are unique per scope (13.1.2 c)/13.1.3 make same-name-different-signature illegal), so no mangling is needed |
| `qualifiers` | `["static"]` when `getIs_static()` **or** the enclosing scope is a package (`U-17`) |
| `signature` | §5.3 |
| `type_ref` | the **result type** of the value form (`getReturn_type()`), so it links like a field's type; `None` for the boolean form; the literal `"numeric"` is stored but marked non-linkable (§5.3) |
| `children` | one `kind="field"` object per parameter — reusing `field` rather than inventing `constraint_param`, because `_function_params` already models function arguments that way and `:param:` cross-validation (`validates_against={"field"}`) then works with no vocabulary change |
| `raw_doc` | `getDocstring()` — works today (§3.1) |
| `location` / `defined_in` | start location and `extend` provenance, both working today |
| `annotations` | as for every other member |

Parameter objects carry `qualifiers=["const"]` where declared, and `type_ref`
set to the parameter type or `"numeric"`.

### 5.3 Signature rendering

A signature in this project is *a quotation of the source* (Phase-1 lesson:
`rand int size`, not `rand field size : int`). Applied here:

```
constraint small_pkt_c()
static constraint jumbo_pkt_c()
constraint gt_elem(bit[64] val, list<bit[64]> l, const bit[64] idx)
constraint numeric max(numeric a, numeric b)
static constraint bit[8] clamp(bit[8] v, const bit[8] hi)
```

Built from a `render_generic_constraint_signature()` next to
`render_function_signature()`, emitting real `desc_parameterlist` /
`desc_parameter` nodes so parameter *types* become links.

Two fidelity problems are visible in the spike and are **ours, not upstream**:

- `_type_name` renders `bit[64]` as `bit [63:0]` — a width declaration printed back as a range.
- `_type_name` drops template arguments: `list<bit[64]>` renders as `list`.

Both already affect field and function signatures; generic constraints simply
make them conspicuous, because a parameter list is where a reader looks for
types. Fixed as `P4-IMPL-3b` below, in `_type_name`, once — not per call site.

`numeric` is a type *category*. It renders as plain text with no cross-reference
attempted; it is not a declared type and never resolves. (The existing
`GENERATED_REF` mechanism suppresses the warning for generated references, but
the cleaner answer is not to emit one.)

### 5.4 Body rendering

Three tiers, in order of preference:

1. **Value form** — the body *is* one expression, and the LRM's own examples are
   most legible as source. Render it with the `pss` Pygments lexer from a source
   slice: start location is known; the statement ends at the `;`, recoverable by
   a bounded forward scan of the source line(s) even without `C3`.
2. **Boolean form, with `C3`** — slice `location`…`endLocation` and render the
   block verbatim, highlighted. This is `P4-IMPL-3`'s design §9.7 promise
   ("the documented intent sits beside the actual expression") and it applies
   unchanged.
3. **Boolean form, without `C3`** — render the declaration signature and the doc
   comment only, with no body. Never reconstruct a body from the AST: there is no
   expression printer in this project, and a paraphrased constraint is worse than
   an absent one.

### 5.5 The reference index — "Applied by"

The differentiator, and the analog of design §9.1's producer/consumer tables.
For each generic constraint, collect the sites that reference it:

| Site | How it is found |
|---|---|
| A fixed or generic constraint body in the same or a derived scope | Walk the constraint's expression tree with `pssparser.ast.VisitorBase`; at each `ExprRefPathContext`, take `getElems()[…]`; a **non-`None` `getParams()`** marks a call. Match the name against generic constraints visible in scope |
| An in-line `with { c(); }` on an action traversal | Same walk over the traversal's `getWith_c()` `ConstraintScope` (already reachable per the activity spike) |
| An activity traversal (`select { d1; d2; }`, LRM 13.4.11) | The node arrives as `ActivityActionHandleTraversal` — indistinguishable from an action traversal at the AST level (§7.1). Resolve the target name against the enclosing action's members: a generic constraint wins over nothing else, since an action handle and a constraint cannot share a name in one scope |

Resolution is **by name through `PssIndex`**, the same convention the activity
design adopted for traversal targets and `type_ref` uses today — so the index
does not depend on `C1`. `C1` still matters, because without it the model does
not link at all and there is no linked tree to walk.

Two guards: recursion (13.1.2 d) means a constraint legitimately references
itself — mark visited nodes; and scope, since a bare name may match a generic
constraint in an outer scope. Where a name matches more than one candidate,
record all of them and emit one warning naming the ambiguity, rather than
picking.

Rendered as an **Applied by** table on the generic constraint's entry, and as
an **Applies** list on the referencing constraint or action — both directions,
like *Produced by*/*Consumed by*.

---

## 6. Documentation convention and rendering

### 6.1 Doc-comment vocabulary

The existing vocabulary (`docparse/fields.py`) needs three changes, all small:

| Change | Field | Why |
|---|---|---|
| Extend `applies_to` | `:param:` | Add `generic_constraint`. Cross-validation against the declaration's parameters comes free, because parameters are `field`-kind children (§5.2) |
| Extend `validates_against` | `:constraint:` | Add `generic_constraint`, so `:constraint small_pkt_c:` on the enclosing type validates |
| Extend `applies_to` | `:returns:` | Document the result of a value-yielding constraint. Already free-form and accepted anywhere; this only makes it *documented* for this kind |

One genuinely new field is proposed, and it is the open question in §8:

| Field | Applies to | Meaning |
|---|---|---|
| `:applies:` (alias `:when:`) | `generic_constraint` | The circumstances under which a caller should reference this constraint — "when the DUT is configured for jumbo frames". Free-form, not cross-validated |

The rationale: for a fixed constraint the useful comment is *what it enforces*;
for a generic constraint the useful comment is *when to reach for it*, and the
existing vocabulary has no place for that. Writing the example set below without
it produced the same sentence, ad hoc, every time.

House example, which `docs/usage/native-style.md` should carry:

```pss
action send_pkt {
    rand bit[16] pkt_sz;

    // Packets are never empty.
    constraint pkt_sz_c { pkt_sz > 0; }

    // Restrict the packet to one MTU-limited frame.
    //
    // :applies: links that have not negotiated jumbo frames
    // :req:     NET-104
    constraint small_pkt_c() { pkt_sz <= 100; }

    // The larger of two sizes.
    //
    // :param a: first size
    // :param b: second size
    // :returns: the greater of `a` and `b`
    constraint numeric max_sz(numeric a, numeric b) (a < b) ? b : a;
}
```

### 6.2 Domain and autodoc surface

- **Directive** `pss:generic_constraint::`, registered from `KIND_LABELS` with the label `generic constraint`. Signature renders per §5.3; `UNKEYWORDED_KINDS` does *not* include it, since `constraint` is a real keyword in the source form.
- **Role** — no new role. `:pss:constraint:` resolves to both kinds (`ROLE_KINDS["constraint"] = ("constraint", "generic_constraint")`), so an author writing ``:pss:constraint:`send_pkt::small_pkt_c` `` need not know which it is.
- **Autodoc** — generic constraints are members, so `:members:` picks them up with no new directive. Optionally add `autopssconstraint` accepting `("constraint", "generic_constraint")` for the case of documenting one directly; `autopssobject` already covers it, so this is convenience, not capability.
- **Member ordering** — `GROUP_ORDER` places `generic_constraint` **immediately after `constraint`**: fixed constraints first (what always holds), then generic (what may be applied), then functions. The order is the reading order.

### 6.3 Making "conditional" visible

The single most important rendering decision (§1.2). Three coordinated signals:

1. **The signature carries `()`** — a quotation of the source, and the LRM's own visual cue.
2. **A one-line annotation under the signature**: *"Applies only where referenced"*, linked to the Applied-by table. Emitted for every generic constraint, not only undocumented ones.
3. **On the enclosing type**, fixed and generic constraints render under separate rubrics — *Constraints* and *Generic constraints* — under `:member-order: groups`.

The deprecated form gets a fourth: `dynamic constraint c { … }` renders with a
**Deprecated** note citing 13.1.1 and naming the replacement (`constraint c()`).

### 6.4 Inheritance and shadowing

Under `:inherited-members:`, a subtype's generic constraint that shadows a base
one renders **once**, in the subtype, annotated *"Overrides `base_s::lim`"* with
a link — never twice. This reuses the extension-provenance rendering (design
§5.3) rather than adding a mechanism. Where the LRM 13.1.2 c) signature-match
rule is violated (differing parameter or result types), emit a warning: it is a
model error the linker does not currently catch, and we have both signatures in
hand.

### 6.5 Degradation, per upstream gap

| Gap | Behavior until fixed |
|---|---|
| `U-13` / `C1` | The model does not link. `pss_tolerate_link_errors=True` gives declarations and doc comments from the per-file walk — no cross-references, no Applied-by table, no diagrams — plus the existing "documentation is degraded" build warning. Additionally: when the pre-link walk finds a generic constraint **and** the build is degraded, emit one warning naming `C1` as the likely cause, so the user is not left guessing which of their constructs broke the link |
| `U-14` / `C2` | An activity traversal naming an unknown constraint produces no diagnostic from the parser. The reference index's own name resolution (§5.5) covers it: an unresolved traversal target emits one Sphinx warning per activity |
| `U-15` / `C3` | No body rendering for the boolean form (§5.4 tier 3); `[source]` links point at the declaration line. The value form still renders via the bounded scan |
| `U-16` | Builder filters `GenericConstraintParam` and bare `DataType*` nodes at the scope level **explicitly**, not by relying on `lineno < 0` |
| `U-17` | `static` derived from enclosing scope for package-scope declarations |

---

## 7. Consequences for other designs

### 7.1 Activity diagrams

`activity-diagrams-design.md` §4.4 resolves traversal targets by name through
`PssIndex` and assumes a target is an action. It is not always: LRM 13.4.11
makes a bare generic-constraint name a legal activity statement, and the spike
confirms it arrives as `ActivityActionHandleTraversal` — the *same node class*
as an action traversal. Two additions, both belonging to that design:

- **Resolution must consider constraints.** A target that resolves to a `generic_constraint` is a constraint application, not an action.
- **It needs its own UML node.** A constraint application is not an activity action — render it as a **note/constraint node attached to the branch**, per §13.4.11's "holds for the entire branch on which it is referenced, as well as the remainder of the activity". Drawing it as an action box would assert an execution step that does not exist. LRM Example 185 (`select { d1; d2; }`) is the fixture.

### 7.2 `P4-IMPL-3` (constraint source rendering) and design §9.7

§9.7 promises constraint bodies rendered beside their doc comments. This design
supersedes it for the generic case and shares the source-slice mechanism with
the fixed case; `C3` is the only reason the two are not identical today.

### 7.3 The standard library and the corpus (design §9.8)

If any of the four standard packages, or the `pssparser` test corpus, adopts
generic constraints, `U-13` turns the corpus smoke test into a link failure
rather than a count regression. Worth an explicit corpus check now — grep the
corpus for `constraint <id>(` — so the Phase-2/3 schedule is not surprised by it.

---

## 8. Work items

Refining `P4-IMPL-3` in the implementation plan.

### Upstream (prerequisite)
| ID | Task | Blocking |
|---|---|---|
| `C1` | Resolve references to generic constraints (`U-13`) | Yes, for any model that uses them |
| `C2` | Marker for unresolvable activity traversal root (`U-14`) | No |
| `C3` | `endLocation` on generic-constraint declarations (`U-15`) | No |

### Implementation
| ID | Task | Done when |
|---|---|---|
| `P4-IMPL-3a` | `generic_constraint` kind end-to-end: `objects.py` (`MEMBER_KINDS`, `GROUP_ORDER`), `builder.py` `_build_generic_constraint` for both AST forms + `_DISPATCH` entries, parameters as `field` children, `static`-by-scope (`U-17`), explicit param/`DataType*` filtering (`U-16`) | fixture declarations build to expected `PssObject` trees |
| `P4-IMPL-3b` | `_type_name` fidelity: width form (`bit[64]`, not `bit [63:0]`) and template arguments (`list<bit[64]>`) | signature golden files match the source |
| `P4-IMPL-3c` | `render_generic_constraint_signature()` + `pss:generic_constraint::` directive with real parameter nodes; `:pss:constraint:` spans both kinds; label and rubric | signature and links render for all five §5.3 forms |
| `P4-IMPL-3d` | "Applies only where referenced" annotation, `dynamic` deprecation note, override annotation (§6.3, §6.4) | rendered; override annotation links to the base |
| `P4-IMPL-3e` | Reference index (§5.5) in `model/index.py` — expression walk, activity traversals, `with` clauses; Applied-by / Applies tables; recursion and ambiguity guards | tables correct on the Example 138/139/140/185 fixtures |
| `P4-IMPL-3f` | Body rendering, three tiers (§5.4) | value form renders today; boolean form renders once `C3` lands |
| `P4-IMPL-3g` | Vocabulary changes (§6.1) incl. `:applies:`, and `:param:` cross-validation against constraint parameters | a `:param:` naming a non-parameter warns |
| `P4-IMPL-3h` | Degradation paths (§6.5), incl. the "`C1` is probably why" warning | degraded build succeeds and names the cause |

### Tests
| ID | Task |
|---|---|
| `P4-TEST-3a` | `tests/fixtures/pss/generic_constraints.pss` — LRM Examples 137, 138, 139, 140, 150, 185, plus `const` and `numeric` parameters, package/struct/action/component scopes, an `extend`-contributed declaration, and a shadowing pair |
| `P4-TEST-3b` | `tests/model/test_generic_constraints.py` — mapping, signatures, static-by-scope, provenance, param filtering |
| `P4-TEST-3c` | `tests/model/test_constraint_refs.py` — reference index incl. the recursive (Example 140) and activity (Example 185) cases; determinism of table ordering |
| `P4-TEST-3d` | `tests/domain/…` + `tests/autodoc/…` (`sphinx`) — directive, role resolution across both kinds, rubric grouping, override and deprecation annotations |
| `P4-TEST-3e` | `tests/test_upstream_guards.py` — one guard per `C1`–`C3` asserting the *current* broken behavior, so each fails loudly when the fix lands and its degradation can be removed. This is the pattern the `upstream` marker exists for |
| `P4-TEST-3f` | Corpus check (§7.3): if the corpus or stdlib uses generic constraints, the smoke test asserts the degraded-mode path rather than failing |

### Docs
| ID | Task |
|---|---|
| `P4-DOC-3a` | `docs/usage/native-style.md` — the §6.1 example and the `:applies:` field |
| `P4-DOC-3b` | `docs/usage/constraints.md` (new) — fixed vs generic, the value form, how Applied-by is computed and its name-matching limits, the deprecated `dynamic` form |

---

## 9. Open questions

1. **`:applies:` — new field, or reuse prose?** It is the one vocabulary addition proposed here. The case for it is that the "when do I use this?" sentence is *structured* metadata a reader wants in a fixed place; the case against is that every new field is a convention users must learn. Leaning **add it**, with `:when:` as the alias, and revisit after the stdlib pass (design §14.2 already schedules a vocabulary review there).
2. **Is the Applied-by table on by default?** It is cheap to compute and the most valuable thing on the page, but it is also a whole-model relation that can be long. Leaning **on by default, capped**, with the cap reported (the "no silent truncation" rule).
3. **How hard do we push on `C1`?** It is the only upstream item this project has that makes an entire model undocumentable, but it is also the largest — real name-resolution work in `TaskResolveRefs`, not a patch. Options: (a) fund `C1` fully; (b) land only its registration half plus a permissive "resolve, do not check" path, which unblocks documentation at the cost of accepting some illegal models; (c) live with degraded mode. Leaning **(b) now, (a) later** — a doc tool is not the right forcing function for full constraint-reference type checking, but a linker that rejects a legal PSS 3.1 model is a defect either way.
4. **Do fixed and generic constraints share a page section?** §6.2 puts them in separate rubrics under `groups` ordering. Under `source` ordering they interleave, as written. That is probably right — source order is a quotation too — but it does mean the distinction rests entirely on §6.3's per-item signals in the default configuration.
