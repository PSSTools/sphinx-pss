"""``exec`` blocks added by ``extend`` (plan ``S2-TEST-5``, design ``STEP-T5``, section 4.5).

A type's steps for one ``exec`` kind are those of every block of that kind:
the declaration's first, then each extension's in the order the linker
processes them, which follows file order. Each block is its own group, and
numbering runs on across groups.
"""

from __future__ import annotations

import pathlib

import pytest
from support import steps_outline

from sphinx_pss.model.parse import parse_model
from sphinx_pss.model.steps import steps_for

pytestmark = pytest.mark.unit

STEPS_DIR = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "pss" / "steps"


def _send_a(*names: str):
    model = parse_model([str(STEPS_DIR / n) for n in ("eth_mac.pss", *names)])
    return steps_for(model, "eth_pkg::eth_c::send_a", exec_kind="body")


def test_the_declaration_then_each_extension_in_file_order() -> None:
    assert steps_outline(_send_a("eth_ext_a.pss", "eth_ext_b.pss")) == [
        "1 Queue the frame @160",
        "== extension @9",
        "2 Start transmission @10",
        "== extension @7",
        "3 Wait for the frame to go out @8",
    ]


def test_swapping_the_files_swaps_the_groups() -> None:
    assert steps_outline(_send_a("eth_ext_b.pss", "eth_ext_a.pss")) == [
        "1 Queue the frame @160",
        "== extension @7",
        "2 Wait for the frame to go out @8",
        "== extension @9",
        "3 Start transmission @10",
    ]


def test_each_group_names_its_block() -> None:
    doc = _send_a("eth_ext_a.pss", "eth_ext_b.pss")

    assert [(pathlib.Path(g.source.path).name, g.source.line, g.is_extension) for g in doc.groups] == [
        ("eth_mac.pss", 159, False),
        ("eth_ext_a.pss", 9, True),
        ("eth_ext_b.pss", 7, True),
    ]


def test_an_extension_in_the_same_file_is_still_an_extension(tmp_path) -> None:
    """Provenance is by declaration, not by file."""
    path = tmp_path / "t.pss"
    path.write_text(
        "package p {\n"
        "    function void w(int v);\n"
        "    component c {\n"
        "        exec init_down {\n"
        "            /// Step: Declared\n"
        "            w(1);\n"
        "        }\n"
        "    }\n"
        "    extend component c {\n"
        "        exec init_down {\n"
        "            /// Step: Extended\n"
        "            w(2);\n"
        "        }\n"
        "    }\n"
        "}\n"
    )
    doc = steps_for(parse_model([str(path)]), "p::c", exec_kind="init_down")

    assert [g.is_extension for g in doc.groups] == [False, True]
    assert steps_outline(doc) == ["1 Declared @5", "== extension @10", "2 Extended @11"]


def test_only_blocks_of_the_kind_asked_for(tmp_path) -> None:
    path = tmp_path / "t.pss"
    path.write_text(
        "package p {\n"
        "    function void w(int v);\n"
        "    component c {\n"
        "        exec init_up {\n"
        "            /// Step: Up\n"
        "            w(1);\n"
        "        }\n"
        "        exec init_down {\n"
        "            /// Step: Down\n"
        "            w(2);\n"
        "        }\n"
        "    }\n"
        "}\n"
    )
    model = parse_model([str(path)])

    assert steps_outline(steps_for(model, "p::c", exec_kind="init_up")) == ["1 Up @5"]
    assert steps_outline(steps_for(model, "p::c", exec_kind="init_down")) == ["1 Down @9"]
