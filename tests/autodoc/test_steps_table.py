"""Step tables in a build (plan ``S3-TEST-1`` to ``S3-TEST-5``).

``test-steps`` renders the Ethernet fixture in every directive form and must
build clean under ``-W``; ``test-steps-errors`` asks for tables wrongly, and
each mistake is an error at its line of ``index.rst``; ``test-steps-warnings``
has problems in its ``.pss`` source, and each is reported there.

Tables are compared as rows of ``(number, step, details, source)`` text, with
the Step column's indentation shown as two spaces per level.
"""

from __future__ import annotations

import re

import pytest
from sphinx.util.console import strip_colors

pytestmark = pytest.mark.sphinx


def _tables(app, docname: str = "index") -> list[list[tuple[str, ...]]]:
    """Every step table on the page, as rows of cell text, header row first."""
    from docutils import nodes

    doctree = app.env.get_doctree(docname)
    found = []
    for table in doctree.findall(nodes.table):
        if "pss-steps" not in table["classes"]:
            continue
        rows = []
        for row in table.findall(nodes.row):
            cells = [" / ".join(p.astext() for p in entry.children) for entry in row.children]
            cells[1] = cells[1].replace("\u2003\u2003", "  ")
            rows.append(tuple(cells))
        found.append(rows)
    return found


def _messages(warning) -> list[tuple[str, int, str]]:
    """``(file name, line, message)`` for each warning or error."""
    found = []
    for line in strip_colors(warning.getvalue()).splitlines():
        match = re.search(r"([^/\s]+):(\d+): (?:WARNING|ERROR): (.*)", line)
        if match:
            found.append((match.group(1), int(match.group(2)), match.group(3)))
    return found


HEADER = ("#", "Step", "Details", "Source")

# --- S3-TEST-1: every directive form, clean under -W ----------------------------


@pytest.mark.sphinx("html", testroot="steps", freshenv=True, warningiserror=True)
def test_every_directive_form_builds_clean(app, warning) -> None:
    app.build()

    assert _messages(warning) == []
    assert len(_tables(app)) == 10
    assert all(table[0] == HEADER for table in _tables(app))


# --- S3-TEST-2: rows, numbering, control rows, groups, sources ------------------


@pytest.mark.sphinx("html", testroot="steps", freshenv=True)
def test_calls_nest_their_callees_steps_in_decimal(app) -> None:
    app.build()
    decimal = _tables(app)[0]

    assert decimal[1:] == [
        ("1", "Initialize the Ethernet controller", "", "eth_mac.pss:89"),
        ("1.1", "  Disable the controller", "Clear ON, then stop reception and transmission.", "eth_mac.pss:35"),
        ("1.2", "  Wait for the controller to go idle", "", "eth_mac.pss:40"),
        ("1.3", "  Disable and clear the Ethernet interrupts", "", "eth_mac.pss:43"),
        ("1.4", "  Clear the descriptor start addresses", "", "eth_mac.pss:47"),
        ("2", "Initialize the MAC", "", "eth_mac.pss:92"),
        ("2.1", "  Reset the MAC", "", "eth_mac.pss:74"),
        ("2.2", "  Initialize the MII management interface", "", "eth_mac.pss:78"),
        ("2.2.1", "    Reset the RMII module, if RMII is in use", "RESETRMII is set, then cleared.", "eth_mac.pss:54"),
        ("2.2.2", "    Reset the MII management block", "", "eth_mac.pss:61"),
        ("2.2.3", "    Select the MDC clock divider", "SYSCLK / 40 keeps MDC below 2.5 MHz.", "eth_mac.pss:64"),
        ("2.2.4", "    Release the MII management block", "", "eth_mac.pss:68"),
        ("2.3", "  Enable the receiver", "", "eth_mac.pss:81"),
        ("3", "Enable the controller", "", "eth_mac.pss:95"),
    ]  # fmt: skip


@pytest.mark.sphinx("html", testroot="steps", freshenv=True)
def test_the_outline_numbering_is_the_frms(app) -> None:
    """``S3-TEST-3``, the acceptance fixture: Microchip FRM 35.4.10 numbers the
    bring-up 1, then a), b), then i., ii. under the MII step."""
    app.build()
    outline = _tables(app)[1]

    assert [(row[0], row[1].strip()) for row in outline[1:]] == [
        ("1", "Initialize the Ethernet controller"),
        ("a)", "Disable the controller"),
        ("b)", "Wait for the controller to go idle"),
        ("c)", "Disable and clear the Ethernet interrupts"),
        ("d)", "Clear the descriptor start addresses"),
        ("2", "Initialize the MAC"),
        ("a)", "Reset the MAC"),
        ("b)", "Initialize the MII management interface"),
        ("i.", "Reset the RMII module, if RMII is in use"),
        ("ii.", "Reset the MII management block"),
        ("iii.", "Select the MDC clock divider"),
        ("iv.", "Release the MII management block"),
        ("c)", "Enable the receiver"),
        ("3", "Enable the controller"),
    ]


@pytest.mark.sphinx("html", testroot="steps", freshenv=True)
def test_a_marked_control_is_one_row_with_its_condition(app) -> None:
    """The marker titles the row and the condition is the second line (design
    4.3); a ``match``'s choices are unnumbered rows of their own."""
    app.build()
    set_speed = _tables(app)[2]

    assert set_speed[1:] == [
        ("1", "Program the speed / Depending on speed:", "", "eth_mac.pss:101"),
        ("", "  When SPEED_10:", "", "eth_mac.pss:103"),
        ("1.1", "    Select 10 Mbps", "", "eth_mac.pss:104"),
        ("", "  When SPEED_100:", "", "eth_mac.pss:107"),
        ("1.2", "    Select 100 Mbps", "", "eth_mac.pss:108"),
        ("2", "Poll the PHY until the link is up / Repeat until not (read_reg(0x2A0) & 0x4) == 0:", "", "eth_mac.pss:113"),
        ("2.1", "  Read the PHY status", "", "eth_mac.pss:115"),
        ("3", "Settle / Repeat retries times:", "", "eth_mac.pss:119"),
        ("3.1", "  Wait one MDC period", "", "eth_mac.pss:121"),
    ]  # fmt: skip


@pytest.mark.sphinx("html", testroot="steps", freshenv=True)
def test_conditions_are_literal_text(app) -> None:
    from docutils import nodes

    app.build()
    doctree = app.env.get_doctree("index")
    literals = {n.astext() for n in doctree.findall(nodes.literal)}

    assert {"speed", "SPEED_10", "(read_reg(0x2A0) & 0x4) == 0", "retries", "d", "descriptors", "n > 0"} <= literals


@pytest.mark.sphinx("html", testroot="steps", freshenv=True)
def test_foreach_recursion_and_links(app) -> None:
    app.build()
    tables = _tables(app)

    assert tables[3][1:] == [
        ("1", "Release each descriptor / For each d in descriptors:", "", "eth_mac.pss:128"),
        ("1.1", "  Clear its ownership bit", "", "eth_mac.pss:130"),
    ]
    assert tables[4][1:] == [
        ("1", "Drain one descriptor", "", "eth_mac.pss:137"),
        ("1.1", "  Release the descriptor", "", "eth_mac.pss:143"),
        ("1.2", "  Flush the rest /   If n > 0:", "", "eth_mac.pss:146"),
        ("", "    Repeat from step 1 (flush_rx)", "", "eth_mac.pss:148"),
    ]
    assert tables[5][1:] == [
        ("1", "Reset the MAC", "", "eth_mac.pss:74"),
        ("2", "Initialize the MII management interface", "", "eth_mac.pss:78"),
        ("", "  Follow the steps of init_miim", "", "eth_mac.pss:79"),
        ("3", "Enable the receiver", "", "eth_mac.pss:81"),
    ]


@pytest.mark.sphinx("html", testroot="steps", freshenv=True)
def test_a_linked_callee_links_to_its_entry(app) -> None:
    """``init_miim`` is documented on the same page, by ``autopssfunction``."""
    app.build()
    html = (app.outdir / "index.html").read_text()

    assert re.search(r'<a class="reference internal" href="#pss-eth_pkg.init_miim"[^>]*>'
                     r'<code[^>]*><span class="pre">init_miim</span>', html)


@pytest.mark.sphinx("html", testroot="steps", freshenv=True)
def test_depth_and_a_relative_name(app) -> None:
    """``init_eth`` resolves as a bare name; ``:depth: 1`` stops at its callees' steps."""
    app.build()
    shallow = _tables(app)[6]

    assert [row[0] for row in shallow[1:]] == ["1", "1.1", "1.2", "1.3", "1.4", "2", "2.1", "2.2", "2.3", "3"]


@pytest.mark.sphinx("html", testroot="steps", freshenv=True)
def test_exec_blocks_and_extension_groups(app) -> None:
    app.build()
    tables = _tables(app)

    assert tables[7][1][:2] == ("1", "Bring up the Ethernet port")
    assert tables[7][-1][:2] == ("1.3", "  Enable the controller")
    assert tables[8][1:] == [
        ("1", "Queue the frame", "", "eth_mac.pss:160"),
        ("", "Added by an extension", "", "eth_ext_a.pss:9"),
        ("2", "Start transmission", "", "eth_ext_a.pss:10"),
        ("", "Added by an extension", "", "eth_ext_b.pss:7"),
        ("3", "Wait for the frame to go out", "", "eth_ext_b.pss:8"),
    ]


@pytest.mark.sphinx("html", testroot="steps", freshenv=True)
def test_the_steps_flag_puts_the_table_in_the_entry(app) -> None:
    from sphinx import addnodes

    app.build()
    doctree = app.env.get_doctree("index")
    [entry] = [
        d for d in doctree.findall(addnodes.desc)
        if any(s.get("pss:fullname") == "eth_pkg::init_miim" for s in d.findall(addnodes.desc_signature))
    ]
    content = next(iter(entry.findall(addnodes.desc_content)))

    assert "pss-steps" in content.children[-1]["classes"]
    assert _tables(app)[9][1][:2] == ("1", "Reset the RMII module, if RMII is in use")


# --- S3-TEST-4: problems in the .pss source are reported there ------------------


@pytest.mark.sphinx("html", testroot="steps-warnings", freshenv=True)
def test_markup_errors_in_steps_point_at_the_pss_lines(app, warning) -> None:
    app.build()
    messages = _messages(warning)

    assert ("model.pss", 7, "Inline literal start-string without end-string. [docutils]") in messages
    assert ("model.pss", 10, "Inline emphasis start-string without end-string. [docutils]") in messages
    assert ("model.pss", 12, 'Unknown target name: "the manual". [docutils]') in messages


@pytest.mark.sphinx(
    "html", testroot="steps-warnings", freshenv=True, confoverrides={"show_warning_types": True}
)
def test_prelude_and_lint_warnings_point_at_the_pss_lines(app, warning) -> None:
    app.build()
    messages = _messages(warning)

    prelude = [m for m in messages if m[2].endswith("[pss.step_prelude_call]")]
    assert [m[:2] for m in prelude] == [("model.pss", 6)], "once, though two tables show p::f"
    assert prelude[0][2].startswith("call to 'helper' is outside every step")
    assert [m[:2] for m in messages if m[2].endswith("[pss.step_syntax]")] == [("model.pss", 17)]


@pytest.mark.sphinx("html", testroot="steps-warnings", freshenv=True)
def test_only_the_request_itself_is_located_on_the_page(app, warning) -> None:
    """A body with no markers is the page's mistake; everything else is the source's."""
    app.build()

    on_page = [m for m in _messages(warning) if m[0] == "index.rst"]
    assert on_page == [
        ("index.rst", 11, "sphinx-pss: 'p::g' has no step markers, so there is no step table [pss.steps]")
    ]


@pytest.mark.sphinx(
    "html", testroot="steps-warnings", freshenv=True, confoverrides={"suppress_warnings": ["pss.step_prelude_call"]}
)
def test_the_prelude_warning_can_be_suppressed(app, warning) -> None:
    app.build()

    assert "outside every step" not in warning.getvalue()


# --- S3-TEST-5: option errors (flowchart and both became valid in S4) -----------


@pytest.mark.sphinx("html", testroot="steps-errors", freshenv=True)
def test_each_wrong_request_is_an_error_at_its_line(app, warning) -> None:
    app.build()
    errors = [(line, message) for name, line, message in _messages(warning) if name == "index.rst"]
    valid = "body, init_down, init_up, post_solve, pre_body, pre_solve, run_end, run_start"

    assert errors == [
        (4, f"sphinx-pss: unknown exec kind 'startup'; expected one of: {valid} [docutils]"),
        (7, f"sphinx-pss: 'eth_pkg::eth_c' is a type: name its exec block with the ':exec:' option, one of: {valid} [docutils]"),
        (9, "sphinx-pss: unknown step format 'diagram'; expected one of: table, flowchart, both [docutils]"),
        (12, "sphinx-pss: unknown step format 'Table'; expected one of: table, flowchart, both [docutils]"),
        (15, "sphinx-pss: no PSS function or type named 'eth_pkg::init_ethernet' [docutils]"),
        (17, "sphinx-pss: function 'eth_pkg::write_reg' has no body, only a declaration [docutils]"),
        (19, "sphinx-pss: 'eth_pkg::init_eth' is a function; the ':exec:' option names an exec block of a type [docutils]"),
        (22, "sphinx-pss: unknown numbering 'roman'; expected one of: decimal, outline [docutils]"),
        (25, "sphinx-pss: unknown expand-calls mode 'sometimes'; expected one of: inline, link, none [docutils]"),
        (28, "sphinx-pss: 'eth_pkg::speed_e' is an enum, which has no body: steps are shown for a function, or for a type's exec blocks [docutils]"),
        (30, "sphinx-pss: 'eth_pkg::eth_c' has no 'exec run_start' block [docutils]"),
        (33, f"sphinx-pss: 'eth_pkg::eth_c::send_a' is a type: name its exec block with the ':exec:' option, one of: {valid} [docutils]"),
    ]  # fmt: skip


@pytest.mark.sphinx("html", testroot="steps-errors", freshenv=True)
def test_a_wrong_steps_flag_still_documents_the_entry(app) -> None:
    from sphinx import addnodes

    app.build()
    doctree = app.env.get_doctree("index")

    assert any(
        s.get("pss:fullname") == "eth_pkg::eth_c::send_a" for s in doctree.findall(addnodes.desc_signature)
    )


@pytest.mark.sphinx("html", testroot="steps-unlinked", freshenv=True)
def test_an_unlinked_model_warns_once_and_renders_nothing(app, warning) -> None:
    """``S2-IMPL-10``, the directive half: one warning for the build, no tables."""
    app.build()

    unavailable = [m for m in _messages(warning) if "programming steps are unavailable" in m[2]]
    assert [m[:2] for m in unavailable] == [("index.rst", 4)]
    assert _tables(app) == []
