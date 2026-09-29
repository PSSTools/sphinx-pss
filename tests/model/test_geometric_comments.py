"""The test-only comment provider agrees with the parser (activity-diagrams plan ``AD4-TEST-1``).

`support.geometric_comments` stands in for pssparser ``AC1``-``AC3`` in the
activity-steps tests. It is only a fair stand-in if it attaches comments the
way the parser does, so it is checked here against the parser on procedural
code, where the parser already attaches them.
"""

from __future__ import annotations

import pytest

from sphinx_pss.model.calls import function_body, symbol_index
from sphinx_pss.model.comments import comments_of
from sphinx_pss.model.parse import iter_children, parse_model
from sphinx_pss.model.steps_lint import _sub_blocks
from support import geometric_comments

pytestmark = pytest.mark.unit

SOURCE = """\
package p {
    function void w(int v);
    function void f(bool b, int x) {
        /// leading
        w(1);
        w(2); /// trailing
        /// detached

        w(3);
        /// a
        /// run
        if (b) {
            /// in if
            w(4);
            /// closing if
        } else {
            w(5); // plain trailing
        }
        /* block */
        while (x > 0) { w(6); }
        repeat {
            w(7);
        } while (b); /// after a do-while
        /// closing
    }
}
"""


def _key(comments) -> list[tuple[str, int, int]]:
    return sorted((c.raw.strip(), c.line, int(c.placement)) for c in comments)


def test_it_attaches_what_the_parser_attaches(tmp_path) -> None:
    path = tmp_path / "t.pss"
    path.write_text(SOURCE)
    model = parse_model([str(path)])
    statement_comments, _ = geometric_comments(model)
    body = function_body(symbol_index(model).scopes["p::f"])

    compared = 0

    def walk(node) -> None:
        nonlocal compared
        ours = _key(statement_comments(node))
        loc = node.getLocation() if hasattr(node, "getLocation") else None
        if loc is not None and loc.lineno == 21:
            # The parser loses a trailing comment after `} while (b);`
            # (pssparser AC5, guarded in test_upstream_activity.py): the
            # stand-in keeps it, as the request asks.
            assert ours == [("/// after a do-while", 23, 1)]
            ours = []
        assert ours == _key(comments_of(node)), node
        compared += bool(comments_of(node))
        for sub in _sub_blocks(node):
            walk(sub)

    for stmt in iter_children(body):
        walk(stmt)
    # Every commented statement above was compared, not skipped.
    assert compared == 7
