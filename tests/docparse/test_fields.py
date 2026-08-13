"""P1-TEST-10 — the PSS field-list vocabulary."""

from __future__ import annotations

import pytest

from sphinx_pss.docparse.fields import (
    FIELD_SPECS,
    VOCABULARY,
    canonical_name,
    parse_field_list,
)

pytestmark = pytest.mark.unit


def fields(text: str):
    return parse_field_list(text)[1]


def one(text: str):
    parsed = fields(text)
    assert len(parsed) == 1, parsed
    return parsed[0]


# --- the vocabulary ---------------------------------------------------------


@pytest.mark.parametrize(
    "text,name,argument,body",
    [
        (":param len: transfer length", "param", "len", "transfer length"),
        (":input in_b: the source buffer", "input", "in_b", "the source buffer"),
        (":output out_b: the filled buffer", "output", "out_b", "the filled buffer"),
        (":lock eng: exclusive claim", "lock", "eng", "exclusive claim"),
        (":share bus: shared claim", "share", "bus", "shared claim"),
        (":field size: bytes written", "field", "size", "bytes written"),
        (":constraint c_len: word aligned", "constraint", "c_len", "word aligned"),
        (":pool chan_p: the channel pool", "pool", "chan_p", "the channel pool"),
        (":exec body: programs the engine", "exec", "body", "programs the engine"),
        (":covers c_modes: every mode", "covers", "c_modes", "every mode"),
        (":req: DMA-014, DMA-015", "req", None, "DMA-014, DMA-015"),
        (":group: Configuration", "group", None, "Configuration"),
        (":realizes: the target memcpy", "realizes", None, "the target memcpy"),
    ],
)
def test_every_field_in_the_vocabulary_parses(
    text: str, name: str, argument: str | None, body: str
) -> None:
    field = one(text)

    assert (field.name, field.argument, field.body) == (name, argument, body)


@pytest.mark.parametrize(
    "alias,canonical",
    [
        ("parameter", "param"),
        ("arg", "param"),
        ("requirement", "req"),
        ("requirements", "req"),
        ("attr", "field"),
        ("attribute", "field"),
        ("coverage", "covers"),
        ("return", "returns"),
    ],
)
def test_aliases_normalize_to_the_canonical_name(alias: str, canonical: str) -> None:
    assert canonical_name(alias) == canonical
    assert one(f":{alias}: text").name == canonical


def test_an_unknown_field_keeps_its_spelling_for_reporting() -> None:
    """Validation reports it; parsing must not silently rewrite it."""
    assert one(":ouput out_b: typo").name == "ouput"


def test_the_vocabulary_has_no_duplicate_spellings() -> None:
    spellings = [s.name for s in VOCABULARY]
    for spec in VOCABULARY:
        spellings.extend(spec.aliases)

    assert len(spellings) == len(set(spellings))
    assert set(FIELD_SPECS) == set(spellings)


# --- parsing shape ----------------------------------------------------------


def test_prose_before_the_field_list_is_kept() -> None:
    prose, parsed = parse_field_list("Summary.\n\nBody.\n\n:param n: count")

    assert prose == "Summary.\n\nBody."
    assert len(parsed) == 1


def test_several_fields_keep_source_order() -> None:
    parsed = fields(":output out_b: filled\n:input in_b: source\n:lock eng: claim")

    assert [f.name for f in parsed] == ["output", "input", "lock"]


def test_a_field_body_continues_onto_indented_lines() -> None:
    field = one(
        ":param len: transfer length in bytes;\n"
        "    must be word-aligned and non-zero"
    )

    assert field.body == (
        "transfer length in bytes;\nmust be word-aligned and non-zero"
    )


def test_a_field_may_have_an_empty_body() -> None:
    assert one(":group:").body == ""


def test_a_colon_in_the_body_is_not_a_delimiter() -> None:
    field = one(":param n: see also: the LRM")

    assert field.argument == "n"
    assert field.body == "see also: the LRM"


def test_a_non_indented_line_ends_the_field_list() -> None:
    prose, parsed = parse_field_list(":param n: count\nBack to prose.")

    assert len(parsed) == 1
    assert prose == "Back to prose."


def test_fields_record_their_line_for_reporting() -> None:
    """A warning should point at the comment line, not at the declaration."""
    parsed = fields("Summary.\n\n:param a: one\n:param b: two")

    assert [f.line for f in parsed] == [3, 4]


def test_text_with_no_fields_is_all_prose() -> None:
    prose, parsed = parse_field_list("Just prose.\n\nMore prose.")

    assert parsed == []
    assert prose == "Just prose.\n\nMore prose."


def test_empty_text() -> None:
    assert parse_field_list("") == ("", [])


def test_a_time_of_day_is_not_mistaken_for_a_field() -> None:
    """The pattern anchors at line start, so mid-line colons are safe."""
    prose, parsed = parse_field_list("Runs at 12:30 every day.")

    assert parsed == []
    assert prose == "Runs at 12:30 every day."
