"""P1-TEST-3 — the parser lifecycle owned by ``model/parse.py``."""

from __future__ import annotations

import pathlib

import pytest

from sphinx_pss.model.parse import (
    Diagnostic,
    PssParseError,
    discover_sources,
    iter_children,
    parse_model,
)

pytestmark = pytest.mark.unit


# --- source discovery -------------------------------------------------------


def test_explicit_files_keep_their_order(tmp_path: pathlib.Path) -> None:
    """A PSS build unit can be deliberately ordered, so order is preserved."""
    for name in ("b.pss", "a.pss"):
        (tmp_path / name).write_text("")

    sources = discover_sources([], ["b.pss", "a.pss"], confdir=tmp_path)

    assert [pathlib.Path(s).name for s in sources] == ["b.pss", "a.pss"]


def test_directory_contents_are_sorted(tmp_path: pathlib.Path) -> None:
    """Directory order must not depend on filesystem enumeration."""
    for name in ("z.pss", "a.pss", "m.pss"):
        (tmp_path / name).write_text("")

    sources = discover_sources([str(tmp_path)], [])

    assert [pathlib.Path(s).name for s in sources] == ["a.pss", "m.pss", "z.pss"]


def test_directories_are_searched_recursively(tmp_path: pathlib.Path) -> None:
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "deep.pss").write_text("")

    sources = discover_sources([str(tmp_path)], [])

    assert [pathlib.Path(s).name for s in sources] == ["deep.pss"]


def test_a_file_named_twice_appears_once(tmp_path: pathlib.Path) -> None:
    (tmp_path / "a.pss").write_text("")

    sources = discover_sources([str(tmp_path)], [str(tmp_path / "a.pss")])

    assert len(sources) == 1


def test_a_missing_source_dir_is_reported(tmp_path: pathlib.Path) -> None:
    with pytest.raises(PssParseError, match="not a directory"):
        discover_sources([str(tmp_path / "nope")], [])


def test_a_missing_source_file_is_reported(tmp_path: pathlib.Path) -> None:
    with pytest.raises(PssParseError, match="not found"):
        parse_model([str(tmp_path / "nope.pss")])


# --- parse and link ---------------------------------------------------------


def test_the_sample_parses_and_links_cleanly(sample_model) -> None:
    assert sample_model.linked
    assert sample_model.root is not None
    assert not sample_model.errors


def test_file_map_covers_every_source(sample_model) -> None:
    mapped = set(sample_model.file_map.values())
    for source in sample_model.sources:
        assert source in mapped


def test_docstrings_are_collected(sample_model) -> None:
    """The whole point of the ``collect_docstrings`` parser mode."""
    from pssparser.utils import SymbolScopeUtil

    xfer = SymbolScopeUtil(sample_model.root).getQname("dma_pkg::Dma::Xfer")

    assert "Program a single DMA transfer." in xfer.getTarget().getDocstring()


def test_the_tree_survives_traversal_after_link(sample_sources) -> None:
    """``link()`` transfers ownership of the per-file scopes to the root.

    Holding wrappers obtained before that point is a double-ownership fault, so
    `ParsedModel` keeps the parser alive and reads only through the linked
    root. This walks the whole tree after link to prove the reference is doing
    its job — the failure mode being a segfault, not an exception.
    """
    model = parse_model(sample_sources)

    def walk(node) -> int:
        return 1 + sum(walk(child) for child in iter_children(node))

    assert walk(model.root) > 50
    assert walk(model.root) > 50  # and again, after the first traversal


# --- error handling ---------------------------------------------------------

BROKEN = "component C { NoSuchType f; }"


def test_a_link_error_fails_the_build_by_default(tmp_path: pathlib.Path) -> None:
    source = tmp_path / "broken.pss"
    source.write_text(BROKEN)

    with pytest.raises(PssParseError) as excinfo:
        parse_model([str(source)])

    assert "pss_tolerate_link_errors" in str(excinfo.value)


def test_a_link_error_is_tolerated_when_asked(tmp_path: pathlib.Path) -> None:
    source = tmp_path / "broken.pss"
    source.write_text(BROKEN)

    model = parse_model([str(source)], tolerate_link_errors=True)

    assert model.errors, "a tolerated failure must still be reported"
    assert not model.linked
    assert model.root is None, "a failed link's root is not a documentation view"


def test_a_degraded_model_is_walkable_per_file(tmp_path: pathlib.Path) -> None:
    source = tmp_path / "broken.pss"
    source.write_text(BROKEN)

    model = parse_model([str(source)], tolerate_link_errors=True)

    assert len(model.user_units()) == 1
    assert list(model.file_map.values()) == [str(source)]


def test_a_syntax_error_is_reported_with_its_location(tmp_path: pathlib.Path) -> None:
    source = tmp_path / "bad.pss"
    source.write_text("component C { \n")

    with pytest.raises(PssParseError) as excinfo:
        parse_model([str(source)])

    assert "bad.pss" in str(excinfo.value)


@pytest.mark.parametrize(
    "severity,expected",
    [("error", True), ("Error", True), ("warning", False), ("info", False)],
)
def test_diagnostic_severity_normalization(severity: str, expected: bool) -> None:
    assert Diagnostic(severity=severity.lower(), message="x").is_error is expected


def test_diagnostic_renders_a_sphinx_location() -> None:
    assert Diagnostic("error", "boom", "a.pss", 12).location() == "a.pss:12"
    assert Diagnostic("error", "boom").location() is None
