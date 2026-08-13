Lexer
=====

A ``pss`` code block, with nothing registering a lexer for it. Pygments finds
``pygments-pss`` through its entry point; an unknown lexer would warn here and
fail a ``-W`` build.

.. code-block:: pss

   package dma_pkg {
       /// A documented buffer.
       buffer Descriptor {
           rand bit[32] addr;
       }

       component Dma {
           action Xfer {
               output Descriptor out_d;

               exec body {
                   // A trailing comment.
               }
           }
       }
   }
