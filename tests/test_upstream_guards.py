"""P1-TEST-16 — the ``pssparser`` behaviors sphinx-pss depends on.

These fail rather than skip. The version floor is hard (enhancement plan
section 8), so a parser that no longer does one of these things is a broken
dependency, not an older one — and the failure should name the behavior that
went away rather than surfacing as a puzzling gap in rendered output.

They deliberately go through ``pssparser`` directly rather than through
``sphinx_pss.model``: a change in the model layer must not be able to make
these pass.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.upstream

SOURCE = """
package g {
    // A documented buffer.
    buffer B {
        // A documented attributed field.
        rand int size;
    }
    // A documented component.
    component C {
        // A documented action.
        action A {
            // A documented flow reference.
            output B out_b;
        }
    }
}

package g_ext {
    import g::*;
    extend action g::C::A {
        // Contributed by an extension.
        rand int prio;
    }
}
"""


@pytest.fixture(scope="module")
def linked(tmp_path_factory):
    from pssparser import Parser

    source = tmp_path_factory.mktemp("upstream") / "g.pss"
    source.write_text(SOURCE)

    parser = Parser(collect_docstrings=True)
    parser.parse([str(source)])
    root = parser.link()
    return parser, root


def _qname(root, name):
    from pssparser.utils import SymbolScopeUtil

    return SymbolScopeUtil(root).getQname(name)


def test_the_parser_collects_docstrings_through_the_public_api(linked) -> None:
    """``Parser(collect_docstrings=True)`` — without it there is no product."""
    _, root = linked

    doc = _qname(root, "g::B").getTarget().getDocstring()

    assert doc == "A documented buffer."


def test_docstring_collection_is_off_by_default(tmp_path) -> None:
    """The default must stay off, or every parser consumer pays for it."""
    from pssparser import Parser

    source = tmp_path / "g.pss"
    source.write_text(SOURCE)

    parser = Parser()
    parser.parse([str(source)])
    root = parser.link()

    assert _qname(root, "g::B").getTarget().getDocstring() == ""


def test_attributed_fields_keep_their_docstring(linked) -> None:
    """A ``rand`` between the comment and the type used to hide it.

    Attribute fields are the most commonly documented elements in real PSS, so
    a regression here empties most of a project's documentation while leaving
    the build green.
    """
    _, root = linked
    buffer_scope = _qname(root, "g::B")

    docs = {
        buffer_scope.getChild(i).getName().getId(): buffer_scope.getChild(
            i
        ).getDocstring()
        for i in range(len(buffer_scope.getChildren()))
        if hasattr(buffer_scope.getChild(i).getName(), "getId")
    }

    assert docs["size"] == "A documented attributed field."


def test_flow_references_keep_their_docstring(linked) -> None:
    _, root = linked
    action = _qname(root, "g::C::A")

    docs = [
        action.getChild(i).getDocstring()
        for i in range(len(action.getChildren()))
        if type(action.getChild(i)).__name__ == "FieldRef"
    ]

    assert docs == ["A documented flow reference."]


def test_docstrings_arrive_normalized(tmp_path) -> None:
    """Markers stripped and dedented by the parser, never downstream."""
    from pssparser import Parser

    source = tmp_path / "n.pss"
    source.write_text(
        """
        package n {
                /** Summary.
                 *
                 * Body.
                 */
                struct S { }
        }
        """
    )

    parser = Parser(collect_docstrings=True)
    parser.parse([str(source)])
    doc = _qname(parser.link(), "n::S").getTarget().getDocstring()

    assert doc == "Summary.\n\nBody."


def test_the_linker_merges_extensions_into_the_base_type(linked) -> None:
    """The whole reason the linked tree is the documentation view."""
    _, root = linked
    action = _qname(root, "g::C::A")

    names = {
        action.getChild(i).getName().getId()
        for i in range(len(action.getChildren()))
        if hasattr(action.getChild(i).getName(), "getId")
    }

    assert {"out_b", "prio"} <= names


def test_a_merged_member_keeps_its_extend_site_location(linked) -> None:
    """What makes provenance derivable with no parser support."""
    _, root = linked
    action = _qname(root, "g::C::A")

    lines = {
        action.getChild(i).getName().getId(): action.getChild(i).getLocation().lineno
        for i in range(len(action.getChildren()))
        if hasattr(action.getChild(i).getName(), "getId")
    }

    assert lines["prio"] > lines["out_b"], "the extend site is later in the file"


def test_synthesized_members_are_identifiable(linked) -> None:
    """``lineno == -1`` is the filter rule the model applies."""
    _, root = linked
    action = _qname(root, "g::C::A")

    synthesized = [
        type(action.getChild(i)).__name__
        for i in range(len(action.getChildren()))
        if action.getChild(i).getLocation().lineno < 0
    ]

    assert "FieldCompRef" in synthesized


def test_file_map_resolves_fileids_after_link(linked) -> None:
    parser, _ = linked

    assert parser.file_map
    assert all(path.endswith(".pss") for path in parser.file_map.values())


def test_the_standard_library_ships_with_the_package() -> None:
    """Needed by the Phase-3 core-library reference and its reconciliation test."""
    import pssparser

    files = pssparser.get_stdlib_files()

    assert files
    names = {f.rsplit("/", 1)[-1] for f in files}
    assert {"std_pkg.pss", "addr_reg_pkg.pss"} <= names
