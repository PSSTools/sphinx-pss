# Getting started

## Install

`sphinx-pss` needs [`pssparser`](https://github.com/psstools/pssparser) 3.1.0 or
later — a parser targeting PSS 3.1.

Separately, on its first parse the extension checks that the installed parser
actually extracts a doc comment from an attributed field such as `rand int len`
(the most commonly documented element in real PSS), and fails with an explicit
message rather than producing documentation with most of the prose silently
missing. That check tests the capability, not the version number, so a
`pssparser` built from a source tree (which reports `0.0.0`) works too.

`pssparser` is a C++/Cython extension, not a pure-Python wheel, so it has to be
*built* rather than merely downloaded. If a prebuilt wheel exists for your
platform, `pip` will use it:

```console
$ pip install sphinx-pss
```

Otherwise build `pssparser` first, following its own README, and then install
`sphinx-pss` against it.

Verify the install:

```console
$ python -c "from sphinx_pss._capability import check_pssparser as c; print(c())"
3.1.7
```

Syntax highlighting for `pss` code blocks comes from
[`pygments-pss`](https://git.dvkit.org/psstools/pygments-pss.git), which
installs alongside this package and needs no configuration.

## Minimal `conf.py`

```python
extensions = ["sphinx_pss"]

# Where your PSS sources live. Relative paths resolve against the directory
# containing conf.py.
pss_source_dirs = ["../model"]
```

That is the whole required configuration. Every other value has a working
default; see {doc}`usage/directives` for the full list.

Two notes about how sources are handled:

- **The whole project is parsed once, as one unit.** PSS's interesting
  relationships — `extend` merging, inheritance, flow-object typing — only
  exist across the whole model, so the extension parses and links everything on
  `builder-inited` and every directive resolves into the result. Nothing
  re-parses per directive.
- **The sources must link.** Unlike a language where a syntax-only pass still
  gives you something, a PSS model that does not link has no resolved types and
  therefore no cross references. If yours cannot link yet, set
  `pss_tolerate_link_errors = True` to document declarations and doc comments
  anyway; the build will say plainly that it is degraded.

## Your first page

Write a doc comment above a declaration:

```pss
package dma_pkg {

    // The DMA controller.
    component Dma {

        // Program a single DMA transfer.
        //
        // Claims a channel for the duration of the transfer and produces a
        // filled buffer for a downstream consumer.
        action Xfer {
            // The filled destination buffer.
            output DmaBuf out_b;

            // Transfer length in bytes.
            rand int len;
        }
    }
}
```

and point a directive at it:

```rst
.. autopssaction:: dma_pkg::Dma::Xfer
   :members:
```

The result is on {doc}`examples/sample` — that page is built by this extension
from a real source file in the repository, so it is also how the project tests
itself.

PSS qualified names use `::` throughout, exactly as in source. A directive
argument, a cross-reference target, and a name in a warning message are all the
same string.

## Referring to things

```rst
The :pss:action:`dma_pkg::Dma::Xfer` action fills a :pss:buffer:`DmaBuf`.
```

A bare name works when it is unambiguous. When it is not, the build tells you
what it could have meant rather than picking one:

```text
WARNING: ambiguous PSS reference :pss:action:`Shared`;
         qualify it as one of: p::C1::Shared, p::C2::Shared
```

{doc}`usage/directives` lists every role.

## Next

- {doc}`usage/native-style` — the doc-comment convention this project
  recommends, and the PSS-specific field vocabulary. Start here: it is what
  makes the output worth reading.
- {doc}`usage/directives` — every directive, role, and configuration value.
- {doc}`examples/sample` — the whole sample model, rendered.
