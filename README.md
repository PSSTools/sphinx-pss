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

## Status

Early development. See `design/` for the design and the phased
implementation plan.

## Requirements

- Python 3.10+
- Sphinx 8+
- `pssparser` 3.0.3 or later (a C++/Cython extension — it must be built, not
  merely downloaded)
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
