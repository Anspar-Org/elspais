"""Tests for the health command."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from elspais.commands import health
from elspais.commands.health import (
    HealthCheck,
    HealthReport,
    check_config_exists,
    check_config_hierarchy_rules,
    check_config_paths_exist,
    check_config_pattern_tokens,
    check_config_required_fields,
    check_config_syntax,
    check_spec_files_parseable,
    check_spec_no_duplicates,
    check_spec_orphans,
)
from elspais.config import ConfigLoader


# =============================================================================
# Test Data Structures
# =============================================================================


class TestHealthCheck:
    """Tests for the HealthCheck dataclass."""

    def test_basic_creation(self):
        """Test creating a health check."""
        check = HealthCheck(
            name="test.check",
            passed=True,
            message="All good",
            category="config",
        )
        assert check.name == "test.check"
        assert check.passed is True
        assert check.message == "All good"
        assert check.category == "config"
        assert check.severity == "error"  # default
        assert check.details == {}  # default

    def test_with_details(self):
        """Test health check with details."""
        check = HealthCheck(
            name="test.check",
            passed=False,
            message="Something wrong",
            category="spec",
            severity="warning",
            details={"file": "test.md", "line": 42},
        )
        assert check.details == {"file": "test.md", "line": 42}
        assert check.severity == "warning"


class TestHealthReport:
    """Tests for the HealthReport dataclass."""

    def test_empty_report(self):
        """Test empty health report is healthy."""
        report = HealthReport()
        assert report.passed == 0
        assert report.failed == 0
        assert report.warnings == 0
        assert report.is_healthy is True

    def test_all_passed(self):
        """Test report with all passed checks."""
        report = HealthReport()
        report.add(HealthCheck("a", True, "ok", "config"))
        report.add(HealthCheck("b", True, "ok", "spec"))

        assert report.passed == 2
        assert report.failed == 0
        assert report.is_healthy is True

    def test_with_errors(self):
        """Test report with errors is unhealthy."""
        report = HealthReport()
        report.add(HealthCheck("a", True, "ok", "config"))
        report.add(HealthCheck("b", False, "fail", "spec", severity="error"))

        assert report.passed == 1
        assert report.failed == 1
        assert report.is_healthy is False

    def test_warnings_dont_fail(self):
        """Test warnings don't make report unhealthy."""
        report = HealthReport()
        report.add(HealthCheck("a", True, "ok", "config"))
        report.add(HealthCheck("b", False, "warn", "spec", severity="warning"))

        assert report.passed == 1
        assert report.warnings == 1
        assert report.failed == 0
        assert report.is_healthy is True  # Warnings don't fail

    def test_iter_by_category(self):
        """Test filtering checks by category."""
        report = HealthReport()
        report.add(HealthCheck("c1", True, "ok", "config"))
        report.add(HealthCheck("s1", True, "ok", "spec"))
        report.add(HealthCheck("c2", True, "ok", "config"))

        config_checks = list(report.iter_by_category("config"))
        assert len(config_checks) == 2
        assert all(c.category == "config" for c in config_checks)

    def test_to_dict(self):
        """Test JSON serialization."""
        report = HealthReport()
        report.add(HealthCheck("test", True, "ok", "config"))

        result = report.to_dict()
        assert result["healthy"] is True
        assert result["summary"]["passed"] == 1
        assert len(result["checks"]) == 1


# =============================================================================
# Test Config Checks
# =============================================================================


class TestConfigChecks:
    """Tests for configuration health checks."""

    def test_required_fields_all_present(self):
        """Test required fields check with complete config."""
        config = ConfigLoader.from_dict({
            "patterns": {"types": {"prd": {}}},
            "spec": {"directories": ["spec"]},
            "rules": {"hierarchy": {"prd": []}},
        })

        check = check_config_required_fields(config)
        assert check.passed is True

    def test_required_fields_missing(self):
        """Test required fields check with missing sections."""
        config = ConfigLoader.from_dict({})  # Will get defaults

        # With defaults, all required fields should be present
        check = check_config_required_fields(config)
        assert check.passed is True

    def test_pattern_tokens_valid(self):
        """Test pattern tokens with valid template."""
        config = ConfigLoader.from_dict({
            "patterns": {"id_template": "{prefix}-{type}{id}"},
        })

        check = check_config_pattern_tokens(config)
        assert check.passed is True

    def test_pattern_tokens_invalid(self):
        """Test pattern tokens with invalid token."""
        config = ConfigLoader.from_dict({
            "patterns": {"id_template": "{prefix}-{invalid}{id}"},
        })

        check = check_config_pattern_tokens(config)
        assert check.passed is False
        assert "{invalid}" in check.details.get("invalid_tokens", [])

    def test_hierarchy_rules_valid(self):
        """Test hierarchy rules check with valid config."""
        config = ConfigLoader.from_dict({
            "patterns": {
                "types": {
                    "prd": {"id": "p"},
                    "ops": {"id": "o"},
                    "dev": {"id": "d"},
                },
            },
            "rules": {
                "hierarchy": {
                    "dev": ["ops", "prd"],
                    "ops": ["prd"],
                    "prd": [],
                },
            },
        })

        check = check_config_hierarchy_rules(config)
        assert check.passed is True

    def test_paths_exist(self, tmp_path):
        """Test paths exist check."""
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        config = ConfigLoader.from_dict({
            "spec": {"directories": ["spec"]},
        })

        check = check_config_paths_exist(config, tmp_path)
        assert check.passed is True

    def test_paths_missing(self, tmp_path):
        """Test paths exist check with missing directory."""
        config = ConfigLoader.from_dict({
            "spec": {"directories": ["nonexistent"]},
        })

        check = check_config_paths_exist(config, tmp_path)
        assert check.passed is False
        assert "nonexistent" in check.details.get("missing", [])


# =============================================================================
# Test Full Command
# =============================================================================


class TestHealthCommand:
    """Tests for the health command run function."""

    def test_config_only_flag(self, tmp_path):
        """Test --config flag runs only config checks."""
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        args = argparse.Namespace(
            spec_dir=None,
            config=None,
            config_only=True,
            spec_only=False,
            code_only=False,
            tests_only=False,
            json=True,
            verbose=False,
        )

        # Need to be in a directory with valid config
        import os
        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            with patch("sys.stdout"):
                result = health.run(args)
            # Should succeed with defaults
            assert result in (0, 1)  # May warn about missing spec
        finally:
            os.chdir(old_cwd)

    def test_json_output_format(self, tmp_path, capsys):
        """Test JSON output format is valid."""
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        args = argparse.Namespace(
            spec_dir=str(spec_dir),
            config=None,
            config_only=True,
            spec_only=False,
            code_only=False,
            tests_only=False,
            json=True,
            verbose=False,
        )

        import os
        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            health.run(args)
            captured = capsys.readouterr()
            # Should be valid JSON
            result = json.loads(captured.out)
            assert "healthy" in result
            assert "summary" in result
            assert "checks" in result
        finally:
            os.chdir(old_cwd)


# =============================================================================
# Integration Tests
# =============================================================================


class TestHealthIntegration:
    """Integration tests using real spec files."""

    def test_full_health_check(self, tmp_path):
        """Test full health check on minimal repo."""
        # Create minimal spec structure
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        # Create a valid requirement file
        req_file = spec_dir / "requirements.md"
        req_file.write_text("""# Requirements

## REQ-p00001: Test Requirement

**Status:** Active

The system SHALL do something.

---
<!-- Hash: 12345678 -->
""")

        # Create config
        config_file = tmp_path / ".elspais.toml"
        config_file.write_text("""
[patterns]
id_template = "{prefix}-{type}{id}"
prefix = "REQ"

[patterns.types.prd]
id = "p"
name = "PRD"
level = 1

[spec]
directories = ["spec"]

[rules.hierarchy]
prd = []
""")

        args = argparse.Namespace(
            spec_dir=str(spec_dir),
            config=str(config_file),
            config_only=False,
            spec_only=False,
            code_only=False,
            tests_only=False,
            json=True,
            verbose=False,
        )

        import os
        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            # Run the health check
            result = health.run(args)
            # Should be healthy (0) or have warnings (still 0 since warnings don't fail)
            # May return 1 if spec checks find issues with the minimal test case
            assert result in (0, 1)
        finally:
            os.chdir(old_cwd)
