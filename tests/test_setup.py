"""P0-TEST-2 — the extension loads and registers what it promises."""

from __future__ import annotations

import types

import pytest

from sphinx_pss.config import CONFIG_VALUES, PssConfigError, validate_config


def _config(**overrides):
    """A stand-in for ``sphinx.config.Config`` holding only the defaults."""
    values = {v.name: v.default for v in CONFIG_VALUES}
    values.update(overrides)
    return types.SimpleNamespace(**values)


@pytest.mark.sphinx("html", testroot="minimal")
def test_extension_loads(app) -> None:
    assert "sphinx_pss" in app.extensions
    assert app.extensions["sphinx_pss"].version != "unknown version"


@pytest.mark.sphinx("html", testroot="minimal")
def test_all_config_values_are_registered(app) -> None:
    for value in CONFIG_VALUES:
        assert hasattr(app.config, value.name), f"{value.name} not registered"
        assert getattr(app.config, value.name) == value.default


@pytest.mark.sphinx(
    "html", testroot="minimal", confoverrides={"pss_doc_style": "nonsense"}
)
def test_a_bad_value_fails_the_build_without_being_re_wrapped(
    make_app, app_params
) -> None:
    """The error must reach the user intact.

    ``EventManager.emit`` wraps any non-``SphinxError`` handler exception in an
    ``ExtensionError`` whose message is "Handler ... threw an exception", which
    hides the actual problem. `PssConfigError` derives from ``ConfigError`` so
    that does not happen.
    """
    args, kwargs = app_params
    with pytest.raises(PssConfigError) as excinfo:
        make_app(*args, **kwargs)
    assert "pss_doc_style" in str(excinfo.value)
    assert "'native'" in str(excinfo.value)


@pytest.mark.unit
def test_unknown_doc_style_is_a_clear_error() -> None:
    with pytest.raises(PssConfigError, match="pss_doc_style"):
        validate_config(None, _config(pss_doc_style="nonsense"))


@pytest.mark.unit
def test_unknown_diagram_backend_is_a_clear_error() -> None:
    with pytest.raises(PssConfigError, match="pss_diagrams"):
        validate_config(None, _config(pss_diagrams="ascii-art"))


@pytest.mark.unit
def test_unknown_member_order_is_a_clear_error() -> None:
    with pytest.raises(PssConfigError, match="member-order"):
        validate_config(None, _config(pss_default_options={"member-order": "random"}))


@pytest.mark.unit
@pytest.mark.parametrize("key", ["pss_source_dirs", "pss_source_files"])
def test_source_paths_must_be_a_list_of_strings(key: str) -> None:
    """A bare string is the obvious typo, and iterates as characters."""
    with pytest.raises(PssConfigError, match=key):
        validate_config(None, _config(**{key: "../model"}))

    with pytest.raises(PssConfigError, match=key):
        validate_config(None, _config(**{key: ["ok", 3]}))


@pytest.mark.unit
def test_defaults_validate() -> None:
    validate_config(None, _config())
