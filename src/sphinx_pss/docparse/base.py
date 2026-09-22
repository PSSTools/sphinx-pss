#****************************************************************************
#* base.py
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
"""The doc-comment dialect contract.

Every dialect turns an element's documentation into the same `ParsedDoc`, so
rendering never has to know which dialect produced it. That is what lets a
project mix ``native`` and ``doxygen`` sources, and what lets a cross-reference
written either way produce the same node.

The ABC takes the whole `PssObject`, not just its ``raw_doc``. That costs
nothing now and is the seam a future ``@doc``-annotation dialect needs, since
it would read `PssObject.annotations` rather than the comment text (design
section 3.4).
"""

from __future__ import annotations

import abc
import dataclasses
from typing import TYPE_CHECKING, Callable, Iterable

if TYPE_CHECKING:
    from ..model.objects import PssObject


@dataclasses.dataclass(frozen=True)
class DocField:
    """One entry of a documentation field list.

    ``:output out_b: the filled buffer`` parses to
    ``DocField("output", "out_b", "the filled buffer")``.
    """

    name: str
    argument: str | None
    body: str
    #: Line within ``raw_doc`` the field started on, 1-based. Used to point a
    #: cross-validation warning at the comment rather than the declaration.
    line: int = 0

    @property
    def key(self) -> tuple[str, str | None]:
        return (self.name, self.argument)


@dataclasses.dataclass
class ParsedDoc:
    """The dialect-independent result of parsing an element's documentation."""

    #: First paragraph. Rendered in summary tables and as the element's lead.
    summary: str = ""
    #: Everything after the summary, as reStructuredText for nested parsing.
    rst_body: str = ""
    #: Structured field-list entries, in source order.
    fields: list[DocField] = dataclasses.field(default_factory=list)
    #: Cross references discovered in the text, for the domain to resolve.
    xrefs: list[str] = dataclasses.field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.summary or self.rst_body or self.fields)

    def fields_named(self, *names: str) -> list[DocField]:
        """Every field whose name is one of ``names``."""
        wanted = frozenset(names)
        return [f for f in self.fields if f.name in wanted]

    def field_arguments(self, *names: str) -> list[str]:
        """The arguments of every field named ``names``, in order.

        ``:input in_b:`` and ``:input:`` are both legal; only the former
        contributes an argument, which is what cross-validation compares
        against the element's declarations.
        """
        return [f.argument for f in self.fields_named(*names) if f.argument]


class DocstringParser(abc.ABC):
    """Base class for a doc-comment dialect."""

    #: Value of ``pss_doc_style`` / ``:doc-style:`` that selects this dialect.
    name: str = ""

    @abc.abstractmethod
    def parse(self, obj: "PssObject") -> ParsedDoc:
        """Parse ``obj``'s documentation.

        Implementations receive the whole object so a dialect can read
        something other than ``raw_doc``, and so field parsing can consult the
        element's declarations.
        """

    def can_parse(self, obj: "PssObject") -> bool:
        """Whether this dialect recognizes ``obj``'s documentation.

        Used only by the ``auto`` dialect to sniff. The default says yes, which
        makes a dialect the fallback rather than a no-op.
        """
        return True


#: Registered dialects by name.
_REGISTRY: dict[str, DocstringParser] = {}


def register(parser: DocstringParser) -> DocstringParser:
    """Register a dialect under its `DocstringParser.name`."""
    if not parser.name:
        raise ValueError("a DocstringParser must declare a name")
    _REGISTRY[parser.name] = parser
    return parser


def get_parser(style: str) -> DocstringParser:
    """The dialect registered as ``style``.

    Raises `KeyError` with the available names, because the alternative — a
    silent fallback to ``native`` — turns a typo in ``pss_doc_style`` into
    documentation that is quietly parsed by the wrong rules.
    """
    try:
        return _REGISTRY[style]
    except KeyError:
        available = ", ".join(sorted(_REGISTRY)) or "none registered"
        raise KeyError(
            f"unknown doc style {style!r}; available styles: {available}"
        ) from None


def registered_styles() -> list[str]:
    return sorted(_REGISTRY)


def parse_doc(obj: "PssObject", style: str = "native") -> ParsedDoc:
    """Parse ``obj`` with the dialect it asks for, or with ``style``.

    A per-element ``doc_style`` wins over the project setting, which is what
    makes a per-directive ``:doc-style:`` option work.
    """
    return get_parser(obj.doc_style or style).parse(obj)


# --- shared text handling ---------------------------------------------------


def split_summary(text: str) -> tuple[str, str]:
    """Split documentation into its first paragraph and the rest.

    A summary is a *paragraph*, not a line: PSS declarations are wordy and the
    one-sentence summary of an action routinely wraps. Splitting on the first
    blank line matches how the comment was written.
    """
    if not text:
        return "", ""

    lines = text.split("\n")
    for i, line in enumerate(lines):
        if not line.strip():
            return "\n".join(lines[:i]).strip(), "\n".join(lines[i + 1 :]).strip()
    return text.strip(), ""


def iter_registered() -> Iterable[tuple[str, DocstringParser]]:
    return sorted(_REGISTRY.items())


def _reset_registry_for_tests(factory: Callable[[], None] | None = None) -> None:
    """Clear the registry. Test support only."""
    _REGISTRY.clear()
    if factory is not None:
        factory()
