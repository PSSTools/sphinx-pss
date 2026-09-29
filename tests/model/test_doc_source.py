"""``PssObject.doc_source``: each line of ``raw_doc`` maps to its source line.

``raw_doc`` is normalized by the parser -- markers stripped, dedented, leading
blank lines dropped -- so its line numbers are not the comment's.
"""

from __future__ import annotations

import pathlib

import pytest

from sphinx_pss.model.index import PssIndex
from sphinx_pss.model.locations import fill_line_map, match_lines
from sphinx_pss.model.parse import parse_model

pytestmark = pytest.mark.unit

SOURCE = """\
package p {
    /** Same line.
     *
     * Body.
     */
    struct A { }
    /**

       Two lines down.
     */
    struct B { }
    /// Triple.
    ///
    /// Body.
    struct C { }
    struct D { } ///< Trailing.
}
"""


@pytest.fixture(scope="module")
def index(tmp_path_factory) -> PssIndex:
    source = tmp_path_factory.mktemp("doc_source") / "d.pss"
    source.write_text(SOURCE)
    return PssIndex(parse_model([str(source)]))


@pytest.mark.parametrize(
    "qualname,lines",
    [
        ("p::A", (2, 3, 4)),
        ("p::B", (9,)),
        ("p::C", (12, 13, 14)),
        ("p::D", (16,)),
    ],
)
def test_each_doc_line_maps_to_its_source_line(index, qualname, lines) -> None:
    doc_source = index.get(qualname).doc_source
    assert pathlib.Path(doc_source.path).name == "d.pss"
    assert doc_source.lines == lines


def test_match_lines_skips_dropped_lines() -> None:
    original = ["/**", " * First.", " *", " * Second.", " */"]
    assert match_lines(["First.", "", "Second."], original) == [1, None, 3]


def test_an_unmatched_line_follows_its_predecessor() -> None:
    assert fill_line_map([1, None, 3], base=10) == (11, 12, 13)
    assert fill_line_map([None, 0], base=5) == (5, 5)
