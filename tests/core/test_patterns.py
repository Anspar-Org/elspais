"""Tests for patterns.py — ID pattern system.

Validates REQ-p00002-A: configurable patterns and rules.
"""

import pytest

from elspais.utilities.patterns import (
    AssertionFormat,
    ComponentFormat,
    IdPatternConfig,
    IdResolver,
    ParsedId,
    TypeDef,
)

# --- Task 1: Data model dataclasses ---


class TestTypeDef:
    """Validates REQ-p00002-A: TypeDef dataclass."""

    def test_REQ_p00002_A_basic_creation(self):
        td = TypeDef(code="prd", level=1, aliases={"letter": "p"})
        assert td.code == "prd"
        assert td.level == 1
        assert td.aliases["letter"] == "p"

    def test_REQ_p00002_A_empty_aliases(self):
        td = TypeDef(code="req", level=1, aliases={})
        assert td.aliases == {}


class TestComponentFormat:
    """Validates REQ-p00002-A: ComponentFormat dataclass."""

    def test_REQ_p00002_A_numeric_defaults(self):
        cf = ComponentFormat(style="numeric", digits=5, leading_zeros=True, pattern=None)
        assert cf.style == "numeric"
        assert cf.digits == 5

    def test_REQ_p00002_A_named_with_pattern(self):
        cf = ComponentFormat(
            style="named", digits=0, leading_zeros=False, pattern="[A-Z][a-zA-Z0-9]+"
        )
        assert cf.pattern == "[A-Z][a-zA-Z0-9]+"

    def test_REQ_p00002_A_unlimited_digits(self):
        cf = ComponentFormat(style="numeric", digits=0, leading_zeros=False, pattern=None)
        assert cf.digits == 0


class TestAssertionFormat:
    """Validates REQ-p00002-A: AssertionFormat dataclass."""

    def test_REQ_p00002_A_defaults(self):
        af = AssertionFormat(
            label_style="uppercase",
            max_count=26,
            zero_pad=False,
            multi_separator="+",
        )
        assert af.label_style == "uppercase"
        assert af.max_count == 26
        assert af.multi_separator == "+"


class TestIdPatternConfig:
    """Validates REQ-p00002-A: IdPatternConfig.from_dict()."""

    def test_REQ_p00002_A_from_dict_hht(self):
        config = IdPatternConfig.from_dict(
            {
                "project": {"namespace": "REQ"},
                "id-patterns": {
                    "canonical": "{namespace}-{type}{component}",
                    "aliases": {"short": "{type.letter}{component}"},
                    "types": {
                        "prd": {"level": 1, "aliases": {"letter": "p"}},
                        "ops": {"level": 2, "aliases": {"letter": "o"}},
                        "dev": {"level": 3, "aliases": {"letter": "d"}},
                    },
                    "component": {"style": "numeric", "digits": 5, "leading_zeros": True},
                    "assertions": {
                        "label_style": "uppercase",
                        "max_count": 26,
                    },
                },
            }
        )
        assert config.namespace == "REQ"
        assert config.canonical_template == "{namespace}-{type}{component}"
        assert "short" in config.aliases
        assert len(config.types) == 3
        assert config.types["prd"].level == 1
        assert config.types["prd"].aliases["letter"] == "p"
        assert config.component.style == "numeric"
        assert config.component.digits == 5
        assert config.assertions.label_style == "uppercase"

    def test_REQ_p00002_A_from_dict_fda(self):
        config = IdPatternConfig.from_dict(
            {
                "project": {"namespace": "FDA"},
                "id-patterns": {
                    "canonical": "{namespace}-{type}-{component}",
                    "types": {
                        "PRD": {"level": 1},
                        "OPS": {"level": 2},
                        "DEV": {"level": 3},
                    },
                    "component": {"style": "numeric", "digits": 5, "leading_zeros": True},
                },
            }
        )
        assert config.namespace == "FDA"
        assert config.canonical_template == "{namespace}-{type}-{component}"
        assert config.types["PRD"].level == 1
        assert config.types["PRD"].aliases == {}

    def test_REQ_p00002_A_from_dict_jira(self):
        config = IdPatternConfig.from_dict(
            {
                "project": {"namespace": "PROJ"},
                "id-patterns": {
                    "canonical": "{namespace}-{component}",
                    "types": {"req": {"level": 1}},
                    "component": {"style": "numeric", "digits": 0, "leading_zeros": False},
                },
            }
        )
        assert config.namespace == "PROJ"
        assert config.component.digits == 0
        assert config.component.leading_zeros is False

    def test_REQ_p00002_A_from_dict_named(self):
        config = IdPatternConfig.from_dict(
            {
                "project": {"namespace": "REQ"},
                "id-patterns": {
                    "canonical": "{namespace}-{component}",
                    "types": {"req": {"level": 1}},
                    "component": {"style": "named", "pattern": "[A-Z][a-zA-Z0-9]+"},
                },
            }
        )
        assert config.component.style == "named"
        assert config.component.pattern == "[A-Z][a-zA-Z0-9]+"

    def test_REQ_p00002_A_from_dict_defaults(self):
        config = IdPatternConfig.from_dict({})
        assert config.namespace == "REQ"
        assert config.canonical_template == "{namespace}-{type}{component}"
        assert config.component.style == "numeric"

    def test_REQ_p00002_A_from_dict_output_forms(self):
        config = IdPatternConfig.from_dict(
            {
                "project": {"namespace": "REQ"},
                "id-patterns": {
                    "canonical": "{namespace}-{type}{component}",
                    "types": {"prd": {"level": 1}},
                    "component": {"style": "numeric", "digits": 5},
                },
                "output": {"id-patterns": {"writer-requirement-edge": "short"}},
            }
        )
        assert config.output_forms["writer-requirement-edge"] == "short"


# --- Task 2: ParsedId dataclass ---


class TestParsedId:
    """Validates REQ-p00002-A: ParsedId dataclass."""

    def test_REQ_p00002_A_basic_creation(self):
        pid = ParsedId(
            namespace="REQ",
            type_code="prd",
            component="00044",
            assertions=[],
            fqn="REQ-prd00044",
        )
        assert pid.namespace == "REQ"
        assert pid.type_code == "prd"
        assert pid.component == "00044"
        assert pid.fqn == "REQ-prd00044"

    def test_REQ_p00002_A_kind_requirement(self):
        pid = ParsedId(
            namespace="REQ",
            type_code="prd",
            component="00044",
            assertions=[],
            fqn="REQ-prd00044",
        )
        assert pid.kind == "requirement"

    def test_REQ_p00002_A_kind_assertion(self):
        pid = ParsedId(
            namespace="REQ",
            type_code="prd",
            component="00044",
            assertions=["A"],
            fqn="REQ-prd00044",
        )
        assert pid.kind == "assertion"

    def test_REQ_p00002_A_composite_id_not_parsed(self):
        """Composite IDs (with ::) must NOT be parsed by IdResolver."""
        r = _make_hht_resolver()
        assert r.parse("REQ-prd00043::REQ-prd80001") is None


# --- Helper factories ---


@pytest.fixture
def resolver():
    """Default IdResolver matching the HHT-style config."""
    config = IdPatternConfig.from_dict(
        {
            "project": {"namespace": "REQ"},
            "id-patterns": {
                "canonical": "{namespace}-{type.letter}{component}",
                "types": {
                    "prd": {"level": 1, "aliases": {"letter": "p"}},
                    "ops": {"level": 2, "aliases": {"letter": "o"}},
                    "dev": {"level": 3, "aliases": {"letter": "d"}},
                },
                "component": {"style": "numeric", "digits": 5, "leading_zeros": True},
                "assertions": {"label_style": "uppercase"},
            },
        }
    )
    return IdResolver(config)


def _make_hht_resolver():
    config = IdPatternConfig.from_dict(
        {
            "project": {"namespace": "REQ"},
            "id-patterns": {
                "canonical": "{namespace}-{type}{component}",
                "aliases": {"short": "{type.letter}{component}"},
                "types": {
                    "prd": {"level": 1, "aliases": {"letter": "p"}},
                    "ops": {"level": 2, "aliases": {"letter": "o"}},
                    "dev": {"level": 3, "aliases": {"letter": "d"}},
                },
                "component": {"style": "numeric", "digits": 5, "leading_zeros": True},
                "assertions": {
                    "label_style": "uppercase",
                    "max_count": 26,
                },
            },
        }
    )
    return IdResolver(config)


def _make_fda_resolver():
    config = IdPatternConfig.from_dict(
        {
            "project": {"namespace": "FDA"},
            "id-patterns": {
                "canonical": "{namespace}-{type}-{component}",
                "types": {
                    "PRD": {"level": 1},
                    "OPS": {"level": 2},
                    "DEV": {"level": 3},
                },
                "component": {"style": "numeric", "digits": 5, "leading_zeros": True},
            },
        }
    )
    return IdResolver(config)


def _make_jira_resolver():
    config = IdPatternConfig.from_dict(
        {
            "project": {"namespace": "PROJ"},
            "id-patterns": {
                "canonical": "{namespace}-{component}",
                "types": {"req": {"level": 1}},
                "component": {"style": "numeric", "digits": 0, "leading_zeros": False},
            },
        }
    )
    return IdResolver(config)


def _make_named_resolver():
    config = IdPatternConfig.from_dict(
        {
            "project": {"namespace": "REQ"},
            "id-patterns": {
                "canonical": "{namespace}-{component}",
                "types": {"req": {"level": 1}},
                "component": {"style": "named", "pattern": "[A-Z][a-zA-Z0-9]+"},
            },
        }
    )
    return IdResolver(config)


# --- Task 3: IdResolver parsing ---


class TestIdResolverParse:
    """Validates REQ-p00002-A: IdResolver.parse()."""

    def test_REQ_p00002_A_parse_canonical_hht(self):
        r = _make_hht_resolver()
        pid = r.parse("REQ-prd00044")
        assert pid is not None
        assert pid.namespace == "REQ"
        assert pid.type_code == "prd"
        assert pid.component == "00044"
        assert pid.assertions == []
        assert pid.fqn == "REQ-prd00044"

    def test_REQ_p00002_A_parse_short_form_hht(self):
        r = _make_hht_resolver()
        pid = r.parse("p00044")
        assert pid is not None
        assert pid.type_code == "prd"
        assert pid.component == "00044"
        assert pid.fqn == "REQ-prd00044"

    def test_REQ_p00002_A_parse_with_assertion(self):
        r = _make_hht_resolver()
        pid = r.parse("REQ-prd00044-A")
        assert pid is not None
        assert pid.assertions == ["A"]
        assert pid.fqn == "REQ-prd00044"

    def test_REQ_p00002_A_parse_multi_assertion(self):
        r = _make_hht_resolver()
        pid = r.parse("REQ-prd00044-A+B+C")
        assert pid is not None
        assert pid.assertions == ["A", "B", "C"]
        assert pid.fqn == "REQ-prd00044"

    def test_REQ_p00002_A_parse_short_with_assertion(self):
        r = _make_hht_resolver()
        pid = r.parse("p00044-A")
        assert pid is not None
        assert pid.type_code == "prd"
        assert pid.assertions == ["A"]
        assert pid.fqn == "REQ-prd00044"

    def test_REQ_p00002_A_parse_invalid_returns_none(self):
        r = _make_hht_resolver()
        assert r.parse("INVALID") is None
        assert r.parse("REQ-x00001") is None

    def test_REQ_p00002_A_parse_fda_style(self):
        r = _make_fda_resolver()
        pid = r.parse("FDA-PRD-00001")
        assert pid is not None
        assert pid.namespace == "FDA"
        assert pid.type_code == "PRD"
        assert pid.component == "00001"

    def test_REQ_p00002_A_parse_jira_style(self):
        r = _make_jira_resolver()
        pid = r.parse("PROJ-123")
        assert pid is not None
        assert pid.component == "123"

    def test_REQ_p00002_A_parse_jira_variable_length(self):
        r = _make_jira_resolver()
        assert r.parse("PROJ-1") is not None
        assert r.parse("PROJ-12345") is not None

    def test_REQ_p00002_A_parse_named_style(self):
        r = _make_named_resolver()
        pid = r.parse("REQ-UserAuth")
        assert pid is not None
        assert pid.component == "UserAuth"

    def test_REQ_p00002_A_component_normalization_short_input(self):
        """Unpadded component should be zero-padded during parse."""
        r = _make_hht_resolver()
        pid = r.parse("p44")
        assert pid is not None
        assert pid.component == "00044"

    def test_REQ_p00002_A_composite_id_not_parsed(self):
        r = _make_hht_resolver()
        assert r.parse("REQ-prd00043::REQ-prd80001") is None


class TestIdResolverToCanonical:
    """Validates REQ-p00002-A: to_canonical()."""

    def test_REQ_p00002_A_canonical_passthrough(self):
        r = _make_hht_resolver()
        assert r.to_canonical("REQ-prd00044") == "REQ-prd00044"

    def test_REQ_p00002_A_short_to_canonical(self):
        r = _make_hht_resolver()
        assert r.to_canonical("p00044") == "REQ-prd00044"

    def test_REQ_p00002_A_with_assertion(self):
        r = _make_hht_resolver()
        assert r.to_canonical("p00044-A") == "REQ-prd00044-A"

    def test_REQ_p00002_A_multi_assertion(self):
        r = _make_hht_resolver()
        assert r.to_canonical("p00044-A+B") == "REQ-prd00044-A+B"

    def test_REQ_p00002_A_invalid_returns_none(self):
        r = _make_hht_resolver()
        assert r.to_canonical("INVALID") is None


# --- Task 4: IdResolver rendering, expand, validation ---


class TestIdResolverRender:
    """Validates REQ-p00002-A: render methods."""

    def test_REQ_p00002_A_render_canonical(self):
        r = _make_hht_resolver()
        pid = r.parse("REQ-prd00044")
        assert r.render(pid, "canonical") == "REQ-prd00044"

    def test_REQ_p00002_A_render_short(self):
        r = _make_hht_resolver()
        pid = r.parse("REQ-prd00044")
        assert r.render(pid, "short") == "p00044"

    def test_REQ_p00002_A_render_canonical_shorthand(self):
        r = _make_hht_resolver()
        pid = r.parse("REQ-prd00044")
        assert r.render_canonical(pid) == "REQ-prd00044"

    def test_REQ_p00002_A_render_with_assertion(self):
        r = _make_hht_resolver()
        pid = r.parse("REQ-prd00044-A")
        assert r.render(pid, "canonical") == "REQ-prd00044-A"
        assert r.render(pid, "short") == "p00044-A"

    def test_REQ_p00002_A_render_multi_assertion(self):
        r = _make_hht_resolver()
        pid = r.parse("REQ-prd00044-A+B+C")
        assert r.render(pid, "canonical") == "REQ-prd00044-A+B+C"

    def test_REQ_p00002_A_render_unknown_form_raises(self):
        r = _make_hht_resolver()
        pid = r.parse("REQ-prd00044")
        with pytest.raises(KeyError):
            r.render(pid, "nonexistent")

    def test_REQ_p00002_A_render_fda(self):
        r = _make_fda_resolver()
        pid = r.parse("FDA-PRD-00001")
        assert r.render_canonical(pid) == "FDA-PRD-00001"


class TestIdResolverExpand:
    """Validates REQ-p00002-A: expand method."""

    def test_REQ_p00002_A_expand_single(self):
        r = _make_hht_resolver()
        pid = r.parse("REQ-prd00044-A")
        expanded = r.expand(pid)
        assert len(expanded) == 1
        assert expanded[0].assertions == ["A"]

    def test_REQ_p00002_A_expand_multi(self):
        r = _make_hht_resolver()
        pid = r.parse("REQ-prd00044-A+B+C")
        expanded = r.expand(pid)
        assert len(expanded) == 3
        assert expanded[0].assertions == ["A"]
        assert expanded[1].assertions == ["B"]
        assert expanded[2].assertions == ["C"]
        assert all(e.fqn == "REQ-prd00044" for e in expanded)

    def test_REQ_p00002_A_expand_no_assertion(self):
        r = _make_hht_resolver()
        pid = r.parse("REQ-prd00044")
        expanded = r.expand(pid)
        assert len(expanded) == 1
        assert expanded[0] is pid


class TestIdResolverValidation:
    """Validates REQ-p00002-A: validation methods."""

    def test_REQ_p00002_A_is_valid(self):
        r = _make_hht_resolver()
        assert r.is_valid("REQ-prd00044") is True
        assert r.is_valid("p00044") is True
        assert r.is_valid("INVALID") is False

    def test_REQ_p00002_A_is_valid_assertion_label(self):
        r = _make_hht_resolver()
        assert r.is_valid_assertion_label("A") is True
        assert r.is_valid_assertion_label("Z") is True
        assert r.is_valid_assertion_label("a") is False
        assert r.is_valid_assertion_label("1") is False


class TestIdResolverAssertionLabels:
    """Validates REQ-p00002-A: assertion label methods."""

    def test_REQ_p00002_A_format_assertion_label_uppercase(self):
        r = _make_hht_resolver()
        assert r.format_assertion_label(0) == "A"
        assert r.format_assertion_label(1) == "B"
        assert r.format_assertion_label(25) == "Z"

    def test_REQ_p00002_A_format_assertion_label_out_of_range(self):
        r = _make_hht_resolver()
        with pytest.raises(ValueError):
            r.format_assertion_label(26)

    def test_REQ_p00002_A_parse_assertion_label_index(self):
        r = _make_hht_resolver()
        assert r.parse_assertion_label_index("A") == 0
        assert r.parse_assertion_label_index("B") == 1
        assert r.parse_assertion_label_index("Z") == 25


class TestIdResolverResolveLevel:
    """Validates REQ-p00002-A: resolve_level method."""

    def test_REQ_p00002_A_resolve_by_type_code(self):
        r = _make_hht_resolver()
        assert r.resolve_level("prd") == "prd"
        assert r.resolve_level("PRD") == "prd"

    def test_REQ_p00002_A_resolve_by_alias(self):
        r = _make_hht_resolver()
        assert r.resolve_level("p") == "prd"

    def test_REQ_p00002_A_resolve_unknown(self):
        r = _make_hht_resolver()
        assert r.resolve_level("unknown") is None

    def test_REQ_p00002_A_resolve_fda_style_uppercase_codes(self):
        r = _make_fda_resolver()
        assert r.resolve_level("PRD") == "PRD"
        assert r.resolve_level("prd") == "PRD"


class TestIdResolverOutputForm:
    """Validates REQ-p00002-A: output_form and render_for methods."""

    def test_REQ_p00002_A_output_form_default(self):
        r = _make_hht_resolver()
        assert r.output_form("anything") == "canonical"

    def test_REQ_p00002_A_output_form_configured(self):
        config = IdPatternConfig.from_dict(
            {
                "project": {"namespace": "REQ"},
                "id-patterns": {
                    "canonical": "{namespace}-{type}{component}",
                    "aliases": {"short": "{type.letter}{component}"},
                    "types": {"prd": {"level": 1, "aliases": {"letter": "p"}}},
                    "component": {"style": "numeric", "digits": 5},
                },
                "output": {"id-patterns": {"writer-requirement-edge": "short"}},
            }
        )
        r = IdResolver(config)
        assert r.output_form("writer-requirement-edge") == "short"
        assert r.output_form("unlisted-context") == "canonical"

    def test_REQ_p00002_A_render_for(self):
        config = IdPatternConfig.from_dict(
            {
                "project": {"namespace": "REQ"},
                "id-patterns": {
                    "canonical": "{namespace}-{type}{component}",
                    "aliases": {"short": "{type.letter}{component}"},
                    "types": {"prd": {"level": 1, "aliases": {"letter": "p"}}},
                    "component": {"style": "numeric", "digits": 5},
                },
                "output": {"id-patterns": {"writer-requirement-edge": "short"}},
            }
        )
        r = IdResolver(config)
        pid = r.parse("REQ-prd00044")
        assert r.render_for(pid, "writer-requirement-edge") == "p00044"
        assert r.render_for(pid, "unlisted") == "REQ-prd00044"


class TestIdResolverCanonicalRegex:
    """Validates REQ-p00002-A: regex methods."""

    def test_REQ_p00002_A_canonical_regex_matches(self):
        r = _make_hht_resolver()
        pat = r.canonical_regex()
        assert pat.search("REQ-prd00044") is not None

    def test_REQ_p00002_A_search_regex_finds_in_header(self):
        r = _make_hht_resolver()
        pat = r.search_regex()
        m = pat.search("# REQ-prd00044: Some Title")
        assert m is not None

    def test_REQ_p00002_A_all_type_codes(self):
        r = _make_hht_resolver()
        codes = r.all_type_codes()
        assert set(codes) == {"prd", "ops", "dev"}
