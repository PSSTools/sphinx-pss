"""Every body in the corpus builds a step tree without failing (plan S2, robustness).

pss-corpus has no step markers, so every tree is empty. What this exercises is
the machinery that runs on every body regardless: the statement walk, call
resolution through ``refs.occurrences()``, and the token scan that bounds each
statement (`sphinx_pss.model.source_text`), over real code the fixtures don't
imitate. A file that doesn't parse or link is skipped: steps need a linked
model, and the comment-collection sweep reports parse failures.
"""

from __future__ import annotations

import pytest

from corpus_finder import corpus_files, corpus_id, require

pytestmark = pytest.mark.corpus


@pytest.mark.parametrize("path", corpus_files(), ids=corpus_id)
def test_every_body_builds_a_step_tree(path) -> None:
    from pssparser import ast

    from sphinx_pss.model.calls import function_body, symbol_index
    from sphinx_pss.model.locations import STDLIB_FILEID, node_type_name
    from sphinx_pss.model.parse import PssParseError, iter_children, parse_model
    from sphinx_pss.model.steps import EXEC_KINDS, StepsError, steps_for

    path = require(path)
    try:
        model = parse_model([str(path)])
    except PssParseError:
        return

    targets = []
    for qualname, scope in symbol_index(model).scopes.items():
        loc = scope.getLocation()
        if loc is None or loc.fileid == STDLIB_FILEID:
            continue
        kind = node_type_name(scope)
        if kind == "SymbolFunctionScope" and function_body(scope) is not None:
            targets.append((qualname, None))
        elif kind == "SymbolTypeScope":
            kinds = [c.getKind() for c in iter_children(scope) if node_type_name(c) == "ExecBlock"]
            targets += [
                (qualname, name)
                for name, k in EXEC_KINDS.items()
                if getattr(ast.ExecKind, k) in kinds
            ]

    failures = []
    for qualname, exec_kind in targets:
        try:
            doc = steps_for(model, qualname, exec_kind=exec_kind)
        except StepsError as e:
            failures.append(f"{qualname} {exec_kind or ''}: {e}")
            continue
        if list(doc.steps()) or doc.issues:
            failures.append(f"{qualname} {exec_kind or ''}: steps in a corpus without markers")
    assert failures == []
