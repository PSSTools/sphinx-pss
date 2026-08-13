# Directives, roles and configuration

This is the reference for what ships in Phase 1. Flow tables, diagrams,
activities and the whole-tree front end land in later phases and are described
in {doc}`../design/implementation-plan`.

## Autodoc directives

Each takes one qualified PSS name and documents it from source.

```rst
.. autopssaction:: dma_pkg::Dma::Xfer
   :members:
```

| Directive | Documents |
|---|---|
| `autopsspackage` | a package |
| `autopsscomponent` | a component |
| `autopssaction` | an action |
| `autopssstruct` | a plain struct |
| `autopssbuffer` | a buffer |
| `autopssstream` | a stream |
| `autopssstate` | a state |
| `autopssresource` | a resource |
| `autopssenum` | an enum |
| `autopssfunction` | a function |
| `autopssobject` | any of the above, when spelling the kind adds nothing |

A directive that names an object of the wrong kind reports an error rather than
documenting it, so `autopssbuffer` cannot quietly document an action.

A name that does not resolve reports what it might have meant:

```text
ERROR: sphinx-pss: no PSS object named 'dma_pkg::Dma::Xfr' of kind action;
       did you mean dma_pkg::Dma::Xfer?
```

### Options

| Option | Effect |
|---|---|
| `:members:` | Document the element's members |
| `:no-members:` | Turn off a project-wide `members` default for this directive |
| `:undoc-members:` | Include members with no documentation, and report the ones that should have some |
| `:exclude-members:` | Comma- or space-separated names to leave out |
| `:member-order:` | `source` (default), `alpha`, or `groups` |
| `:inherited-members:` | Include members from base types *(Phase 2)* |
| `:recursive:` | Descend into nested types |
| `:show-extensions:` | Label members contributed by an `extend` |
| `:no-index:` | Do not add an index entry or a cross-reference target |
| `:doc-style:` | Override `pss_doc_style` for this directive |

`:member-order: source` is the default because for PSS the declaration order
carries meaning — an action's flow signature reads in the order it was written.

Directive body content is appended after the generated documentation, which is
how you add commentary that does not belong in the source:

```rst
.. autopssaction:: dma_pkg::Dma::Xfer
   :members:

   .. note::

      Superseded by ``XferV2`` in this integration.
```

## Domain directives

Autodoc emits these, and they are equally available by hand — for documenting a
model whose sources you do not have, or for overriding what autodoc produced.
The generated and hand-written paths are the same path.

```rst
.. pss:component:: Dma

   The DMA controller.

   .. pss:action:: Xfer

      Program a single DMA transfer.

      .. pss:flow_ref:: output DmaBuf out_b

         The filled destination buffer.
```

Available: `pss:package`, `pss:component`, `pss:action`, `pss:monitor`,
`pss:struct`, `pss:buffer`, `pss:stream`, `pss:state`, `pss:resource`,
`pss:enum`, `pss:enum_item`, `pss:field`, `pss:flow_ref`,
`pss:resource_claim`, `pss:constraint`, `pss:function`, `pss:pool`.

Nesting a directive inside another qualifies its name automatically, so `Xfer`
above becomes `Dma::Xfer`. The argument is written as it appears in PSS source —
`rand int len`, `output DmaBuf out_b`, `int align_up(int n)` — and is rendered
as such, with type names linked.

Options: `:no-index-entry:`, `:module:` (the enclosing scope), `:qualname:` (the
target name, when it differs from what the signature shows), `:type:`,
`:qualifiers:`, `:extends:`.

## Roles

| Role | Resolves to |
|---|---|
| `:pss:pkg:` | a package |
| `:pss:comp:` | a component |
| `:pss:action:` | an action |
| `:pss:monitor:` | a monitor |
| `:pss:struct:` `:pss:buffer:` `:pss:stream:` `:pss:state:` `:pss:resource:` | the corresponding type |
| `:pss:enum:` | an enum |
| `:pss:func:` | a function |
| `:pss:field:` | a field, flow reference, resource claim or enum value |
| `:pss:constraint:` | a named constraint |
| `:pss:type:` | any type |
| `:pss:obj:` | anything |

A target may be fully qualified (`dma_pkg::Dma::Xfer`) or bare (`Xfer`) when
unambiguous. Resolution is lexical, so a bare name inside a documented scope
finds that scope's member first. A leading `~` shortens the displayed title to
the last component while keeping the link.

An unresolved reference warns; an ambiguous one warns *and lists the
candidates*, because the useful thing to say about a name that plainly exists is
which one was meant.

## Configuration

| Value | Default | Meaning |
|---|---|---|
| `pss_source_dirs` | `[]` | Directories searched recursively for `.pss` files. Relative paths resolve against `conf.py`'s directory |
| `pss_source_files` | `[]` | Explicit files, in order. Use when the build unit's order matters |
| `pss_doc_style` | `"native"` | Doc-comment dialect: `native`, `doxygen` *(Phase 4)*, or `auto` |
| `pss_document_stdlib` | `False` | Publish the PSS standard library as well. It is always parsed and indexed so references into it resolve; this decides whether it is *documented* |
| `pss_tolerate_link_errors` | `False` | Continue after a link failure with declarations and doc comments only |
| `pss_diagrams` | `"graphviz"` | Diagram backend *(Phase 2)*: `graphviz`, `mermaid`, or `off` |
| `pss_viewcode` | `True` | Generate `[source]` links *(Phase 3)* |
| `pss_default_options` | `{}` | Options applied to every `autopss*` directive |

```python
pss_default_options = {"members": True, "member-order": "source"}
```

An invalid value fails the build immediately with a message naming what was
accepted, rather than surfacing later as an empty page.

## Events

| Event | Signature | Use |
|---|---|---|
| `pss-autodoc-process-doc` | `(app, kind, qualname, options, doc)` | Rewrite documentation before it renders. Mutate `doc` in place |
| `pss-autodoc-skip-member` | `(app, kind, qualname, skip, options)` | Return `True` to skip a member, `False` to force it in, `None` to leave the decision alone |

```python
def skip_internal(app, kind, qualname, skip, options):
    return True if qualname.rsplit("::", 1)[-1].startswith("_") else None

def setup(app):
    app.connect("pss-autodoc-skip-member", skip_internal)
```

## PSS syntax highlighting

The extension registers a Pygments lexer for PSS, so ` ```pss ` code blocks
highlight in any project that loads it — including projects that use no other
part of the extension.

````markdown
```pss
action Xfer {
    output DmaBuf out_b;
}
```
````
