"""Tests for the health command."""

from __future__ import annotations

import argparse
import json

from elspais.commands import health
from elspais.commands.health import (
    HealthCheck,
    HealthReport,
    check_config_hierarchy_rules,
    check_config_paths_exist,
    check_config_pattern_tokens,
    check_config_required_fields,
)
from elspais.config import _merge_configs, config_defaults

# =============================================================================
# Test Data Structures
# =============================================================================


class TestHealthCheck:
    """Tests for the HealthCheck dataclass."""

    # Implements: REQ-d00085-I
    def test_basic_creation_defaults(self):
        """Test HealthCheck default values for severity and details."""
        check = HealthCheck(
            name="test.check",
            passed=True,
            message="All good",
            category="config",
        )
        assert check.severity == "error"  # default
        assert check.details == {}  # default


class TestHealthReport:
    """Tests for the HealthReport dataclass."""

    # Implements: REQ-d00080-A
    def test_empty_and_all_passed_are_healthy(self):
        """Empty report and all-passed report are both healthy."""
        empty = HealthReport()
        assert empty.is_healthy is True

        report = HealthReport()
        report.add(HealthCheck("a", True, "ok", "config"))
        report.add(HealthCheck("b", True, "ok", "spec"))
        assert report.passed == 2
        assert report.failed == 0
        assert report.is_healthy is True

    # Implements: REQ-d00080-A
    def test_with_errors(self):
        """Test report with errors is unhealthy."""
        report = HealthReport()
        report.add(HealthCheck("a", True, "ok", "config"))
        report.add(HealthCheck("b", False, "fail", "spec", severity="error"))

        assert report.passed == 1
        assert report.failed == 1
        assert report.is_healthy is False

    # Implements: REQ-d00080-A
    def test_REQ_d00080_A_warnings_fail_by_default(self):
        """Validates REQ-d00080-A: warnings cause non-zero exit by default."""
        report = HealthReport()
        report.add(HealthCheck("a", True, "ok", "config"))
        report.add(HealthCheck("b", False, "warn", "spec", severity="warning"))

        assert report.passed == 1
        assert report.warnings == 1
        assert report.failed == 0
        assert report.is_healthy is False  # Warnings fail by default
        assert report.is_healthy_lenient is True  # Lenient ignores warnings

    # Implements: REQ-d00085-I
    def test_iter_by_category(self):
        """Test filtering checks by category."""
        report = HealthReport()
        report.add(HealthCheck("c1", True, "ok", "config"))
        report.add(HealthCheck("s1", True, "ok", "spec"))
        report.add(HealthCheck("c2", True, "ok", "config"))

        config_checks = list(report.iter_by_category("config"))
        assert len(config_checks) == 2
        assert all(c.category == "config" for c in config_checks)

    # Implements: REQ-d00085-I
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

    # Implements: REQ-d00080-C
    def test_required_fields_all_present(self):
        """Test required fields check with complete config."""
        config = _merge_configs(
            config_defaults(),
            {
                "levels": {"prd": {"rank": 1, "letter": "p", "implements": []}},
                "scanning": {"spec": {"directories": ["spec"]}},
            },
        )

        check = check_config_required_fields(config)
        assert check.passed is True

    # Implements: REQ-d00080-C
    def test_required_fields_present_with_defaults(self):
        """Test that default config with spec dirs has all required fields present."""
        config = _merge_configs(
            config_defaults(),
            {"scanning": {"spec": {"directories": ["spec"]}}},
        )

        # With spec dirs set, all required fields should be present
        check = check_config_required_fields(config)
        assert check.passed is True

    # Implements: REQ-d00204-A
    def test_pattern_tokens_valid(self):
        """Test pattern tokens with valid template."""
        config = _merge_configs(
            config_defaults(),
            {
                "id-patterns": {"canonical": "{namespace}-{level}{component}"},
            },
        )

        check = check_config_pattern_tokens(config)
        assert check.passed is True

    # Implements: REQ-d00204-A
    def test_pattern_tokens_invalid(self):
        """Test pattern tokens with invalid token."""
        config = _merge_configs(
            config_defaults(),
            {
                "id-patterns": {"canonical": "{namespace}-{invalid}{component}"},
            },
        )

        check = check_config_pattern_tokens(config)
        assert check.passed is False
        assert "{invalid}" in check.details.get("invalid_tokens", [])

    # Implements: REQ-d00204-A
    def test_hierarchy_rules_valid(self):
        """Test hierarchy rules check with valid config."""
        config = _merge_configs(
            config_defaults(),
            {
                "levels": {
                    "prd": {"rank": 1, "letter": "p", "implements": []},
                    "ops": {"rank": 2, "letter": "o", "implements": ["prd"]},
                    "dev": {"rank": 3, "letter": "d", "implements": ["ops", "prd"]},
                },
            },
        )

        check = check_config_hierarchy_rules(config)
        assert check.passed is True

    # Implements: REQ-d00080-C
    def test_paths_exist(self, tmp_path):
        """Test paths exist check."""
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        config = _merge_configs(
            config_defaults(),
            {
                "scanning": {"spec": {"directories": ["spec"]}},
            },
        )

        check = check_config_paths_exist(config, tmp_path)
        assert check.passed is True

    # Implements: REQ-d00080-C
    def test_paths_missing(self, tmp_path):
        """Test paths exist check with missing directory."""
        config = _merge_configs(
            config_defaults(),
            {
                "scanning": {"spec": {"directories": ["nonexistent"]}},
            },
        )

        check = check_config_paths_exist(config, tmp_path)
        assert check.passed is False
        assert "nonexistent" in check.details.get("missing", [])


# =============================================================================
# Test Full Command
# =============================================================================


class TestHealthCommand:
    """Tests for the health command run function."""

    # Implements: REQ-d00085-E
    def test_json_output_format(self, tmp_path, capsys):
        """Test JSON output format is valid."""
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        args = argparse.Namespace(
            spec_dir=str(spec_dir),
            config=None,
            spec_only=False,
            code_only=False,
            tests_only=False,
            format="json",
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

    # Implements: REQ-d00080-A
    def test_full_health_check(self, tmp_path):
        """Test full health check on minimal repo."""
        # Create minimal spec structure
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        # Create a valid requirement file
        req_file = spec_dir / "requirements.md"
        req_file.write_text(
            """# REQ-p00001: Test Requirement

**Level**: PRD | **Status**: Active

The system SHALL do something.

*End* *Test Requirement* | **Hash**: 12345678
---
"""
        )

        # Create config using the current schema
        config_file = tmp_path / ".elspais.toml"
        config_file.write_text(
            """
version = 3

[project]
namespace = "REQ"

[levels.prd]
rank = 1
letter = "p"
implements = []

[id-patterns]
canonical = "{namespace}-{level.letter}{component}"

[id-patterns.component]
style = "numeric"
digits = 5
leading_zeros = true

[scanning.spec]
directories = ["spec"]

[rules.format]
no_assertions_severity = "info"

[changelog]
hash_current = false
present = false
"""
        )

        args = argparse.Namespace(
            spec_dir=spec_dir,
            config=config_file,
            spec_only=False,
            code_only=False,
            tests_only=False,
            format="json",
            verbose=False,
        )

        import os

        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            # Run the health check — minimal valid config should pass
            result = health.run(args)
            assert result == 0, f"Expected healthy (0) but got {result}"
        finally:
            os.chdir(old_cwd)
