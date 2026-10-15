"""pssparser behaviors that activity diagrams depend on (plan ``AD0-TEST-2``).

Each docstring names the part of ``design/activity-diagrams-design.md`` that
depends on the guard, and what to do when it fails. Several assert behavior
that is *expected to change*: those fail on purpose when pssparser fixes it, so
the fallback built around it can be removed.

These talk to ``pssparser`` directly, not through ``sphinx_pss``, so that a
failure here says "the parser changed" rather than "our wrapper changed".
"""

from __future__ import annotations

import pytest
from support import parser_comments_activities

pytestmark = pytest.mark.upstream

SOURCE = """\
package p {
    component c {
        action a { rand int x; }
        action top {
            a a1, a2;
            activity {
                /// Step: first
                a1;
                atomic {
                    a1;
                    a2;
                }
                bind a1.x
                     a2.x;
                lbl: do a1;
                /// Step: closing
            }
        }
    }
}
"""


def _children(node) -> list:
    return [node.getChild(i) for i in range(len(node.getChildren()))]


#: Parsers kept alive for the module: the tree is freed with its parser.
_PARSERS: list = []


@pytest.fixture(scope="module")
def top():
    from pssparser import Parser
    from pssparser.utils import SymbolScopeUtil

    parser = Parser(collect_docstrings=True, collect_comments=True)
    parser.parses([("t.pss", SOURCE)])
    root = parser.link()
    _PARSERS.append(parser)
    return SymbolScopeUtil(root).getQname("p::c::top")


@pytest.fixture(scope="module")
def activity(top):
    return next(c for c in _children(top) if type(c).__name__ == "ActivityDecl")


def test_ac1_activity_statements_carry_comments_from_3_3_0(activity) -> None:
    """Design 4.7: steps in activities need pssparser AC1-AC3, released in 3.3.0.

    Before 3.3.0 no activity statement carries a comment. The token-scan
    fallback, ``pss.step_unsupported`` and ``geometric_comments`` in
    ``tests/support.py`` stay while the floor is ``pssparser>=3.1.0``; they can
    go when the floor reaches 3.3.0 (plan decision D4).
    """
    stmts = _children(activity)
    if parser_comments_activities():
        assert stmts[0].numComments() == 1
        assert activity.numTrailing_comments() == 1
    else:
        assert all(s.numComments() == 0 for s in stmts)
        assert activity.numTrailing_comments() == 0


def test_ac1_the_capability_probe_agrees(activity) -> None:
    """Design 4.7: the run-time probe decides whether steps are read in activities.

    Checked against the parse above rather than a constant, so the probe can't
    drift from what the parser actually does.
    """
    from sphinx_pss._capability import activity_comments_supported

    assert activity_comments_supported() is (_children(activity)[0].numComments() > 0)


def test_r1_the_atomic_body_is_unlocated(activity) -> None:
    """Design 2, R1: the atomic body must not be dropped as compiler-injected.

    pssparser 3.3.0 locates the body and the block's end. The span fallback
    for ``atomic`` in ``model/activity.py`` can go when the floor reaches 3.3.0.
    """
    atomic = next(s for s in _children(activity) if type(s).__name__ == "ActivityAtomicBlock")
    assert atomic.getLocation().lineno == 9
    if parser_comments_activities():
        assert atomic.getEndLocation().lineno == 12
        assert atomic.getBody().getLocation().lineno == 9
    else:
        assert atomic.getEndLocation().lineno == -1
        assert atomic.getBody().getLocation().lineno == -1


def test_r2_a_bind_has_no_end_location(activity) -> None:
    """Design 2, R2: nothing needs a bind's end, so there is no fallback to remove.

    pssparser 3.3.0 records it.
    """
    bind = next(s for s in _children(activity) if type(s).__name__ == "ActivityBindStmt")
    assert bind.getLocation().lineno == 13
    assert bind.getEndLocation().lineno == (14 if parser_comments_activities() else -1)


def test_labels_are_listed_in_the_action_scope(top) -> None:
    """Design 2: the builder must skip ``Activity*`` when collecting an action's members.

    A labeled top-level statement is listed among the action's children, as
    the same node as in the activity (LRM 11.8 label resolution).
    """
    kinds = [type(c).__name__ for c in _children(top)]
    assert "ActivityActionTypeTraversal" in kinds


def test_do_on_a_field_is_a_type_traversal_resolving_to_the_field(activity) -> None:
    """Design 2 and 3.3: handle versus type is decided by what the target resolves to."""
    stmt = _children(activity)[-1]
    assert type(stmt).__name__ == "ActivityActionTypeTraversal"
    target = stmt.getTarget().getType_id().getTarget()
    assert target is not None


def test_ac5_a_trailing_comment_after_a_do_while() -> None:
    """pssparser AC5 (``sphinx-pss-requests-2026-09-29.md``): the comment reaches no node.

    Procedural code, but the same rule will apply to ``repeat { } while (c);``
    in activities. Fixed in pssparser 3.3.0; the exception for it in
    ``tests/model/test_geometric_comments.py`` applies only before that.
    """
    from pssparser import Parser
    from pssparser.utils import SymbolScopeUtil

    parser = Parser(collect_docstrings=True, collect_comments=True)
    parser.parses(
        [
            (
                "t.pss",
                "package p {\n"
                "    function void w(int v);\n"
                "    function void f(bool b) {\n"
                "        repeat {\n"
                "            w(1);\n"
                "        } while (b); /// after\n"
                "    }\n"
                "}\n",
            )
        ]
    )
    root = parser.link()
    _PARSERS.append(parser)
    body = SymbolScopeUtil(root).getQname("p::f").getBody()
    stmt = body.getChild(0)

    if parser_comments_activities():
        assert stmt.numComments() == 1
        return
    assert stmt.numComments() == 0
    assert body.numTrailing_comments() == 0
    assert all(stmt.getBody().getChild(i).numComments() == 0 for i in range(len(stmt.getBody().getChildren())))
