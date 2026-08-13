# sphinx-pss

Sphinx autodoc support for Accellera PSS (Portable Test and Stimulus Standard)
source.

`sphinx-pss` documents PSS the way `sphinx.ext.autodoc` documents Python:
declarations and doc comments are read directly from PSS source through
[`pssparser`](https://github.com/psstools/pssparser), and rendered through a
custom `pss` Sphinx domain.

What sets it apart from a general-purpose documentation tool is that it
understands what PSS *means*. From a project-wide index it can render the
producer/consumer relationships around each flow object, the activity graph of a
compound action, the static component instance tree, and where each member of a
type came from when that type is spread across `extend` sites.

```{toctree}
:maxdepth: 2
:caption: Using sphinx-pss

getting-started
usage/native-style
usage/directives
```

```{toctree}
:maxdepth: 2
:caption: Examples

examples/sample
```

```{toctree}
:maxdepth: 1
:caption: Design

design/index
```

## Project status

Early development. The design and the phased build plan are the most complete
documents in the set:

- {doc}`design/sphinx-pss-design` — the approach, the object model, and the
  PSS-specific capabilities that motivate the project.
- {doc}`design/implementation-plan` — phases, work items, and their status.
- {doc}`design/pssparser-enhancement-plan` — the upstream `pssparser`
  doc-comment work this project depends on.
