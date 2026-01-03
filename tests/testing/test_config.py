"""Tests for elspais.testing.config module."""

import pytest

from elspais.testing.config import TestingConfig


class TestTestingConfig:
    """Tests for TestingConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = TestingConfig()

        assert config.enabled is False
        assert config.test_dirs == []
        assert config.patterns == []
        assert config.result_files == []
        assert config.reference_patterns == []

    def test_from_dict_minimal(self):
        """Test creating config from minimal dictionary."""
        data = {"enabled": True}
        config = TestingConfig.from_dict(data)

        assert config.enabled is True
        assert config.test_dirs == []

    def test_from_dict_full(self):
        """Test creating config from full dictionary."""
        data = {
            "enabled": True,
            "test_dirs": ["tests", "apps/**/test"],
            "patterns": ["*_test.py", "test_*.py"],
            "result_files": ["build-reports/**/*.xml"],
            "reference_patterns": [r"REQ-([pod]\d{5})"],
        }
        config = TestingConfig.from_dict(data)

        assert config.enabled is True
        assert config.test_dirs == ["tests", "apps/**/test"]
        assert config.patterns == ["*_test.py", "test_*.py"]
        assert config.result_files == ["build-reports/**/*.xml"]
        assert config.reference_patterns == [r"REQ-([pod]\d{5})"]

    def test_from_dict_empty(self):
        """Test creating config from empty dictionary."""
        config = TestingConfig.from_dict({})

        assert config.enabled is False
        assert config.test_dirs == []

    def test_from_dict_with_defaults(self):
        """Test that missing keys get default values."""
        data = {
            "enabled": True,
            "test_dirs": ["tests"],
        }
        config = TestingConfig.from_dict(data)

        assert config.enabled is True
        assert config.test_dirs == ["tests"]
        assert config.patterns == []  # Default
        assert config.result_files == []  # Default
