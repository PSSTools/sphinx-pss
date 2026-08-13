Basic
=====

.. pss:package:: dma_pkg

   A small DMA subsystem.

   .. pss:buffer:: DmaBuf

      A block of memory handed from one action to the next.

      .. pss:field:: rand int size

         Number of bytes the producer wrote.

   .. pss:resource:: DmaChannel

      Exclusive access to one DMA channel.

   .. pss:component:: Dma

      The DMA controller.

      .. pss:function:: int align_up(int n)

         Round a byte count up to the next word boundary.

      .. pss:action:: Xfer

         Program a single DMA transfer.

         .. pss:flow_ref:: output DmaBuf out_b

            The filled destination buffer.

         .. pss:resource_claim:: lock DmaChannel chan

            Exclusive claim on the channel.

         .. pss:constraint:: c_len_aligned

            Transfers are word-aligned.

Prose referring to :pss:action:`dma_pkg::Dma::Xfer`, to
:pss:buffer:`DmaBuf` by its bare name, and to :pss:obj:`dma_pkg::Dma`.
