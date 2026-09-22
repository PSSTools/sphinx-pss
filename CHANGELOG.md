# Changelog

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
