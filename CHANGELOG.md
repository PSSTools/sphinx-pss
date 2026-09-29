# Changelog

## 0.1.0 — programming steps and activity diagrams

Procedures and scenarios, drawn from the source: step tables and flowcharts
from `/// Step:` markers, UML activity diagrams of an action's activity, and
a `pssparser` checker to migrate existing `// Step:` comments.

### Added

- **Activity diagrams** (`docs/usage/activities.md`).
  `.. pss:activity-diagram:: <action>` draws an action's activity as a UML
  activity diagram:
  - traversals are boxes linked to the traversed action's entry;
  - `parallel` is a fork and a join;
  - `schedule` has hollow bars in a frame of its own, so it is never read as a
    `parallel`;
  - `select`, `if` and `match` are decisions;
  - loops, `replicate` and `atomic` are titled frames;
  - `with` constraints are notes;
  - `bind`s are dashed object flows.

  Several `activity` blocks from `extend` are drawn as the implicit schedule
  PSS runs them as, and an action with no activity of its own shows its
  base's. `:depth:` opens compound traversals up to 4 levels, cutting
  recursion. `:weights:` labels `select` arms with their weights.
  `:format: outline` or `both` gives the activity as a nested list, which is
  also what a page shows when the diagram can't be drawn. `:activity-diagram:`
  on `autopssaction`, `autopsscomponent` and `autopsspackage` puts the diagram
  in each documented action's entry, and it can be a `pss_default_options`
  default.
- **Steps in activities.** `/// Step:` markers in an activity:
  - label regions of its diagram (`:steps: collapsed` draws one box per step);
  - give a compound action a step table, with `pss:steps` or `:steps:` and no
    `:exec:`.

  In `parallel` and `schedule` a marker covers its own branch; in `select` and
  `match` its own arm. Traversals expand into the traversed action's activity
  steps, and into an atomic action's `exec body` steps only with
  `:expand-exec:`. This needs a pssparser that attaches comments to activity
  statements (its `AC1`); with one that doesn't, the build says so once
  (`pss.step_unsupported`) and draws no steps.
- **Step tables.** `.. pss:steps:: <function>`, or `<type>` with
  `:exec: <kind>`, renders a body's programming steps as a table with the
  columns #, Step, Details and Source (`docs/usage/steps.md`). Steps in a
  nested block are sub-steps. An `if`, `match` or loop that holds steps is a
  row with its condition as written. A call to a function with steps brings
  its steps in as sub-steps (`:expand-calls: inline`, the default), or links
  to it (`link`); `:depth:` limits how far, and recursion is cut with a
  reference back. `exec` blocks added by `extend` follow the declaration's,
  in file order. Numbering is generated: `:numbering: decimal` (1, 1.1) or
  `outline` (1, a), i.). The `autopssfunction`, `autopssaction` and
  `autopsscomponent` directives take `:steps:` with the same options; it is
  rejected in `pss_default_options`. Step titles and details are
  reStructuredText, and a markup error in one is reported at its `.pss` line.
- **Step flowcharts.** `:format: flowchart` draws a body's steps as a
  flowchart, and `:format: both` shows the table and then the flowchart. Steps
  are boxes, conditions diamonds labelled as written, loops draw a back-edge,
  a called function's steps are a frame named after it, and a linked call is
  one box that links to the callee's entry. Each shape shows its source line
  on hover.
- **`SPSS001` migration checker.** Installing `sphinx-pss` registers a
  `pssparser` extension with the checker `sphinx-pss-steps`. Enabled with
  `enabled = true` under `[checker.sphinx-pss-steps]` in `.pssparser.toml`, it
  reports each plain `//` or `/* */` comment line that would be a step marker
  as a `///` or `/** */` comment. It is off by default, so a `pssparser` run is
  unchanged until a project turns it on.
- **Diagram back-end** (`docs/usage/diagrams.md`). `pss_diagrams` now does
  something: `graphviz` (the default, through `sphinx.ext.graphviz`, which
  `sphinx-pss` now loads), `mermaid` (through `sphinxcontrib-mermaid`, which
  the project adds to its extensions) or `off`. A missing `dot`, or Mermaid
  without its extension, is one `pss.diagrams` warning per build, not a failed
  build; a flowchart that can't be drawn is shown as its table. Diagram text
  is the same on every build.
- **`pss.step_prelude_call`**: in a body a step table shows, a call outside
  every step is reported at its line, once per build, since the table leaves
  it out. Declarations and conditions are exempt.
- **Programming-step markers are read and checked.** A `/// Step: <title>` or
  `/** Step: … */` comment inside a function body or `exec` block marks a step
  of a programming procedure (`docs/usage/steps.md`). Every
  build lints markers across the whole model and reports, at the comment's
  line in the `.pss` file, a near miss such as `/// step: reset`
  (`pss.step_syntax`), a marker outside any body (`pss.step_misplaced`), and a
  marker with no title or no statements (`pss.step_empty`). Plain `//` and
  `/* */` comments are never read, so existing code produces no warnings: the
  whole `pss-corpus` produces none.

### Changed

- **Requires `pssparser` 3.1.0 or later** (was 3.0.3), a parser targeting PSS
  3.1. A floor, not a pin. The run-time capability probe is unchanged and still
  decides whether a parser is usable; the suite was run against every published
  3.1 release (3.1.0–3.1.7) and passes on each.

- **The `pssparser` gate is a capability probe, not a version floor.** The
  first parse of a build parses a few lines of PSS in memory and fails hard
  unless a doc comment on an attributed field (`rand int f;`) arrives attached
  and normalized. `pssparser` source trees now report version `0.0.0` (only a
  release tag carries a number), so the old `>= 3.0.3` floor rejected every
  working-tree build. The check also moved from import time to first parse.
  `sphinx_pss._version_floor` is now `sphinx_pss._capability`.

- **The `pssparser` workarounds are retired** (design
  `pssparser-followup-plan.md` §4.4), now that `U-1` through `U-6` are fixed
  upstream. Doc comments are read from the linked symbol for every kind; the
  `(fileid, lineno)` declaration index that recovered package and enum docs is
  gone, as is the second parse that recovered a model after a failed link.
  Each fix the model now depends on is pinned by an `upstream` guard test.
- **Type references use the linker's resolution** where it is a plain path to
  a documented object (`U-3`). A name visible only through an `import`, or
  through a package alias, and declared in more than one package used to render
  unlinked; it now links to the declaration the linker chose. Written names are
  still resolved by scope when there is no such path.
- **The model is parsed with `collect_comments`**, the groundwork for
  programming steps (`design/programming-steps-design.md`). No visible change:
  the object model is identical with and without it, over the test fixtures
  and every parseable `pss-corpus` file, and a test keeps it so. Parse + link
  over the corpus is about 2% slower.
- **`pss-corpus` is a development dependency** (`default-dev` in `ivpm.yaml`),
  read by the opt-in `corpus` tests from `packages/pss-corpus`, `$PSS_CORPUS`
  or a sibling checkout. Selecting those tests without a corpus fails rather
  than skips. Only the test extra gains a dependency (`tomli`, on Python 3.10).

### Fixed

- **Warnings about a doc comment now point at the comment.** A reStructuredText
  error inside a doc comment was reported against the page that rendered it
  (`index.rst:91`, in a six-line file), and a doc-field cross-validation
  warning against the declaration's line plus an offset, which missed the
  comment above it. Both now report the line in the `.pss` file. Each object
  carries a `doc_source` mapping its normalized doc-comment lines back to
  source, built from the parser's `getDocLocation()` / `getDocRaw()`.
- **`import` and prototype-only functions lost their signature**:
  `import target function void poke(bit[32] addr)` rendered as `void poke()`,
  with no parameters and no return type. Degraded builds
  (`pss_tolerate_link_errors`) dropped such functions altogether.
- **An in-line `covergroup` was documented as `package <covergroup>`.**
  Anonymous scopes are skipped; covergroups are not documented yet.
- **Annotation parameters were keyed by an object repr**
  (`<pssparser.ast.ExprId object at …>`) rather than by their name.
- **Function parameters were indexed under their bare name**, so two functions
  sharing a parameter name (`f(int i0)`, `g(int i0)`) produced duplicate object
  descriptions and a duplicate-ID error under `-W`. Parameters are now
  qualified by their function (`p::f::i0`). Found by rendering the
  `pss-corpus` examples.

## 0.0.1 — first release

The first working vertical slice: a `.pss` source tree in, a documented Sphinx
project out.

### Added

- **The `pss` domain.** 17 object directives and 15 roles covering packages,
  components, actions, flow objects (buffer, stream, state, resource), structs,
  enums, functions, constraints and pools, with qualified-name cross-references,
  index entries and permalinks.
- **`autopss*` directives.** 11 of them, mirroring `sphinx.ext.autodoc`:
  `autopsspackage`, `autopsscomponent`, `autopssaction` and so on. Each takes a
  qualified PSS name and documents it from source, with `:members:`,
  `:no-members:` and per-object option control.
- **Doc-comment parsing** in a `native` dialect, with a 13-field vocabulary
  (`param`, `input`, `output`, `lock`, `share`, …) cross-validated **against the
  AST in both directions** — a documented field that does not exist and an
  undocumented field that does are both reported.
- **Configuration**, eight `pss_*` values covering source discovery, the doc
  dialect, default options and link-error tolerance.
- **PSS syntax highlighting**, through a dependency on
  [`pygments-pss`](https://git.dvkit.org/psstools/pygments-pss.git). It
  registers the `pss` lexer via a `pygments.lexers` entry point, so no
  configuration is needed and highlighting also works outside Sphinx —
  `pygmentize`, MkDocs and plain docutils included.

### License — BSD-3-Clause to Apache-2.0 (2026-09-22)

The `LICENSE` file was BSD-3-Clause while `pyproject.toml` already declared
`license = "Apache-2.0"`. **Apache-2.0 is the intended and now the actual
license**, matching every other active project in the organization.

This is a metadata reconciliation rather than a relicensing event, and it is
recorded here so the history stays legible rather than looking like a silent
license change later:

- The package has **never been published**, so no released artifact carries the
  mismatch and nothing downstream was ever obtained under BSD-3-Clause.
- All three commits to date are by the sole copyright holder, so no contributor
  consent was required.
- The old notice read `Copyright (c) 2021, PSSTools`, asserting rights on behalf
  of an entity that does not exist — psstools is a GitHub organization, not a
  legal person. Attribution now reads `Copyright 2021 Matthew Ballance and
  Contributors`, the shared-copyright form used across the organization, and
  lives in the new `NOTICE` file as Apache-2.0 §4(d) intends.

Also added Apache-2.0 headers to `src/sphinx_pss/**.py`, which previously had
docstrings but no license header.

- `pssparser` 3.0.3 or later. The floor is hard: the extension checks it at
  import and fails with an explicit message rather than producing documentation
  with most of the prose silently missing. 3.0.3 is the release carrying the
  doc-comment rework — without it, doc comments are missing on attributed
  fields such as `rand int len`, unrelated comment blocks merge, and block
  comments arrive with `*` markers and source indentation intact.

  Note that the check is a version comparison standing in for a capability
  test, which is the wrong question to ask: `pssparser` numbers releases after
  the PSS LRM revision it targets, so the number says nothing about whether
  doc-comment extraction works. Replacing it with a capability probe is
  tracked in `design/pssparser-followup-plan.md`.

- `pygments-pss` 0.1.0 or later, and Sphinx 8.

### Known limitations

- **Not on PyPI**, and cannot be until `pygments-pss` is: a declared dependency
  that PyPI cannot resolve makes `pip install sphinx-pss` fail. Install from
  git, or through `ivpm`.
- Flow-object relationship tables, activity graphs, component instance trees
  and the whole-tree front end are designed but not implemented; see
  `design/implementation-plan.md`.
- `parallel_read_safe` is `False`. The model is parsed once per build and held
  in a process-wide index, which a parallel read would not share.
