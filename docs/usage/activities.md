# Activity diagrams

An action's `activity` says which sub-actions run, and how: in sequence, in
parallel, one of several, in a loop. `sphinx-pss` draws it as a UML activity
diagram, from the source, so the picture changes when the code does.

(activity-example)=
## An example

This action moves a block of memory through two DMA channels and checks it:

```{literalinclude} ../../tests/fixtures/pss/activities/xfer_pkg.pss
:language: pss
:start-at: /// Move a block through two channels
:dedent: 8
:end-before: // The page's excerpt ends here.
```

`pss:activity-diagram` draws its activity:

```rst
.. pss:activity-diagram:: xfer_pkg::dma_c::xfer
```

```{eval-rst}
.. pss:activity-diagram:: xfer_pkg::dma_c::xfer
```

Each traversed action links to its entry when a page documents it, as
`configure` and `copy` do here:

```{eval-rst}
.. autopssaction:: xfer_pkg::dma_c::configure
.. autopssaction:: xfer_pkg::dma_c::copy
```

## How PSS is drawn

| PSS | Drawn as |
|---|---|
| The activity | A filled circle where it starts, and a bullseye where it ends |
| `c1;` | A rounded box, `c1 : copy`. A `⋔` after the name means `copy` has an activity of its own |
| `do copy;` | A rounded box, `copy`, or `«any» copy` when `copy` is abstract and the tool picks a subtype |
| `s1: c1;` | The label comes first: `s1: c1 : copy` |
| `parallel { }` | Two solid bars, with the branches between them |
| `join_first (1)` and the other join specifications | The join bar is labelled with the specification |
| `join_none` | No join bar: each branch ends in a circle of its own, and what follows starts straight away |
| `schedule { }` | Two **hollow** bars inside a dashed frame titled `schedule`. The tool picks the order of the branches, and may run them in parallel. The different bars keep a `schedule` from being read as a `parallel` |
| `constraint parallel { s1, s2 };` | A dotted line between `s1` and `s2`, labelled `parallel`. `constraint sequence` is a dotted arrow |
| `select { }`, `if`, `match` | A diamond where the paths divide, and a small diamond where they meet. Paths are labelled with their guard, `[verify]`, `[else]`, `[0..3]` |
| `repeat`, `foreach`, `replicate`, `atomic` | A dashed frame titled with the statement: `repeat (beats)`, `«iterative» foreach (e : arr)`, `«parallel» replicate (4)` |
| `with { }` | A note beside the box |
| `constraint { }` in the activity | A note on its own |
| `bind a.x b.y;` | A dashed line between the two boxes, labelled with the fields. A `bind` to the action's own field, such as `bind in_data c1.src`, draws that field as a box |
| `super;` | A box, `super`, linked to the base action |
| Several `activity` blocks, from `extend` | A `schedule` of the blocks, each in its own frame, since PSS runs them that way |
| `/// Step: …` | A shaded frame around the statements the step covers, titled with its number and title. See {ref}`steps-in-activities` |

An action with no `activity` of its own, deriving from one that has one, shows
the base's activity, and the caption says so.

## Options

```rst
.. pss:activity-diagram:: xfer_pkg::dma_c::xfer
   :format: both
   :depth: 2
   :weights:
   :caption: A two-channel transfer
```

| Option | Values |
|---|---|
| `:format:` | `diagram` (default); `outline`, the activity as a nested list; or `both`, the diagram with the outline below it, folded away in HTML |
| `:depth:` | `1` (default) to `4`. At `1`, each traversal is one box. Each level more opens the traversals of actions that have activities, as a frame holding their activity. A traversal that would repeat an action already open is drawn once, as `(recursive, see above)` |
| `:steps:` | How {ref}`programming steps <steps-in-activities>` marked in the activity are drawn: `regions` (default), a shaded frame titled with each step's number and title; `collapsed`, each outermost step as one box; or `none` |
| `:weights:` | Label `select` paths with their weights. They're left out by default: a weight tunes how often a tool picks a path, and doesn't change what the scenario does |
| `:caption:` | The figure's caption. The default is the action's name |

This is the same activity at depth 2, where `c2`'s `burst_copy` opens:

```{eval-rst}
.. pss:activity-diagram:: xfer_pkg::dma_c::xfer
   :depth: 2
   :caption: xfer_pkg::dma_c::xfer, two levels deep
```

## In an action's entry

`autopssaction` takes an `:activity-diagram:` flag, which puts the diagram in
the action's entry, after its description and before its members:

```rst
.. autopssaction:: xfer_pkg::dma_c::burst_copy
   :activity-diagram:
```

```{eval-rst}
.. autopssaction:: xfer_pkg::dma_c::burst_copy
   :activity-diagram:
```

The options above work here with an `activity-` prefix, `:activity-format:`,
`:activity-depth:`, `:activity-steps:` and `:activity-weights:`, so they can't be mistaken for a
step table's `:format:` and `:depth:`. An action with no activity gets
nothing, so the flag is harmless on atomic actions.

`autopsscomponent` and `autopsspackage` take the flag too, and pass it to the
actions they document as members. To give every action with an activity its
diagram, make it a project default:

```python
# conf.py
pss_default_options = {"members": True, "activity-diagram": True}
```

`:activity-diagram: false` turns it off for one entry.

## The outline

The outline is the diagram's text equivalent, for readers who can't see the
diagram, and for search. It is what `:format: outline` shows:

```{eval-rst}
.. pss:activity-diagram:: xfer_pkg::dma_c::xfer
   :format: outline
```

It is also what a page shows when the diagram can't be drawn: with
`pss_diagrams = "off"`, or when Graphviz or Mermaid isn't available (see
{doc}`diagrams`).

## What isn't drawn

- **A `bind` whose ends can't be placed.** When a handle is traversed in two
  places, or a path reaches into a sub-action, there's no single box to draw
  the line to. The caption lists it instead: `Also bound: f.data ↔ c1.src`.
- **Monitors.** A monitor's activity is about the order of events over time,
  which an activity diagram is the wrong picture for.
- **Anything a solver decides.** The diagram is the activity as written: every
  path of a `select`, and a loop drawn once. A particular run's choices are
  not something the source says.

A statement `sphinx-pss` doesn't know is drawn as a box naming its kind, with
a `pss.activity` warning, rather than left out silently.
