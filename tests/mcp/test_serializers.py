"""
Tests for elspais.mcp.serializers module.
"""

import pytest
from pathlib import Path


class TestSerializeRequirement:
    """Tests for requirement serialization."""

    def test_serialize_requirement(self):
        """Test serializing a requirement to dict."""
        from elspais.mcp.serializers import serialize_requirement
        from elspais.core.models import Requirement, Assertion

        req = Requirement(
            id="REQ-p00001",
            title="Test Requirement",
            level="PRD",
            status="Active",
            body="This is the body.",
            implements=["REQ-p00000"],
            assertions=[
                Assertion(label="A", text="The system SHALL do something."),
            ],
            hash="abc12345",
            file_path=Path("spec/prd-core.md"),
            line_number=10,
        )

        result = serialize_requirement(req)

        assert result["id"] == "REQ-p00001"
        assert result["title"] == "Test Requirement"
        assert result["level"] == "PRD"
        assert result["status"] == "Active"
        assert result["body"] == "This is the body."
        assert result["implements"] == ["REQ-p00000"]
        assert len(result["assertions"]) == 1
        assert result["assertions"][0]["label"] == "A"
        assert result["hash"] == "abc12345"
        assert "spec/prd-core.md" in result["file_path"]
        assert result["line_number"] == 10

    def test_serialize_requirement_summary(self):
        """Test serializing requirement summary."""
        from elspais.mcp.serializers import serialize_requirement_summary
        from elspais.core.models import Requirement, Assertion

        req = Requirement(
            id="REQ-p00001",
            title="Test Requirement",
            level="PRD",
            status="Active",
            body="This is the body.",
            assertions=[
                Assertion(label="A", text="..."),
                Assertion(label="B", text="..."),
            ],
        )

        result = serialize_requirement_summary(req)

        assert result["id"] == "REQ-p00001"
        assert result["title"] == "Test Requirement"
        assert result["level"] == "PRD"
        assert result["status"] == "Active"
        assert result["assertion_count"] == 2
        assert "body" not in result  # Summary doesn't include body


class TestSerializeAssertion:
    """Tests for assertion serialization."""

    def test_serialize_assertion(self):
        """Test serializing an assertion."""
        from elspais.mcp.serializers import serialize_assertion
        from elspais.core.models import Assertion

        assertion = Assertion(
            label="A",
            text="The system SHALL do something.",
            is_placeholder=False,
        )

        result = serialize_assertion(assertion)

        assert result["label"] == "A"
        assert result["text"] == "The system SHALL do something."
        assert result["is_placeholder"] is False


class TestSerializeViolation:
    """Tests for violation serialization."""

    def test_serialize_violation(self):
        """Test serializing a rule violation."""
        from elspais.mcp.serializers import serialize_violation
        from elspais.core.rules import RuleViolation, Severity

        violation = RuleViolation(
            rule_name="format.require_hash",
            requirement_id="REQ-p00001",
            message="Missing hash",
            severity=Severity.ERROR,
            location="spec/prd-core.md:10",
        )

        result = serialize_violation(violation)

        assert result["rule_name"] == "format.require_hash"
        assert result["requirement_id"] == "REQ-p00001"
        assert result["message"] == "Missing hash"
        assert result["severity"] == "error"
        assert result["location"] == "spec/prd-core.md:10"


class TestSerializeContentRule:
    """Tests for content rule serialization."""

    def test_serialize_content_rule(self):
        """Test serializing a content rule."""
        from elspais.mcp.serializers import serialize_content_rule
        from elspais.core.models import ContentRule

        rule = ContentRule(
            file_path=Path("spec/AI-AGENT.md"),
            title="AI Agent Guidelines",
            content="# Guidelines\n\nFollow these rules.",
            type="guidance",
            applies_to=["requirements", "assertions"],
        )

        result = serialize_content_rule(rule)

        assert result["title"] == "AI Agent Guidelines"
        assert result["type"] == "guidance"
        assert result["applies_to"] == ["requirements", "assertions"]
        assert "spec/AI-AGENT.md" in result["file_path"]
        assert "# Guidelines" in result["content"]
