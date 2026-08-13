# `pssparser` follow-up — Phase-1 integration gaps, dependency pinning, and the PSS lexer

**Status:** Draft for review — no work started
**Date:** 2026-08-13
**Target repos:** `psstools/pssparser`, `mballance-utils/pyastbuilder`, and this one
**Follows:** `design/pssparser-enhancement-plan.md` (Releases A–C, the doc-comment rework)
**Consumers:** `design/implementation-plan.md` §2.1 (findings `U-1`…`U-6`)
**Execution:** `design/pssparser-fixes-plan.md` — the trackable work plan for §3's defects. This document is the *why*; that one is the *what to do*.

---

## 1. Why this exists

Building `sphinx-pss` Phase 1 against the reworked parser surfaced three separate things, and they need separate decisions:

1. **Six integration gaps** (`U-1`…`U-6`). None blocked Phase 1 — each has a contained in-model handling — but in every case the parser *has* the information and the Python view does not, so every workaround is code `sphinx-pss` should not be carrying. §3.
2. **The version floor does not work.** `sphinx-pss` asserts `pssparser >= 3.1.0` at import, per the enhancement plan's §8 resolution. As of this writing that assertion **rejects a parser that has every feature it needs**, because the version stamp and the code moved independently. §2 records the evidence and §4 proposes a different gate.
3. **PSS has no Pygments lexer**, so `sphinx-pss` ships one. That was expedient rather than decided; §5 decides it.

The through-line: the enhancement plan resolved several questions on the assumption that its work would be *released*. It has not been, and the assumption is load-bearing in more places than it looks.

---

## 2. The release-state problem

### 2.1 The versioning convention

`pssparser` versions as **`<PSS major>.<PSS minor>.<patch>`**: the first two components name the PSS LRM revision the parser targets, and the patch increments with each change. So `3.0.3` is "targets PSS 3.0, third patch", and `3.1.0` would mean "targets **PSS 3.1**" — a claim about language coverage, not about any particular feature.

This is decisive for §4, and it is worth stating plainly before the evidence:

> **Under this convention a `pssparser` version number carries no information about capability.** The major and minor encode the LRM target; the patch is a monotonic counter. Neither answers "does this parser extract doc comments?".

A floor of `>= 3.1.0` would therefore not have meant "has the doc-comment rework" even if it had been released — it would have meant "supports PSS 3.1", which `sphinx-pss` does not require and which would exclude every conforming 3.0 parser. The floor was mis-specified from the start, independently of anything that happened to the working tree.

### 2.2 What is actually on disk

Observed in `packages/pssparser`, the editable-installed working clone, on 2026-08-13:

| | |
|---|---|
| Doc-comment rework (Releases A–C) | **Present and working.** `src/DocCommentExtractor.{h,cpp}`, `src/DocAnchorScope.{h,cpp}`, `docs/doc_comments.rst`, `CHANGELOG.md` |
| Its commit state | **Entirely uncommitted** — 10 untracked files, 23 modified |
| `CHANGELOG.md` | Heads its entry **3.1.0** — wrong under §2.1, and to be renumbered |
| `python/pssparser/__version__.py` | **3.0.3** (working-tree edit over committed `3.0.2`) — correct under §2.1 |
| Docstring collection through `Parser` | Verified working, dedented and marker-free |
| `import sphinx_pss` | **Raises `PssParserTooOldError`** |

So a parser that does everything `sphinx-pss` asks of it is rejected by `sphinx-pss`'s own gate, because that gate compares a number that was never about the thing it is gating.

### 2.3 What this proves

Two independent problems, and the version convention is the deeper one:

1. **The floor asks the wrong question.** Per §2.1, `>= 3.1.0` is a claim about LRM coverage. No amount of releasing fixes this — the number will never carry capability information.
2. **For an unreleased dependency built from a working tree, the stamp is not evidence about the code anyway.** It can move without the code and vice versa; here `CHANGELOG.md` and `__version__.py` currently disagree, and the code matches neither claim in any checkable way.

Neither is a criticism of `pssparser`'s convention, which is a perfectly reasonable thing to want — knowing at a glance which LRM a parser targets is more useful day to day than knowing which internal rework it contains. It does mean the consumer needs a different mechanism.

### 2.4 Re-reading the original resolution

Enhancement plan §8 says:

> **Version floor — hard requirement.** `sphinx-pss` requires the Release-A `pssparser` outright rather than degrading. Partially-working doc extraction is worse than a clear failure.

The rationale is about **degrading**, not about **detecting**. It rules out "probe, and quietly do something worse if the feature is missing". It says nothing against detecting the capability accurately and then failing just as hard.

That distinction is the whole of §4's proposal, and it means the resolution's *intent* is preserved rather than reversed. What the resolution got wrong was assuming a version number could express the requirement — an assumption §2.1 shows was never available.

---

## 3. Defect catalogue

Numbering continues `implementation-plan.md` §2.1. Every entry was reproduced against the working clone, and the proposed fix names a file and line.

### 3.1 `U-1` — a package's and an enum's doc comment are unreachable from the linked tree

**Symptom.** `SymbolScope` (package) and `SymbolEnumScope` both report `getDocstring() == ""` and `getTarget() == None`, so neither a package's nor an enum's documentation can be read from the linked tree. The text *is* collected — the `PackageScope` / `EnumDecl` reached through `Parser.user_units()` has it.

**Root cause.** `target` is declared on `SymbolChildrenScope` (`ast/linking.yaml:63`), so both classes have the field. The linker simply never sets it for these two:

- `TaskBuildSymbolTree::visitEnumDecl` (`src/TaskBuildSymbolTree.cpp:229`) calls `setLocation` and `setSynthetic` but not `setTarget` — unlike the type-scope path at `:912`, which does.
- `TaskBuildSymbolTree::visitPackageScope` (`:186`) never sets it either, and here a single `target` is genuinely the wrong shape: one package has one `PackageScope` **per file**, and `package a::b { }` creates an intermediate scope `a` with no declaration at all.

**Proposed fix — and it subsumes a known trap.** Rather than making every consumer remember which kinds need `getTarget()` and which do not, **copy the declaration's docstring onto the symbol at link time**:

- `visitEnumDecl`: add `ts->setTarget(i)` and `ts->setDocstring(i->getDocstring())`.
- `visitPackageScope`: on the branch that creates the scope, `pkg->setDocstring(i->getDocstring())`; on the branch that finds an existing one, adopt the incoming docstring only if the existing one is empty (first non-empty in link order wins). An intermediate scope gets none, which is correct.
- `visitStruct`-family (`:912`): already sets `target`; add the docstring copy for consistency.

The payoff is that **`getDocstring()` becomes uniformly correct on the linked tree**, which also retires the trap recorded in enhancement plan §10.3 ("`SymbolTypeScope` hides the docstring; consumers must go through `getTarget()`"). Cost is one duplicated string per declared type.

*Design question for the maintainer:* a package declared across several files with a doc comment in more than one. "First non-empty wins" is proposed because it is predictable and needs no merge rule; concatenation and last-wins are both defensible. Worth deciding explicitly rather than falling out of traversal order.

### 3.2 `U-2` — `EnumItem` carries no source location

**Symptom.** Every `EnumItem` reports `lineno == -1`. The documented filter rule for compiler-injected members is `lineno < 0`, so applying it uniformly discards every enum value in the model.

**Root cause.** `AstBuilderInt.cpp:2716` builds the item and calls `attachDocstring(item, (*it)->start)` — the token is in hand — but never `setLoc`. Same at `:309` for the `extend enum` path.

**Proposed fix.** `setLoc(item, (*it)->start);` at both sites. One line each.

**Why it matters beyond the filter.** Without a location an enum value cannot get a `[source]` link (Phase 3), cannot be reported against a file and line by the doc-field cross-validation, and cannot have its provenance determined when contributed by an `extend`.

### 3.3 `U-3` — `SymbolRefPath` generates a broken Python accessor

**Symptom.** A `TypeIdentifier`'s resolved target is a `SymbolRefPath`, and reading its path raises:

```
AttributeError: 'pssparser.ast.SymbolRefPath' object has no attribute 'numPath'
```

**Root cause — a generator bug, not a parser one.** The generated `ast.pyx` emits the property:

```python
return ListUtil(self.numPath, self.getPath)
```

but generates **neither** `numPath` nor `getPath`. `SymbolRefPath.path` is `list<SymbolRefPathElem>` (`ast/linking.yaml:360`) — a list of *by-value* structs, unlike the `list<UP<T>>` / `list<P<T>>` forms used everywhere else. `pyastbuilder`'s accessor generator emits the property for that shape but not its two helpers.

**Proposed fix.** In `pyastbuilder`'s `pyext_accessor_gen`, generate `num<Field>` / `get<Field>` for value-typed list fields as it does for pointer-typed ones. **This needs a sweep**: any `list<value-struct>` field in any schema is broken identically and silently — the property exists, so the field looks bound until it is called.

**Impact if unfixed.** A type reference cannot be resolved to its declaration from Python, so `sphinx-pss` resolves type names *by name* through its own index. That is the design's stated model (`PssObject.type_ref`), so the workaround is not costly — but it is name-based where the parser already has the resolved answer, which will matter for shadowed names and for template specializations.

### 3.4 `U-4` — `FunctionPrototype` carries neither location nor docstring

**Symptom.** `getLocation().lineno == -1` and `getDocstring() == ""` on every prototype, so a prototype is indistinguishable from a compiler-injected node.

**Root cause.** `AstBuilderInt::mkFunctionPrototype` (`src/AstBuilderInt.cpp:5170`) constructs the node and never calls `setLoc`. `FunctionDefinition` gets both, which is why functions are readable at all today.

**Proposed fix.** `setLoc(proto, ctx->start);` in `mkFunctionPrototype`.

**Why it matters.** A prototype-only function — an `import` / `export` function, i.e. exactly the target-integration surface Phase 4 documents — has *no* definition to fall back on. Those functions are currently unlocatable and undocumentable.

### 3.5 `U-5` — a failed `link()` leaves nothing walkable

**Symptom.** After a link error, `Parser.user_units()` returns `[]` and `Parser.file_map` is `{}`. The per-file scopes that a degraded mode is supposed to fall back on cannot be reached through the public API at all.

**Root cause.** `Parser.link()` (`python/pssparser/parser.py`) raises **before** it snapshots:

```python
ret = linker.link(marker_l, self._files)
self._markers.extend(self._collectMarkers(marker_l))
if marker_l.hasSeverity(zspp.MarkerSeverityE.Error):
    raise ParseException(err, self._markers)     # <-- raises here
self._file_map = dict(self._filenames)            # <-- never reached
self._root = ret
```

Ownership of the units has already moved to `ret` by then, so the units exist and are reachable — the parser just never records where they went.

**Proposed fix.** Move the snapshot block above the severity check, keeping the raise last:

```python
ret = linker.link(marker_l, self._files)
self._markers.extend(self._collectMarkers(marker_l))

# Record the result before reporting failure. Ownership of the units moved to
# `ret` inside link(), so a caller that catches the exception must still be
# able to reach them -- otherwise a partially-linked model is unreachable.
self._file_map = dict(self._filenames)
self._root = ret
self._filenames.clear()
self._files.clear()
self._builder = None

if marker_l.hasSeverity(zspp.MarkerSeverityE.Error):
    raise ParseException(err, self._markers)
return ret
```

*Needs confirming:* that `linker.link()` returns a usable root on the error path rather than null. If it can return null, the snapshot must be conditional and the fix is the same shape.

**Current cost.** `sphinx-pss` recovers by re-parsing into a second `Parser` that is never linked, then reading its `_files` / `_filenames`. That is the **one private-attribute access in the codebase**, and it exists only because of this. It is safe — that parser never links, so ownership never transfers — but it should not be necessary, and it doubles parse time on the degraded path.

### 3.6 `U-6` — a line-comment run dedents to zero if any line lacks a space after `//`

**Symptom.**

```pss
//@doc(text = "x")
// Real prose.
struct S { }
```

yields `'@doc(text = "x")\n Real prose.'` — note the leading space on the second line. A one-space indent is a block quote in reStructuredText, so this is a rendering bug, not a cosmetic one. Realistic triggers: `//@…`, `//---` rules, ASCII diagrams, and any line where the author omitted the space.

**Root cause.** `stripLineMarker` (`src/DocCommentExtractor.cpp:150`) removes the marker and an optional Doxygen `<`, but **not** the conventional single space after it. The block form's `stripContinuationStar` (`:193`) *does* strip "an optional single space" after `*`. Normalization then relies on the dedent to remove the space, which works only while every line has one — a single line without it drops the common prefix to zero and every other line keeps its space.

**Proposed fix.** In `stripLineMarker`, after removing the marker and the optional `<`, strip one optional leading space — exactly what the block path already does. Relative indentation is unaffected: `//     indented` becomes `    indented` and the dedent still sees a 4-space difference against `// text`.

This also makes the two forms consistent, which enhancement plan §3.3 states as the design goal.

### 3.7 Summary

| Finding | Fix | Repo | Item in the fixes plan |
|---|---|---|---|
| `U-1` | Set `target` + copy docstring onto package/enum/type symbol scopes | `pssparser` | `F3` |
| `U-2` | `setLoc` on `EnumItem`, two sites | `pssparser` | `F1` |
| `U-3` | Generate helpers for value-typed list fields | `pyastbuilder` | `G1` |
| `U-4` | `setLoc` on `FunctionPrototype` | `pssparser` | `F2` |
| `U-5` | Snapshot `_root`/`_file_map` before raising in `link()` | `pssparser` | `F4` |
| `U-6` | Strip one optional space in `stripLineMarker` | `pssparser` | `F5` |

Five of six are one-to-a-few lines. `U-3` is the only one in a third repo, and the audit it seemed to need turned out to be bounded: `SymbolRefPath.path` is the **only** value-typed list field in `pssparser`'s whole schema (fixes plan `G1`).

**Tests.** Each needs a regression test in `pssparser` (or `pyastbuilder`), because every one of these is a *silent* failure — nothing crashes, output is merely missing or subtly wrong. `sphinx-pss` keeps its own guards in `tests/test_upstream_guards.py`, which assert the behaviors it depends on rather than the implementations.

---

## 4. How `sphinx-pss` should pin to `pssparser`

### 4.1 The requirement

The gate must:

- **fail hard** when doc extraction will not work — the enhancement plan §8 intent, unchanged;
- **express a capability**, which a `<PSS major>.<PSS minor>.<patch>` version cannot (§2.1);
- **be accurate** against a locally-built, unreleased dependency, which the version stamp is not (§2.3);
- **stay accurate** permanently, including across future PSS revisions — a parser retargeted to PSS 3.1 must not have to be re-permitted by hand;
- cost approximately nothing.

The second and fourth points are what make this a permanent design choice rather than a stopgap for the unreleased state.

### 4.2 Proposal — assert the capability, keep the version for the message

**Gate on a capability probe, not on the version string.** At first index build (not at import), parse a few lines of PSS from memory and assert that the doc comment arrives attached and normalized:

```python
_PROBE = """
package _sphinx_pss_probe {
    struct S {
        /** Summary.
         *
         * Body.
         */
        rand int f;
    }
}
"""
```

The probe asserts three things at once, and they are exactly the three the extension cannot work without:

1. `Parser(collect_docstrings=True)` produces a docstring at all (`E1`);
2. the docstring reaches an **attributed** field — `rand int f` — which is the anchor fix (`E2`);
3. the text is **normalized** — no `*` residue, no source indentation — which is what makes it usable as reStructuredText (`E2.2`).

A parser that passes cannot be one that predates the rework, and no version string is consulted to decide.

On failure, raise the same hard error as today, and **use the version to make the message actionable** rather than to make the decision:

```
sphinx-pss cannot use the installed pssparser: doc comments on attributed
fields ('rand int f;') come back empty.

  installed: pssparser 3.0.2 (/path/to/packages/pssparser)

This needs the doc-comment rework described in pssparser's CHANGELOG. If you
are building pssparser from a working tree, check that it has been rebuilt
since those changes landed.
```

That message is useful in the case that actually happened this week. `requires pssparser >= 3.1.0` was not — and, per §2.1, was additionally asking for PSS 3.1 support, which this project does not need.

**Cost.** One in-memory parse per process, on the path that is about to parse the whole project anyway. The standard library dominates it. Cached on the module, so repeated builds in one process pay once.

**Keep a version in `pyproject.toml`,** set to whichever patch release carries the rework (`>= 3.0.3` on current numbering). A dependency needs *some* constraint for a resolver to work with, and that is the right place for a version to appear. But it is **advice to the installer, not the gate** — the probe decides at run time. Once the two are understood to answer different questions, them disagreeing is untidy rather than fatal, which is exactly the situation today.

Note the constraint should stay a floor rather than a `~=` or an upper bound: a parser retargeted to PSS 3.1 or 4.0 keeps the capability, and pinning against LRM revisions would exclude parsers that work fine.

**What this is not.** It is not the rejected "probe and degrade". There is no degraded path: the probe fails the build. The change is in *what is measured*, not in what happens when the measurement fails.

### 4.3 When to pin, and to what

The user's framing is right: **settle the parser work first, then pin.** Concretely:

1. Land `U-1`…`U-6` (§3) and commit the Releases A–C work, which is currently uncommitted in the working clone.
2. **Renumber `CHANGELOG.md`'s entry from `3.1.0` to the patch release it actually is** (§2.1). Left as-is it claims PSS 3.1 support the parser does not have, which is a more consequential error than a wrong version string usually is.
3. Cut **one** `pssparser` release containing all of it, and **tag** it — `3.0.3` on current numbering, or a later patch if other work lands first.
4. Release `pyastbuilder` first if `U-3` lands, since `pssparser` CI resolves it from git or PyPI rather than from the local checkout (enhancement plan §10.4 hit this already).
5. Only then set the `pyproject.toml` constraint in `sphinx-pss` to that tag — as installer advice, per §4.2, not as the gate.

Until step 5, the probe is what holds, and it holds correctly today.

### 4.4 Retiring the workarounds

Each of the six has a defined removal, and the guard tests are what make removal safe:

| Fix lands | `sphinx-pss` removes |
|---|---|
| `U-1` | `ParsedModel.declaration_at` and the `(fileid, lineno)` declaration index in `model/parse.py`; the `_doc_for` fallback chain in `model/builder.py` collapses to `getDocstring()` |
| `U-2` | The `UNLOCATED_NODE_TYPES` exemption in `model/locations.py` |
| `U-3` | Name-based type resolution *stays* — it is the design — but gains an exact path for shadowed names |
| `U-4` | The prototype/definition fallback in `_build_function_scope` |
| `U-5` | `_degraded_model`'s re-parse and its two private-attribute reads |
| `U-6` | Nothing to remove; rendering silently improves |

None of these removals is urgent. They are listed so the debt is visible and so nothing is left behind after the parser stops needing it.

---

## 5. The PSS Pygments lexer — **done**

> **Resolved (M. Ballance, 2026-08-13): the lexer becomes its own package**, owned outside `sphinx-pss`. That settles §5.4's collision concern by giving the `pss` alias a single owner, and it makes the lexer available to MkDocs, `pygmentize` and plain docutils without waiting on Pygments' release cadence.
>
> **Done 2026-08-13.** [`pygments-pss`](https://git.dvkit.org/psstools/pygments-pss.git) 0.1.0 exists. `sphinx-pss` now depends on it, `src/sphinx_pss/lexer.py` is deleted, and `setup()` makes no `add_lexer` call — the package registers `pss` through a `pygments.lexers` entry point, so the dependency *is* the wiring. `tests/test_pygments_pss.py` covers the integration; the token-stream tests moved to the new package, where they are checked against the grammar rather than hand-transcribed.
>
> **Two conclusions below were overtaken by that decision**, and are wrong as written if read on their own:
>
> - **§5.2 "it should keep shipping here even after upstreaming"** — no. Two copies of a lexer drift, and the one this project shipped would be the one nobody fixes. `test_this_package_no_longer_ships_a_lexer` asserts the deletion rather than trusting it.
> - **§5.3 "`sphinx-pss` should keep registering its own"** — no, and for a reason §5.3 had backwards. `app.add_lexer` overrides *within the Sphinx application only*, so a leftover call would shadow the packaged lexer in Sphinx while every other Pygments consumer kept using it. That is a divergence in rendered output, which is the hardest place to notice one. `test_setup_registers_no_lexer` guards it.
>
> **§5.4's collision concern stands and is resolved by ownership, not avoided.** Exactly one distribution registers `pss`, and it is the one whose only job is that entry point — which is the escape hatch §5.4 itself named.
>
> The analysis below is retained as the record of how this was reached.

### 5.1 The situation

Pygments has no PSS lexer. Without one, a ```` ```pss ```` block warns (`Pygments lexer name 'pss' is not known`) and **fails any `-W` build** — which is every project that documents PSS carefully, and this repository's own docs. Phase 3's `viewcode` needs the same lexer to render source listings.

`sphinx-pss` therefore ships `src/sphinx_pss/lexer.py`, registered with `app.add_lexer("pss", PssLexer)`. Its keyword set is extracted from `pssparser`'s `src/PSSLexer.g4`, so the two cannot drift silently.

### 5.2 Should it ship here?

**Yes, and it should keep shipping here even after upstreaming.** Reasons:

- **It is needed now.** Pygments' release cadence is measured in months, and a new lexer would then impose a `pygments >= X` floor for a language almost no Pygments user has heard of.
- **The extension is the right owner of the keyword set.** It is derived from the grammar of the parser this project already depends on, so it can be regenerated when PSS revs. An upstream lexer would lag the LRM by a Pygments release.
- **`app.add_lexer` is scoped.** It affects the Sphinx application that loads the extension and nothing else, so shipping it cannot surprise anyone.

### 5.3 Should it be upstreamed?

**Yes, as a separate, non-blocking piece of work** — PSS deserves highlighting in every tool, not only in Sphinx, and Pygments is where MkDocs, `pygmentize`, GitHub's rendering path and plain docutils would find it.

When an upstream lexer exists, `sphinx-pss` should **keep registering its own**. `app.add_lexer` overrides by name within the application, so behavior stays predictable and version-independent; sniffing which lexer to prefer would make output depend on the installed Pygments version, which is worse than a small duplication.

### 5.4 What is deliberately *not* done: a `pygments.lexers` entry point

Registering a global entry point would make the lexer available outside Sphinx without waiting for upstream. It is rejected for now because **two distributions registering the alias `pss` is a real collision**, resolved nondeterministically by installation order, and the second registrant would be a future upstream Pygments. A silent, environment-dependent change of highlighter is a worse failure than not having the lexer outside Sphinx.

If demand for non-Sphinx use appears before upstreaming lands, the clean answer is a separate `pygments-pss` distribution whose only job is that entry point — one owner for the alias.

### 5.5 Work items

| ID | Task | Repo |
|---|---|---|
| ~~`L-1`~~ | ~~Keep `sphinx_pss/lexer.py`~~ — **superseded:** deleted, and depended on instead | this |
| ☑ `L-2` | Script the keyword extraction from `PSSLexer.g4`, with a test that fails when the grammar gains a keyword the lexer does not know | **moved to `pygments-pss`**, where it landed as `scripts/gen_keywords.py` and `tests/test_vocabulary_sync.py` |
| ☐ `L-3` | Submit the lexer to Pygments | upstream — no longer urgent, since the entry point already reaches every Pygments consumer |
| ☑ `L-4` | Note in the docs that highlighting also works outside Sphinx | done — `docs/usage/directives.md` |

`L-2` was the item worth doing soon, and it is the clearest argument for the split: the keyword set here was a hand-transcribed snapshot, and the claim that it "cannot drift" was only ever true once a test enforced it. That test now lives with the lexer, next to the generator that produces the keyword set from the grammar.

---

## 6. Sequencing

Ordered by what unblocks what, not by size.

1. **Commit the Releases A–C work** in `pssparser`. Everything else is on top of it, and it is currently only a working tree — one `git clean` from gone.
2. **`U-6`, `U-2`, `U-4`** — one-line fixes, independent, no API change. Land together.
3. **`U-1`** — needs the multi-file package docstring decision (§3.1) before it can be written.
4. **`U-5`** — needs the "does `link()` return a usable root on error?" confirmation (§3.5).
5. **`U-3`** in `pyastbuilder`, plus the value-typed-list sweep, then a `pyastbuilder` release. Independent of 2–4 and on nobody's critical path — `sphinx-pss` resolves type names through its index by design.
6. **Renumber the `CHANGELOG.md` entry** off `3.1.0` (§2.1), then **cut and tag one `pssparser` release** containing 1–4 (and 5 if ready).
7. **`sphinx-pss`:** switch the gate to the capability probe (§4.2) — *this one need not wait for any of the above*, and should land first, since it is what makes the extension usable against the current clone.
8. **`sphinx-pss`:** set the `pyproject.toml` constraint to the tag from 6, and retire the workarounds in §4.4 as each fix lands.

Step 7 is the only urgent item and is entirely within this repository. **Interim:** the `pyproject.toml` and `_version_floor.py` numbers have been lowered to `3.0.3` so the extension loads against the current clone; that is a stopgap that the probe replaces, not an alternative to it.

---

## 7. Decisions needed

1. **Capability probe over version floor** (§4.2) — reverses the *mechanism* of enhancement plan §8 while preserving its intent. Needs an explicit yes, since §8 was a recorded resolution. The version convention (§2.1) makes this permanent rather than a stopgap: no `<PSS major>.<PSS minor>.<patch>` number can express "has doc comments".
2. **The `CHANGELOG.md` entry currently headed `3.1.0`** (§2.1, §6 step 6) — under the convention that announces PSS 3.1 support. Renumbering to the real patch release looks right, but it is the maintainer's call and it is the one item here that misstates something publicly.
3. **Multi-file package docstrings** (§3.1) — first non-empty in link order, concatenate, or last wins.
4. **Whether `U-3` is worth doing now.** It is the only multi-repo item and `sphinx-pss` does not need it. The generator bug affects exactly one field today, but its failure mode — a property that exists until it is called — is invisible until a consumer hits it, and it will recur for the next value-typed list added to any schema. Fixes plan `G1.0` offers a smaller answer: make the generator fail loudly instead.
5. ~~**Upstreaming the lexer**~~ — **resolved:** a separate package, owned elsewhere (§5).

*(A sixth question — what to number the combined release — is answered by the convention itself: the next patch. It is listed here only because an earlier draft treated it as open.)*
