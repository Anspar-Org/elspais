"""Tests for the Component Style Redesign (REQ-d00251).

These tests encode the behavior specified in
``docs/superpowers/specs/2026-05-11-component-style-redesign-design.md``,
which is now implemented in this codebase (config schema, resolver,
grammar tokens).

Each test function carries a ``# Verifies: REQ-d00251-X`` comment naming
the assertion it exercises.
"""

from __future__ import annotations

import re

import pytest
from pydantic import ValidationError

from elspais.config.schema import ElspaisConfig
from elspais.utilities.patterns import IdPatternConfig, IdResolver

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_resolver(
    *,
    style: str,
    pattern: str | None = None,
    separator: str = "-",
    label_style: str = "uppercase",
    multi_separator: str = "+",
    namespace: str = "EVS",
) -> IdResolver:
    """Construct an IdResolver mimicking the Cure-HHT shape.

    Canonical template ``{namespace}-{type}-{component}`` with a single
    ``PRD`` type, configurable component style + assertion separator.
    """
    raw_assert: dict = {
        "label_style": label_style,
        "max_count": 26,
        "separator": separator,
        "multi_separator": multi_separator,
    }
    raw_comp: dict = {"style": style}
    if pattern is not None:
        raw_comp["pattern"] = pattern
    config = IdPatternConfig.from_dict(
        {
            "project": {"namespace": namespace},
            "id-patterns": {
                "canonical": "{namespace}-{type}-{component}",
                "types": {"PRD": {"level": 1}},
                "component": raw_comp,
                "assertions": raw_assert,
            },
        }
    )
    return IdResolver(config)


def _elspais_config_payload(
    *,
    style: str,
    pattern: str | None = None,
    separator: str | None = None,
    multi_separator: str | None = None,
    label_style: str = "uppercase",
) -> dict:
    """Build a minimal payload for ``ElspaisConfig.model_validate``."""
    component: dict = {"style": style}
    if pattern is not None:
        component["pattern"] = pattern
    assertions: dict = {"label_style": label_style}
    if separator is not None:
        assertions["separator"] = separator
    if multi_separator is not None:
        assertions["multi_separator"] = multi_separator
    return {
        "id-patterns": {
            "component": component,
            "assertions": assertions,
        }
    }


# ---------------------------------------------------------------------------
# REQ-d00251-A: style vocabulary
# ---------------------------------------------------------------------------


class TestStyleVocabulary:
    """``ComponentConfig.style`` accepts exactly six values."""

    @pytest.mark.parametrize(
        "style,extra",
        [
            ("numeric", {}),
            ("camelCase", {}),
            ("PascalCase", {}),
            ("snake_case", {}),
            # "-" cannot bound a kebab-case component, so this style is
            # exercised with a separator it does not overlap.
            ("kebab-case", {"separator": "/"}),
            ("regex", {"pattern": "[A-Z][a-z]+"}),
        ],
    )
    def test_valid_styles_load(self, style, extra):
        # Verifies: REQ-d00251-A
        payload = _elspais_config_payload(style=style, **extra)
        cfg = ElspaisConfig.model_validate(payload)
        assert cfg.id_patterns.component.style == style

    @pytest.mark.parametrize("legacy_style", ["named", "alphanumeric"])
    def test_legacy_styles_rejected_at_config_load(self, legacy_style):
        # Verifies: REQ-d00251-A
        payload = _elspais_config_payload(style=legacy_style, pattern="[A-Za-z][A-Za-z0-9]+")
        with pytest.raises(ValidationError):
            ElspaisConfig.model_validate(payload)


# ---------------------------------------------------------------------------
# REQ-d00251-B: fixed regexes per case-style
# ---------------------------------------------------------------------------


class TestCamelCaseRegex:
    """camelCase: lowercase first letter, min 2 chars, mixed allowed."""

    @pytest.mark.parametrize(
        "raw_id,expected_component",
        [
            ("EVS-PRD-userAuth", "userAuth"),
            ("EVS-PRD-userAuth123", "userAuth123"),
            ("EVS-PRD-ab", "ab"),
        ],
    )
    def test_camel_case_accepts(self, raw_id, expected_component):
        # Verifies: REQ-d00251-B
        r = _build_resolver(style="camelCase")
        pid = r.parse(raw_id)
        assert pid is not None, f"camelCase should accept {raw_id}"
        assert pid.component == expected_component

    @pytest.mark.parametrize(
        "raw_id",
        [
            "EVS-PRD-UserAuth",  # PascalCase, not camelCase
            "EVS-PRD-a",  # single char fails the +1 quantifier
            "EVS-PRD-user_auth",  # snake form
            "EVS-PRD-user-auth",  # kebab form
        ],
    )
    def test_camel_case_rejects(self, raw_id):
        # Verifies: REQ-d00251-B
        r = _build_resolver(style="camelCase")
        assert r.parse(raw_id) is None, f"camelCase should reject {raw_id}"


class TestPascalCaseRegex:
    """PascalCase: uppercase first letter, min 2 chars, mixed allowed."""

    @pytest.mark.parametrize(
        "raw_id,expected_component",
        [
            ("EVS-PRD-UserAuth", "UserAuth"),
            ("EVS-PRD-UserAuth123", "UserAuth123"),
            ("EVS-PRD-Ab", "Ab"),
        ],
    )
    def test_pascal_case_accepts(self, raw_id, expected_component):
        # Verifies: REQ-d00251-B
        r = _build_resolver(style="PascalCase")
        pid = r.parse(raw_id)
        assert pid is not None, f"PascalCase should accept {raw_id}"
        assert pid.component == expected_component

    @pytest.mark.parametrize(
        "raw_id",
        [
            "EVS-PRD-userAuth",  # camelCase
            "EVS-PRD-A",  # single char
            "EVS-PRD-user_auth",  # snake
            "EVS-PRD-user-auth",  # kebab
        ],
    )
    def test_pascal_case_rejects(self, raw_id):
        # Verifies: REQ-d00251-B
        r = _build_resolver(style="PascalCase")
        assert r.parse(raw_id) is None, f"PascalCase should reject {raw_id}"


class TestSnakeCaseRegex:
    """snake_case: lowercase + digits, optional ``_`` segments."""

    @pytest.mark.parametrize(
        "raw_id,expected_component",
        [
            ("EVS-PRD-user_auth", "user_auth"),
            ("EVS-PRD-destinations", "destinations"),
            ("EVS-PRD-event_store_append", "event_store_append"),
            ("EVS-PRD-a", "a"),  # snake allows single-segment, any length >=1
        ],
    )
    def test_snake_case_accepts(self, raw_id, expected_component):
        # Verifies: REQ-d00251-B
        r = _build_resolver(style="snake_case", separator="-", label_style="uppercase")
        pid = r.parse(raw_id)
        assert pid is not None, f"snake_case should accept {raw_id}"
        assert pid.component == expected_component

    @pytest.mark.parametrize(
        "raw_id",
        [
            "EVS-PRD-user-auth",  # kebab form
            "EVS-PRD-User_auth",  # uppercase letter
            "EVS-PRD-userAuth",  # camelCase
        ],
    )
    def test_snake_case_rejects(self, raw_id):
        # Verifies: REQ-d00251-B
        r = _build_resolver(style="snake_case", separator="-", label_style="uppercase")
        assert r.parse(raw_id) is None, f"snake_case should reject {raw_id}"


class TestKebabCaseRegex:
    """kebab-case: lowercase + digits, optional ``-`` segments."""

    @pytest.mark.parametrize(
        "raw_id,expected_component",
        [
            ("EVS-PRD-user-auth", "user-auth"),
            ("EVS-PRD-destinations", "destinations"),
            ("EVS-PRD-hash-chain-integrity", "hash-chain-integrity"),
            ("EVS-PRD-action-dispatch", "action-dispatch"),
        ],
    )
    def test_kebab_case_accepts(self, raw_id, expected_component):
        # Verifies: REQ-d00251-B
        r = _build_resolver(style="kebab-case", separator="-", label_style="uppercase")
        pid = r.parse(raw_id)
        assert pid is not None, f"kebab-case should accept {raw_id}"
        assert pid.component == expected_component

    @pytest.mark.parametrize(
        "raw_id",
        [
            "EVS-PRD-user_auth",  # snake form
            "EVS-PRD-User-auth",  # uppercase letter
            "EVS-PRD-userAuth",  # camelCase
        ],
    )
    def test_kebab_case_rejects(self, raw_id):
        # Verifies: REQ-d00251-B
        r = _build_resolver(style="kebab-case", separator="-", label_style="uppercase")
        assert r.parse(raw_id) is None, f"kebab-case should reject {raw_id}"

    def test_pattern_field_ignored_for_case_styles(self):
        # Verifies: REQ-d00251-B
        # Even if the user sets a garbage pattern, the case-style regex wins.
        r = _build_resolver(
            style="kebab-case",
            pattern="GARBAGE_PATTERN",
            separator="-",
            label_style="uppercase",
        )
        pid = r.parse("EVS-PRD-hash-chain-integrity")
        assert pid is not None
        assert pid.component == "hash-chain-integrity"
        # The garbage literal should NOT be accepted.
        assert r.parse("EVS-PRD-GARBAGE_PATTERN") is None


# ---------------------------------------------------------------------------
# REQ-d00251-C: regex style requires a non-empty pattern
# ---------------------------------------------------------------------------


class TestRegexStyleRequiresPattern:
    def test_regex_without_pattern_rejected(self):
        # Verifies: REQ-d00251-C
        payload = _elspais_config_payload(style="regex")
        with pytest.raises(ValidationError):
            ElspaisConfig.model_validate(payload)

    def test_regex_with_empty_pattern_rejected(self):
        # Verifies: REQ-d00251-C
        payload = _elspais_config_payload(style="regex", pattern="")
        with pytest.raises(ValidationError):
            ElspaisConfig.model_validate(payload)

    def test_regex_with_pattern_loads(self):
        # Verifies: REQ-d00251-C
        payload = _elspais_config_payload(style="regex", pattern="[A-Z][a-z]+")
        cfg = ElspaisConfig.model_validate(payload)
        assert cfg.id_patterns.component.style == "regex"
        assert cfg.id_patterns.component.pattern == "[A-Z][a-z]+"

    def test_regex_with_pattern_parses(self):
        # Verifies: REQ-d00251-C
        r = _build_resolver(style="regex", pattern="[A-Z][a-z]+")
        pid = r.parse("EVS-PRD-Foo")
        assert pid is not None
        assert pid.component == "Foo"


# ---------------------------------------------------------------------------
# REQ-d00251-D: deprecation/error text
# ---------------------------------------------------------------------------


class TestDeprecationErrorText:
    def _capture_error(self, style: str, pattern: str | None = None) -> str:
        payload = _elspais_config_payload(style=style, pattern=pattern)
        try:
            ElspaisConfig.model_validate(payload)
        except ValidationError as exc:
            return str(exc)
        raise AssertionError(f"Expected ValidationError for style={style!r}")

    def test_named_error_mentions_regex_and_legacy_pattern(self):
        # Verifies: REQ-d00251-D
        msg = self._capture_error("named", pattern="[A-Za-z][A-Za-z0-9]+")
        assert "regex" in msg
        assert "[A-Za-z][A-Za-z0-9]+" in msg

    def test_named_error_lists_case_style_names(self):
        # Verifies: REQ-d00251-D
        msg = self._capture_error("named", pattern="[A-Za-z][A-Za-z0-9]+")
        case_styles = ["camelCase", "PascalCase", "snake_case", "kebab-case"]
        present = [s for s in case_styles if s in msg]
        assert (
            len(present) >= 2
        ), f"Expected >=2 case-style names in error, got {present!r}. msg={msg}"

    def test_alphanumeric_error_mentions_legacy_pattern(self):
        # Verifies: REQ-d00251-D
        msg = self._capture_error("alphanumeric", pattern="[A-Z0-9]+")
        assert "[A-Z0-9]+" in msg


# ---------------------------------------------------------------------------
# REQ-d00251-E: configurable assertion separator
# ---------------------------------------------------------------------------


class TestConfigurableAssertionSeparator:
    def test_assertion_config_has_separator_field(self):
        # Verifies: REQ-d00251-E
        from elspais.config.schema import AssertionConfig

        ac = AssertionConfig()
        # default should be "-"
        assert getattr(ac, "separator", None) == "-"

    def test_non_component_separator_single_assertion(self):
        # Verifies: REQ-d00251-E
        r = _build_resolver(style="kebab-case", separator="|", label_style="uppercase")
        pid = r.parse("EVS-PRD-action-dispatch|A")
        assert pid is not None
        assert pid.component == "action-dispatch"
        assert pid.assertions == ["A"]

    def test_non_component_separator_multi_assertion(self):
        # Verifies: REQ-d00251-E
        r = _build_resolver(style="kebab-case", separator="|", label_style="uppercase")
        pid = r.parse("EVS-PRD-action-dispatch|A+B+C")
        assert pid is not None
        assert pid.component == "action-dispatch"
        assert pid.assertions == ["A", "B", "C"]

    def test_non_component_separator_unlocks_numeric_labels_under_kebab(self):
        # Verifies: REQ-d00251-E
        r = _build_resolver(style="kebab-case", separator="~", label_style="numeric")
        pid = r.parse("EVS-PRD-action-dispatch~1+2+3")
        assert pid is not None
        assert pid.component == "action-dispatch"
        assert pid.assertions == ["1", "2", "3"]

    def test_default_dash_separator_under_a_non_overlapping_style(self):
        # Verifies: REQ-d00251-E
        # "-" is the default separator and stays usable under any component
        # style that cannot itself contain "-".
        r = _build_resolver(style="camelCase", separator="-", label_style="uppercase")
        pid = r.parse("EVS-PRD-actionDispatch-A")
        assert pid is not None
        assert pid.component == "actionDispatch"
        assert pid.assertions == ["A"]


# ---------------------------------------------------------------------------
# REQ-d00251-F: ambiguity rejection
# ---------------------------------------------------------------------------


# (component style, separator, label_style, component pattern). Each entry
# names a separator drawn from the alphabet of the part it is meant to
# bound: the component swallows it along with the label behind it, or two
# labels run together.
AMBIGUOUS_COMBOS = [
    ("snake_case", "_", "numeric", None),
    ("snake_case", "_", "numeric_1based", None),
    ("snake_case", "_", "alphanumeric", None),
    ("snake_case", "_", "uppercase", None),
    ("kebab-case", "-", "numeric", None),
    ("kebab-case", "-", "numeric_1based", None),
    ("kebab-case", "-", "alphanumeric", None),
    ("kebab-case", "-", "uppercase", None),
    # The overlap is not confined to the punctuation a case style uses
    # internally: digits and letters are component characters too.
    ("numeric", "5", "uppercase", None),
    ("camelCase", "x", "uppercase", None),
    # A character legal only after the first position is a component
    # character all the same.
    ("PascalCase", "x", "uppercase", None),
    ("PascalCase", "5", "uppercase", None),
    # A custom component pattern is read the same way, by asking the
    # pattern itself which characters it admits.
    ("regex", ".", "uppercase", "[A-Z.]+"),
    # ... including one whose shortest match is longer than any probe.
    ("regex", "5", "uppercase", "[0-9]{5,}"),
    # The label's own alphabet is the other half of the rule.
    ("numeric", "A", "uppercase", None),
    ("numeric", "3", "numeric", None),
]

UNAMBIGUOUS_COMBOS = [
    ("numeric", "-", "uppercase", None),
    ("snake_case", "-", "uppercase", None),
    ("camelCase", "-", "uppercase", None),
    ("kebab-case", "/", "uppercase", None),
    ("snake_case", ".", "numeric", None),
    ("kebab-case", "~", "numeric", None),
    ("regex", "/", "uppercase", "[A-Z.]+"),
]

# (label_style, multi_separator) pairs where the multi-separator is itself a
# legal label character, so a two-label reference has no findable boundary.
COLLIDING_MULTI_SEPARATORS = [
    ("uppercase", "A"),
    ("numeric", "7"),
    ("numeric_1based", "3"),
    # "10" is a legal numeric_1based label, so "0" is a label character.
    ("numeric_1based", "0"),
    ("alphanumeric", "B"),
]

_SUGGESTION_RE = re.compile(r'e\.g\. "(.)"')


def _suggested_replacement(msg: str) -> str:
    """The replacement character the rejection message offers."""
    match = _SUGGESTION_RE.search(msg)
    assert match is not None, f"Rejection must suggest a replacement character. msg={msg}"
    return match.group(1)


class TestAmbiguityRejection:
    @pytest.mark.parametrize("style,separator,label_style,pattern", AMBIGUOUS_COMBOS)
    def test_ambiguous_combos_rejected(self, style, separator, label_style, pattern):
        # Verifies: REQ-d00251-F
        payload = _elspais_config_payload(
            style=style, pattern=pattern, separator=separator, label_style=label_style
        )
        with pytest.raises(ValidationError) as excinfo:
            ElspaisConfig.model_validate(payload)
        msg = str(excinfo.value)
        assert "separator" in msg, f"Rejection must name the offending field. msg={msg}"
        assert (
            f'"{separator}"' in msg
        ), f"Rejection must name the character {separator!r}. msg={msg}"
        assert (
            style in msg and label_style in msg
        ), f"Rejection must name the styles that make {separator!r} legal. msg={msg}"

        # The suggested replacement has to actually clear the conflict.
        suggestion = _suggested_replacement(msg)
        assert suggestion != separator
        ElspaisConfig.model_validate(
            _elspais_config_payload(
                style=style, pattern=pattern, separator=suggestion, label_style=label_style
            )
        )

    @pytest.mark.parametrize("label_style,multi_separator", COLLIDING_MULTI_SEPARATORS)
    def test_multi_separator_inside_label_alphabet_rejected(self, label_style, multi_separator):
        # Verifies: REQ-d00251-J
        payload = _elspais_config_payload(
            style="numeric", label_style=label_style, multi_separator=multi_separator
        )
        with pytest.raises(ValidationError) as excinfo:
            ElspaisConfig.model_validate(payload)
        msg = str(excinfo.value)
        assert "multi_separator" in msg, f"Rejection must name the offending field. msg={msg}"
        assert (
            f'"{multi_separator}"' in msg
        ), f"Rejection must name the character {multi_separator!r}. msg={msg}"
        assert label_style in msg, f"Rejection must name the label style. msg={msg}"

        suggestion = _suggested_replacement(msg)
        assert suggestion != multi_separator
        ElspaisConfig.model_validate(
            _elspais_config_payload(
                style="numeric", label_style=label_style, multi_separator=suggestion
            )
        )

    @pytest.mark.parametrize("style,separator,label_style,pattern", UNAMBIGUOUS_COMBOS)
    def test_unambiguous_combos_load(self, style, separator, label_style, pattern):
        # Verifies: REQ-d00251-F
        payload = _elspais_config_payload(
            style=style, pattern=pattern, separator=separator, label_style=label_style
        )
        cfg = ElspaisConfig.model_validate(payload)
        assert cfg.id_patterns.component.style == style
        assert cfg.id_patterns.assertions.label_style == label_style


# ---------------------------------------------------------------------------
# REQ-d00251-A+B: the component sub-pattern each style resolves to
# ---------------------------------------------------------------------------


class TestComponentRegexHelper:
    @pytest.mark.parametrize(
        "style,probe,expected",
        [
            ("camelCase", "userAuth", True),
            ("camelCase", "UserAuth", False),
            ("PascalCase", "UserAuth", True),
            ("PascalCase", "userAuth", False),
            ("snake_case", "user_auth", True),
            ("snake_case", "user-auth", False),
            ("kebab-case", "user-auth", True),
            ("kebab-case", "user_auth", False),
        ],
    )
    def test_helper_returns_matching_regex_per_style(self, style, probe, expected):
        # Verifies: REQ-d00251-B
        import re as _re

        from elspais.utilities.patterns import ComponentFormat, component_regex

        cf = ComponentFormat(style=style, digits=0, leading_zeros=False, pattern=None)
        regex_str = component_regex(cf)
        m = _re.fullmatch(regex_str, probe)
        assert (m is not None) == expected, (
            f"style={style!r} probe={probe!r}: expected match={expected}, "
            f"got regex={regex_str!r}"
        )

    def test_helper_returns_numeric_regex(self):
        # Verifies: REQ-d00251-A
        import re as _re

        from elspais.utilities.patterns import ComponentFormat, component_regex

        cf = ComponentFormat(style="numeric", digits=5, leading_zeros=True, pattern=None)
        regex_str = component_regex(cf)
        assert _re.fullmatch(regex_str, "00042") is not None
        assert _re.fullmatch(regex_str, "abc") is None

    def test_helper_returns_user_pattern_for_regex_style(self):
        # Verifies: REQ-d00251-A
        import re as _re

        from elspais.utilities.patterns import ComponentFormat, component_regex

        cf = ComponentFormat(style="regex", digits=0, leading_zeros=False, pattern="[A-Z][a-z]+")
        regex_str = component_regex(cf)
        assert _re.fullmatch(regex_str, "Foo") is not None
        assert _re.fullmatch(regex_str, "foo") is None
