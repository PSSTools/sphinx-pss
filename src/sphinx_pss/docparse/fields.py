"""The PSS documentation field vocabulary, and its cross-validation.

Two things live here.

**The vocabulary** (design section 3.1) names the things PSS has that Python and
SystemVerilog do not — flow-object references, resource claims, pools, exec
blocks, coverage and requirement traceability. It is the project's opinionated
contribution: PSS has no entrenched doc-comment convention, so this defines one.

**The cross-validation** is what makes it more than a naming scheme. Every field
that names a declaration is checked against the model: a ``:output:`` naming
something the action does not declare is a warning, and a declared flow
reference with no field entry is reportable under ``:undoc-members:``. That
gives documentation a property prose alone cannot have — it is verifiably in
sync with the model, and it *stays* in sync, because renaming a flow object
without updating its comment fails the build under ``-W``.
"""

from __future__ import annotations

import dataclasses
import re
from typing import TYPE_CHECKING

from .base import DocField, ParsedDoc

if TYPE_CHECKING:
    from ..model.objects import PssObject


@dataclasses.dataclass(frozen=True)
class FieldSpec:
    """One entry of the vocabulary."""

    name: str
    #: Additional spellings accepted for this field.
    aliases: tuple[str, ...] = ()
    #: Element kinds the field is meaningful on. Empty means any.
    applies_to: frozenset[str] = frozenset()
    #: Member kinds the field's argument must name. Empty means the argument
    #: is free-form and is not cross-validated.
    validates_against: frozenset[str] = frozenset()
    #: Whether the field takes an argument at all.
    takes_argument: bool = True
    description: str = ""


TYPE_SCOPES = frozenset(
    {"component", "action", "monitor", "struct", "buffer", "stream", "state", "resource"}
)

VOCABULARY: tuple[FieldSpec, ...] = (
    FieldSpec(
        "param",
        aliases=("parameter", "arg", "argument"),
        applies_to=frozenset({"action", "component", "struct", "function"})
        | TYPE_SCOPES,
        validates_against=frozenset({"field"}),
        description="Template parameter or function argument.",
    ),
    FieldSpec(
        "input",
        applies_to=frozenset({"action", "monitor"}),
        validates_against=frozenset({"flow_ref"}),
        description="An input flow-object reference.",
    ),
    FieldSpec(
        "output",
        applies_to=frozenset({"action", "monitor"}),
        validates_against=frozenset({"flow_ref"}),
        description="An output flow-object reference.",
    ),
    FieldSpec(
        "lock",
        applies_to=frozenset({"action", "monitor"}),
        validates_against=frozenset({"resource_claim"}),
        description="An exclusive resource claim.",
    ),
    FieldSpec(
        "share",
        applies_to=frozenset({"action", "monitor"}),
        validates_against=frozenset({"resource_claim"}),
        description="A shared resource claim.",
    ),
    FieldSpec(
        "field",
        aliases=("attr", "attribute"),
        applies_to=TYPE_SCOPES,
        validates_against=frozenset({"field"}),
        description="An attribute field, when not documented at its declaration.",
    ),
    FieldSpec(
        "constraint",
        applies_to=TYPE_SCOPES,
        validates_against=frozenset({"constraint"}),
        description="The intent of a named constraint.",
    ),
    FieldSpec(
        "pool",
        applies_to=frozenset({"component"}),
        validates_against=frozenset({"pool"}),
        description="A pool declaration and its bind intent.",
    ),
    FieldSpec(
        "exec",
        applies_to=frozenset({"action", "component", "monitor"}),
        description="What a body / run_start / init_down block does.",
    ),
    FieldSpec(
        "covers",
        aliases=("coverage",),
        applies_to=frozenset({"action", "covergroup", "monitor"}),
        description="Coverage intent.",
    ),
    FieldSpec(
        "req",
        aliases=("requirement", "requirements"),
        takes_argument=False,
        description="Traceability IDs, comma-separated.",
    ),
    FieldSpec(
        "group",
        takes_argument=False,
        description="Logical grouping, rendered as a rubric.",
    ),
    FieldSpec(
        "realizes",
        applies_to=frozenset({"action"}),
        takes_argument=False,
        description="The target-side operation this action stands for.",
    ),
    # Accepted for compatibility with reStructuredText habits. Not part of the
    # PSS vocabulary, and never cross-validated.
    FieldSpec("returns", aliases=("return",), takes_argument=False),
    FieldSpec("raises", takes_argument=False),
    FieldSpec("see", aliases=("seealso",), takes_argument=False),
    FieldSpec("note", takes_argument=False),
    FieldSpec("warning", takes_argument=False),
)

#: Every accepted spelling -> its canonical spec.
FIELD_SPECS: dict[str, FieldSpec] = {}
for _spec in VOCABULARY:
    FIELD_SPECS[_spec.name] = _spec
    for _alias in _spec.aliases:
        FIELD_SPECS[_alias] = _spec
del _spec

#: Fields whose absence is reportable under ``:undoc-members:`` — the members a
#: reader most needs described, because the AST gives their name and type but
#: never their purpose.
DOCUMENTABLE_MEMBER_KINDS = frozenset({"flow_ref", "resource_claim"})


#: ``:name argument: body`` at the start of a line. The argument is optional,
#: and a colon inside the body is not a delimiter — only the first two are.
FIELD_RE = re.compile(r"^:(?P<name>[A-Za-z_][\w-]*)(?:\s+(?P<arg>[^:]+?))?:\s?(?P<body>.*)$")


def canonical_name(name: str) -> str:
    """The canonical spelling of ``name``, or ``name`` if it is unknown."""
    spec = FIELD_SPECS.get(name.lower())
    return spec.name if spec else name


def parse_field_list(text: str) -> tuple[str, list[DocField]]:
    """Split ``text`` into prose and field-list entries.

    Fields are recognized anywhere a line begins with ``:name:``, and a field's
    body continues onto following indented lines — so a long ``:param:``
    description reads naturally in source. Prose before the first field is
    returned separately; text after a field list is treated as continuation of
    the last field, matching reStructuredText.
    """
    if not text:
        return "", []

    prose: list[str] = []
    fields: list[DocField] = []
    open_field: DocField | None = None
    open_body: list[str] = []

    def close() -> None:
        nonlocal open_field, open_body
        if open_field is not None:
            body = "\n".join(open_body).strip()
            fields.append(dataclasses.replace(open_field, body=body))
        open_field = None
        open_body = []

    for lineno, line in enumerate(text.split("\n"), start=1):
        match = FIELD_RE.match(line)
        if match is not None:
            close()
            open_field = DocField(
                name=canonical_name(match.group("name")),
                argument=(match.group("arg") or "").strip() or None,
                body="",
                line=lineno,
            )
            first = match.group("body").strip()
            open_body = [first] if first else []
            continue

        if open_field is not None:
            if not line.strip() or line.startswith((" ", "\t")):
                open_body.append(line.strip())
                continue
            close()

        prose.append(line)

    close()
    return "\n".join(prose).strip(), fields


@dataclasses.dataclass(frozen=True)
class ValidationIssue:
    """One cross-validation finding, ready to become a Sphinx warning."""

    message: str
    #: Line within the element's doc comment, when the issue is a field.
    line: int = 0
    #: ``undocumented`` issues are reported only under ``:undoc-members:``;
    #: ``undeclared`` ones are always warnings.
    category: str = "undeclared"


def validate(doc: ParsedDoc, obj: "PssObject") -> list[ValidationIssue]:
    """Check ``doc``'s fields against what ``obj`` actually declares.

    Reports in both directions:

    * a field naming a member the element does not declare — almost always a
      rename that the comment did not follow;
    * a declared flow reference or resource claim with no field entry — the
      members whose purpose the AST cannot convey.

    Field *names* are checked too: an unknown field is reported rather than
    rendered, since a misspelled ``:ouput:`` would otherwise silently become a
    generic field list entry and read as though it worked.
    """
    issues: list[ValidationIssue] = []

    for field in doc.fields:
        spec = FIELD_SPECS.get(field.name)
        if spec is None:
            issues.append(
                ValidationIssue(
                    f"unknown documentation field ':{field.name}:' on "
                    f"{obj.kind} '{obj.qualname}'; known fields: "
                    + ", ".join(sorted({s.name for s in VOCABULARY})),
                    line=field.line,
                )
            )
            continue

        if spec.applies_to and obj.kind not in spec.applies_to:
            issues.append(
                ValidationIssue(
                    f"':{spec.name}:' does not apply to a {obj.kind} "
                    f"('{obj.qualname}'); it applies to "
                    + ", ".join(sorted(spec.applies_to)),
                    line=field.line,
                )
            )
            continue

        if not spec.validates_against or not field.argument:
            continue

        declared = set(obj.member_names(*spec.validates_against))
        # A function's parameters are its children, and a type's template
        # parameters are not, so ``:param:`` checks both.
        if spec.name == "param":
            declared |= {p.name for p in obj.template_params}

        if field.argument not in declared:
            kinds = ", ".join(sorted(spec.validates_against))
            issues.append(
                ValidationIssue(
                    f"':{spec.name} {field.argument}:' names something "
                    f"{obj.kind} '{obj.qualname}' does not declare "
                    f"(declared {kinds}: "
                    + (", ".join(sorted(declared)) if declared else "none")
                    + ")",
                    line=field.line,
                )
            )

    issues.extend(_undocumented(doc, obj))
    return issues


def _undocumented(doc: ParsedDoc, obj: "PssObject") -> list[ValidationIssue]:
    """Declared members with neither a doc comment nor a field entry."""
    issues: list[ValidationIssue] = []

    documented: set[str] = set()
    for field in doc.fields:
        spec = FIELD_SPECS.get(field.name)
        if spec is not None and field.argument and spec.validates_against:
            documented.add(field.argument)

    for member in obj.children:
        if member.kind not in DOCUMENTABLE_MEMBER_KINDS:
            continue
        if member.is_documented or member.name in documented:
            continue
        issues.append(
            ValidationIssue(
                f"{member.kind.replace('_', ' ')} '{member.name}' of "
                f"{obj.kind} '{obj.qualname}' is undocumented",
                category="undocumented",
            )
        )
    return issues
