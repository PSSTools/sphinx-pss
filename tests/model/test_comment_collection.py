"""Comment collection changes nothing the documentation reads (``S0-TEST-3``).

``parse_model`` turned on ``collect_comments`` for programming steps. The
readiness review showed, over the fixtures and the corpus, that the object
model is identical either way (programming-steps plan section 1.1); this keeps
it so. The corpus half of the check is ``tests/corpus/test_comment_collection.py``.
"""

from __future__ import annotations

import pathlib

import pytest

from support import model_snapshot

pytestmark = pytest.mark.unit

FIXTURE_DIR = pathlib.Path(__file__).parents[1] / "fixtures" / "pss"

#: Every fixture, in the combinations that link. ``dma_ext.pss`` extends
#: ``dma_pkg.pss`` and cannot be parsed without it.
SOURCE_SETS = [
    ["dma_pkg.pss"],
    ["dma_pkg.pss", "dma_ext.pss"],
    ["steps_pkg.pss"],
]


def test_every_fixture_is_covered() -> None:
    covered = {name for names in SOURCE_SETS for name in names}
    assert covered == {p.name for p in FIXTURE_DIR.glob("*.pss")}


def _snapshot(names):
    from sphinx_pss.model.index import PssIndex
    from sphinx_pss.model.parse import parse_model

    model = parse_model([str(FIXTURE_DIR / n) for n in names])
    return model, model_snapshot(PssIndex(model))


@pytest.mark.parametrize("names", SOURCE_SETS, ids="+".join)
def test_collecting_comments_leaves_the_object_model_unchanged(
    names, request
) -> None:
    _, with_comments = _snapshot(names)
    request.getfixturevalue("without_comment_collection")
    _, without = _snapshot(names)

    assert with_comments == without


def test_parse_model_collects_comments(pss_fixture_dir) -> None:
    """Otherwise the comparison above compares two identical parses."""
    from pssparser.utils import SymbolScopeUtil

    from sphinx_pss.model.comments import comments_of
    from sphinx_pss.model.parse import parse_model

    model = parse_model([str(pss_fixture_dir / "steps_pkg.pss")])
    body = SymbolScopeUtil(model.root).getQname("mac_pkg::init_mac").getTarget().getBody()

    texts = [c.text for i in range(len(body.getChildren())) for c in comments_of(body.getChild(i))]
    assert "Step: Reset the MAC" in texts


def test_the_fixture_really_turns_collection_off(
    pss_fixture_dir, without_comment_collection
) -> None:
    from pssparser.utils import SymbolScopeUtil

    from sphinx_pss.model.comments import comments_of
    from sphinx_pss.model.parse import parse_model

    model = parse_model([str(pss_fixture_dir / "steps_pkg.pss")])
    body = SymbolScopeUtil(model.root).getQname("mac_pkg::init_mac").getTarget().getBody()

    assert all(comments_of(body.getChild(i)) == [] for i in range(len(body.getChildren())))
