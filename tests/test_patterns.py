"""
Tests for elspais.core.patterns module.
"""

import pytest
from pathlib import Path


class TestPatternValidator:
    """Tests for PatternValidator class."""

    def test_hht_pattern_parse(self, sample_config_dict):
        """Test parsing HHT-style IDs (REQ-p00001)."""
        from elspais.core.patterns import PatternValidator, PatternConfig

        config = PatternConfig.from_dict(sample_config_dict["patterns"])
        validator = PatternValidator(config)

        parsed = validator.parse("REQ-p00001")
        assert parsed is not None
        assert parsed.prefix == "REQ"
        assert parsed.type_code == "p"
        assert parsed.number == "00001"
        assert parsed.associated is None

    def test_hht_pattern_parse_with_associated(self):
        """Test parsing HHT-style IDs with associated prefix (REQ-CAL-d00001)."""
        from elspais.core.patterns import PatternValidator, PatternConfig

        config = PatternConfig(
            id_template="{prefix}-{associated}{type}{id}",
            prefix="REQ",
            types={"prd": {"id": "p", "level": 1}, "dev": {"id": "d", "level": 3}},
            id_format={"style": "numeric", "digits": 5, "leading_zeros": True},
            associated={"enabled": True, "length": 3, "format": "uppercase", "separator": "-"},
        )
        validator = PatternValidator(config)

        parsed = validator.parse("REQ-CAL-d00001")
        assert parsed is not None
        assert parsed.prefix == "REQ"
        assert parsed.associated == "CAL"
        assert parsed.type_code == "d"
        assert parsed.number == "00001"

    def test_type_prefix_pattern_parse(self):
        """Test parsing type-prefix style IDs (PRD-00001)."""
        from elspais.core.patterns import PatternValidator, PatternConfig

        config = PatternConfig(
            id_template="{type}-{id}",
            prefix="",
            types={
                "PRD": {"id": "PRD", "level": 1},
                "OPS": {"id": "OPS", "level": 2},
                "DEV": {"id": "DEV", "level": 3},
            },
            id_format={"style": "numeric", "digits": 5, "leading_zeros": True},
        )
        validator = PatternValidator(config)

        parsed = validator.parse("PRD-00001")
        assert parsed is not None
        assert parsed.type_code == "PRD"
        assert parsed.number == "00001"

        parsed_dev = validator.parse("DEV-00042")
        assert parsed_dev is not None
        assert parsed_dev.type_code == "DEV"
        assert parsed_dev.number == "00042"

    def test_jira_pattern_parse(self):
        """Test parsing Jira-style IDs (PROJ-123)."""
        from elspais.core.patterns import PatternValidator, PatternConfig

        config = PatternConfig(
            id_template="{prefix}-{id}",
            prefix="PROJ",
            types={"req": {"id": "", "level": 1}},
            id_format={"style": "numeric", "digits": 0, "leading_zeros": False},
        )
        validator = PatternValidator(config)

        parsed = validator.parse("PROJ-1")
        assert parsed is not None
        assert parsed.prefix == "PROJ"
        assert parsed.number == "1"

        parsed_long = validator.parse("PROJ-12345")
        assert parsed_long is not None
        assert parsed_long.number == "12345"

    def test_named_pattern_parse(self):
        """Test parsing named IDs (REQ-UserAuth)."""
        from elspais.core.patterns import PatternValidator, PatternConfig

        config = PatternConfig(
            id_template="{prefix}-{id}",
            prefix="REQ",
            types={"req": {"id": "", "level": 1}},
            id_format={"style": "named", "pattern": "[A-Z][a-zA-Z0-9]+", "max_length": 32},
        )
        validator = PatternValidator(config)

        parsed = validator.parse("REQ-UserAuthentication")
        assert parsed is not None
        assert parsed.number == "UserAuthentication"

    def test_invalid_id_returns_none(self, sample_config_dict):
        """Test that invalid IDs return None."""
        from elspais.core.patterns import PatternValidator, PatternConfig

        config = PatternConfig.from_dict(sample_config_dict["patterns"])
        validator = PatternValidator(config)

        assert validator.parse("INVALID") is None
        assert validator.parse("REQ-x00001") is None  # Invalid type
        assert validator.parse("REQ-p1") is None  # Wrong digit count
        assert validator.parse("req-p00001") is None  # Wrong case

    def test_format_id(self, sample_config_dict):
        """Test formatting a requirement ID from components."""
        from elspais.core.patterns import PatternValidator, PatternConfig

        config = PatternConfig.from_dict(sample_config_dict["patterns"])
        validator = PatternValidator(config)

        formatted = validator.format(type_code="p", number=1)
        assert formatted == "REQ-p00001"

        formatted_dev = validator.format(type_code="d", number=42)
        assert formatted_dev == "REQ-d00042"

    def test_format_id_with_associated(self):
        """Test formatting ID with associated prefix."""
        from elspais.core.patterns import PatternValidator, PatternConfig

        config = PatternConfig(
            id_template="{prefix}-{associated}{type}{id}",
            prefix="REQ",
            types={"dev": {"id": "d", "level": 3}},
            id_format={"style": "numeric", "digits": 5, "leading_zeros": True},
            associated={"enabled": True, "length": 3, "format": "uppercase", "separator": "-"},
        )
        validator = PatternValidator(config)

        formatted = validator.format(type_code="d", number=1, associated="CAL")
        assert formatted == "REQ-CAL-d00001"

    def test_validate_id(self, sample_config_dict):
        """Test validating requirement IDs."""
        from elspais.core.patterns import PatternValidator, PatternConfig

        config = PatternConfig.from_dict(sample_config_dict["patterns"])
        validator = PatternValidator(config)

        assert validator.is_valid("REQ-p00001") is True
        assert validator.is_valid("REQ-d00042") is True
        assert validator.is_valid("INVALID") is False
        assert validator.is_valid("REQ-x00001") is False


class TestPatternConfig:
    """Tests for PatternConfig dataclass."""

    def test_from_dict(self, sample_config_dict):
        """Test creating PatternConfig from dictionary."""
        from elspais.core.patterns import PatternConfig

        config = PatternConfig.from_dict(sample_config_dict["patterns"])

        assert config.id_template == "{prefix}-{type}{id}"
        assert config.prefix == "REQ"
        assert "prd" in config.types
        assert config.id_format["style"] == "numeric"

    def test_get_type_by_id(self, sample_config_dict):
        """Test getting type config by type ID."""
        from elspais.core.patterns import PatternConfig

        config = PatternConfig.from_dict(sample_config_dict["patterns"])

        prd_type = config.get_type_by_id("p")
        assert prd_type is not None
        assert prd_type["level"] == 1

        dev_type = config.get_type_by_id("d")
        assert dev_type is not None
        assert dev_type["level"] == 3

        unknown = config.get_type_by_id("x")
        assert unknown is None
