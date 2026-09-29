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
"""sphinx-pss's pssparser extension: checkers run by ``pssparser``, not Sphinx.

Registered through the ``pssparser.extensions`` entry point, so installing
sphinx-pss makes them available to ``pssparser`` on the command line. Nothing
here imports Sphinx.
"""

from __future__ import annotations

from .steps import StepCommentChecker

__all__ = ["StepCommentChecker", "register"]


def register(reg) -> None:
    """The ``pssparser.extensions`` entry point."""
    from .. import __version__

    reg.version = __version__
    reg.description = "Migration aid for programming-step markers"
    reg.add_checker(StepCommentChecker)
