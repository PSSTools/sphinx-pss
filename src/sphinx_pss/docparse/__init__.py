"""Doc-comment dialects: an element's documentation -> `ParsedDoc`.

Importing this package registers the dialects that ship. ``native`` is the
recommended style and the default; ``doxygen`` is a migration path for teams
arriving from a C/C++ codebase (Phase 4). An ``annotation`` dialect reading
``@doc`` is designed but unscheduled (design section 3.2) — the ABC takes the
whole `PssObject` so that it can be added without touching anything else.
"""

from __future__ import annotations

from .base import (
    DocField,
    DocstringParser,
    ParsedDoc,
    get_parser,
    parse_doc,
    register,
    registered_styles,
    split_summary,
)
from .fields import (
    FIELD_SPECS,
    VOCABULARY,
    FieldSpec,
    ValidationIssue,
    parse_field_list,
    validate,
)
from .native import NativeDocstringParser

__all__ = [
    "FIELD_SPECS",
    "VOCABULARY",
    "DocField",
    "DocstringParser",
    "FieldSpec",
    "NativeDocstringParser",
    "ParsedDoc",
    "ValidationIssue",
    "get_parser",
    "parse_doc",
    "parse_field_list",
    "register",
    "registered_styles",
    "split_summary",
    "validate",
]
