"""Comment collection changes nothing the documentation reads, corpus-wide.

The corpus half of ``S0-TEST-3`` (the fixture half is
``tests/model/test_comment_collection.py``). Each file is parsed on its own,
with ``pss_tolerate_link_errors`` semantics, so both the linked and the
degraded paths are compared. A file must behave identically either way: the
same error, or the same object model.

No list of known failures is kept: whether a file links is pssparser's
business, and a change there shows up in both halves of the comparison.
"""

from __future__ import annotations

import pytest

from corpus_finder import corpus_files, corpus_id, require
from support import model_snapshot

pytestmark = pytest.mark.corpus


def _outcome(path):
    from sphinx_pss.model.index import PssIndex
    from sphinx_pss.model.parse import PssParseError, parse_model

    try:
        model = parse_model([str(path)], tolerate_link_errors=True)
    except PssParseError as e:
        return ("error", str(e))
    return ("linked" if model.linked else "degraded", model_snapshot(PssIndex(model)))


@pytest.mark.parametrize("path", corpus_files(), ids=corpus_id)
def test_collecting_comments_leaves_the_object_model_unchanged(path, request) -> None:
    path = require(path)
    with_comments = _outcome(path)
    request.getfixturevalue("without_comment_collection")
    without = _outcome(path)

    assert with_comments == without
