# sphinx-pss

Sphinx support for autodocumenting Accellera PSS (Portable Test and Stimulus
Standard) source.

`sphinx-pss` documents PSS the way `sphinx.ext.autodoc` documents Python:
declarations and doc comments are pulled directly from PSS source via
[`pssparser`](https://github.com/psstools/pssparser), and rendered through a
custom `pss` Sphinx domain.

Beyond declarations, it renders the structure that is specific to PSS and that
no general-purpose documentation tool can produce — flow-object producer /
consumer relationships, activity graphs, component instance trees, and `extend`
provenance.

## Programming steps

A `/// Step: <title>` comment in a function body or `exec` block marks a step
of a device-programming procedure. `pss:steps` renders the steps as a numbered
table, the way a vendor programming guide lists them. Conditions and loops
appear as rows, and a called function's steps nest under the step that calls
it. Numbers are generated, in decimal (1, 1.1) or outline (1, a), i.) style.
`:format: flowchart` draws the same steps as a flowchart, with Graphviz or
Mermaid. For a codebase that already writes `// Step: …`, an opt-in
`pssparser` checker (`SPSS001`) lists the comments to convert.

```rst
.. pss:steps:: eth_pkg::init_eth
   :numbering: outline
   :format: both
```

See `docs/usage/steps.md` and `docs/usage/diagrams.md`.

## Activity diagrams

`pss:activity-diagram` draws an action's activity as a UML activity diagram,
with forks and joins for `parallel`, decisions for `select`, `if` and `match`,
frames for loops, and each traversal linked to the action it runs.
`:activity-diagram:` on `autopssaction` puts it in the action's entry.
Programming steps marked in the activity become labelled regions of it.

```rst
.. pss:activity-diagram:: xfer_pkg::dma_c::xfer
   :depth: 2
```

See `docs/usage/activities.md`.

## Status

Early development. See `design/` for the design and the phased
implementation plan.

## Requirements

- Python 3.10+
- Sphinx 8+
- `pssparser` 3.1.0 or later, a PSS 3.1 parser (a C++/Cython extension —
  prebuilt wheels are published for common platforms; otherwise it must be
  built)
- [`pygments-pss`](https://git.dvkit.org/psstools/pygments-pss.git), installed
  automatically — it provides the `pss` Pygments lexer

## Syntax highlighting

PSS code blocks highlight with no configuration: `pygments-pss` registers the
`pss` lexer through a `pygments.lexers` entry point, so Pygments finds it
everywhere it looks. That includes `pygmentize`, MkDocs and plain docutils, not
only Sphinx — a project that wants highlighting and nothing else can depend on
`pygments-pss` alone.

## Quick start

```python
# conf.py
extensions = ["sphinx_pss"]

pss_source_dirs = ["../model"]
pss_doc_style = "native"
```

```rst
.. autopsspackage:: dma_pkg
   :members:
```

## License

Apache-2.0. See `LICENSE`.
