#****************************************************************************
#* __init__.py
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
