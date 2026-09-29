Steps
=====

The bring-up sequence, decimal:

.. pss:steps:: eth_pkg::init_eth

The same, as the Microchip FRM numbers it:

.. pss:steps:: eth_pkg::init_eth
   :numbering: outline

A ``match``, a ``repeat … while`` and a count loop:

.. pss:steps:: eth_pkg::set_speed

A ``foreach``:

.. pss:steps:: eth_pkg::clear_rx

Recursion, cut:

.. pss:steps:: eth_pkg::flush_rx

Calls linked rather than inlined:

.. pss:steps:: eth_pkg::init_mac
   :expand-calls: link

One level of calls, named relative to nothing:

.. pss:steps:: init_eth
   :depth: 1

A component's ``exec init_down``:

.. pss:steps:: eth_pkg::eth_c
   :exec: init_down

An action's ``exec body``, with the blocks two extensions add:

.. pss:steps:: eth_pkg::eth_c::send_a
   :exec: body
   :format: table

The table on a documented function:

.. autopssfunction:: eth_pkg::init_miim
   :steps:
