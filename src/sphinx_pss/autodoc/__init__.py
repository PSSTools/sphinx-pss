"""The ``autopss*`` directives and the documenters behind them."""

from __future__ import annotations

from .directives import AUTO_DIRECTIVES, AutoPssDirective, get_index
from .documenters import (
    EVENT_PROCESS_DOC,
    EVENT_SKIP_MEMBER,
    DocumenterOptions,
    PssDocumenter,
    document_object,
)

__all__ = [
    "AUTO_DIRECTIVES",
    "EVENT_PROCESS_DOC",
    "EVENT_SKIP_MEMBER",
    "AutoPssDirective",
    "DocumenterOptions",
    "PssDocumenter",
    "document_object",
    "get_index",
]


def setup(app) -> None:
    from . import directives as _directives
    from . import documenters as _documenters

    # Events first: directives fire them, so they must exist before a build
    # can reach one.
    _documenters.setup(app)
    _directives.setup(app)
