"""No step warnings anywhere in the corpus (plan ``S1-TEST-3``, design ``STEP-T3``).

pss-corpus contains no step markers, but it has plenty of ordinary comments,
doc comments on declarations, and prose that mentions steps. A warning here
means the lint reads something it should not: that is the false positive
design section 3.2 exists to rule out. A file that does not parse is skipped
here; the comment-collection sweep already reports it.
"""

from __future__ import annotations

import pytest

from corpus_finder import corpus_files, corpus_id, require

pytestmark = pytest.mark.corpus


@pytest.mark.parametrize("path", corpus_files(), ids=corpus_id)
def test_the_corpus_has_no_step_warnings(path) -> None:
    from sphinx_pss.model.parse import PssParseError, parse_model
    from sphinx_pss.model.steps_lint import lint_markers

    path = require(path)
    try:
        model = parse_model([str(path)], tolerate_link_errors=True)
    except PssParseError:
        return

    assert [f"{i.location()}: {i.message}" for i in lint_markers(model)] == []
