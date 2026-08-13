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

from ..docparse import ParsedDoc, parse_doc, validate
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

    def document(self, obj: PssObject, indent: str = "") -> list[str]:
        """Render ``obj`` as reStructuredText lines."""
        lines: list[str] = []
        doc = self._documentation(obj)

        lines.append(f"{indent}.. pss:{obj.kind}:: {obj.signature}")
        for option in self._directive_options(obj):
            lines.append(f"{indent}   {option}")
        lines.append("")

        body_indent = indent + "   "
        lines.extend(self._body(obj, doc, body_indent))

        if self.options.members:
            for member in self._members(obj):
                lines.extend(self.document(member, body_indent))

        lines.append("")
        return lines

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

    def _body(self, obj: PssObject, doc: ParsedDoc, indent: str) -> list[str]:
        lines: list[str] = []

        if doc.summary:
            lines.extend(_indent_block(doc.summary, indent))
            lines.append("")
        if doc.rst_body:
            lines.extend(_indent_block(doc.rst_body, indent))
            lines.append("")

        field_lines = list(self._field_list(obj, doc))
        if field_lines:
            lines.extend(f"{indent}{line}" for line in field_lines)
            lines.append("")

        return lines

    def _field_list(self, obj: PssObject, doc: ParsedDoc) -> Iterator[str]:
        """Render documentation fields, plus provenance, as a field list."""
        for field in doc.fields:
            label = field.name if field.argument is None else f"{field.name} {field.argument}"
            body = " ".join(field.body.split()) if field.body else ""
            yield f":{label}: {body}".rstrip()

        if self.options.show_extensions and obj.defined_in.is_extension:
            source = obj.defined_in.source
            yield f":added by: an extension ({source})"

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
) -> tuple[list[str], list[tuple[PssObject, Any]]]:
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
