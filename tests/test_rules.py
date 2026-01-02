"""
Tests for elspais.core.rules module.
"""

import pytest
from pathlib import Path


class TestRuleEngine:
    """Tests for RuleEngine class."""

    def test_hierarchy_rule_valid(self, sample_config_dict):
        """Test hierarchy rule passes for valid relationships."""
        from elspais.core.rules import RuleEngine, RulesConfig
        from elspais.core.models import Requirement

        config = RulesConfig.from_dict(sample_config_dict["rules"])
        engine = RuleEngine(config)

        requirements = {
            "REQ-p00001": Requirement(
                id="REQ-p00001", title="PRD", level="PRD", status="Active", body=""
            ),
            "REQ-d00001": Requirement(
                id="REQ-d00001",
                title="DEV",
                level="DEV",
                status="Active",
                body="",
                implements=["p00001"],
            ),
        }

        violations = engine.validate(requirements)
        hierarchy_violations = [v for v in violations if "hierarchy" in v.rule_name]
        assert len(hierarchy_violations) == 0

    def test_hierarchy_rule_invalid(self, sample_config_dict):
        """Test hierarchy rule fails for invalid relationships."""
        from elspais.core.rules import RuleEngine, RulesConfig
        from elspais.core.models import Requirement

        # Modify config to forbid PRD -> DEV
        config = RulesConfig.from_dict(sample_config_dict["rules"])
        engine = RuleEngine(config)

        requirements = {
            "REQ-d00001": Requirement(
                id="REQ-d00001", title="DEV", level="DEV", status="Active", body=""
            ),
            "REQ-p00001": Requirement(
                id="REQ-p00001",
                title="PRD",
                level="PRD",
                status="Active",
                body="",
                implements=["d00001"],  # PRD implementing DEV - invalid!
            ),
        }

        violations = engine.validate(requirements)
        hierarchy_violations = [v for v in violations if "hierarchy" in v.rule_name]
        assert len(hierarchy_violations) > 0

    def test_circular_dependency_detection(self, sample_config_dict):
        """Test circular dependency detection."""
        from elspais.core.rules import RuleEngine, RulesConfig
        from elspais.core.models import Requirement

        # Allow DEV -> DEV for this test, but forbid circular
        rules_dict = sample_config_dict["rules"].copy()
        rules_dict["hierarchy"]["allowed_implements"] = ["dev -> dev, prd"]
        config = RulesConfig.from_dict(rules_dict)
        engine = RuleEngine(config)

        requirements = {
            "REQ-d00001": Requirement(
                id="REQ-d00001",
                title="First",
                level="DEV",
                status="Active",
                body="",
                implements=["d00002"],
            ),
            "REQ-d00002": Requirement(
                id="REQ-d00002",
                title="Second",
                level="DEV",
                status="Active",
                body="",
                implements=["d00001"],  # Circular!
            ),
        }

        violations = engine.validate(requirements)
        circular_violations = [v for v in violations if "circular" in v.rule_name]
        assert len(circular_violations) > 0

    def test_orphan_detection(self, sample_config_dict):
        """Test orphan requirement detection."""
        from elspais.core.rules import RuleEngine, RulesConfig, Severity
        from elspais.core.models import Requirement

        config = RulesConfig.from_dict(sample_config_dict["rules"])
        engine = RuleEngine(config)

        requirements = {
            "REQ-d00001": Requirement(
                id="REQ-d00001",
                title="Orphan",
                level="DEV",
                status="Active",
                body="",
                implements=[],  # No parent - orphan!
            ),
        }

        violations = engine.validate(requirements)
        orphan_violations = [v for v in violations if "orphan" in v.rule_name.lower()]
        assert len(orphan_violations) > 0

    def test_format_rule_missing_hash(self, sample_config_dict):
        """Test format rule detects missing hash."""
        from elspais.core.rules import RuleEngine, RulesConfig
        from elspais.core.models import Requirement

        config = RulesConfig.from_dict(sample_config_dict["rules"])
        engine = RuleEngine(config)

        requirements = {
            "REQ-p00001": Requirement(
                id="REQ-p00001",
                title="No Hash",
                level="PRD",
                status="Active",
                body="",
                hash=None,  # Missing hash!
            ),
        }

        violations = engine.validate(requirements)
        hash_violations = [v for v in violations if "hash" in v.rule_name.lower()]
        assert len(hash_violations) > 0

    def test_format_rule_missing_assertions(self, sample_config_dict):
        """Test format rule detects missing assertions."""
        from elspais.core.rules import RuleEngine, RulesConfig
        from elspais.core.models import Requirement

        config = RulesConfig.from_dict(sample_config_dict["rules"])
        engine = RuleEngine(config)

        requirements = {
            "REQ-p00001": Requirement(
                id="REQ-p00001",
                title="No Assertions",
                level="PRD",
                status="Active",
                body="",
                hash="a1b2c3d4",
                assertions=[],  # Empty!
            ),
        }

        violations = engine.validate(requirements)
        assertion_violations = [v for v in violations if "assertions" in v.rule_name.lower()]
        assert len(assertion_violations) > 0


class TestRulesConfig:
    """Tests for RulesConfig dataclass."""

    def test_from_dict(self, sample_config_dict):
        """Test creating RulesConfig from dictionary."""
        from elspais.core.rules import RulesConfig

        config = RulesConfig.from_dict(sample_config_dict["rules"])

        assert config.hierarchy.allow_circular is False
        assert config.hierarchy.allow_orphans is False
        assert config.format.require_hash is True
        assert config.format.require_assertions is True
        assert config.format.acceptance_criteria == "warn"

    def test_parse_allowed_implements(self, sample_config_dict):
        """Test parsing allowed_implements rules."""
        from elspais.core.rules import RulesConfig

        config = RulesConfig.from_dict(sample_config_dict["rules"])

        # Check that "dev -> ops, prd" was parsed correctly
        assert config.hierarchy.can_implement("dev", "ops") is True
        assert config.hierarchy.can_implement("dev", "prd") is True
        assert config.hierarchy.can_implement("dev", "dev") is False
        assert config.hierarchy.can_implement("prd", "dev") is False


class TestSeverity:
    """Tests for Severity enum."""

    def test_severity_values(self):
        """Test severity enum values."""
        from elspais.core.rules import Severity

        assert Severity.ERROR.value == "error"
        assert Severity.WARNING.value == "warning"
        assert Severity.INFO.value == "info"

    def test_severity_comparison(self):
        """Test severity comparison for filtering."""
        from elspais.core.rules import Severity

        # Errors are more severe than warnings
        severities = [Severity.INFO, Severity.WARNING, Severity.ERROR]
        sorted_severities = sorted(severities, key=lambda s: ["info", "warning", "error"].index(s.value))
        assert sorted_severities[0] == Severity.INFO
        assert sorted_severities[-1] == Severity.ERROR


class TestRuleViolation:
    """Tests for RuleViolation dataclass."""

    def test_violation_creation(self):
        """Test creating a RuleViolation."""
        from elspais.core.rules import RuleViolation, Severity

        violation = RuleViolation(
            rule_name="hierarchy.circular",
            requirement_id="REQ-d00001",
            message="Circular dependency detected",
            severity=Severity.ERROR,
            location="spec/dev-impl.md:42",
        )

        assert violation.rule_name == "hierarchy.circular"
        assert violation.severity == Severity.ERROR
        assert "42" in violation.location

    def test_violation_str(self):
        """Test RuleViolation string representation."""
        from elspais.core.rules import RuleViolation, Severity

        violation = RuleViolation(
            rule_name="format.require_hash",
            requirement_id="REQ-p00001",
            message="Missing hash",
            severity=Severity.ERROR,
            location="spec/prd-core.md:10",
        )

        violation_str = str(violation)
        assert "REQ-p00001" in violation_str
        assert "Missing hash" in violation_str
