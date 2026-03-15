# Validates REQ-d00002-A:
"""Tests for CLI config override functionality.

Validates:
- REQ-d00002-A: Configuration system supports runtime overrides
"""

import copy

import pytest

from elspais.config import DEFAULT_CONFIG, apply_cli_overrides


class TestApplyCliOverrides:
    """Validates REQ-d00002-A: CLI config override tests."""

    def test_REQ_d00002_A_override_simple_string(self):
        config = copy.deepcopy(DEFAULT_CONFIG)
        apply_cli_overrides(config, ["project.namespace=MYREQ"])
        assert config["project"]["namespace"] == "MYREQ"

    def test_REQ_d00002_A_override_boolean_true(self):
        config = {"testing": {"enabled": False}}
        apply_cli_overrides(config, ["testing.enabled=true"])
        assert config["testing"]["enabled"] is True

    def test_REQ_d00002_A_override_boolean_false(self):
        config = {"testing": {"enabled": True}}
        apply_cli_overrides(config, ["testing.enabled=false"])
        assert config["testing"]["enabled"] is False

    def test_REQ_d00002_A_override_json_list(self):
        config = {"spec": {"directories": ["spec"]}}
        apply_cli_overrides(config, ['spec.directories=["a","b"]'])
        assert config["spec"]["directories"] == ["a", "b"]

    def test_REQ_d00002_A_override_invalid_format(self):
        config = {}
        with pytest.raises(ValueError, match="key=value"):
            apply_cli_overrides(config, ["no-equals-sign"])

    def test_REQ_d00002_A_override_multiple(self):
        config = {"spec": {"directories": ["spec"]}, "testing": {"enabled": False}}
        apply_cli_overrides(config, ['spec.directories=["a"]', "testing.enabled=true"])
        assert config["spec"]["directories"] == ["a"]
        assert config["testing"]["enabled"] is True

    def test_REQ_d00002_A_override_creates_nested(self):
        config = {}
        apply_cli_overrides(config, ["new.nested.key=value"])
        assert config["new"]["nested"]["key"] == "value"

    def test_REQ_d00002_A_override_empty_list(self):
        config = {}
        result = apply_cli_overrides(config, [])
        assert result == config

    def test_REQ_d00002_A_override_none_list(self):
        config = {}
        result = apply_cli_overrides(config, None)
        assert result == config
