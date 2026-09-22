#****************************************************************************
#* objects.py
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
"""The normalized object model (design section 8).

Everything downstream of `sphinx_pss.model.builder` sees only these types, never
a ``pssparser`` node. That boundary is deliberate: the parser's Python surface
is generated from ``ast/*.yaml`` and changes with it, while directives, roles
and documenters should not.
"""

from __future__ import annotations

import dataclasses
from typing import Any


# --- kinds -----------------------------------------------------------------
#
# ``PssObject.kind`` is a plain string rather than an enum so it can be written
# straight into a directive name (``pss:action``) and read back out of a
# doctree without a lookup table.

#: Kinds that declare a type and can own members.
TYPE_KINDS = frozenset(
    {
        "package",
        "component",
        "action",
        "monitor",
        "struct",
        "buffer",
        "stream",
        "state",
        "resource",
        "enum",
    }
)

#: Kinds that are members of a type.
MEMBER_KINDS = frozenset(
    {
        "field",
        "flow_ref",
        "resource_claim",
        "constraint",
        "function",
        "exec",
        "pool",
        "enum_item",
        "covergroup",
        "activity",
        "bind",
    }
)

#: The five PSS flow-object kinds. Their pages carry producer/consumer tables
#: (Phase 2), which is what makes them worth naming as a set.
FLOW_OBJECT_KINDS = frozenset({"buffer", "stream", "state", "resource"})

ALL_KINDS = TYPE_KINDS | MEMBER_KINDS | {"typedef", "annotation"}


@dataclasses.dataclass(frozen=True)
class SourceRef:
    """Where an element was written.

    ``path`` is whatever the user handed to ``pss_source_dirs`` /
    ``pss_source_files``, resolved through ``Parser.file_map``.
    """

    path: str
    line: int
    col: int = 0
    fileid: int = -1

    def __str__(self) -> str:
        return f"{self.path}:{self.line}"


#: How a member came to be part of the type it appears in.
PROVENANCE_DECLARATION = "declaration"
PROVENANCE_EXTENSION = "extension"


@dataclasses.dataclass(frozen=True)
class Provenance:
    """Whether a member came from a type's declaration or from an ``extend``.

    The linker merges ``extend`` bodies into the base type, which is what makes
    the linked tree the right documentation view — and also what makes this
    field necessary. Without it a reader cannot tell that ``Xfer.prio`` is
    contributed by a different file than ``Xfer.len``, which for idiomatic PSS
    is actively misleading (design section 5.3).
    """

    origin: str = PROVENANCE_DECLARATION
    source: SourceRef | None = None

    @property
    def is_extension(self) -> bool:
        return self.origin == PROVENANCE_EXTENSION


@dataclasses.dataclass(frozen=True)
class TemplateParam:
    """One entry of a generic type's parameter list (``action A<T>``)."""

    name: str
    kind: str = "type"
    default: str | None = None

    def __str__(self) -> str:
        text = f"{self.kind} {self.name}" if self.kind != "type" else self.name
        if self.default is not None:
            text += f" = {self.default}"
        return text


@dataclasses.dataclass(frozen=True)
class Annotation:
    """An annotation applied to an element (``@doc {.text = "…"}``).

    Captured from Phase 1 and rendered as element metadata. Treating ``@doc``
    as a *documentation source* is a separate, unscheduled piece of work
    (design section 3.2) — hence ``params`` as plain data rather than anything
    doc-shaped.
    """

    name: str
    params: dict[str, str] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass(frozen=True)
class FlowRef:
    """An ``input`` / ``output`` flow-object reference on an action."""

    name: str
    type_name: str
    direction: str  # 'input' | 'output'
    qualname: str | None = None


@dataclasses.dataclass(frozen=True)
class ResourceClaim:
    """A ``lock`` / ``share`` resource claim on an action."""

    name: str
    type_name: str
    mode: str  # 'lock' | 'share'
    qualname: str | None = None


@dataclasses.dataclass
class FlowSpec:
    """An action's flow signature: what it consumes, produces and claims.

    Populated in Phase 2 by `sphinx_pss.model.flow`; declared here from Phase 1
    so the field exists on `PssObject` and nothing downstream has to grow a new
    attribute later.
    """

    inputs: list[FlowRef] = dataclasses.field(default_factory=list)
    outputs: list[FlowRef] = dataclasses.field(default_factory=list)
    locks: list[ResourceClaim] = dataclasses.field(default_factory=list)
    shares: list[ResourceClaim] = dataclasses.field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.inputs or self.outputs or self.locks or self.shares)


@dataclasses.dataclass
class ActivityGraph:
    """A normalized activity (Phase 3, `sphinx_pss.model.activity`)."""

    root: Any = None


@dataclasses.dataclass
class PssObject:
    """One documentable PSS element.

    Members are ordered as they appear in source, which is the order the
    default ``:member-order: source`` renders and the order the linker
    produces for a merged type (declaration members first, then each
    ``extend`` site).
    """

    kind: str
    name: str
    qualname: str

    qualifiers: list[str] = dataclasses.field(default_factory=list)
    signature: str = ""
    type_ref: str | None = None
    extends: str | None = None
    template_params: list[TemplateParam] = dataclasses.field(default_factory=list)

    raw_doc: str | None = None
    annotations: list[Annotation] = dataclasses.field(default_factory=list)
    doc_style: str | None = None

    location: SourceRef | None = None
    defined_in: Provenance = dataclasses.field(default_factory=Provenance)

    flow: FlowSpec | None = None
    activity: ActivityGraph | None = None
    group: str | None = None

    children: list["PssObject"] = dataclasses.field(default_factory=list)

    def __post_init__(self) -> None:
        if self.kind not in ALL_KINDS:
            raise ValueError(f"unknown PssObject kind: {self.kind!r}")

    # --- convenience -------------------------------------------------------

    @property
    def is_documented(self) -> bool:
        """True when the element carries a doc comment of its own."""
        return bool(self.raw_doc and self.raw_doc.strip())

    @property
    def is_flow_object(self) -> bool:
        return self.kind in FLOW_OBJECT_KINDS

    def child(self, name: str) -> "PssObject | None":
        """The direct child called ``name``, if any."""
        for c in self.children:
            if c.name == name:
                return c
        return None

    def walk(self):
        """Yield this object and every descendant, depth-first, in source order."""
        yield self
        for c in self.children:
            yield from c.walk()

    def member_names(self, *kinds: str) -> list[str]:
        """Names of direct children, optionally restricted to ``kinds``.

        Used by the doc-field cross-validation (design section 3.1) to answer
        "does this element actually declare what the comment claims?".
        """
        return [c.name for c in self.children if not kinds or c.kind in kinds]
