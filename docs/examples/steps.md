# Example: Ethernet bring-up steps

The Microchip PIC32 Family Reference Manual, section 35.4.10, describes how to
bring up the Ethernet controller as a numbered procedure: initialize the
controller, then the MAC, and inside the MAC, the MII management interface.
Below is that procedure written in PSS, as the functions a test would call,
with a `/// Step:` marker on each step. The tables and the flowchart after it
are generated from the code by the docs build. Nothing in them is written by
hand.

The source is `tests/fixtures/pss/steps/eth_mac.pss` in this repository, the
file the test suite checks these tables against.

## The code

```{literalinclude} ../../tests/fixtures/pss/steps/eth_mac.pss
:language: pss
:start-at: /// Bring the controller to a known, idle state
:end-before: /// Set the link speed, and wait
:dedent: 4
```

Nothing in `init_eth` says that `init_mac`'s steps belong under its second
step, or that `init_miim`'s belong under `init_mac`'s. The calls say so.

## As the manual numbers it

`:numbering: outline` numbers the levels 1, a), i., as the FRM does.
`:format: both` shows the flowchart after the table. Each called function's
steps are a dashed frame, labelled with its name:

```rst
.. pss:steps:: eth_pkg::init_eth
   :numbering: outline
   :format: both
```

```{eval-rst}
.. pss:steps:: eth_pkg::init_eth
   :numbering: outline
   :format: both
```

`revision` is read before the first step, but it is a declaration, so the
table has no step for it and nothing is reported.

## Decimal

The default numbering, 1, 1.1, 1.1.1:

```{eval-rst}
.. pss:steps:: eth_pkg::init_eth
```

## One level of calls

`:depth: 1` expands the functions `init_eth` calls, but not the ones they
call in turn. `Initialize the MII management interface` has no sub-steps
here:

```{eval-rst}
.. pss:steps:: eth_pkg::init_eth
   :depth: 1
```

## From the component

The component that owns the port runs the sequence in its `exec init_down`.
Its table holds the whole bring-up one level down:

```{literalinclude} ../../tests/fixtures/pss/steps/eth_mac.pss
:language: pss
:start-at: component eth_c {
:end-before: action send_a {
:dedent: 4
```

```{eval-rst}
.. pss:steps:: eth_pkg::eth_c
   :exec: init_down
```
