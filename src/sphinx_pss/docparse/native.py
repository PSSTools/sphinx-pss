#****************************************************************************
#* native.py
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
"""The ``native`` dialect — the doc-comment style this project recommends.

The immediately preceding comment block is the documentation. Its first
paragraph is the summary, the rest is the body, and the body is
reStructuredText, so authors get the whole Sphinx toolbox without any invented
markup. Field-list entries carry the PSS-specific vocabulary in
`sphinx_pss.docparse.fields`.

The text arrives already normalized — markers stripped, continuation ``*``
removed, dedented — because that is the parser's job and it is the only place
where the source text and its lexical form are both known. Re-normalizing here
is explicitly rejected (``pssparser`` enhancement plan section 5), so this
module does not touch indentation.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .base import DocstringParser, ParsedDoc, register, split_summary
from .fields import parse_field_list

if TYPE_CHECKING:
    from ..model.objects import PssObject


#: An explicit cross-reference role, ``:pss:action:`Xfer```.
XREF_RE = re.compile(r":pss:(?P<role>[a-z]+):`(?P<target>[^`]+)`")


class NativeDocstringParser(DocstringParser):
    """Parses the ``native`` dialect."""

    name = "native"

    def parse(self, obj: "PssObject") -> ParsedDoc:
        text = obj.raw_doc or ""
        if not text.strip():
            return ParsedDoc()

        prose, fields = parse_field_list(text)
        summary, body = split_summary(prose)

        return ParsedDoc(
            summary=summary,
            rst_body=body,
            fields=fields,
            xrefs=extract_xrefs(text),
        )


def extract_xrefs(text: str) -> list[str]:
    """Targets of the explicit ``:pss:…:`` roles in ``text``.

    Collected so the domain can report an unresolvable reference against the
    comment that wrote it. Resolution itself happens downstream, once the whole
    index exists.
    """
    seen: list[str] = []
    for match in XREF_RE.finditer(text):
        target = match.group("target").strip()
        if target and target not in seen:
            seen.append(target)
    return seen


register(NativeDocstringParser())
