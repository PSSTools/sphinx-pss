# Programming steps

A device's programming guide describes its initialization as a list of numbered
steps: *reset the MAC, wait for the reset to complete, initialize the MIIM
interface, …*. When that sequence is written in PSS, as functions and `exec`
blocks that write registers and poll status, the code and the guide describe
the same procedure. Programming steps let the documentation be generated from
the code, so the two can't drift apart.

You mark which code is a step; `sphinx-pss` works out the structure: the
conditions and loops around each step, and the steps of the functions it calls.
It shows the result as a numbered table, a flowchart, or both.

## Marking steps

A step is a `///` or `/** */` comment line that starts with `Step:`, placed on
the first statement of the step:

```{literalinclude} ../../tests/fixtures/pss/steps_pkg.pss
:language: pss
:start-at: /// Bring the MAC out of reset
:end-before: component mac_c {
:dedent: 4
```

This is the MAC driver the test suite uses. Four things to notice:

- **A step runs to the next marker.** `Reset the MAC` covers one register
  write, but a step can cover as many statements as the procedure needs. The
  prose of a programming guide is one step per *action*, not one per write.
- **The lines after the marker are detail.** `SOFTRESET self-clears …` belongs
  to `Wait for the reset to complete`. It is reStructuredText, like any doc
  comment. Lines of the same comment *before* the marker are ignored, so a
  comment can start with a note to the code's reader.
- **`init_miim` has steps of its own.** They become sub-steps of `Initialize the
  MIIM interface`, numbered from it. Nothing about that is written by hand.
- **The last comment is a plain `//` comment**, so it is not a marker, even
  though it starts with `Step:`. Plain comments are never read.

This is the table the docs build makes from it, with
`` .. pss:steps:: mac_pkg::init_mac ``:

```{eval-rst}
.. pss:steps:: mac_pkg::init_mac
```

The numbers are generated. `init_miim`'s steps are numbered from the step that
calls it, and each row's Source is the line of its marker.

### The rules

1. **Only `///` and `/** */` comments are read.** Driver code is full of `//`
   comments, including hand-written `// Step 1:` notes; none of them are
   markers, and the Sphinx build never warns about them. To convert a codebase
   that already writes `// Step:`, see {ref}`step-migration`.
2. **A marker is a line of the form `Step: <title>`**: a capital `S`, then a
   colon, then the title. Indentation before it is ignored. A number is
   accepted and ignored (`Step 3: Reset the MAC`): steps are always numbered by
   the tool, because hand-written numbers drift.
3. **The title is the rest of the line; the detail is the rest of the
   comment**, up to the next marker.
4. **`Step:` is the only keyword.** A line such as `Note:` or `Warning:` is
   prose.

### Where a marker can go

Inside a function body, an `exec` block or an
{ref}`activity <steps-in-activities>`, at any depth: above a statement, after a
statement on its line, or above it with a blank line between.

```{code-block} pss
:name: step-example-valid-placements

function void configure(bool rmii) {
    /// Step: Select the interface mode
    if (rmii) {
        /// Step: Reset the RMII module
        write_reg(0x18, 1);
    }

    /// Step: Set the MDC clock divider

    write_reg(0x14, 40);
    write_reg(0x4, 1); /// Step: Enable the receiver
}
```

`Reset the RMII module` is a sub-step of `Select the interface mode`, because
the `if` is inside that step's range. The `if` itself is shown too, labelled
with its condition as written.

`exec` blocks are marked the same way. When `extend` statements add more
blocks of the same kind to a type, their steps follow the declaration's own,
in the order the extensions are processed.

(showing-steps)=
## Showing steps

Step tables and flowcharts appear only where a page asks for one. A function
with markers gets no table just because it has them.

`pss:steps` renders the table of one function:

```rst
.. pss:steps:: mac_pkg::init_mac
```

or of a type's `exec` blocks of one kind, named with `:exec:`:

```rst
.. pss:steps:: mac_pkg::mac_c
   :exec: init_down
```

The `autopssfunction`, `autopssaction` and `autopsscomponent` directives take a
`:steps:` flag, which puts the table in the entry they render, after its
description and before its members. They take the same options:

```rst
.. autopssfunction:: mac_pkg::init_mac
   :steps:
   :numbering: outline
```

| Option | Values |
|---|---|
| `:exec:` | Required when the target is a type, except a compound action, whose steps without `:exec:` are its activity's: `body`, `init_down`, `init_up`, `pre_solve`, `post_solve`, `pre_body`, `run_start` or `run_end`. Not allowed for a function |
| `:numbering:` | `decimal` (default): 1, 1.1, 1.1.1. `outline`: 1, a), i., as vendor programming guides number them |
| `:expand-calls:` | `inline` (default): a called function's steps become sub-steps. `link`: one row that links to the callee. `none`: calls are never expanded |
| `:depth:` | How many levels of calls expand. `0` expands none; the default is no limit |
| `:format:` | `table` (default), `flowchart`, or `both`: the table, then the flowchart. See {ref}`step-flowcharts`. A compound action's steps are a table only |
| `:expand-exec:` | For a compound action: follow traversals of atomic actions into their `exec body` steps. See {ref}`activity-step-table` |
| `:weights:` | For a compound action: show `select` weights in the table |

`:steps:` can't be set in `pss_default_options`: a table everywhere is never
what a project means, and the build stops with an error if it is there.

A mistake in the request (an unknown name, a type with no `:exec:`, an option
value that doesn't exist) is an error at the directive's line, with the values
that would have worked. A body with no markers gives a `pss.steps` warning and
no table.

### The table

| Column | Content |
|---|---|
| **#** | The generated number. Empty on rows that show a condition or a loop |
| **Step** | The title, indented by nesting level. A row for an `if` or a loop gives its condition as written |
| **Details** | The marker's detail lines, as reStructuredText |
| **Source** | The file and line of the marker |

Titles and details are reStructuredText, parsed where they were written: a
markup mistake in a detail is reported at its line in the `.pss` file, not at
the page that shows the table.

(step-flowcharts)=
### The flowchart

`:format: flowchart` draws the same steps as a flowchart, and `:format: both`
shows the table and then the flowchart. This is `set_speed`, whose source is
{ref}`below <step-conditions-and-loops>`:

```rst
.. pss:steps:: eth_pkg::set_speed
   :format: flowchart
```

```{eval-rst}
.. pss:steps:: eth_pkg::set_speed
   :format: flowchart
```

| Shape | Is |
|---|---|
| Box | A step: its number and title. Details are only in the table |
| Diamond | A condition, as written: `yes` and `no` out of an `if`, one edge per choice out of a `match`. A `while` tests before its body and a `repeat … while` after it, and loops back on `yes` |
| Hexagon | A `repeat (n)` or `foreach` loop. The body loops back to it, and `done` leaves it |
| Double-bordered box | A call shown as one box, with `:expand-calls: link`, or a recursive call. It links to the callee's entry when a page documents it |
| Dashed frame | The steps of a called function, labelled with its name, or the steps an `extend` adds |

Each shape shows its source line when the pointer is over it.

Flowcharts are drawn by the [diagram back-end](diagrams.md), Graphviz by
default, so the build machine needs Graphviz's `dot` command. Without it the
build does not fail: it gives one `pss.diagrams` warning, and each flowchart is
replaced by its table, which every output format can show. The same happens
with `pss_diagrams = "off"`, but without the warning.

## How the table is built

(step-conditions-and-loops)=
### Conditions and loops

An `if`, `match` or loop that has steps inside it gets a row of its own,
labelled with its condition exactly as the source writes it. A marker on the
statement itself makes the two one row: the title, and under it the condition.

```{literalinclude} ../../tests/fixtures/pss/steps/eth_mac.pss
:language: pss
:start-at: /// Set the link speed, and wait
:end-before: /// Clear every receive descriptor.
:dedent: 4
```

```{eval-rst}
.. pss:steps:: eth_pkg::set_speed
```

The steps inside a condition or a loop continue the numbering around it. The
condition rows are not numbered, since they aren't steps.

| Statement | Row |
|---|---|
| `if (c)` / `else if (d)` / `else` | "If `c`:", "Else if `d`:", "Otherwise:" |
| `match (e)` and its choices | "Depending on `e`:", then "When `[A]`:" or "Otherwise:" per choice |
| `while (c)` | "While `c`:" |
| `repeat { … } while (c)` | "Repeat until not `c`:" |
| `repeat (n)` | "Repeat `n` times:" |
| `foreach (e : xs)` | "For each `e` in `xs`:" |

An `if` or loop with no steps inside it is just part of its step, like any
other statement. That is the case of `init_miim`'s first step above.

### Calls

A call inside a step, to a function that has steps of its own, brings those
steps in as sub-steps, in the order the calls are made. The call is followed
through the linker, so `comp.sub.configure()` finds the right function, and a
call to a function without markers is just part of its step.

`:expand-calls: link` shows the call as one row instead, naming the function.
The name links to the function's entry when a page documents it:

```{eval-rst}
.. pss:steps:: mac_pkg::init_mac
   :expand-calls: link
```

A function that calls itself, directly or through others, is expanded once.
The repeat is a row that refers back to where its steps are:

```{literalinclude} ../../tests/fixtures/pss/steps/eth_mac.pss
:language: pss
:start-at: /// Flush received frames
:end-before: component eth_c {
:dedent: 4
```

```{eval-rst}
.. pss:steps:: eth_pkg::flush_rx
```

### `exec` blocks and `extend`

A type's steps for one `exec` kind are those of every block of that kind: the
declaration's own first, then each one an `extend` adds, in the order the
extensions are processed, which is the order of the files. Numbering runs on
across them, and a row marks where each extension's steps begin:

```{literalinclude} ../../tests/fixtures/pss/steps_pkg.pss
:language: pss
:start-at: exec init_down {
:end-before: action reset_a {
:dedent: 8
```

and, later in the same file:

```{literalinclude} ../../tests/fixtures/pss/steps_pkg.pss
:language: pss
:lines: 72-77
:dedent: 4
```

```{eval-rst}
.. pss:steps:: mac_pkg::mac_c
   :exec: init_down
```

The [Ethernet example](../examples/steps.md) shows a larger sequence in both
numbering styles.

(steps-in-activities)=
## Steps in activities

```{admonition} Needs a newer pssparser
:class: note

Markers in an activity are read from the comments pssparser attaches to
activity statements, and releases up to 3.1.7 attach none. With such a
parser, activity diagrams are drawn without steps, and the build says why
once, as a `pss.step_unsupported` warning at the first marker it finds.
```

A compound action's `activity` can be marked like a function body. The steps
become labelled regions of its {doc}`activity diagram <activities>`:

```{literalinclude} ../../tests/fixtures/pss/activities/steps_xfer.pss
:language: pss
:start-at: /// Copy a block in two halves
:end-before: // The page's excerpt ends here.
:dedent: 8
```

```{eval-rst}
.. pss:activity-diagram:: sxfer_pkg::dma_c::xfer
```

### How far a step reaches

In a function, a step covers the statements from its marker to the next marker
in the same block. In an activity, that holds only where the statements run
one after another. A `parallel`'s branches run at the same time, so a marker
there covers its own branch:

| Block | A marker covers |
|---|---|
| The `activity` itself, `sequence`, and the braced bodies of `if`, `repeat`, `foreach`, `replicate` and `atomic` | Its statement, up to the next marker in the block, as in a function |
| `parallel`, `schedule` | Its own branch |
| `select`, `match` | Its own arm. Write the marker above the arm: `/// Step: Fast path` above `(fast): burst;` |

So in the example, `Copy the first half` covers `c1` and nothing else, even
though `c2` follows it. A branch can still hold a procedure of its own: make
it a `sequence { }` and mark the statements inside it.

A `schedule` reaches like a `parallel`, because its branches run in an order
the tool chooses. The two are still drawn differently: a `schedule` has hollow
bars in a frame of its own (see {doc}`activities`).

Everything else is as in a function: markers in a nested block are sub-steps,
a marker on a `parallel`, `select` or loop titles it, and steps are numbered
for you, continuing across the `activity` blocks an `extend` adds.

### Showing them

Step regions are drawn by default. `:steps: collapsed` draws each outermost
step as one box, which gives a large activity an overview. `:steps: none`
ignores the markers.

```rst
.. pss:activity-diagram:: sxfer_pkg::dma_c::xfer
   :steps: collapsed
```

```{eval-rst}
.. pss:activity-diagram:: sxfer_pkg::dma_c::xfer
   :steps: collapsed
```

In an activity that has steps, a traversal outside every step is reported, as
a call is in a function (`pss.step_prelude_call`, below). In a `parallel`,
that includes an unmarked branch beside marked ones.

(activity-step-table)=
### The step table of a compound action

`pss:steps`, and `:steps:` on `autopssaction`, take a compound action with no
`:exec:`: the table is its activity's steps. A traversal inside a step expands
like a call, into the traversed action's own activity steps.

An activity says which actions run, and in what arrangement; an atomic
action's `exec body` says how it does its work. The table keeps the two apart
unless `:expand-exec:` asks to follow a traversal into an atomic action's
`exec body` steps, which then sit under a row that marks the boundary:

```rst
.. pss:steps:: sxfer_pkg::dma_c::xfer
   :expand-exec:
```

```{table}
:name: activity-step-table-example

| # | Step |
|---|---|
| 1 | Configure the channel |
|  | The `exec body` of `configure`: |
| 1.1 | Write the descriptor |
| 1.2 | Enable the channel |
| 2 | Move the data<br>In parallel: |
| 2.1 | Copy the first half |
| 2.2 | Copy the second half |
| 3 | Check the result |
```

The Details and Source columns are left out here. A marked `parallel` is one
row, the step's title and then "In parallel:", as a marked `if` is. The other
controls read:

| Control | Row |
|---|---|
| `parallel` | "In parallel:", or with a join specification "In parallel, until the first `1` finish:", "Start in parallel, without waiting:" |
| `schedule` | "In an order the tool chooses:", with its scheduling constraints: "(`s1`, then `s2`)" |
| `select` | "One of:", then "If `fast`:" for a guarded arm and "Or:" for an unguarded one. `:weights:` adds "(weight `3`)" |
| `replicate` | "`4` copies, in parallel:" |
| `atomic` | "Without interleaving:" |

`:format: flowchart` isn't offered for an activity: its
{doc}`activity diagram <activities>` is its flowchart.

## What is checked

Markers are checked across the whole model on every build, including functions
no page documents. A typo in a marker is a mistake wherever it is. Each problem
is a warning at the comment's line in the `.pss` file.

| Warning | When |
|---|---|
| `pss.step_syntax` | Inside a function body, `exec` block or activity, a line that starts with `step` or `steps`, in any case, but isn't a marker |
| `pss.step_misplaced` | A marker outside any function body, `exec` block or activity. It is ignored |
| `pss.step_empty` | A marker with no title, or a step with nothing in it |
| `pss.step_prelude_call` | In a body a step table shows, a call outside every step; in an activity with steps, a traversal outside every step |
| `pss.step_unsupported` | The installed pssparser can't read markers in activities, and one is there. Once per build |

The first three are only ever about `///` and `/** */` comments.
`pss.step_prelude_call` is about the code, and is only checked where a table
shows the body.

### `pss.step_syntax`

Reported when a line almost matches the marker form: the wrong case, a missing
colon, or `Steps`.

```{code-block} pss
:name: step-example-syntax

function void init_mac() {
    /// step: Reset the MAC
    write_reg(0x0, 0x8000);
}
```

```text
drv.pss:3: WARNING: not a step marker: 'step: Reset the MAC'. A marker is written 'Step: <title>', with a capital S and a colon [pss.step_syntax]
```

Near misses are only looked for inside bodies. A declaration's doc comment is
prose, where `/// Steps are generated by the tool.` is just a sentence.

### `pss.step_misplaced`

Reported when a marker is on a declaration, such as a type, field, action,
function or `exec` block, or sits at package or component scope. A step is part
of a procedure, so it has to be inside one.

```{code-block} pss
:name: step-example-misplaced

/// Step: Configure the channel
struct channel_cfg_s {
    bit[32] src;
}
```

```text
drv.pss:2: WARNING: step marker outside a function body, exec block or activity is ignored: 'Step: Configure the channel' [pss.step_misplaced]
```

### `pss.step_empty`

Reported for a marker with no title, and for a step with nothing in it: one
that another marker follows before any statement does, or one after the last
statement in a block.

```{code-block} pss
:name: step-example-empty

function void init_mac() {
    /// Step:
    write_reg(0x0, 0x8000);
    /// Step: Wait for the reset to complete
    /// Step: Poll SOFTRESET
    while ((read_reg(0x0) & 0x8000) != 0) { }
    /// Step: Done
}
```

```text
drv.pss:3: WARNING: step marker has no title [pss.step_empty]
drv.pss:5: WARNING: step 'Wait for the reset to complete' has no statements: the next marker follows it directly [pss.step_empty]
drv.pss:8: WARNING: step 'Done' has no statements: the block ends after its marker [pss.step_empty]
```

### `pss.step_prelude_call`

Reported for a call that is outside every step, in a body with steps that a
table shows. The table leaves that call out, so it would describe a sequence
the code doesn't follow. It is usually a first step no one marked:

```{code-block} pss
:name: step-example-prelude-call

function void init_mac() {
    write_reg(0x0, 0x8000);
    /// Step: Wait for the reset to complete
    while ((read_reg(0x0) & 0x8000) != 0) { }
}
```

```text
drv.pss:3: WARNING: call to 'write_reg' is outside every step, so the step table leaves it out: move it into a step, or mark a step above it [pss.step_prelude_call]
```

A declaration is not reported, even when it is initialized by a call
(`bit[32] id = read_reg(0xF0);`): setting up a variable isn't a step. Nor is a
call in the condition of an `if` or a loop. An assignment from a call is
reported, since it reads the device (`status = read_reg(0x8);`). A call in the
middle of the body, after a nested step's block ends but before the next outer
step starts, is outside every step too.

Each call is reported once per build, however many tables show its body.

### Silencing a warning

Each warning has its own type, so Sphinx's `suppress_warnings` can turn one off
without hiding the rest:

```python
# conf.py
suppress_warnings = ["pss.step_misplaced"]
```

`"pss"` alone silences every `sphinx-pss` warning, including those about doc
comments, which is rarely what you want.

(step-migration)=
## Migrating existing comments

A codebase that already writes its steps as `// Step: …` gets no steps from
them, and no warning, because plain comments are never read. `sphinx-pss` comes
with a `pssparser` checker that finds them: `SPSS001` reports each plain `//`
or `/* */` comment line that would be a marker as a `///` or `/** */` comment.

Installing `sphinx-pss` makes the checker available to the `pssparser` command,
but it stays silent until you enable it in `.pssparser.toml`, or under
`[tool.pssparser]` in `pyproject.toml`:

```{code-block} toml
:name: step-migration-config

[checker.sphinx-pss-steps]
enabled = true
```

With that in place, running `pssparser` on this driver:

```{code-block} pss
:name: step-migration-source

package drv {
    function void init_mac() {
        // Step: Reset the MAC
        write_reg(0x0, 0x8000);
        // Step 2: Wait for the reset to complete
        while ((read_reg(0x0) & 0x8000) != 0) { }
        /* Step: Enable the receiver */
        write_reg(0x4, 0x1);
        /// Step: Enable the transmitter
        write_reg(0x8, 0x1);
        // Stepping through the counters clears them
        write_reg(0xC, 0x0);
    }

    function void write_reg(bit[32] offset, bit[32] value);
    function bit[32] read_reg(bit[32] offset);
}
```

reports the three plain markers, and neither the `///` marker nor the comment
that only starts with the word *Stepping*:

```{code-block} text
:name: step-migration-output

$ pssparser drv.pss
drv.pss:3:12: warning: [SPSS001] plain comment looks like a step marker; write it as '/// Step: ...' to make it a step
 3 |         // Step: Reset the MAC
   |            ^~~~~~~~~~~~~~~~~~~

drv.pss:5:12: warning: [SPSS001] plain comment looks like a step marker; write it as '/// Step: ...' to make it a step
 5 |         // Step 2: Wait for the reset to complete
   |            ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

drv.pss:7:12: warning: [SPSS001] plain block comment looks like a step marker; write it as '/** Step: ... */' to make it a step
 7 |         /* Step: Enable the receiver */
   |            ^~~~~~~~~~~~~~~~~~~~~~~~~

3 warnings in 1 file
```

Change the comments it reports, and turn the checker off again when none are
left. Where a comment sits isn't checked: once converted, a marker outside a
function body or `exec` block is reported by the Sphinx build as
`pss.step_misplaced`.
