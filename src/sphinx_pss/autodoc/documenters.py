#****************************************************************************
#* documenters.py
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
"""Documenters: a `PssObject` -> the domain directives that describe it.

The architecture is ``sphinx.ext.autodoc``'s, not its code. Autodoc is wired to
Python's runtime object model — it imports a module and introspects live
objects — and PSS has no runtime to import. What transfers is the shape: a
registry of documenters keyed by kind, ``:members:`` / ``:undoc-members:`` /
``:exclude-members:`` options, doc text processed through a dialect, and events
that let a project post-process both.

A documenter emits **reStructuredText**, which is then parsed. Emitting domain
directives rather than nodes directly is what makes the output identical to
what a user could have written by hand, so autodoc and manual documentation
compose instead of being two separate paths.
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any, Iterable, Iterator

from docutils.statemachine import StringList

from ..docparse import ParsedDoc, parse_doc, validate
from ..model.locations import match_lines
from ..model.objects import PssObject

if TYPE_CHECKING:
    from ..model.index import PssIndex

#: Emitted before a documenter renders an element's documentation, so a project
#: can rewrite it. Handlers receive ``(app, kind, qualname, options, doc)`` and
#: mutate ``doc`` in place, matching ``autodoc-process-docstring``.
EVENT_PROCESS_DOC = "pss-autodoc-process-doc"

#: Emitted per candidate member. A handler returning ``True`` skips the member
#: and ``False`` forces it in; ``None`` leaves the decision alone.
EVENT_SKIP_MEMBER = "pss-autodoc-skip-member"

#: Order members appear in when ``:member-order:`` is ``groups``: the members
#: that define an element's contract first, its implementation after.
GROUP_ORDER = (
    "flow_ref",
    "resource_claim",
    "pool",
    "field",
    "enum_item",
    "constraint",
    "function",
    "action",
    "monitor",
    "buffer",
    "stream",
    "state",
    "resource",
    "struct",
    "enum",
    "component",
)


@dataclasses.dataclass
class DocumenterOptions:
    """The resolved options for one ``autopss*`` directive."""

    members: bool = False
    undoc_members: bool = False
    inherited_members: bool = False
    exclude_members: frozenset[str] = frozenset()
    member_order: str = "source"
    recursive: bool = False
    no_index: bool = False
    doc_style: str = "native"
    #: Rendering options carried through to Phase-2 features; accepted now so
    #: a document written today does not have to change when they land.
    show_extensions: bool = False

    @classmethod
    def from_directive(
        cls, options: dict[str, Any], defaults: dict[str, Any] | None = None
    ) -> "DocumenterOptions":
        """Combine ``pss_default_options`` with a directive's own options.

        A flag directive option is present-or-absent, so a project default of
        ``members: True`` cannot be turned *off* per directive by the flag
        alone — ``:no-members:`` exists for that, mirroring how
        ``autodoc_default_options`` is overridden.
        """
        merged: dict[str, Any] = dict(defaults or {})
        for key, value in options.items():
            merged[key] = value

        def flag(name: str) -> bool:
            if f"no-{name}" in options:
                return False
            return name in merged and merged[name] is not False

        exclude = merged.get("exclude-members") or ""
        if isinstance(exclude, str):
            exclude = {e.strip() for e in exclude.replace(",", " ").split() if e.strip()}

        return cls(
            members=flag("members"),
            undoc_members=flag("undoc-members"),
            inherited_members=flag("inherited-members"),
            exclude_members=frozenset(exclude),
            member_order=merged.get("member-order") or "source",
            recursive=flag("recursive"),
            no_index=flag("no-index"),
            doc_style=merged.get("doc-style") or "native",
            show_extensions=flag("show-extensions"),
        )


class PssDocumenter:
    """Renders one `PssObject` and, on request, its members."""

    def __init__(
        self,
        index: "PssIndex",
        options: DocumenterOptions,
        *,
        events: Any = None,
    ) -> None:
        self.index = index
        self.options = options
        #: Sphinx ``EventManager``, or ``None`` outside a build. Taken rather
        #: than the application because a directive can reach ``env.events``
        #: but not the application -- ``BuildEnvironment.app`` is deprecated
        #: for removal in Sphinx 11.
        self.events = events
        #: Cross-validation findings, collected for the caller to report as
        #: Sphinx warnings with the right location.
        self.issues: list[tuple[PssObject, Any]] = []

    # --- entry point -------------------------------------------------------

    def document(self, obj: PssObject, indent: str = "") -> StringList:
        """Render ``obj`` as reStructuredText.

        Every line carries its origin: text taken from a doc comment is
        attributed to its line in the ``.pss`` file, so a reStructuredText
        error in a comment is reported where the author can fix it, and
        generated scaffolding to a pseudo-file named for the object.
        """
        out = StringList()
        generated = f"<autopss:{obj.qualname}>"

        def emit(text: str) -> None:
            out.append(text, generated, len(out))

        doc = self._documentation(obj)

        emit(f"{indent}.. pss:{obj.kind}:: {obj.signature}")
        for option in self._directive_options(obj):
            emit(f"{indent}   {option}")
        emit("")

        body_indent = indent + "   "
        for text, line in self._body(obj, doc, body_indent):
            if line is None or obj.doc_source is None:
                emit(text)
            else:
                out.append(text, obj.doc_source.path, line - 1)

        if self.options.members:
            for member in self._members(obj):
                out.extend(self.document(member, body_indent))

        emit("")
        return out

    # --- pieces ------------------------------------------------------------

    def _documentation(self, obj: PssObject) -> ParsedDoc:
        doc = parse_doc(obj, self.options.doc_style)

        for issue in validate(doc, obj):
            if issue.category == "undocumented" and not self.options.undoc_members:
                continue
            self.issues.append((obj, issue))

        if self.events is not None:
            self.events.emit(
                EVENT_PROCESS_DOC, obj.kind, obj.qualname, self.options, doc
            )
        return doc

    def _directive_options(self, obj: PssObject) -> list[str]:
        options: list[str] = []
        # The signature carries the name as written, so members nested inside a
        # rendered parent would otherwise be named relative to it. Passing the
        # qualified name explicitly keeps targets stable no matter which
        # directive rendered the object.
        options.append(f":qualname: {obj.qualname}")
        if self.options.no_index:
            options.append(":no-index:")
        return options

    def _body(
        self, obj: PssObject, doc: ParsedDoc, indent: str
    ) -> list[tuple[str, int | None]]:
        """The body lines, each with its source line in the ``.pss`` file.

        A dialect is free to reshape the comment (split off the summary, lift
        fields out, rewrite Doxygen commands), so rendered prose is matched back
        to ``raw_doc`` by content rather than by position. A line with no match
        is paired with ``None`` and reported against the generated text.
        """
        raw_lines = (obj.raw_doc or "").split("\n")

        def sourced(block: list[str]) -> list[tuple[str, int | None]]:
            if obj.doc_source is None:
                return [(line, None) for line in block]
            indices = match_lines(block, raw_lines)
            return [
                (line, None if i is None else obj.doc_source.line_of(i))
                for line, i in zip(block, indices)
            ]

        lines: list[tuple[str, int | None]] = []
        if doc.summary:
            lines.extend(sourced(_indent_block(doc.summary, indent)))
            lines.append(("", None))
        if doc.rst_body:
            lines.extend(sourced(_indent_block(doc.rst_body, indent)))
            lines.append(("", None))

        field_lines = list(self._field_list(obj, doc))
        if field_lines:
            for text, raw_line in field_lines:
                line = None
                if raw_line and obj.doc_source is not None:
                    line = obj.doc_source.line_of(raw_line - 1)
                lines.append((f"{indent}{text}", line))
            lines.append(("", None))

        return lines

    def _field_list(
        self, obj: PssObject, doc: ParsedDoc
    ) -> Iterator[tuple[str, int]]:
        """Render documentation fields, plus provenance, as a field list.

        Each entry is paired with the ``raw_doc`` line (1-based) it came from,
        or 0 for a generated entry.
        """
        for field in doc.fields:
            label = field.name if field.argument is None else f"{field.name} {field.argument}"
            body = " ".join(field.body.split()) if field.body else ""
            yield f":{label}: {body}".rstrip(), field.line

        if self.options.show_extensions and obj.defined_in.is_extension:
            source = obj.defined_in.source
            yield f":added by: an extension ({source})", 0

    def _members(self, obj: PssObject) -> list[PssObject]:
        """The members to render, filtered and ordered."""
        candidates = [m for m in obj.children if self._include(obj, m)]

        if self.options.member_order == "alpha":
            candidates.sort(key=lambda m: m.name)
        elif self.options.member_order == "groups":
            order = {kind: i for i, kind in enumerate(GROUP_ORDER)}
            candidates.sort(key=lambda m: order.get(m.kind, len(order)))
        # 'source' is the order the model already holds, so it needs no work --
        # and it is the default because for PSS the declaration order is
        # meaningful: an action's flow signature reads in the order it was
        # written.

        return candidates

    def _include(self, owner: PssObject, member: PssObject) -> bool:
        decision = None

        if member.name in self.options.exclude_members:
            decision = True
        elif not member.is_documented and not self.options.undoc_members:
            decision = True

        if self.events is not None:
            override = self.events.emit_firstresult(
                EVENT_SKIP_MEMBER,
                member.kind,
                member.qualname,
                bool(decision),
                self.options,
            )
            if override is not None:
                decision = override

        return not decision


def _indent_block(text: str, indent: str) -> list[str]:
    """Indent ``text`` for nesting inside a directive body.

    Blank lines stay genuinely blank rather than becoming whitespace-only,
    which docutils treats differently at a block boundary.
    """
    return [f"{indent}{line}" if line.strip() else "" for line in text.split("\n")]


def document_object(
    index: "PssIndex",
    obj: PssObject,
    options: DocumenterOptions,
    *,
    events: Any = None,
) -> tuple[StringList, list[tuple[PssObject, Any]]]:
    """Render ``obj``, returning its lines and any cross-validation issues."""
    documenter = PssDocumenter(index, options, events=events)
    return documenter.document(obj), documenter.issues


def setup(app) -> None:
    app.add_event(EVENT_PROCESS_DOC)
    app.add_event(EVENT_SKIP_MEMBER)


__all__ = [
    "EVENT_PROCESS_DOC",
    "EVENT_SKIP_MEMBER",
    "DocumenterOptions",
    "PssDocumenter",
    "document_object",
    "setup",
]


def iter_kinds() -> Iterable[str]:
    return GROUP_ORDER
