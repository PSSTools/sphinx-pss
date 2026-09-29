#****************************************************************************
#* steps_markers.py
#*
#* Copyright 2026 Matthew Ballance and Contributors
#*
#* Licensed under the Apache License, Version 2.0 (the "License"); you may
#* not use this file except in compliance with the License.
#* You may obtain a copy of the License at:
#*
#*   http://www.apache.org/licenses/LICENSE-2.0
#*
#* Unless required by applicable law or agreed to in writing, software
#* distributed under the License is distributed on an "AS IS" BASIS,
#* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#* See the License for the specific language governing permissions and
#* limitations under the License.
#****************************************************************************
"""Programming-step markers: reading ``Step:`` lines out of a comment.

The rules are those of the programming-steps design, section 3.1:

1. Only ``///`` and ``/** */`` comments are read. That is the caller's job
   (`sphinx_pss.model.comments.CommentForm.is_doc`); this module sees text.
2. A marker is a line matching `MARKER_RE`: ``Step:``, optionally with a
   number (``Step 3:``, ``Step 2.1:``, which is accepted and dropped), then
   the title. It is case-sensitive, and the colon is required. Indentation
   before ``Step`` is ignored.
3. The lines of the same comment after the marker are its detail, up to the
   next marker. Lines before the first marker are the author's prose, and
   are ignored.

A marker with nothing after the colon is still a marker, with an empty title,
so that it is reported (``pss.step_empty``) rather than read as prose.
"""

from __future__ import annotations

import dataclasses
import re
import textwrap
from typing import Sequence

__all__ = [
    "MARKER_RE",
    "Marker",
    "is_near_miss",
    "parse_marker",
    "parse_markers",
]

#: Design section 3.1, rule 2. The title group is optional here, so that
#: ``Step:`` alone is recognized as a marker with no title.
MARKER_RE = re.compile(r"^Step(?:\s+(?P<number>\d+(?:\.\d+)*))?:\s*(?P<title>\S.*)?$")

#: The first word is ``step`` or ``steps``, in any case, followed by a space,
#: a colon, a period, a digit or the end of the line. ``Stepper`` and
#: ``Step-by-step`` are ordinary words.
_NEAR_MISS_RE = re.compile(r"^steps?(?=[\s:.\d]|$)", re.IGNORECASE)


@dataclasses.dataclass(frozen=True)
class Marker:
    """One ``Step:`` line and the detail that follows it."""

    #: The rest of the marker line; empty for a bare ``Step:``.
    title: str
    #: The comment's lines after the marker, up to the next marker, dedented,
    #: with leading and trailing blank lines removed.
    detail: tuple[str, ...]
    #: A hand-written number (``Step 3:`` gives ``"3"``). Never used for
    #: numbering, which is always generated (design section 4.6).
    number: str | None
    #: The source line of the marker.
    line: int
    #: The source line of ``detail[0]``; 0 when there is no detail. The detail
    #: lines are consecutive, so ``detail[i]`` is on ``detail_line + i``.
    detail_line: int = 0


def is_near_miss(text: str) -> bool:
    """True for a line that looks meant as a marker but is not one.

    ``step: reset``, ``STEP 3 Reset``, ``Steps: ...`` and ``Step Reset`` are
    near misses; ``Step: Reset`` is a marker, and ``Stepping through ...`` is
    prose.
    """
    line = text.strip()
    return bool(_NEAR_MISS_RE.match(line)) and not MARKER_RE.match(line)


def parse_markers(lines: Sequence[str], first_line: int = 1) -> list[Marker]:
    """Every marker in one comment's ``lines``, in order.

    ``first_line`` is the source line of ``lines[0]``, so each marker carries
    its own line.
    """
    starts = []
    for i, text in enumerate(lines):
        match = MARKER_RE.match(text.strip())
        if match:
            starts.append((i, match))

    markers = []
    for n, (i, match) in enumerate(starts):
        end = starts[n + 1][0] if n + 1 < len(starts) else len(lines)
        body = lines[i + 1 : end]
        detail = _detail(body)
        skipped = next((k for k, text in enumerate(body) if text.strip()), 0)
        markers.append(
            Marker(
                title=(match.group("title") or "").strip(),
                detail=detail,
                number=match.group("number"),
                line=first_line + i,
                detail_line=first_line + i + 1 + skipped if detail else 0,
            )
        )
    return markers


def parse_marker(lines: Sequence[str], first_line: int = 1) -> Marker | None:
    """The first marker in ``lines``, or ``None`` when there is none."""
    markers = parse_markers(lines, first_line)
    return markers[0] if markers else None


def _detail(lines: Sequence[str]) -> tuple[str, ...]:
    text = textwrap.dedent("\n".join(lines)).strip("\n")
    return tuple(text.split("\n")) if text.strip() else ()
