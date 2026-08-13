# The native doc-comment style

PSS has no entrenched documentation convention. There is no UVM-style legacy to
accommodate and no vendor format to be compatible with, which is an unusual
opportunity: the convention can be designed rather than inherited.

This page is that design. It has two parts — where a comment goes and what it
may contain, which is straightforward, and the **field vocabulary**, which is
where the real work is, because a documentation convention for PSS has to name
things that Python and SystemVerilog conventions never had to.

## Where documentation goes

The comment block immediately above a declaration documents it.

```pss
// Program a single DMA transfer.
action Xfer { }
```

Both comment forms work, and so do the `///` and `/**` marker forms if you
prefer them. A blank line between the comment and the declaration breaks the
association, which is how you write a note that is not documentation:

```pss
// TODO: revisit once the arbiter lands -- not documentation.

// Program a single DMA transfer.
action Xfer { }
```

A trailing comment on the same line documents the declaration it follows, which
suits short fields:

```pss
rand int len;   // transfer length in bytes
```

A leading comment always wins over a trailing one, so adding prose above a field
never silently competes with the note beside it.

:::{note}
The association rules, the marker forms, and the trailing-comment convention are
implemented in `pssparser` and specified in its `docs/doc_comments.rst`. They
are deliberately documented once, there, rather than restated here where the two
could drift apart. This page owns the *convention* — what to write and how to
structure it.
:::

## What a comment contains

**The first paragraph is the summary.** It appears in listings and as the
element's lead, so write it as a sentence about what the element *is* or
*does*. Everything after the first blank line is the body.

**The body is reStructuredText.** Not a custom markup language — the full
Sphinx toolbox, including literal blocks, lists, admonitions and references:

```pss
// Program a single DMA transfer.
//
// Claims a channel for the duration of the transfer and produces a filled
// buffer for a downstream consumer. The transfer is indivisible: nothing
// else may use the channel until it completes.
//
// See :pss:action:`Configure`, which must run first.
action Xfer { }
```

Indentation inside a comment is preserved relative to the block, so a literal
block works the way you would expect:

```pss
/** Round a byte count up to the next word boundary.
 *
 * Equivalent to::
 *
 *     (n + 3) & ~3
 */
function int align_up(int n) { }
```

## The field vocabulary

Structured metadata goes in a field list. This is the part specific to PSS, and
it exists because a PSS element has structure that prose cannot carry: an action
does not merely *have parameters*, it consumes and produces flow objects and
claims resources, and those are the things a reader needs named.

| Field | Applies to | Means |
|---|---|---|
| `:param X:` | action, component, struct, function | Template parameter or function argument |
| `:input X:` | action, monitor | An input flow-object reference |
| `:output X:` | action, monitor | An output flow-object reference |
| `:lock X:` | action, monitor | An exclusive resource claim |
| `:share X:` | action, monitor | A shared resource claim |
| `:field X:` | any type scope | An attribute field, when not documented at its declaration |
| `:constraint C:` | any type scope | The intent of a named constraint |
| `:pool P:` | component | A pool declaration and its bind intent |
| `:exec K:` | action, component | What a `body` / `run_start` / `init_down` block does |
| `:covers C:` | action, covergroup | Coverage intent |
| `:req:` | anything | Traceability IDs |
| `:group:` | any member | Logical grouping, rendered as a rubric |
| `:realizes:` | action | The target-side operation this action stands for |

`:parameter:`, `:requirement:`, `:attr:` and a few other natural spellings are
accepted as aliases.

Worked example:

```pss
// Program a single DMA transfer.
//
// :output out_b: the filled destination buffer
// :input  in_b:  the source buffer to read from
// :lock   eng:   exclusive claim on the DMA engine
// :param  len:   transfer length in bytes; must be word-aligned
// :req:   DMA-014, DMA-015
action Xfer {
    input  DmaBuf    in_b;
    output DmaBuf    out_b;
    lock   DmaEngine eng;
    rand   int       len;
}
```

### Documenting members at their declaration instead

The field list is not the only option, and often not the best one. A member can
carry its own comment, which keeps the description next to the thing it
describes:

```pss
action Xfer {
    // The filled destination buffer.
    output DmaBuf out_b;

    // Transfer length in bytes.
    rand int len;
}
```

Use the field list when the description belongs to the *action's* story — when
what matters is the relationship between the members — and per-declaration
comments when each member stands on its own. Doing both for the same member is
redundant and the second one wins nothing.

## Cross-validation, or why this is more than a naming scheme

Every field that names a declaration is checked against the model.

**A field naming something the element does not declare is a warning.** This is
the case that matters, because it is what happens when a flow object is renamed
and the comment is not:

```text
WARNING: ':output out_b:' names something action 'dma_pkg::Dma::Xfer' does not
         declare (declared flow_ref: in_s, result)
```

The message lists what *is* declared, so the fix does not require opening the
source.

**A misspelled field name is a warning too**, rather than being rendered as a
generic field:

```text
WARNING: unknown documentation field ':ouput:' on action 'dma_pkg::Dma::Xfer';
         known fields: constraint, covers, exec, field, group, input, lock, ...
```

Without this, `:ouput out_b:` renders as a field called "Ouput" and looks
entirely fine.

**A field used on the wrong kind of element is a warning.** `:pool:` documents a
component, and an action cannot declare one.

**In the other direction**, a declared flow reference or resource claim with
neither its own comment nor a field entry is reported under `:undoc-members:`.
Only those two kinds are reported: `rand int len` largely reads for itself,
while `output DmaBuf out_b` never says what the buffer carries.

Warnings are located at the **doc comment** — the `.pss` file and line — not at
the directive that rendered it, because the comment is what needs changing.

Under `sphinx-build -W`, all of this means documentation cannot drift away from
the model without the build failing. That is a property prose comments alone
cannot give you, and it is the reason to prefer the field vocabulary over
free-form text wherever a field applies.

## Conventions worth adopting

Not enforced, but they make the output better:

- **Write the summary as a sentence, ending with a period.** It is rendered
  next to other summaries, and a mix of fragments and sentences reads badly.
- **Say what an action *accomplishes*, not what it traverses.** The activity
  graph already shows the traversal.
- **Document flow objects from the consumer's point of view.** "The filled
  destination buffer" tells a reader what they will receive; "output buffer"
  restates the declaration.
- **Put requirement IDs in `:req:` rather than in prose**, so the Phase-4
  requirements index can find them.
- **Do not restate the type.** `:param len: an int` adds nothing that the
  signature does not already show.
