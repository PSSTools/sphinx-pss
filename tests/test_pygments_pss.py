"""``pygments-pss`` — the PSS lexer, as a dependency rather than as code here.

This project shipped its own lexer until the separate package existed. What
is left to test is not how PSS tokenizes — that belongs to ``pygments-pss``
and is tested there against the grammar — but the two things *this* project
depends on:

1. the ``pss`` alias resolves through Pygments' entry-point discovery, with no
   ``add_lexer`` call in ``setup()``; and
2. a ``pss`` code block therefore renders as highlighted PSS in a real build.

Both are integration facts, and both fail loudly if the dependency is missing
rather than degrading into plain text. That matters because the failure this
guards against is a ``-W`` build breaking in a downstream project, which is
exactly the audience this extension has.
"""

from __future__ import annotations

import pytest

# Marked per-test rather than per-module: the last one drives a real Sphinx
# build over tests/roots/test-lexer, which is what ``sphinx`` means here, while
# the rest are pure Python.


@pytest.mark.unit
def test_the_pss_alias_resolves_without_registration() -> None:
    """No ``add_lexer``: the entry point is the whole wiring.

    Asserted through ``get_lexer_by_name`` rather than by importing the class,
    because importing would pass even if the entry point were not installed —
    and the entry point is what makes ``pygmentize``, MkDocs and plain
    docutils work too, not only a Sphinx app that loaded this extension.
    """
    from pygments.lexers import get_lexer_by_name

    lexer = get_lexer_by_name("pss")

    assert type(lexer).__module__.startswith("pygments_pss")


@pytest.mark.unit
def test_this_package_no_longer_ships_a_lexer() -> None:
    """The in-tree lexer is gone, not merely unused.

    Leaving a second copy importable is how the two drift apart: a fix landing
    in ``pygments-pss`` would silently not reach anyone importing this one.
    """
    import importlib

    with pytest.raises(ImportError):
        importlib.import_module("sphinx_pss.lexer")


@pytest.mark.unit
def test_setup_registers_no_lexer(monkeypatch) -> None:
    """``setup()`` must not call ``add_lexer``.

    A leftover call would shadow the entry-point lexer inside Sphinx while
    leaving every other Pygments consumer on the packaged one — the two would
    diverge in the one place hardest to notice, rendered output.
    """
    import sphinx_pss

    calls = []

    class _App:
        def __getattr__(self, name):
            def _record(*args, **kwargs):
                calls.append(name)
                return None

            return _record

    sphinx_pss.setup(_App())

    assert "add_lexer" not in calls


@pytest.mark.sphinx("html", testroot="lexer")
def test_a_pss_code_block_is_highlighted(app, warning) -> None:
    """The end-to-end fact: a ``pss`` block renders as PSS, and warns about
    nothing.

    An unknown lexer is a warning, so this would fail a ``-W`` build — which
    is how the missing lexer surfaced in the first place.
    """
    app.build()

    assert "WARNING" not in warning.getvalue()

    html = (app.outdir / "index.html").read_text(encoding="utf-8")

    # The fallback for an unknown lexer emits the source with no spans at all,
    # so requiring the specific tokens is what separates "highlighted" from
    # "rendered as text". ``kd`` is Keyword.Declaration (``package``,
    # ``buffer``), ``nc`` is Name.Class (the declared name).
    assert '<span class="kd">package</span>' in html
    assert '<span class="kd">buffer</span>' in html
    assert '<span class="nc">Descriptor</span>' in html
