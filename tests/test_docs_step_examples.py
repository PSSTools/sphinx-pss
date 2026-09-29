"""The examples in ``docs/usage/steps.md`` do what the page says they do.

Each ``pss`` block named ``step-example-<name>`` is checked inside a package,
as ``drv.pss``, with the register helpers the examples call. The ``text`` block
after it is the output the page shows; the lint must produce exactly those
warnings, at those lines. A block with no ``text`` block after it must produce
none. So the page can't claim a warning the code doesn't give, or miss one it
does.

``pss.step_prelude_call`` is only given for a body a table shows, so each
function in an example is taken as shown.

The page's first example is included straight from the fixture, whose
silence ``tests/model/test_step_lint.py`` asserts.
"""

from __future__ import annotations

import pathlib
import re

import pytest

pytestmark = pytest.mark.unit

PAGE = pathlib.Path(__file__).resolve().parents[1] / "docs" / "usage" / "steps.md"

#: The example sits on the second line of the file, after ``package drv {``,
#: so the page's line numbers are the snippet's plus one.
_PRELUDE = "package drv {\n"
_HELPERS = (
    "    function void write_reg(bit[32] offset, bit[32] value);\n"
    "    function bit[32] read_reg(bit[32] offset);\n"
    "}\n"
)

_BLOCK_RE = re.compile(
    r"```\{code-block\} pss\n:name: step-example-(?P<name>[\w-]+)\n\n"
    r"(?P<code>.*?)```\n"
    r"(?:\n```text\n(?P<output>.*?)```\n)?",
    re.DOTALL,
)
_WARNING_RE = re.compile(r"^drv\.pss:(\d+): WARNING: (.*) \[pss\.(\w+)\]$")


def _examples() -> list:
    text = PAGE.read_text()
    found = [
        pytest.param(m.group("code"), m.group("output") or "", id=m.group("name"))
        for m in _BLOCK_RE.finditer(text)
    ]
    assert len(found) == text.count(":name: step-example-"), "an example didn't match"
    return found


def test_the_page_has_examples() -> None:
    names = {p.id for p in _examples()}
    assert {"syntax", "misplaced", "empty", "valid-placements", "prelude-call"} <= names


@pytest.mark.parametrize("code,output", _examples())
def test_the_example_gives_the_warnings_shown(tmp_path, code, output) -> None:
    from sphinx_pss.model.parse import parse_model
    from sphinx_pss.model.steps_lint import lint_markers

    path = tmp_path / "drv.pss"
    path.write_text(_PRELUDE + code + _HELPERS)
    model = parse_model([str(path)])
    assert model.linked

    shown = [_WARNING_RE.match(line).groups() for line in output.splitlines()]
    issues = lint_markers(model) + _prelude_issues(model, code)
    actual = [(str(i.line), i.message, i.code) for i in sorted(issues, key=lambda i: i.line)]
    assert actual == shown


def _prelude_issues(model, code: str) -> list:
    """``pss.step_prelude_call`` problems, as if a table showed each function in ``code``."""
    from sphinx_pss.model.steps import StepsError, steps_for

    found = []
    for name in re.findall(r"function\s+[\w\[\]]+\s+(\w+)\s*\(", code):
        try:
            found += steps_for(model, f"drv::{name}").issues
        except StepsError:
            pass
    return found


def test_the_placements_example_nests_as_the_page_says(tmp_path) -> None:
    """"``Reset the RMII module`` is a sub-step of ``Select the interface mode``",
    and the ``if`` is shown, labelled with its condition."""
    from support import steps_outline

    from sphinx_pss.model.parse import parse_model
    from sphinx_pss.model.steps import steps_for

    [code] = [p.values[0] for p in _examples() if p.id == "valid-placements"]
    path = tmp_path / "drv.pss"
    path.write_text(_PRELUDE + code + _HELPERS)

    assert steps_outline(steps_for(parse_model([str(path)]), "drv::configure")) == [
        "1 Select the interface mode @3",
        "  if rmii*",
        "    1.1 Reset the RMII module @5",
        "2 Set the MDC clock divider @9",
        "3 Enable the receiver @12",
    ]
