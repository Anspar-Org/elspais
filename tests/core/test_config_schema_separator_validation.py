"""Separator ambiguity validation in the config schema (REQ-d00251-F/-H).

The guard derives the alphabet of the component and of the assertion label
from their patterns and rejects a separator drawn from either alphabet.
These tests pin the parts of that derivation that a filler-character probe
got wrong: characters legal only after the first position, patterns whose
shortest match is longer than a probe string, and separators longer than one
character (checked per character, since a run of legal characters is absorbed
exactly as a single one is) or empty (no boundary at all -- and an empty
multi-separator was silently rewritten to "+" downstream).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from elspais.config.schema import ElspaisConfig, _legal_chars
from elspais.utilities.patterns import ComponentFormat, component_regex


def _payload(*, component: dict | None = None, assertions: dict | None = None) -> dict:
    return {
        "project": {"name": "x", "namespace": "REQ"},
        "id-patterns": {
            "component": component or {"style": "numeric"},
            "assertions": assertions or {},
        },
    }


def _legal_component_chars(style: str, pattern: str = "") -> set[str]:
    return _legal_chars(
        component_regex(ComponentFormat(style=style, digits=5, leading_zeros=True, pattern=pattern))
    )


class TestLegalCharDerivation:
    """The alphabet is the whole alphabet, not just the leading position."""

    @pytest.mark.parametrize(
        "style,expected",
        [
            ("PascalCase", set("abcxyz0159")),
            ("camelCase", set("ABCXYZ0159")),
            ("snake_case", set("_09az")),
            ("kebab-case", set("-09az")),
            ("numeric", set("0123456789")),
        ],
    )
    def test_non_leading_characters_are_legal(self, style, expected):
        # Verifies: REQ-d00251-F
        legal = _legal_component_chars(style)
        assert expected <= legal, f"{style}: missing {sorted(expected - legal)}"

    @pytest.mark.parametrize("style,forbidden", [("PascalCase", "-"), ("camelCase", ":")])
    def test_characters_outside_the_pattern_stay_illegal(self, style, forbidden):
        # Verifies: REQ-d00251-F
        assert forbidden not in _legal_component_chars(style)

    def test_pattern_longer_than_a_probe_still_yields_its_alphabet(self):
        # Verifies: REQ-d00251-F
        # No match of this pattern is shorter than five characters, so a
        # short probe string never matches and the alphabet came back empty.
        assert _legal_component_chars("regex", "[0-9]{5,}") == set("0123456789")

    def test_label_alphabet_covers_multi_character_labels(self):
        # Verifies: REQ-d00251-J
        # "10" is a legal numeric_1based label, so "0" is a label character.
        assert "0" in _legal_chars(r"[1-9][0-9]?")


class TestSeparatorRejectedFromWholeAlphabet:
    @pytest.mark.parametrize(
        "style,pattern,separator",
        [
            ("PascalCase", None, "x"),
            ("PascalCase", None, "5"),
            ("camelCase", None, "X"),
            ("regex", "[0-9]{5,}", "5"),
        ],
    )
    def test_separator_legal_after_first_position_rejected(self, style, pattern, separator):
        # Verifies: REQ-d00251-F
        component = {"style": style}
        if pattern:
            component["pattern"] = pattern
        with pytest.raises(ValidationError) as excinfo:
            ElspaisConfig.model_validate(
                _payload(
                    component=component,
                    assertions={"label_style": "uppercase", "separator": separator},
                )
            )
        msg = str(excinfo.value)
        assert "separator" in msg and f'"{separator}"' in msg

    def test_multi_separator_legal_in_a_two_digit_label_rejected(self):
        # Verifies: REQ-d00251-J
        with pytest.raises(ValidationError) as excinfo:
            ElspaisConfig.model_validate(
                _payload(
                    assertions={
                        "label_style": "numeric_1based",
                        "separator": "-",
                        "multi_separator": "0",
                    }
                )
            )
        assert "multi_separator" in str(excinfo.value)

    @pytest.mark.parametrize(
        "style,pattern,separator",
        [
            ("PascalCase", None, "-"),
            ("regex", "[0-9]{5,}", "/"),
            ("numeric", None, "-"),
        ],
    )
    def test_separator_outside_both_alphabets_still_loads(self, style, pattern, separator):
        # Verifies: REQ-d00251-F
        component = {"style": style}
        if pattern:
            component["pattern"] = pattern
        cfg = ElspaisConfig.model_validate(
            _payload(
                component=component,
                assertions={"label_style": "uppercase", "separator": separator},
            )
        )
        assert cfg.id_patterns.assertions.separator == separator


class TestSeparatorLength:
    """A separator is a character. Any other length is not a findable boundary."""

    @pytest.mark.parametrize(
        "style,separator",
        [
            ("kebab-case", "--"),
            ("snake_case", "__"),
            ("numeric", "AB"),
            ("numeric", "1x"),
        ],
    )
    def test_multi_character_separator_with_a_taken_character_rejected(self, style, separator):
        # Verifies: REQ-d00251-K
        with pytest.raises(ValidationError) as excinfo:
            ElspaisConfig.model_validate(
                _payload(
                    component={"style": style},
                    assertions={"label_style": "uppercase", "separator": separator},
                )
            )
        assert "separator" in str(excinfo.value)

    @pytest.mark.parametrize("separator", ["::", "//", " -"])
    def test_multi_character_separator_of_clean_characters_rejected(self, separator):
        """Length is decided on its own terms: none of these characters can
        appear in a component or a label, and the separator is still refused."""
        # Verifies: REQ-d00251-K
        with pytest.raises(ValidationError) as excinfo:
            ElspaisConfig.model_validate(
                _payload(
                    component={"style": "kebab-case"},
                    assertions={"label_style": "uppercase", "separator": separator},
                )
            )
        assert "at most 1 character" in str(excinfo.value)

    def test_multi_character_multi_separator_of_clean_characters_rejected(self):
        # Verifies: REQ-d00251-K
        with pytest.raises(ValidationError) as excinfo:
            ElspaisConfig.model_validate(
                _payload(assertions={"label_style": "uppercase", "multi_separator": "++"})
            )
        assert "at most 1 character" in str(excinfo.value)

    def test_empty_separator_rejected(self):
        # Verifies: REQ-d00251-K
        with pytest.raises(ValidationError) as excinfo:
            ElspaisConfig.model_validate(_payload(assertions={"separator": ""}))
        assert "separator" in str(excinfo.value)

    @pytest.mark.parametrize("multi_separator", ["", "AB", "1A"])
    def test_empty_or_colliding_multi_separator_rejected(self, multi_separator):
        # Verifies: REQ-d00251-J, REQ-d00251-K
        with pytest.raises(ValidationError) as excinfo:
            ElspaisConfig.model_validate(
                _payload(
                    assertions={
                        "label_style": "uppercase",
                        "multi_separator": multi_separator,
                    }
                )
            )
        assert "multi_separator" in str(excinfo.value)

    def test_shipped_defaults_still_load(self):
        # Verifies: REQ-d00251-F
        cfg = ElspaisConfig.model_validate(_payload())
        assert cfg.id_patterns.assertions.separator == "-"
        assert cfg.id_patterns.assertions.multi_separator == "+"


class TestSeparatorMustNotDivideReferences:
    """A character a reference list already spends cannot also join an
    identifier to its label.

    A *Traceability* keyword introduces a list, and the list is divided into
    its items before any item is read. A "," inside an identifier is
    therefore consumed by the outer boundary first: what reaches the reader
    is a truncated reference and a bare label with no requirement in front of
    it -- no edge, no diagnostic. The configuration is refused instead.
    """

    @pytest.mark.parametrize("field", ["separator", "multi_separator"])
    def test_reference_list_separator_rejected(self, field):
        # Verifies: REQ-d00251-M
        with pytest.raises(ValidationError) as excinfo:
            ElspaisConfig.model_validate(
                _payload(assertions={"label_style": "uppercase", field: ","})
            )
        msg = str(excinfo.value)
        assert field in msg, f"the refusal must name the offending field; got {msg!r}"
        assert '","' in msg, f"the refusal must name the offending character; got {msg!r}"
        assert "divides" in msg, (
            "the refusal must say the character is already spent dividing one "
            f"reference from the next; got {msg!r}"
        )

    @pytest.mark.parametrize("field", ["separator", "multi_separator"])
    def test_an_unspent_character_is_still_accepted(self, field):
        """The refusal is about this one character's other role, not about
        departing from the shipped defaults."""
        # Verifies: REQ-d00251-M
        cfg = ElspaisConfig.model_validate(
            _payload(assertions={"label_style": "uppercase", field: "&"})
        )
        assert getattr(cfg.id_patterns.assertions, field) == "&"
