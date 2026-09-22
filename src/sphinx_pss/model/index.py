#****************************************************************************
#* index.py
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
"""The project-wide index — one parse per build, referenced by every directive.

This is the contract the whole extension rests on (design section 6.1): the
model is parsed and linked **once**, on ``builder-inited``, and every directive
and role resolves into the result. Nothing re-parses. Beyond avoiding repeated
work, it is what makes PSS's global relationships — which actions produce a
given buffer, which components instantiate another — computable at all, since
they are only visible with the whole model in hand.

The relation tables those features need are declared here from Phase 1 and
populated in Phase 2 by `sphinx_pss.model.flow`, so that no consumer has to
grow a new attribute later.
"""

from __future__ import annotations

import dataclasses
from typing import Iterable, Iterator

from .builder import build_objects
from .objects import FLOW_OBJECT_KINDS, PssObject
from .parse import ParsedModel, PssParseError, discover_sources, parse_model


@dataclasses.dataclass
class RelationTables:
    """Derived, whole-model relationships (design section 6.1).

    Declared in Phase 1, populated in Phase 2. Every value is a **list**, kept
    in a deterministic order, never a set — the rendered output is compared
    byte-for-byte by the determinism test, and set iteration order is not
    stable across runs.
    """

    produces: dict[str, list[str]] = dataclasses.field(default_factory=dict)
    consumes: dict[str, list[str]] = dataclasses.field(default_factory=dict)
    locks: dict[str, list[str]] = dataclasses.field(default_factory=dict)
    shares: dict[str, list[str]] = dataclasses.field(default_factory=dict)
    instantiates: dict[str, list[str]] = dataclasses.field(default_factory=dict)
    extends: dict[str, list[str]] = dataclasses.field(default_factory=dict)
    derived: dict[str, list[str]] = dataclasses.field(default_factory=dict)


class PssIndex:
    """Qualified name -> `PssObject`, plus the derived relation tables."""

    def __init__(
        self,
        model: ParsedModel,
        *,
        document_stdlib: bool = False,
    ) -> None:
        self.model = model
        self.document_stdlib = document_stdlib
        self.relations = RelationTables()

        #: Top-level packages, in linker order.
        self.roots: list[PssObject] = build_objects(
            model, document_stdlib=document_stdlib
        )

        self._by_qualname: dict[str, PssObject] = {}
        #: Bare name -> every object with that name. Populated for the
        #: "unqualified reference" path, where an ambiguous name must report
        #: its candidates rather than silently picking one.
        self._by_name: dict[str, list[PssObject]] = {}

        for root in self.roots:
            for obj in root.walk():
                self._by_qualname.setdefault(obj.qualname, obj)
                self._by_name.setdefault(obj.name, []).append(obj)

        #: The written form of each object's declared type, before resolution.
        #: Signatures render from this, so a type that does not resolve still
        #: reads the way the author wrote it.
        self.written_type_ref: dict[str, str] = {
            obj.qualname: obj.type_ref for obj in self if obj.type_ref
        }
        self._resolve_type_refs()

    def _resolve_type_refs(self) -> None:
        """Rewrite each ``type_ref`` from the written name to a qualified name.

        Design section 8 specifies ``type_ref`` as resolved, which is what lets
        a signature's type render as a link. Built-in types (``int``, ``bool``)
        and anything outside the documented set simply do not resolve, and keep
        their written form — the fallback a reader sees is the source text,
        which is never wrong, only unlinked.
        """
        for root in self.roots:
            self._resolve_in(root, scope=root.qualname)

    def _resolve_in(self, obj: PssObject, scope: str) -> None:
        for child in obj.children:
            if child.type_ref:
                resolved = self.resolve_qualname(child.type_ref, scope=scope)
                if resolved is not None:
                    child.type_ref = resolved
            if child.extends:
                resolved = self.resolve_qualname(child.extends, scope=scope)
                if resolved is not None:
                    child.extends = resolved
            if child.flow is not None:
                self._resolve_flow(child.flow, scope=scope)
            self._resolve_in(child, scope=child.qualname)

    def _resolve_flow(self, flow, scope: str) -> None:
        for entry in (*flow.inputs, *flow.outputs, *flow.locks, *flow.shares):
            resolved = self.resolve_qualname(entry.type_name, scope=scope)
            if resolved is not None:
                object.__setattr__(entry, "qualname", resolved)

    # --- lookup ------------------------------------------------------------

    def __contains__(self, qualname: str) -> bool:
        return qualname in self._by_qualname

    def __len__(self) -> int:
        return len(self._by_qualname)

    def __iter__(self) -> Iterator[PssObject]:
        """Every indexed object, in source order within each package."""
        for root in self.roots:
            yield from root.walk()

    def get(self, qualname: str) -> PssObject | None:
        """The object with exactly this qualified name."""
        return self._by_qualname.get(qualname)

    def candidates(self, name: str) -> list[PssObject]:
        """Every object whose bare name is ``name``."""
        return list(self._by_name.get(name, ()))

    def of_kind(self, *kinds: str) -> list[PssObject]:
        """Every indexed object of the given kinds, in index order."""
        wanted = frozenset(kinds)
        return [obj for obj in self if obj.kind in wanted]

    @property
    def flow_objects(self) -> list[PssObject]:
        """Every buffer, stream, state and resource type."""
        return [obj for obj in self if obj.kind in FLOW_OBJECT_KINDS]

    # --- reference resolution ----------------------------------------------

    def resolve(self, name: str, *, scope: str = "") -> PssObject | None:
        """Resolve a written type name, as seen from ``scope``.

        PSS name resolution is lexical, so an unqualified ``DmaBuf`` written
        inside ``dma_pkg::Dma::Xfer`` means the nearest ``DmaBuf`` visible from
        there. Enclosing scopes are tried innermost-first, then the name is
        taken as already qualified, and only then is a bare-name match
        considered — and that last step is skipped when it would be ambiguous,
        so a caller can report candidates instead of guessing.

        This exists because a type reference cannot be resolved through the
        parser: ``TypeIdentifier.getTarget()`` returns a ``SymbolRefPath`` that
        exposes only an index to Python (finding ``U-3``). Resolving against
        the index is the design's model regardless (``PssObject.type_ref``).
        """
        if not name:
            return None

        parts = scope.split("::") if scope else []
        for i in range(len(parts), 0, -1):
            candidate = "::".join(parts[:i]) + "::" + name
            found = self._by_qualname.get(candidate)
            if found is not None:
                return found

        found = self._by_qualname.get(name)
        if found is not None:
            return found

        matches = self._by_name.get(name.split("::")[-1], [])
        if len(matches) == 1:
            return matches[0]
        return None

    def resolve_qualname(self, name: str, *, scope: str = "") -> str | None:
        """`resolve`, returning the qualified name rather than the object."""
        found = self.resolve(name, scope=scope)
        return found.qualname if found is not None else None

    # --- documented set ----------------------------------------------------

    def documented(self) -> list[PssObject]:
        """Objects that belong in the published output.

        The standard library is always parsed — ``Parser`` loads ``std_pkg``
        and friends unconditionally — and stays in the index so references into
        it resolve. Whether it is *documented* is a separate decision
        (``pss_document_stdlib``, design section 4.4), and this is where the two
        part company.
        """
        return list(self)


def build_index(
    source_dirs: Iterable[str] = (),
    source_files: Iterable[str] = (),
    *,
    confdir: str | None = None,
    document_stdlib: bool = False,
    tolerate_link_errors: bool = False,
) -> PssIndex:
    """Discover, parse, link and index a project's PSS sources.

    Raises `PssParseError` when there is nothing to document, rather than
    producing an empty index: an empty API reference that still reports success
    is the failure mode that wastes the most time.
    """
    sources = discover_sources(source_dirs, source_files, confdir)
    if not sources:
        raise PssParseError(
            "No PSS sources found. Set pss_source_dirs or pss_source_files in "
            "conf.py; pss_source_dirs entries are resolved relative to the "
            "directory containing conf.py."
        )

    model = parse_model(sources, tolerate_link_errors=tolerate_link_errors)
    return PssIndex(model, document_stdlib=document_stdlib)
