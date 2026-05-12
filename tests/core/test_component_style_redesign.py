"""Tests for the Component Style Redesign (REQ-d00251).

These tests encode the behavior specified in
``docs/superpowers/specs/2026-05-11-component-style-redesign-design.md``,
which is now implemented in this codebase (config schema, resolver,
grammar tokens).

Each test function carries a ``# Verifies: REQ-d00251-X`` comment naming
the assertion it exercises.
"""

from __future__ import annotations

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
    label_style: str = "uppercase",
) -> dict:
    """Build a minimal payload for ``ElspaisConfig.model_validate``."""
    component: dict = {"style": style}
    if pattern is not None:
        component["pattern"] = pattern
    assertions: dict = {"label_style": label_style}
    if separator is not None:
        assertions["separator"] = separator
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
            ("kebab-case", {}),
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

    def test_colon_separator_single_assertion(self):
        # Verifies: REQ-d00251-E
        r = _build_resolver(style="kebab-case", separator=":", label_style="uppercase")
        pid = r.parse("EVS-PRD-action-dispatch:A")
        assert pid is not None
        assert pid.component == "action-dispatch"
        assert pid.assertions == ["A"]

    def test_colon_separator_multi_assertion(self):
        # Verifies: REQ-d00251-E
        r = _build_resolver(style="kebab-case", separator=":", label_style="uppercase")
        pid = r.parse("EVS-PRD-action-dispatch:A+B+C")
        assert pid is not None
        assert pid.component == "action-dispatch"
        assert pid.assertions == ["A", "B", "C"]

    def test_colon_separator_unlocks_numeric_labels_under_kebab(self):
        # Verifies: REQ-d00251-E
        r = _build_resolver(style="kebab-case", separator=":", label_style="numeric")
        pid = r.parse("EVS-PRD-action-dispatch:1+2+3")
        assert pid is not None
        assert pid.component == "action-dispatch"
        assert pid.assertions == ["1", "2", "3"]

    def test_default_dash_separator_still_works(self):
        # Verifies: REQ-d00251-E
        # Backward compatibility: kebab + "-" separator + uppercase labels
        # remains the supported case.
        r = _build_resolver(style="kebab-case", separator="-", label_style="uppercase")
        pid = r.parse("EVS-PRD-action-dispatch-A")
        assert pid is not None
        assert pid.component == "action-dispatch"
        assert pid.assertions == ["A"]


# ---------------------------------------------------------------------------
# REQ-d00251-F: ambiguity rejection
# ---------------------------------------------------------------------------


AMBIGUOUS_COMBOS = [
    ("snake_case", "_", "numeric"),
    ("snake_case", "_", "numeric_1based"),
    ("snake_case", "_", "alphanumeric"),
    ("kebab-case", "-", "numeric"),
    ("kebab-case", "-", "numeric_1based"),
    ("kebab-case", "-", "alphanumeric"),
]

UNAMBIGUOUS_COMBOS = [
    ("snake_case", "_", "uppercase"),
    ("kebab-case", "-", "uppercase"),
    ("snake_case", ":", "numeric"),
    ("kebab-case", ":", "numeric"),
]


class TestAmbiguityRejection:
    @pytest.mark.parametrize("style,separator,label_style", AMBIGUOUS_COMBOS)
    def test_ambiguous_combos_rejected(self, style, separator, label_style):
        # Verifies: REQ-d00251-F
        payload = _elspais_config_payload(style=style, separator=separator, label_style=label_style)
        with pytest.raises(ValidationError) as excinfo:
            ElspaisConfig.model_validate(payload)
        # Per REQ-d00251-F: the error must suggest changing `separator` to a
        # non-overlapping character — i.e. mention `separator` and either
        # the style or label_style values being conflicted.
        msg = str(excinfo.value)
        assert "separator" in msg, f"Ambiguity error must mention `separator`. msg={msg}"

    @pytest.mark.parametrize("style,separator,label_style", UNAMBIGUOUS_COMBOS)
    def test_unambiguous_combos_load(self, style, separator, label_style):
        # Verifies: REQ-d00251-F
        payload = _elspais_config_payload(style=style, separator=separator, label_style=label_style)
        cfg = ElspaisConfig.model_validate(payload)
        assert cfg.id_patterns.component.style == style
        assert cfg.id_patterns.assertions.label_style == label_style


# ---------------------------------------------------------------------------
# REQ-d00251-G: helper centralization
# ---------------------------------------------------------------------------


class TestComponentRegexHelper:
    def test_helper_is_importable_from_utilities_patterns(self):
        # Verifies: REQ-d00251-G
        from elspais.utilities import patterns as patterns_mod

        assert hasattr(
            patterns_mod, "component_regex"
        ), "component_regex must live in elspais.utilities.patterns"

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
        # Verifies: REQ-d00251-G
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
        # Verifies: REQ-d00251-G
        import re as _re

        from elspais.utilities.patterns import ComponentFormat, component_regex

        cf = ComponentFormat(style="numeric", digits=5, leading_zeros=True, pattern=None)
        regex_str = component_regex(cf)
        assert _re.fullmatch(regex_str, "00042") is not None
        assert _re.fullmatch(regex_str, "abc") is None

    def test_helper_returns_user_pattern_for_regex_style(self):
        # Verifies: REQ-d00251-G
        import re as _re

        from elspais.utilities.patterns import ComponentFormat, component_regex

        cf = ComponentFormat(style="regex", digits=0, leading_zeros=False, pattern="[A-Z][a-z]+")
        regex_str = component_regex(cf)
        assert _re.fullmatch(regex_str, "Foo") is not None
        assert _re.fullmatch(regex_str, "foo") is None

    def test_helper_is_sole_authority_no_inline_dispatch_in_lark(self):
        # Verifies: REQ-d00251-G
        # The lark grammar must call component_regex(), not duplicate the
        # style dispatch. Detect duplication via grep on the source file.
        import inspect

        from elspais.graph.parsers import lark as lark_mod

        src = inspect.getsource(lark_mod)
        # The forbidden patterns are the per-style if/elif chain literals.
        # If the helper is used, these literal strings shouldn't appear.
        forbidden_literals = [
            'comp.style == "named"',
            'comp.style == "alphanumeric"',
        ]
        offenders = [lit for lit in forbidden_literals if lit in src]
        assert not offenders, f"lark parser still contains inline style dispatch: {offenders}"
        assert (
            "component_regex" in src
        ), "lark parser should call component_regex() from utilities.patterns"
