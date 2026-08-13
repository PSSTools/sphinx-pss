"""P1-TEST-6 — doc comments reach the model, in every form and position.

The association rules themselves belong to ``pssparser`` (its
``docs/doc_comments.rst``), and are not restated here. What these tests pin is
that `sphinx_pss` *reads* them — including for the two element kinds whose doc
comment is not reachable from the linked tree at all (finding ``U-1``).
"""

from __future__ import annotations

import pytest

from sphinx_pss.model.builder import build_objects
from sphinx_pss.model.parse import parse_model

pytestmark = pytest.mark.unit


def build(tmp_path, source: str) -> dict[str, str | None]:
    """Parse ``source`` and return ``qualname -> raw_doc``."""
    path = tmp_path / "t.pss"
    path.write_text(source)
    return {
        obj.qualname: obj.raw_doc
        for root in build_objects(parse_model([str(path)]))
        for obj in root.walk()
    }


# --- comment forms ----------------------------------------------------------


def test_a_line_comment_block(tmp_path) -> None:
    docs = build(
        tmp_path,
        """
        package p {
            // First line.
            // Second line.
            struct S { }
        }
        """,
    )
    assert docs["p::S"] == "First line.\nSecond line."


def test_a_block_comment(tmp_path) -> None:
    docs = build(
        tmp_path,
        """
        package p {
            /** A buffer.
             *
             * With a body.
             */
            buffer B { }
        }
        """,
    )
    assert docs["p::B"] == "A buffer.\n\nWith a body."


def test_a_block_comment_arrives_dedented_and_unmarked(tmp_path) -> None:
    """Normalization happens in the parser; `docparse` must not redo it.

    Indentation is syntax in reStructuredText, so ``*`` residue or leftover
    source indentation would turn prose into a block quote.
    """
    docs = build(
        tmp_path,
        """
        package p {
                /** Summary.
                 *
                 * A paragraph at the body margin::
                 *
                 *     indented code
                 */
                struct S { }
        }
        """,
    )
    body = docs["p::S"]
    assert "*" not in body
    assert body.startswith("Summary.")
    assert "\nA paragraph at the body margin::" in body, "the margin is removed"
    assert "\n    indented code" in body, "relative indentation must survive"


def test_a_blank_line_breaks_the_association(tmp_path) -> None:
    docs = build(
        tmp_path,
        """
        package p {
            // Not attached to anything.

            struct S { }
        }
        """,
    )
    assert docs["p::S"] is None


def test_adjacent_comment_blocks_do_not_merge(tmp_path) -> None:
    docs = build(
        tmp_path,
        """
        package p {
            // An unrelated note.

            // The real documentation.
            struct S { }
        }
        """,
    )
    assert docs["p::S"] == "The real documentation."


# --- positions that used to lose their comment ------------------------------


@pytest.mark.parametrize(
    "declaration,name",
    [
        ("rand int x;", "x"),
        ("int y;", "y"),
        ("rand bit [7:0] z;", "z"),
    ],
)
def test_attributed_fields_keep_their_docstring(
    tmp_path, declaration: str, name: str
) -> None:
    """The qualifier between the comment and the type used to hide it.

    Attribute fields in actions and structs are the most commonly documented
    elements in real PSS, which is what made this the highest-impact fix
    upstream.
    """
    docs = build(
        tmp_path,
        f"""
        package p {{
            struct S {{
                // Documented.
                {declaration}
            }}
        }}
        """,
    )
    assert docs[f"p::S::{name}"] == "Documented."


def test_a_static_const_field_keeps_its_docstring(tmp_path) -> None:
    docs = build(
        tmp_path,
        """
        package p {
            component C {
                // How many channels.
                static const int n = 4;
            }
        }
        """,
    )
    assert docs["p::C::n"] == "How many channels."


def test_a_trailing_comment_documents_its_own_declaration(tmp_path) -> None:
    """Adopted convention: unmarked trailing comments count, leading wins."""
    docs = build(
        tmp_path,
        """
        package p {
            struct S {
                rand int a; // bytes
                rand int b;
            }
        }
        """,
    )
    assert docs["p::S::a"] == "bytes"
    assert docs["p::S::b"] is None


def test_a_leading_comment_beats_a_trailing_one(tmp_path) -> None:
    docs = build(
        tmp_path,
        """
        package p {
            struct S {
                // Leading.
                rand int a; // trailing
            }
        }
        """,
    )
    assert docs["p::S::a"] == "Leading."


# --- kinds whose comment is not on the linked node --------------------------


def test_a_package_is_documented(sample_index) -> None:
    """Finding ``U-1``: recovered from the pre-link declaration."""
    package = sample_index.get("dma_pkg")
    assert package.raw_doc.startswith("A small DMA subsystem")


def test_an_enum_and_its_values_are_documented(sample_index) -> None:
    enum = sample_index.get("dma_pkg::AddrMode")
    assert enum.raw_doc == "How a transfer addresses its endpoints."

    first = sample_index.get("dma_pkg::AddrMode::INCREMENT")
    assert first.raw_doc == "Address advances by the element size after each beat."


def test_a_type_is_documented_through_its_declaration(sample_index) -> None:
    """``SymbolTypeScope`` hides the docstring; ``getTarget()`` has it."""
    action = sample_index.get("dma_pkg::Dma::Xfer")
    assert action.raw_doc.startswith("Program a single DMA transfer.")


def test_a_function_is_documented_through_its_definition(sample_index) -> None:
    """The prototype has neither location nor docstring (finding ``U-4``)."""
    function = sample_index.get("dma_pkg::Dma::align_up")
    assert function.raw_doc.startswith("Round a byte count up")


def test_an_at_sign_line_is_kept_verbatim(tmp_path) -> None:
    """``//@…`` is an ordinary comment and must not be silently edited.

    An earlier plan had the native parser strip a leading ``@…`` line, to work
    around a dead ``//@`` annotation token upstream. The token was removed
    instead, so the line is just text — and quietly deleting a line of a user's
    comment is exactly the kind of special case this project avoids.
    """
    docs = build(
        tmp_path,
        """
        package p {
            //@doc(text = "not an annotation")
            // Real prose.
            struct S { }
        }
        """,
    )
    body = docs["p::S"]

    assert '@doc(text = "not an annotation")' in body
    assert "Real prose." in body
    # Not asserted more tightly on purpose: the second line arrives with one
    # leading space, because the run's common prefix is zero once a line with
    # no space after ``//`` is in it (finding ``U-6``). Normalization is the
    # parser's job and is deliberately not repeated downstream.
