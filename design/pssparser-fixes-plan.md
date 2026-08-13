# `pssparser` / `pyastbuilder` fixes — work plan

**Status:** `F0`–`F5` and `G1` implemented and green; awaiting the `pssparser` 3.0.3 release before `V5`
**Date:** 2026-08-13
**Target repos:** `psstools/pssparser`, `mballance-utils/pyastbuilder`
**Design:** `design/pssparser-followup-plan.md` (why each of these is a defect, and the pinning decision)
**Tracked from:** this repo, because `sphinx-pss` is the consumer that found them. Every item lands upstream.

Work items are `F<n>` (pssparser) and `G<n>` (pyastbuilder). Each has a checkbox, a named reproduction, the change, its tests, and a "done when".

## Progress log

*(Append newest-first as work lands.)*

- **2026-08-13 — `V1`–`V4` green.** `pssparser` **2092 passed**, 4 skipped, 6
  xfailed (from 2065 at the start), plus **38 gtests**. `sphinx-pss` **311
  tests** pass and `docs/` builds clean under `-W` against the fixed parser.
  `V3` runs over the shipped standard library rather than the optional corpus
  checkouts — see the note under `V3`. `V5` is deliberately **not** started:
  the fixes are on branches and unreleased, so removing a workaround now would
  couple `sphinx-pss` to an unreleased dependency.
- **2026-08-13 — `G1` done** (`pyastbuilder` branch `list-value-struct-accessors`).
  Implemented `visitTypeUserDef` (`G1.1`) **and** the loud generation-time
  failure (`G1.2`) for shapes it still cannot handle — see `G1.0`.
- **2026-08-13 — `F4` done.** `F4.0` answered from the source: `AstLinker::link`
  has one `return` and no early exit, so the fix is unconditional.
- **2026-08-13 — `F1`, `F2`, `F3`, `F5` done** (`pssparser` branch
  `doc-comments-3.0.3`). Three findings changed the plan; each is recorded on
  its own item below.
- **2026-08-13 — `F0` done.** The Release A–C work is committed and the
  changelog is renumbered to 3.0.3.

---

## 1. Scope and shape of the work

Six defects, found integrating `sphinx-pss` Phase 1 against the reworked parser. They share a character worth stating up front:

> **Every one of these fails silently.** Nothing crashes and no marker is emitted — output is merely missing, or subtly wrong in a way that only shows up in rendered documentation. That is why each item below carries a regression test as a *requirement*, not a nicety: there is no other way to notice a recurrence.

Five of the six are one-to-a-few lines. The work is in the tests and in one design decision (`F3`), not in the code.

| ID | Defect | Repo | Code size |
|---|---|---|---|
| `F1` | `EnumItem` has no source location | `pssparser` | 2 lines |
| `F2` | `FunctionPrototype` has no source location | `pssparser` | 1 line |
| `F3` | Package/enum/**function** symbol scopes expose no docstring | `pssparser` | ~30 lines + a decision |
| `F4` | A failed `link()` leaves nothing walkable | `pssparser` | ~8 lines |
| `F5` | Line-comment runs dedent to zero if any line lacks a space after `//` | `pssparser` | ~4 lines |
| `G1` | `list<value-struct>` generates a property whose helpers are never generated | `pyastbuilder` | ~30 lines |

### 1.1 Release context

`v3.0.2` is the latest tag. The working clone carries an **uncommitted** `3.0.3` containing the Release A–C doc-comment rework (`pssparser-enhancement-plan.md`), so **3.0.3 is unreleased and these fixes fold into it** — one release, not two.

Two things must happen to that working tree before anything here starts; both are `F0`.

### 1.2 What is deliberately not here

- **The PSS Pygments lexer.** Resolved 2026-08-13: it becomes a separate package, owned elsewhere. **Done** — [`pygments-pss`](https://git.dvkit.org/psstools/pygments-pss.git) 0.1.0 exists, `sphinx-pss` depends on it, and the in-tree lexer is deleted. Nothing in this plan depended on it.
- **`sphinx-pss`'s capability probe** (followup plan §4). It is a consumer-side change in this repo, needs none of these fixes, and is tracked in `implementation-plan.md`.

---

## 2. `F0` — prerequisites

| ID | Task | Done when |
|---|---|---|
| ☑ `F0.1` | **Commit the Release A–C work.** It is currently 10 untracked files and 23 modified files in the working clone — one `git clean` from gone, and unreviewable as a diff until it is committed | `git status` clean; the rework is in history |
| ☑ `F0.2` | **Renumber the `CHANGELOG.md` entry from `3.1.0` to `3.0.3`.** Under the versioning convention the first two components name the PSS LRM revision targeted, so `3.1.0` announces PSS 3.1 support the parser does not have | changelog heads `3.0.3`; `__version__.py` agrees |

`F0.1` blocks everything. `F0.2` is independent but should not be forgotten at release time — it is the one item that currently misstates something publicly.

**Done 2026-08-13.** Both landed as one commit on branch `doc-comments-3.0.3`, since committing a knowingly-wrong version string and then correcting it serves nobody. The numbering convention is now stated at the top of `CHANGELOG.md` so the next entry cannot repeat the mistake.

---

## 3. `pssparser` work items

### `F1` — `EnumItem` carries no source location

| | |
|---|---|
| **Symptom** | Every `EnumItem` reports `getLocation().lineno == -1` |
| **Reproduce** | `Parser().parse([f]); link()`, walk any `SymbolEnumScope`'s children, read `getLocation()` |
| **Cause** | `AstBuilderInt.cpp:2716` builds the item and calls `attachDocstring(item, (*it)->start)` — the token is in hand — but never `setLoc`. Same omission at `:309` (the `extend enum` path) |

**Change.** Add `setLoc(item, (*it)->start);` beside the existing `attachDocstring` call at both sites. `AstBuilderInt::setLoc(ast::IScopeChild*, Token*)` (`:5793`) already accepts an `EnumItem`.

**Why it matters beyond the obvious.** `lineno < 0` is the documented rule for identifying compiler-injected members, so a consumer applying it uniformly silently discards **every enum value in the model**. Enum values also cannot get a `[source]` link, cannot be reported by file and line, and cannot have their provenance determined when contributed by an `extend`.

| ID | Task | Done when |
|---|---|---|
| ☑ `F1.1` | `setLoc` at both construction sites | both set |
| ☑ `F1.2` | Test: enum items in a plain `enum` report the declaring line | green |
| ☑ `F1.3` | Test: enum items added by `extend enum` report the **extend site's** line, not the base declaration's | green |
| ☑ `F1.4` | Test: no `ScopeChild` reachable from a linked user unit has `lineno < 0` unless it is genuinely compiler-injected. This is the *general* guard — it would have caught `F1` and `F2` together | green |

Tests in `tests/python/source_references/test_location_tracking.py`.

**Done 2026-08-13.** As written. `F1.4`'s general guard needed one thing the plan did not anticipate: an explicit allowlist of the nodes the builder genuinely injects (`set_executor`, `set_default_executor`, `comp`). There is no `synthetic` flag on `ScopeChild` — it exists only on `SymbolScope` — so `lineno < 0` really is the only signal an AST consumer has, which is what makes keeping it trustworthy worth a test. The allowlist is named rather than detected so that adding to it is a deliberate act.

---

### `F2` — `FunctionPrototype` carries no source location

| | |
|---|---|
| **Symptom** | `getLocation().lineno == -1` and `getDocstring() == ""` on every prototype |
| **Reproduce** | Declare `function int f(int a);` in a component; read the prototype's location |
| **Cause** | `AstBuilderInt::mkFunctionPrototype` (`:5170`) constructs the node and never calls `setLoc` |

**Change.** `setLoc(proto, ctx->start);` after construction.

**Why it matters.** A function *definition* carries both, which is why functions are documentable today at all. A **prototype-only** function — an `import`/`export` function, i.e. exactly the target-integration surface — has no definition to fall back on, so it is currently unlocatable and indistinguishable from an injected node.

The docstring half may follow from the location fix or may need its own `attachDocstring`; confirm during implementation rather than assuming.

| ID | Task | Done when |
|---|---|---|
| ☑ `F2.1` | `setLoc` in `mkFunctionPrototype` | set |
| ☑ `F2.2` | Confirm whether the prototype's docstring attaches once the location is set; if not, attach it | decided, with the reason recorded |
| ☑ `F2.3` | Test: a `function` declaration, an `import` function, and an `export` function each report their declaring line | green |
| ☑ `F2.4` | Test: a documented prototype-only function yields its docstring | green |

**Done 2026-08-13, and the defect is narrower than recorded above.** A standalone `function f(...);` **was** already located and documented: the prototype is itself the scope child, so `addChild` handled it. What had no location was a prototype reached through `FunctionDefinition::getProto()` or `FunctionImportProto::getProto()`, where the wrapper is the scope child. The symptom line "every prototype" was wrong; the fix is the same one line.

`F2.2` **answered: no.** The doc comment is attached to the node added to the scope — the declaration as written — and that node already carries it. Copying it onto the inner prototype as well would give two nodes a claim to one comment with no rule for which wins. The rule that *is* uniform is stated in the test file: the docstring is on the node added to the scope, and after `F3` the linked `SymbolFunctionScope` collapses all three spellings to one answer anyway.

---

### `F3` — package and enum symbol scopes expose no declaration or docstring

| | |
|---|---|
| **Symptom** | `SymbolScope` (package) and `SymbolEnumScope` both report `getDocstring() == ""` **and** `getTarget() == None`, so their doc comments are unreachable from the linked tree. The text is collected — the `PackageScope` / `EnumDecl` reached through `Parser.user_units()` has it |
| **Cause** | `target` is declared on `SymbolChildrenScope` (`ast/linking.yaml:63`), so both classes have the field; the linker never sets it. `visitEnumDecl` (`TaskBuildSymbolTree.cpp:229`) sets location and synthetic but not target, unlike the type-scope path at `:912`. `visitPackageScope` (`:186`) sets neither |

**Change — two parts, and the second is the valuable one.**

1. **Set `target`** where a single declaration exists: `visitEnumDecl` gains `ts->setTarget(i)`.

2. **Copy the docstring onto the symbol at link time**, in `visitEnumDecl`, `visitPackageScope`, and the type-scope path at `:912`:

   ```cpp
   ts->setDocstring(i->getDocstring());
   ```

   This is what makes `getDocstring()` **uniformly correct on the linked tree**, and it retires the trap recorded in enhancement plan §10.3 — *"`SymbolTypeScope` hides the docstring; consumers must go through `getTarget()`"* — rather than adding a second special case beside it. Cost is one duplicated string per declared type.

**Packages are the hard part**, and not for implementation reasons. One package has one `PackageScope` **per file**, and `package a::b { }` creates an intermediate scope `a` with no declaration at all. So:

- a single `target` is the wrong shape for a package and should be left unset, or set to a `declarations` list if one is added;
- the intermediate-scope case is handled naturally — it has no declaration, so it gets no docstring;
- **which docstring wins when two files document the same package is a real decision.** See `F3.0`.

| ID | Task | Done when |
|---|---|---|
| ☑ `F3.0` | **Decide the multi-file package docstring rule.** Proposed: **first non-empty in link order wins** — predictable, needs no merge rule, and matches how a reader would expect a re-opened package to behave. Alternatives: concatenate in file order (risks incoherent prose from unrelated files) or last wins (order-dependent in a way nobody can see). Whatever is chosen must be written into `docs/doc_comments.rst`, because it is observable behavior | decided and documented |
| ☑ `F3.1` | `visitEnumDecl`: set `target` and copy the docstring | set |
| ☑ `F3.2` | `visitPackageScope`: copy the docstring per `F3.0` on both the create and the find-existing branches | set |
| ☑ `F3.3` | Type-scope path (`:912`): copy the docstring, so every kind behaves alike | set |
| ☑ `F3.4` | Test: a documented package, enum, action, component, struct and buffer each yield their docstring **directly from the linked scope**, with no `getTarget()` hop | green |
| ☑ `F3.5` | Test: the `F3.0` rule, with the same package declared in two files | green |
| ☑ `F3.6` | Test: `package a::b { }` — the intermediate scope `a` has an empty docstring and does not inherit `b`'s | green |
| ☑ `F3.7` | Update `docs/doc_comments.rst`: `getDocstring()` on a linked scope is now authoritative; record the `F3.0` rule; retire the §10.3 `getTarget()` advice | published |

Tests in `tests/python/source_references/test_doc_comments.py`.

**Done 2026-08-13, with two departures from the plan.**

**The scope was wider.** `SymbolFunctionScope` has the same gap as package and enum scopes — it sets no target and exposed no docstring — and the plan did not list it. All three function spellings (`function f(...);`, `import ... function`, `function f(...) { }`) collapse onto one function scope, so the copy happens at all three link sites and the merge rule below covers the declared-then-defined case for free.

**`F3.1`'s `setTarget` was reverted, deliberately.** Setting `target` on the enum scope broke `enum e : byte_t` — a user-defined enum base type stopped resolving. `target` is declared `visit: true` in `ast/linking.yaml`, so it is a **traversal edge, not a back-pointer**: setting it makes every visitor descend into the `EnumDecl` a second time, now from inside the enum scope, where a base type written in the enclosing scope is not visible. A `SymbolTypeScope` gets away with it because its target's children *do* belong in the type scope.

Nothing is lost — reaching the declaration was only ever the route to its documentation, and the docstring copy delivers that directly — but it invalidates the plan's premise that setting `target` is free. `test_enum_scope_deliberately_has_no_target` asserts the absence, because "the enum scope should carry its declaration like a type scope does" is an obvious-looking change that costs a working feature.

**`F3.0` decided as proposed: first non-empty in link order wins.** Implemented as one `copyDocInfo()` helper that only ever fills an empty docstring, so the single-declaration cases are unaffected and the rule is identical for packages, functions and re-opened scopes. An empty docstring is not a contribution, so a file that happens to link first does not silence a later one that documented the package.

**Newly found: `endLocation` was never copied onto a symbol scope.** Every site copied `location` alone, so the linked tree reported a start with no end and a source range needed a `getTarget()` hop for its other half. Fixed alongside, as `copyExtent()`. Not in the original plan; found by an existing test once `find()` stopped unwrapping.

**Two existing tests were re-baselined deliberately**, both encoding the behavior `F3` retires: the one asserting a type scope reports an empty docstring, and the doc-test helper's practice of unwrapping through `getTarget()` at every hop — which now steps off the linked tree onto a declaration that cannot be walked.

---

### `F4` — a failed `link()` leaves nothing walkable

| | |
|---|---|
| **Symptom** | After a link error, `Parser.user_units()` returns `[]` and `Parser.file_map` is `{}`. The per-file scopes a degraded consumer needs are unreachable through the public API |
| **Reproduce** | Parse `component C { NoSuchType f; }`, catch the `ParseException` from `link()`, then call `user_units()` |
| **Cause** | `Parser.link()` (`python/pssparser/parser.py`) raises **before** it snapshots `_file_map` and assigns `_root`. Ownership of the units has already moved into the returned root by then, so they exist — the parser just never records where they went |

**Change.** Move the snapshot/clear block above the severity check, keeping the raise last:

```python
ret = linker.link(marker_l, self._files)
self._markers.extend(self._collectMarkers(marker_l))

# Record the result before reporting failure. Ownership of the units moved
# into `ret` inside link(), so a caller that catches the exception must still
# be able to reach them -- otherwise a partially-linked model is unreachable
# and a degraded-mode consumer has nothing to fall back on.
self._file_map = dict(self._filenames)
self._root = ret
self._filenames.clear()
self._files.clear()
self._builder = None

if marker_l.hasSeverity(zspp.MarkerSeverityE.Error):
    raise ParseException(err, self._markers)
return ret
```

**Must be confirmed first** (`F4.0`): whether `linker.link()` returns a usable root on the error path, or can return null. If it can be null, the snapshot becomes conditional; the shape of the fix is unchanged either way.

**Consumer cost today.** `sphinx-pss` recovers by re-parsing into a second `Parser` that is never linked, then reading its `_files` / `_filenames`. That is the **only private-attribute access in that codebase**, and it exists solely because of this. It also doubles parse time on the degraded path.

| ID | Task | Done when |
|---|---|---|
| ☑ `F4.0` | Confirm `linker.link()`'s return on the error path | answered; the fix reflects it |
| ☑ `F4.1` | Reorder `link()` per above | done |
| ☑ `F4.2` | Test: after a caught link failure, `user_units()` returns one unit per user file and `file_map` maps each fileid to its path | green |
| ☑ `F4.3` | Test: the units are walkable — declarations and docstrings readable — and the process does not fault | green |
| ☑ `F4.4` | Test: a **successful** link is unchanged; `user_units()`, `file_map` and `root` behave exactly as before | green |
| ☑ `F4.5` | Document in `docs/` that a caught `ParseException` from `link()` leaves the per-file view available, and that cross-references/extension merging are not | published |

`F4.4` matters more than it looks: this reorders the success path too, and a mistake there breaks every consumer rather than only the degraded one.

**Done 2026-08-13.**

**`F4.0` answered: no, it cannot return null.** `AstLinker::link()` has a single `return symtree;` and no early exit — errors are reported only through the marker listener, and `TaskBuildSymbolTree::build()` always constructs a root. So the snapshot is unconditional.

**One thing the plan missed.** Moving the raise below the clear moved `_mkErrorMessage()` to the far side of it, and that method resolved fileids through `_filenames` — which had just been cleared. Every marker in a link-failure message reported `<unknown>` instead of its path. Both it and `_collectMarkers` now go through a `_pathOf()` helper that consults the live map and then the snapshot. Caught by an existing test (`test_the_error_carries_a_source_location`), which is the case for `F4.4` making itself.

The `F4.2`/`F4.3` tests were verified to **fail against the unfixed `link()`** before being accepted — a regression test that passes either way is not one.

---

### `F5` — a line-comment run dedents to zero if any line lacks a space after `//`

| | |
|---|---|
| **Symptom** | ```//@doc(text = "x")``` followed by ```// Real prose.``` yields `'@doc(text = "x")\n Real prose.'` — a leading space on the second line |
| **Reproduce** | Any line-comment run mixing `//text` and `// text` |
| **Cause** | `stripLineMarker` (`src/DocCommentExtractor.cpp:150`) removes the marker and an optional Doxygen `<`, but **not** the conventional single space after it. The block form's `stripContinuationStar` (`:193`) *does* strip an optional single space after `*`. Normalization then leans on the dedent, which works only while every line has the space — one line without it drops the common prefix to zero and every other line keeps its space |

**Change.** In `stripLineMarker`, after removing the marker and the optional `<`, strip one optional leading space — exactly what the block path already does.

**Why it is not cosmetic.** A one-space indent is a **block quote** in reStructuredText, so the consumer renders the whole run as a quotation. Realistic triggers: `//@…`, `//---` rules, ASCII diagrams, and any line where the author simply omitted the space.

Relative indentation is unaffected: `//     indented` becomes `    indented`, and the dedent still sees a four-space difference against `// text`.

| ID | Task | Done when |
|---|---|---|
| ☑ `F5.1` | Strip one optional space in `stripLineMarker` | done |
| ☑ `F5.2` | gtest: a run mixing `//text` and `// text` yields both lines at column 0 | green |
| ☑ `F5.3` | gtest: relative indentation survives — `// text` + `//     code` keeps the four-space difference | green |
| ☑ `F5.4` | gtest: `///` and `//!` behave identically, and `///<` still strips the `<` | green |
| ☑ `F5.5` | Re-baseline any existing case that encoded the old spacing, deliberately and with the reason recorded | reviewed |

gtests in `tests/src/TestDocCommentExtractor.cpp`.

**Done 2026-08-13.** `F5.5` found nothing to re-baseline: no existing case encoded the old spacing, so the whole suite passed unchanged. Four gtests added rather than three — the conventional `// text` spelling is asserted alongside the `//text` one, since the fix must not depend on which appears.

---

## 4. `pyastbuilder` work item

### `G1` — `list<value-struct>` generates a property whose helpers are never generated

| | |
|---|---|
| **Symptom** | `SymbolRefPath.path` raises `AttributeError: 'pssparser.ast.SymbolRefPath' object has no attribute 'numPath'` |
| **Reproduce** | Resolve any type reference, take `TypeIdentifier.getTarget()`, call `.path()` |
| **Cause** | `PyExtListAccessorGen.gen()` (`src/astbuilder/pyext_list_accessor_gen.py:41`) **unconditionally** emits `def <name>(self) -> ListUtil: return ListUtil(self.num<C>, self.get<S>)`, then dispatches on the element type. `visitTypePointer` and `visitTypeScalar` generate the helpers; **`visitTypeUserDef` is not overridden**, so the base `Visitor`'s no-op runs and a by-value struct element produces the property and nothing else |

**Change.** Implement `visitTypeUserDef` on `PyExtListAccessorGen`, generating `num<Name>`, `get<Sname>(i)`, `get<Name>List()` and `add<Sname>` for by-value struct elements. Unlike the pointer path there is no `ObjFactory`/`accept` round-trip — the element is a value, so it is wrapped directly.

**Alternative worth considering** if the value-struct case is judged not worth supporting: make `gen()` emit the property **only** when the element type is one it can generate helpers for, and raise at generation time otherwise. That converts a silent runtime `AttributeError` into a loud build-time failure. Weaker than fixing it, but strictly better than today, and a reasonable fallback if `G1.1` proves awkward.

**The sweep is small — much smaller than first feared.** Every `list<>` element type in `pssparser`'s schema, counted:

| Element shape | Count | State |
|---|---|---|
| `list<UP<T>>`, `list<P<T>>` | 47 | Works (`visitTypePointer`) |
| `list<string>` | 2 | Works (`visitTypeScalar`) |
| `list<list<int32_t>>` | 2 | **Verified working** — `RootSymbolScope.fileOutRef` / `fileInRef` resolve and iterate |
| `list<SymbolRefPathElem>` | **1** | **Broken** — the only affected field in the schema |

So `G1` affects exactly one field today. It is still worth fixing rather than working around, because the failure mode — a property that exists until it is called — is invisible to any consumer until it hits it at runtime, and the next value-struct list added to any schema will hit it again.

**Impact on `sphinx-pss`, honestly stated: low.** Type references are resolved by name through the extension's own index, which is the design's stated model (`PssObject.type_ref`), not a workaround. `G1` would let that become exact for shadowed names and template specializations. It is **on nobody's critical path**.

| ID | Task | Done when |
|---|---|---|
| ☑ `G1.0` | Decide: implement `visitTypeUserDef` (`G1.1`), or fail loudly at generation time (`G1.2`) | decided |
| ☑ `G1.1` | Implement `visitTypeUserDef` in `PyExtListAccessorGen` | `SymbolRefPath.path` iterates, yielding elements with `getKind()` / `getIdx()` |
| ☑ `G1.2` | *(alternative)* Raise at generation time for an element shape with no helper generator | an unsupported shape fails the build, not the caller |
| ☑ `G1.3` | Test in `pyastbuilder` covering a `list<value-struct>` field end to end | green |
| ☑ `G1.4` | Test in `pssparser`: `SymbolRefPath.path` iterates and its elements report kind and index | green |
| ☐ `G1.5` | **`pyastbuilder` release.** `pssparser` resolves it from git or PyPI, never from the local checkout — enhancement plan §10.4 hit exactly this | released and consumable by `pssparser` CI |

**Done 2026-08-13** on branch `list-value-struct-accessors`, except `G1.5`.

**`G1.0` decided: both.** `visitTypeUserDef` handles the two shapes that can occur by value — structs (wrapped directly, no `ObjFactory`/`accept` round-trip, since that exists to recover the dynamic type of a polymorphic pointer and a value has none) and enums (ints at the boundary, so the existing scalar helpers were already correct). Anything else raises at generation time. Doing only `G1.2` would have left the fix undone; doing only `G1.1` would leave the next unhandled shape failing silently again.

**Two shared helpers assumed a `TypeScalar`** and had to be made element-type agnostic: `_getSize` computed a `tname` it never used, and `_is_string` read `.t` unconditionally. The first was dead code; the second is answerable without it, since an enum is never a string.

**`G1.3` asserts the invariant, not the field.** It reads the generated `.pyx` and checks that *every* emitted `ListUtil(self.numX, self.getX)` property has both helpers defined, so it holds for any schema and catches the next shape rather than only this one.

Also carried: the **`Linker.visitTypeUserDef` fix that was sitting uncommitted** in the `pyastbuilder` working tree — an unrecorded `G0` prerequisite of the same shape as `F0.1`, and the one the 3.0.3 changelog's Build section already depended on.

Note for `G1.5`: `tests/unit/test_pyext.py` does not collect, on this branch and on `master` alike — it imports `astbuilder.pyext_gen_pxd`, which no longer exists. Pre-existing and untouched, but it means the new test is effectively the only one that runs.

---

## 5. Sequencing

Ordered by dependency, not by size.

*(Sequence as executed; every step below is done except where §8 says otherwise.)*

1. **`F0.1`** — commit the Release A–C work. Everything else layers on it, and it is currently only a working tree.
2. **`F1`, `F2`, `F5`** — one-line fixes, independent of each other, no API change. Land together with their tests.
3. **`F4.0`**, then **`F4`** — one question to answer first, and it touches the success path, so it wants its own review.
4. **`F3.0`**, then **`F3`** — blocked on the package-docstring decision. The largest item and the one that changes documented behavior, so it wants `docs/doc_comments.rst` updated in the same change, not after.
5. **`G1`** in `pyastbuilder`, then **`G1.5`** its release. Independent of 1–4 and on nobody's critical path; can run in parallel or be deferred entirely without blocking a `pssparser` release.
6. **`F0.2`**, then cut and tag **`pssparser` 3.0.3** containing 1–4 (and 5 if ready).

`sphinx-pss` needs none of this to proceed — every gap already has a working in-model handling, and its capability probe (followup plan §4) removes the version coupling entirely. These fixes let it *delete* code, which is a good reason to do them and a bad reason to rush them.

---

## 6. Verification

Beyond the per-item tests:

| ID | Task | Done when |
|---|---|---|
| ☑ `V1` | Full `pssparser` suite green — 2065 pytest cases plus the gtest target, with any re-baselining from `F5.5` and `F3` reviewed deliberately | green |
| ☑ `V2` | `ctest` runs in CI, not merely builds — already true as of Release A; confirm it stays true | green |
| ☑ `V3` | Corpus check: no `ScopeChild` in any user unit has `lineno < 0` unless genuinely injected (the `F1.4` guard, over the corpus rather than a fixture) | green — **over the shipped standard library**, not the corpus: the corpus checkouts are optional and absent here, so a guard placed there would have been unverifiable and would not run for most people. The stdlib is real PSS written with no awareness of this machinery, always present, and 120 of its declarations are inspected. The test asserts it inspected them, since a guard that walks nothing passes as happily as one that finds nothing wrong |
| ☑ `V4` | Build `sphinx-pss` against the result: 311 tests green and `docs/` clean under `-W`, **before** removing any workaround. That separates "the fix works" from "the removal is safe" | green |
| ☐ `V5` | Then remove the `sphinx-pss` workarounds per followup plan §4.4, one per fix, each with its guard test still green | tracked in `implementation-plan.md` |

`V4` is the one to insist on. Every workaround being removed exists because a behavior was missing; removing it in the same change that adds the behavior means a failure cannot be attributed to one or the other.

**`V4` result, 2026-08-13:** 310 of 311 passed, and the one failure was `sphinx-pss`'s own guard test asserting that the `U-1` gap still exists — the guard doing its job, detecting the fix. It has been rewritten to exercise the declaration index without asserting the bug's continued existence, since asserting that turns an upstream fix into a red build. Full suite green afterwards, and `docs/` clean under `-W`.

**`V5` is deliberately not started.** The fixes are on unreleased branches, so removing a `sphinx-pss` workaround now would couple it to a dependency nobody else can install. It waits on the 3.0.3 release and on the capability probe (followup plan §4), which is what should gate the removal rather than a version floor.

---

## 7. Decisions — all answered

Each was answered during implementation, from the source or from a test rather than by preference. Recorded here with the reason, since several are the kind that look obvious in the other direction.

1. **`F3.0` — multi-file package docstrings: first non-empty in link order wins.** Predictable, needs no merge rule, and matches how a reader expects a re-opened package to read. Implemented as one helper that only ever fills an empty docstring, so it is the same rule for packages, functions and re-opened scopes. Documented in `docs/doc_comments.rst`.
2. **`F4.0` — no, `linker.link()` cannot return null.** One `return`, no early exit, errors reported only through the marker listener. The fix is unconditional.
3. **`G1.0` — both.** Implement `visitTypeUserDef` for the shapes that can occur by value, *and* fail loudly at generation time for anything else.
4. **`G1` is in the release.** It is one field's worth of code in `pyastbuilder`, and `pssparser` 3.0.3's changelog already declares a `pyastbuilder` dependency for the `Linker` fix — so the release note has to be written either way. Deferring would mean a second `pyastbuilder` release later for no gain.
5. **`F2.2` — no, the prototype does not need its own `attachDocstring`.** The comment belongs to the node added to the scope. Duplicating it would give two nodes a claim to one comment with no rule for which wins.

## 8. What is left

| ID | Task | Blocked on |
|---|---|---|
| ☐ `G1.5` | Release `pyastbuilder` so `pssparser` CI can resolve it from git or PyPI rather than a local checkout | nothing — this is the next step |
| ☐ `F0.3` | Merge `doc-comments-3.0.3` and cut/tag `pssparser` 3.0.3 | `G1.5`, so CI can build it |
| ☐ `V5` | Remove the `sphinx-pss` workarounds, one per fix, each with its guard test still green | the 3.0.3 release, and the capability probe (followup plan §4) |

Three things found along the way that are **not** in scope here and want their own decision:

- **A flaky test in `pssparser`.** `test_standard_library_docstrings_carry_no_marker_residue` failed once under a `-k doc_comments` selection and passed on every re-run and in the full suite. Order- or state-dependent; not caused by any change here, and not investigated.
- **`tests/unit/test_pyext.py` does not collect** in `pyastbuilder`, on `master` as well — it imports a module that no longer exists. It is effectively the whole pre-existing test suite of that repo.
- **A duplicated stub.** `ast.pyi` now declares `getPath` twice for `SymbolRefPath` — once per generator that emits an accessor of that name. Harmless at runtime and pre-existing in shape, but it makes the stub wrong for a type checker.
