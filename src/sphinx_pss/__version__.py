#****************************************************************************
#* __version__.py
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
"""Version, following the ``pssparser`` / ``pygments-pss`` pattern.

``BASE`` is the released number and ``SUFFIX`` is empty in the source tree; CI
rewrites ``SUFFIX`` to ``.$RUN_ID`` so every build carries a unique, increasing
dev version without a hand edit. ``get_version()`` additionally appends
``git describe`` output when run from a checkout.

Single-sourced deliberately: the version lived in both ``pyproject.toml`` and
``__init__.py`` as two hand-maintained literals, which is one edit away from a
wheel whose metadata and ``sphinx_pss.__version__`` disagree -- and Sphinx
reports the latter in ``sphinx-build`` diagnostics, so the two being different
is confusing exactly when someone is debugging.

This module must stay importable on its own: ``pyproject.toml`` reads
``_pkg_version`` from it at build time, when neither Sphinx nor ``pssparser``
is necessarily installed.
"""

import os
import re

BASE = "0.0.1"
SUFFIX = ""

__version__ = (BASE, SUFFIX)

# Read by pyproject.toml's dynamic-version hook.
_pkg_version = BASE + SUFFIX


def get_version() -> str:
    """Return the full version, appending git describe when in a source tree."""
    base, suffix = __version__
    version = base + suffix

    src_dir = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    git_dir = os.path.join(src_dir, ".git")

    if os.path.isdir(git_dir):
        try:
            import subprocess

            out = (
                subprocess.check_output(
                    ["git", "describe", "--tags", "--dirty", "--always"],
                    cwd=src_dir,
                    stderr=subprocess.DEVNULL,
                )
                .decode()
                .strip()
            )
            if out != base:
                # PEP 440 local versions allow only alphanumerics and dots, so
                # "v0.0.1-3-gdeadbee-dirty" has to be normalised -- pip rejects
                # the raw form as soon as this repo carries a tag.
                local = re.sub(r"[^0-9A-Za-z.]+", ".", out).strip(".")
                return "%s+%s" % (version, local)
        except Exception:
            pass

    return version
