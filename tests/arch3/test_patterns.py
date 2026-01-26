"""Tests for patterns.py - Requirement ID pattern matching."""

import pytest

from elspais.arch3.utilities.patterns import (
    PatternConfig,
    PatternValidator,
    normalize_req_id,
)


@pytest.fixture
def hht_config():
    """HHT-style pattern configuration."""
    return PatternConfig(
        id_template="{prefix}-{associated}{type}{id}",
        prefix="REQ",
        types={
            "prd": {"id": "p", "name": "PRD", "level": 1},
            "ops": {"id": "o", "name": "OPS", "level": 2},
            "dev": {"id": "d", "name": "DEV", "level": 3},
        },
        id_format={"style": "numeric", "digits": 5, "leading_zeros": True},
        associated={"enabled": True, "length": 3, "separator": "-"},
    )


@pytest.fixture
def jira_config():
    """Jira-style pattern configuration."""
    return PatternConfig(
        id_template="{prefix}-{id}",
        prefix="PROJ",
        types={},
        id_format={"style": "numeric", "digits": 0},
    )


class TestPatternConfig:
    """Tests for PatternConfig dataclass."""

    def test_from_dict(self):
        data = {
            "id_template": "{prefix}-{type}{id}",
            "prefix": "REQ",
            "types": {"prd": {"id": "p"}},
            "id_format": {"style": "numeric", "digits": 5},
        }
        config = PatternConfig.from_dict(data)
        assert config.prefix == "REQ"
        assert config.id_template == "{prefix}-{type}{id}"

    def test_from_dict_defaults(self):
        config = PatternConfig.from_dict({})
        assert config.prefix == "REQ"
        assert config.id_template == "{prefix}-{type}{id}"

    def test_get_all_type_ids(self, hht_config):
        type_ids = hht_config.get_all_type_ids()
        assert set(type_ids) == {"p", "o", "d"}

    def test_get_type_by_id(self, hht_config):
        prd_type = hht_config.get_type_by_id("p")
        assert prd_type["name"] == "PRD"
        assert prd_type["level"] == 1

    def test_assertion_label_pattern_uppercase(self):
        config = PatternConfig(
            id_template="",
            prefix="",
            types={},
            id_format={},
            assertions={"label_style": "uppercase"},
        )
        assert config.get_assertion_label_pattern() == r"[A-Z]"

    def test_assertion_label_pattern_numeric(self):
        config = PatternConfig(
            id_template="",
            prefix="",
            types={},
            id_format={},
            assertions={"label_style": "numeric"},
        )
        assert config.get_assertion_label_pattern() == r"[0-9]{1,2}"


class TestPatternValidator:
    """Tests for PatternValidator class."""

    def test_parse_hht_basic(self, hht_config):
        validator = PatternValidator(hht_config)
        parsed = validator.parse("REQ-p00001")

        assert parsed is not None
        assert parsed.full_id == "REQ-p00001"
        assert parsed.prefix == "REQ"
        assert parsed.type_code == "p"
        assert parsed.number == "00001"
        assert parsed.associated is None

    def test_parse_hht_with_associated(self, hht_config):
        validator = PatternValidator(hht_config)
        parsed = validator.parse("REQ-CAL-d00027")

        assert parsed is not None
        assert parsed.associated == "CAL"
        assert parsed.type_code == "d"
        assert parsed.number == "00027"

    def test_parse_with_assertion(self, hht_config):
        validator = PatternValidator(hht_config)
        parsed = validator.parse("REQ-p00001-A", allow_assertion=True)

        assert parsed is not None
        assert parsed.assertion == "A"

    def test_parse_invalid_returns_none(self, hht_config):
        validator = PatternValidator(hht_config)
        assert validator.parse("INVALID") is None
        assert validator.parse("REQ-x00001") is None  # Invalid type

    def test_is_valid(self, hht_config):
        validator = PatternValidator(hht_config)
        assert validator.is_valid("REQ-p00001") is True
        assert validator.is_valid("INVALID") is False

    def test_format_basic(self, hht_config):
        validator = PatternValidator(hht_config)
        formatted = validator.format("p", 1)
        assert formatted == "REQ-p00001"

    def test_format_with_associated(self, hht_config):
        validator = PatternValidator(hht_config)
        formatted = validator.format("d", 27, associated="CAL")
        assert formatted == "REQ-CAL-d00027"

    def test_jira_style(self, jira_config):
        validator = PatternValidator(jira_config)
        assert validator.is_valid("PROJ-123") is True
        assert validator.is_valid("PROJ-1") is True
        assert validator.is_valid("PROJ-12345") is True

    def test_extract_implements_ids(self, hht_config):
        validator = PatternValidator(hht_config)
        ids = validator.extract_implements_ids("REQ-p00001, REQ-o00002")
        assert ids == ["REQ-p00001", "REQ-o00002"]

    def test_extract_implements_ids_empty(self, hht_config):
        validator = PatternValidator(hht_config)
        assert validator.extract_implements_ids("") == []
        assert validator.extract_implements_ids(None) == []


class TestAssertionLabels:
    """Tests for assertion label handling."""

    def test_format_assertion_label_uppercase(self, hht_config):
        validator = PatternValidator(hht_config)
        assert validator.format_assertion_label(0) == "A"
        assert validator.format_assertion_label(1) == "B"
        assert validator.format_assertion_label(25) == "Z"

    def test_format_assertion_label_out_of_range(self, hht_config):
        validator = PatternValidator(hht_config)
        with pytest.raises(ValueError):
            validator.format_assertion_label(26)

    def test_parse_assertion_label_index(self, hht_config):
        validator = PatternValidator(hht_config)
        assert validator.parse_assertion_label_index("A") == 0
        assert validator.parse_assertion_label_index("B") == 1
        assert validator.parse_assertion_label_index("Z") == 25

    def test_is_valid_assertion_label(self, hht_config):
        validator = PatternValidator(hht_config)
        assert validator.is_valid_assertion_label("A") is True
        assert validator.is_valid_assertion_label("Z") is True
        assert validator.is_valid_assertion_label("a") is False
        assert validator.is_valid_assertion_label("1") is False


class TestNormalizeReqId:
    """Tests for normalize_req_id function."""

    def test_adds_prefix(self):
        assert normalize_req_id("d00027") == "REQ-d00027"

    def test_preserves_existing_prefix(self):
        assert normalize_req_id("REQ-d00027") == "REQ-d00027"

    def test_custom_prefix(self):
        assert normalize_req_id("123", prefix="JIRA") == "JIRA-123"
