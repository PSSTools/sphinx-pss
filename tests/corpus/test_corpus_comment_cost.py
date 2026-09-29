"""What comment collection costs over the corpus (plan ``S0-TEST-4``).

Parse + link time with ``collect_comments`` against docstrings alone, which is
what sphinx-pss did before. Design section 5.1 measured +1.9% over the corpus.

**Recorded, not asserted, until pssparser ``PERF-1`` lands.** Today comment
collection also switches the parser to lexing each file up front, which is
faster, so the comparison measures two things at once. Once ``PERF-1`` makes
that unconditional the ratio isolates the cost of collection, and
`PERF_1_LANDED` turns the assertion on.
"""

from __future__ import annotations

import time

import pytest
from corpus_finder import corpus_files, require

pytestmark = pytest.mark.corpus

#: Set once pssparser calls ``fill()`` unconditionally (its
#: ``docs/design/sphinx-pss-requests-2026-09-28.md``, ``PERF-1``).
PERF_1_LANDED = False

#: Budget over docstrings-only (plan ``S0-TEST-4``).
BUDGET = 1.05

#: Interleaved rounds; the minimum of each configuration is compared, which is
#: the figure least disturbed by whatever else the machine is doing.
ROUNDS = 5

CONFIGS = {
    "docstrings": {"collect_docstrings": True},
    "comments": {"collect_docstrings": True, "collect_comments": True},
}


def _parse_all(paths, options) -> float:
    from pssparser import ParseException, Parser

    start = time.perf_counter()
    for path in paths:
        parser = Parser(**options)
        try:
            parser.parse([str(path)])
            parser.link()
        except ParseException:
            # Same work either way; whether a file links is not measured here.
            pass
    return time.perf_counter() - start


def test_comment_collection_cost(record_property, capsys) -> None:
    paths = [require(p) for p in corpus_files()]

    best = {name: float("inf") for name in CONFIGS}
    for _ in range(ROUNDS):
        for name, options in CONFIGS.items():
            best[name] = min(best[name], _parse_all(paths, options))

    ratio = best["comments"] / best["docstrings"]
    for name, seconds in best.items():
        record_property(f"{name}_ms", round(seconds * 1000, 1))
    record_property("ratio", round(ratio, 4))
    with capsys.disabled():
        print(
            f"\n[S0-TEST-4] {len(paths)} files, min of {ROUNDS}: "
            f"docstrings {best['docstrings'] * 1000:.1f} ms, "
            f"comments {best['comments'] * 1000:.1f} ms ({(ratio - 1) * 100:+.1f}%)"
        )

    if PERF_1_LANDED:
        assert ratio <= BUDGET
