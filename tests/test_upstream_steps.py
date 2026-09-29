"""pssparser behaviors that programming steps depend on (plan ``S0-TEST-1``).

One guard per row of ``design/programming-steps-plan.md`` section 1.1, plus the
call-resolution route of section 1.2. Each docstring names the part of
``design/programming-steps-design.md`` that breaks if the guard does.

These talk to ``pssparser`` directly, not through ``sphinx_pss``, so that a
failure here says "the parser changed" rather than "our wrapper changed".
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.upstream


def _parse(*files: tuple[str, str]):
    from pssparser import Parser

    parser = Parser(collect_docstrings=True, collect_comments=True)
    parser.parses(list(files))
    return parser, parser.link()


def _qname(root, name):
    from pssparser.utils import SymbolScopeUtil

    return SymbolScopeUtil(root).getQname(name)


def _children(node) -> list:
    return [node.getChild(i) for i in range(len(node.getChildren()))]


def _comments(node) -> list[tuple[str, int]]:
    return sorted(
        (
            (node.getComment(i).getRaw(), node.getComment(i).getPlacement())
            for i in range(node.numComments())
        ),
        key=lambda c: c[0],
    )


def _exec_blocks(type_scope) -> list:
    return [c for c in _children(type_scope) if type(c).__name__ == "ExecBlock"]


# --- comments on statements ---------------------------------------------------

PLACEMENTS = """\
package p {
    function void w(int v);
    function void f() {
        /// leading
        w(1);
        w(2); /// trailing
        /// detached

        w(3);
        /// closing
    }
    component c {
        exec init_down {
            /// in exec
            w(4);
        }
    }
}
"""


@pytest.fixture(scope="module")
def placements():
    return _parse(("t.pss", PLACEMENTS))


def test_statements_carry_comments_in_every_placement(placements) -> None:
    """Design 3.3 / 3.4 / 6.1: markers are valid leading, trailing, or detached.

    ``collect_comments`` is what provides these; the docstring API drops the
    trailing and detached forms, which is why the design reads comments.
    """
    _, root = placements
    body = _qname(root, "p::f").getTarget().getBody()
    w1, w2, w3 = _children(body)

    assert _comments(w1) == [("/// leading\n", 0)]
    assert _comments(w2) == [("/// trailing\n", 1)]
    assert _comments(w3) == [("/// detached\n", 2)]


def test_a_comment_after_the_last_statement_is_kept_on_the_block(placements) -> None:
    """Design 3.5 (``pss.step_empty``): a marker with nothing after it.

    With no statement to attach to, the parser keeps it on the enclosing
    scope. Regressing drops it silently, so an empty step is never reported.
    """
    _, root = placements
    body = _qname(root, "p::f").getTarget().getBody()

    raws = [body.getTrailing_comment(i).getRaw() for i in range(body.numTrailing_comments())]
    assert raws == ["/// closing\n"]


def test_exec_block_statements_carry_comments(placements) -> None:
    """Design 3.4: ``exec`` blocks are marked exactly like function bodies."""
    _, root = placements
    [block] = _exec_blocks(_qname(root, "p::c"))
    [w4] = _children(block)

    assert _comments(w4) == [("/// in exec\n", 0)]


@pytest.mark.parametrize(
    "comment",
    ["/// line doc", "// line", "/** block doc */", "/* block */"],
)
def test_get_raw_is_verbatim(comment) -> None:
    """Design 3.3, rule 1: ``getRaw()`` is what tells ``///`` from ``//``.

    ``getText()`` is not usable for this: on ``///`` it strips two slashes and
    keeps the third.
    """
    _, root = _parse(
        ("t.pss", f"package p {{ function void w(); function void f() {{\n{comment}\nw(); }} }}")
    )
    [call] = _children(_qname(root, "p::f").getTarget().getBody())

    assert call.getComment(0).getRaw().rstrip("\n") == comment
    assert bool(call.getComment(0).getIs_block()) == comment.startswith("/*")


# --- exec blocks and extensions ------------------------------------------------

EXEC_BASE = """\
package p {
    function void w(int v);
    component c {
        exec init_down { w(0); }
        exec body { w(9); }
    }
}
"""


def _exec_ext(n: int) -> str:
    return f"package e{n} {{ import p::*; extend component p::c {{ exec init_down {{ w({n}); }} }} }}\n"


def _init_down_files(order: list[str]) -> list[str]:
    """Parse ``base.pss`` and the named extensions in ``order``; report the
    file each ``init_down`` block of the linked component came from."""
    from pssparser.ast import ExecKind

    sources = {"base": EXEC_BASE, "ext1": _exec_ext(1), "ext2": _exec_ext(2)}
    parser, root = _parse(*((f"{name}.pss", sources[name]) for name in order))
    blocks = _exec_blocks(_qname(root, "p::c"))
    return [
        parser.file_map[b.getLocation().fileid].rsplit("/", 1)[-1]
        for b in blocks
        if b.getKind() == ExecKind.ExecKind_InitDown
    ]


def test_extension_exec_blocks_follow_file_order() -> None:
    """Design 4.5: the order of the ``extend`` statements dictates step order.

    The linked type holds every ``ExecBlock``, the declaration's first, then
    each extension's in the order its file was parsed.
    """
    assert _init_down_files(["base", "ext1", "ext2"]) == ["base.pss", "ext1.pss", "ext2.pss"]
    assert _init_down_files(["base", "ext2", "ext1"]) == ["base.pss", "ext2.pss", "ext1.pss"]


def test_exec_blocks_report_their_kind() -> None:
    """Design 7.1 / plan D4: ``:exec: <kind>`` selects blocks by ``getKind()``."""
    from pssparser.ast import ExecKind

    _, root = _parse(("base.pss", EXEC_BASE))
    kinds = [b.getKind() for b in _exec_blocks(_qname(root, "p::c"))]

    assert kinds == [ExecKind.ExecKind_InitDown, ExecKind.ExecKind_Body]


# --- statement positions and the token stream ------------------------------------

CONTROL = """\
package p {
    function bit[32] r();
    function void w(int v);
    function void f(bool b) {
        if (b) {
            w(1);
        } else {
            w(2);
        }
        while (((r() & 0x8000)) != 0) { }
        repeat (4) { w(3); }
    }
}
"""


@pytest.fixture(scope="module")
def control():
    return _parse(("t.pss", CONTROL))


def test_statements_and_clause_bodies_are_located(control) -> None:
    """Design 4.3 / 6.1: every step and condition is found by position."""
    _, root = control
    body = _qname(root, "p::f").getTarget().getBody()
    stmts = _children(body)

    assert [(s.getLocation().lineno, s.getLocation().linepos) for s in stmts] == [
        (5, 9),
        (10, 9),
        (11, 9),
    ]
    clause = stmts[0].getIf_then(0)
    assert clause.getBody().getLocation().lineno == 5
    assert [type(s).__name__ for s in stmts] == [
        "ProceduralStmtIfElse",
        "ProceduralStmtWhile",
        "ProceduralStmtRepeat",
    ]


def test_the_token_stream_is_lossless_and_aligned_with_statements(control) -> None:
    """Design 4.3: condition text comes from tokens, parentheses and all.

    Two facts: joining the tokens gives back the source byte for byte, and a
    statement's ``(lineno, linepos)`` finds its keyword token, whose ``col`` is
    0-based where ``linepos`` is 1-based.
    """
    from pssparser import tokens

    _, root = control
    ts = tokens.tokenize(CONTROL.encode())
    assert "".join(t.text for t in ts.tokens) == CONTROL

    [_, loop, _] = _children(_qname(root, "p::f").getTarget().getBody())
    loc = loop.getLocation()
    toks = list(ts.tokens)
    [start] = [i for i, t in enumerate(toks) if t.line == loc.lineno and t.col == loc.linepos - 1]
    assert toks[start].text == "while"

    # The condition: everything inside the keyword's outermost parentheses.
    depth, cond = 0, []
    for t in toks[start + 1 :]:
        if t.text == ")":
            depth -= 1
            if depth == 0:
                break
        if depth > 0:
            cond.append(t.text)
        if t.text == "(":
            depth += 1
    assert "".join(cond) == "((r() & 0x8000)) != 0"


def test_comment_tokens_are_on_their_own_channels() -> None:
    """Plan ``S5-IMPL-1``: the plain-comment lint scans comment channels only."""
    from pssparser import tokens

    ts = tokens.tokenize(b"// a\n/* b */\nx")
    channels = {t.text: t.channel for t in ts.tokens if t.is_comment}

    # A line comment's token includes its newline.
    assert channels == {
        "// a\n": tokens.CHANNEL_SL_COMMENT,
        "/* b */": tokens.CHANNEL_ML_COMMENT,
    }


# --- call resolution -----------------------------------------------------------

CALLS = """\
package p {
    function void pkg_fn();
    component sub_c {
        function void sub_fn() { }
    }
    component pss_top {
        sub_c sub;
        function void top_fn() { }
        action a {
            exec body {
                comp.sub.sub_fn();
                comp.top_fn();
                pkg_fn();
            }
        }
    }
}
"""


def _callee(root, occurrences, stmt):
    """The plan section 1.2 route: last path element -> occurrence -> scope."""
    hier = stmt.getExpr().getHier_id()
    last = hier.getElem(hier.numElems() - 1).getId().getLocation()
    return occurrences[(last.fileid, last.lineno, last.linepos)]


def test_member_calls_resolve_through_occurrences() -> None:
    """Plan 1.2 / design 4.4: calls are expanded by following them.

    ``ExprRefPathContext.getTarget()`` resolves only the first path element,
    so ``comp.sub.sub_fn()`` is followed through ``refs.occurrences()`` at the
    last element's position, then from its ``FunctionPrototype`` to the
    function's symbol scope. Regressing makes member calls unexpandable.
    """
    from pssparser import refs

    parser, root = _parse(("t.pss", CALLS))
    occurrences = {(o.fileid, o.line, o.col): o for o in refs.occurrences(root)}
    [block] = _exec_blocks(_qname(root, "p::pss_top::a"))

    targets = []
    for stmt in _children(block):
        occ = _callee(root, occurrences, stmt)
        assert occ.resolution == refs.Resolution.USER
        assert type(occ.decl).__name__ == "FunctionPrototype"
        targets.append(occ.decl)

    # A prototype has no parent; each is found from its scope's prototypes,
    # and the wrappers compare and hash by node.
    by_proto = {}
    for qname in ("p::sub_c::sub_fn", "p::pss_top::top_fn", "p::pkg_fn"):
        scope = _qname(root, qname)
        for i in range(scope.numPrototypes()):
            by_proto[scope.getPrototype(i)] = qname

    assert [by_proto[t] for t in targets] == [
        "p::sub_c::sub_fn",
        "p::pss_top::top_fn",
        "p::pkg_fn",
    ]


def test_first_element_targets_stop_at_the_field() -> None:
    """Plan 1.2: why the occurrence route exists.

    When this starts resolving the whole path, the route can be simplified to
    ``getTarget()``; update the plan rather than just this test.
    """
    _, root = _parse(("t.pss", CALLS))
    [block] = _exec_blocks(_qname(root, "p::pss_top::a"))
    member_call = _children(block)[0]

    target = member_call.getExpr().getTarget()
    assert type(target).__name__ != "SymbolFunctionScope"
