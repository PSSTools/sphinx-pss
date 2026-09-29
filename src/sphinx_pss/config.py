#****************************************************************************
#* config.py
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
"""Configuration values for the ``sphinx_pss`` extension.

Every ``pss_*`` value the extension understands is declared here, in one place,
so ``__init__.setup`` stays a wiring function. See ``design/sphinx-pss-design.md``
section 7 for the rationale behind each value.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, NamedTuple

from sphinx.errors import ConfigError

if TYPE_CHECKING:
    from sphinx.application import Sphinx
    from sphinx.config import Config


#: Doc-comment dialects ``pss_doc_style`` accepts. ``annotation`` is designed
#: but unscheduled (design section 3.2), so it is deliberately absent.
DOC_STYLES = ("native", "doxygen", "auto")

#: Diagram back-ends ``pss_diagrams`` accepts.
DIAGRAM_BACKENDS = ("graphviz", "mermaid", "off")

#: Member orderings ``:member-order:`` and ``pss_default_options`` accept.
MEMBER_ORDERS = ("source", "alpha", "groups")

#: ``activity-format`` values (activity-diagrams design 7.1).
ACTIVITY_FORMATS = ("diagram", "outline", "both")
#: ``activity-steps`` values (activity-diagrams design 5.2).
ACTIVITY_STEP_MODES = ("regions", "collapsed", "none")
#: The deepest ``activity-depth`` (activity-diagrams design 5.3).
ACTIVITY_MAX_DEPTH = 4


class ConfigValue(NamedTuple):
    """One ``app.add_config_value`` registration."""

    name: str
    default: Any
    rebuild: str
    types: Any


CONFIG_VALUES: tuple[ConfigValue, ...] = (
    # --- input -------------------------------------------------------------
    ConfigValue("pss_source_dirs", [], "env", (list, tuple)),
    ConfigValue("pss_source_files", [], "env", (list, tuple)),
    # --- documentation extraction -----------------------------------------
    ConfigValue("pss_doc_style", "native", "env", str),
    ConfigValue("pss_document_stdlib", False, "env", bool),
    ConfigValue("pss_tolerate_link_errors", False, "env", bool),
    # --- rendering ---------------------------------------------------------
    ConfigValue("pss_diagrams", "graphviz", "env", str),
    ConfigValue("pss_viewcode", True, "env", bool),
    ConfigValue("pss_default_options", {}, "env", dict),
)


class PssConfigError(ConfigError):
    """Raised for a ``pss_*`` value that cannot produce a sensible build.

    Deriving from Sphinx's `ConfigError` matters: `sphinx.events.EventManager`
    re-wraps an arbitrary handler exception in an `ExtensionError` ("Handler
    ... threw an exception"), which buries the actual problem. A `SphinxError`
    subclass propagates unwrapped, so the user sees the message below and
    nothing else.
    """


def _check_choice(name: str, value: Any, choices: tuple[str, ...]) -> None:
    if value not in choices:
        raise PssConfigError(
            f"{name}: {value!r} is not a valid value; expected one of "
            + ", ".join(repr(c) for c in choices)
        )


def validate_config(app: Sphinx | None, config: Config) -> None:
    """Validate ``pss_*`` values once the user's ``conf.py`` has been read.

    Connected to ``config-inited``. Fails early and specifically rather than
    letting a typo surface later as an empty document.
    """
    _check_choice("pss_doc_style", config.pss_doc_style, DOC_STYLES)
    _check_choice("pss_diagrams", config.pss_diagrams, DIAGRAM_BACKENDS)

    for key in ("pss_source_dirs", "pss_source_files"):
        value = getattr(config, key)
        if isinstance(value, str) or not all(isinstance(v, str) for v in value):
            raise PssConfigError(
                f"{key}: expected a list of path strings, got {value!r}"
            )

    if "steps" in config.pss_default_options:
        raise PssConfigError(
            "pss_default_options: 'steps' can't be a default. Step tables appear "
            "only where a page asks for one, with ':steps:' on an autopss "
            "directive or with 'pss:steps'"
        )

    order = config.pss_default_options.get("member-order")
    if order is not None:
        _check_choice("pss_default_options['member-order']", order, MEMBER_ORDERS)

    # An activity diagram on every action is a reasonable project default,
    # unlike a step table (activity-diagrams design 7.2).
    fmt = config.pss_default_options.get("activity-format")
    if fmt is not None:
        _check_choice("pss_default_options['activity-format']", fmt, ACTIVITY_FORMATS)
    steps = config.pss_default_options.get("activity-steps")
    if steps is not None:
        _check_choice("pss_default_options['activity-steps']", steps, ACTIVITY_STEP_MODES)
    depth = config.pss_default_options.get("activity-depth")
    if depth is not None and (
        isinstance(depth, bool) or not isinstance(depth, int) or not 1 <= depth <= ACTIVITY_MAX_DEPTH
    ):
        raise PssConfigError(
            f"pss_default_options['activity-depth']: {depth!r} is not a valid value; "
            f"expected a whole number from 1 to {ACTIVITY_MAX_DEPTH}"
        )


def setup(app: Sphinx) -> None:
    """Register every ``pss_*`` config value and the validator."""
    for value in CONFIG_VALUES:
        app.add_config_value(value.name, value.default, value.rebuild, value.types)
    app.connect("config-inited", validate_config)
