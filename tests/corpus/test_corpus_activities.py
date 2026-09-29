"""Every activity in the corpus lifts, draws and step-passes (activity-diagrams plan ``AD4-TEST-4``).

pss-corpus has no step markers, so no activity has steps. What this exercises
is the machinery that runs on every activity: the lift over real code the
fixtures don't imitate, target resolution, the token lookups, and the lowering
at the deepest depth. A file that doesn't parse or link is skipped, as for
steps.
"""

from __future__ import annotations

import pytest

from corpus_finder import corpus_files, corpus_id, require

pytestmark = pytest.mark.corpus


@pytest.mark.parametrize("path", corpus_files(), ids=corpus_id)
def test_every_activity_lifts_and_draws(path) -> None:
    from sphinx_pss.model.activity import Unknown, activity_for
    from sphinx_pss.model.activity_diagram import MAX_DEPTH, activity_diagram
    from sphinx_pss.model.activity_steps import has_steps, stepped
    from sphinx_pss.model.calls import symbol_index
    from sphinx_pss.model.locations import STDLIB_FILEID, node_type_name
    from sphinx_pss.model.parse import PssParseError, iter_children, parse_model

    path = require(path)
    try:
        model = parse_model([str(path)])
    except PssParseError:
        return
    if not model.linked:
        return

    failures = []
    for qualname, scope in symbol_index(model).scopes.items():
        loc = scope.getLocation()
        if loc is None or loc.fileid == STDLIB_FILEID or node_type_name(scope) != "SymbolTypeScope":
            continue
        if not any(node_type_name(c) == "ActivityDecl" for c in iter_children(scope)):
            continue
        try:
            activity = activity_for(model, qualname)
            steps = stepped(model, activity)
            activity_diagram(model, activity, depth=MAX_DEPTH)
        except Exception as e:  # noqa: BLE001 - any failure is the finding
            failures.append(f"{qualname}: {type(e).__name__}: {e}")
            continue
        unknown = [n.node_type for n in activity.nodes() if isinstance(n, Unknown)]
        if unknown:
            failures.append(f"{qualname}: unknown statements {unknown}")
        if has_steps(steps) or steps.issues != activity.issues:
            failures.append(f"{qualname}: steps in a corpus without markers")
    assert failures == []
