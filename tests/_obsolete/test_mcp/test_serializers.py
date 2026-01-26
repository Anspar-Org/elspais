"""
Tests for elspais.mcp.serializers module.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch


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


class TestSerializeNodeFull:
    """Tests for serialize_node_full function."""

    @pytest.fixture
    def mock_context(self, tmp_path):
        """Create a mock WorkspaceContext."""
        from elspais.core.graph import TraceGraph, TraceNode, NodeKind

        context = Mock()
        context.working_dir = tmp_path

        # Create a mock graph with a requirement node
        mock_node = Mock()
        mock_node.source = None
        mock_node.metrics = {
            "total_assertions": 2,
            "covered_assertions": 1,
            "coverage_pct": 50.0,
            "direct_covered": 1,
            "explicit_covered": 0,
            "inferred_covered": 0,
            "total_tests": 3,
            "passed_tests": 2,
            "pass_rate_pct": 66.7,
        }
        mock_node.children = []

        mock_graph = Mock()
        mock_graph.find_by_id.return_value = mock_node
        mock_validation = Mock()

        context.get_graph.return_value = (mock_graph, mock_validation)
        return context

    def test_serialize_node_full_basic(self, mock_context):
        """Test basic node serialization."""
        from elspais.mcp.serializers import serialize_node_full
        from elspais.core.models import Requirement, Assertion

        req = Requirement(
            id="REQ-p00001",
            title="Test Requirement",
            level="PRD",
            status="Active",
            body="This is the requirement body.",
            implements=["REQ-p00000"],
            refines=[],
            assertions=[
                Assertion(label="A", text="The system SHALL do A."),
                Assertion(label="B", text="The system SHALL do B."),
            ],
            hash="abc12345",
            file_path=Path("spec/prd-core.md"),
            line_number=10,
        )

        result = serialize_node_full(req, mock_context, include_full_text=False)

        assert result["id"] == "REQ-p00001"
        assert result["title"] == "Test Requirement"
        assert result["level"] == "PRD"
        assert result["status"] == "Active"
        assert result["implements"] == ["REQ-p00000"]
        assert result["refines"] == []
        assert result["body"] == "This is the requirement body."
        assert result["hash"] == "abc12345"
        assert len(result["assertions"]) == 2
        assert result["assertions"][0]["label"] == "A"
        assert result["metrics"]["coverage_pct"] == 50.0

    def test_serialize_node_full_with_metrics(self, mock_context):
        """Test node serialization includes metrics from graph."""
        from elspais.mcp.serializers import serialize_node_full
        from elspais.core.models import Requirement

        req = Requirement(
            id="REQ-p00001",
            title="Test",
            level="PRD",
            status="Active",
            body="Body",
        )

        result = serialize_node_full(req, mock_context, include_full_text=False)

        assert "metrics" in result
        assert result["metrics"]["total_assertions"] == 2
        assert result["metrics"]["covered_assertions"] == 1
        assert result["metrics"]["coverage_pct"] == 50.0
        assert result["metrics"]["direct_covered"] == 1
        assert result["metrics"]["total_tests"] == 3
        assert result["metrics"]["passed_tests"] == 2

    def test_serialize_node_full_implemented_by(self, mock_context):
        """Test that implemented_by is populated from graph children."""
        from elspais.mcp.serializers import serialize_node_full
        from elspais.core.models import Requirement
        from elspais.core.graph import NodeKind

        req = Requirement(
            id="REQ-p00001",
            title="Test",
            level="PRD",
            status="Active",
            body="Body",
        )

        # Add child requirement nodes
        child1 = Mock()
        child1.kind = NodeKind.REQUIREMENT
        child1.id = "REQ-d00001"

        child2 = Mock()
        child2.kind = NodeKind.REQUIREMENT
        child2.id = "REQ-d00002"

        child_assertion = Mock()
        child_assertion.kind = NodeKind.ASSERTION
        child_assertion.id = "REQ-p00001-A"
        # Set metrics with proper get() behavior for assertions
        child_assertion.metrics = {"_coverage_contributions": []}

        mock_graph, _ = mock_context.get_graph()
        mock_node = mock_graph.find_by_id.return_value
        mock_node.children = [child1, child2, child_assertion]

        result = serialize_node_full(req, mock_context, include_full_text=False)

        assert "implemented_by" in result
        assert set(result["implemented_by"]) == {"REQ-d00001", "REQ-d00002"}

    def test_serialize_node_full_conflict(self, mock_context):
        """Test serialization of conflict entry."""
        from elspais.mcp.serializers import serialize_node_full
        from elspais.core.models import Requirement

        req = Requirement(
            id="REQ-p00001__conflict",
            title="Duplicate",
            level="PRD",
            status="Active",
            body="Body",
            is_conflict=True,
            conflict_with="REQ-p00001",
        )

        result = serialize_node_full(req, mock_context, include_full_text=False)

        assert result["is_conflict"] is True
        assert result["conflict_with"] == "REQ-p00001"

    def test_serialize_node_full_no_graph_node(self, mock_context):
        """Test serialization when node not found in graph."""
        from elspais.mcp.serializers import serialize_node_full
        from elspais.core.models import Requirement

        req = Requirement(
            id="REQ-p00001",
            title="Test",
            level="PRD",
            status="Active",
            body="Body",
            assertions=[],
        )

        # Node not found in graph
        mock_graph, _ = mock_context.get_graph()
        mock_graph.find_by_id.return_value = None

        result = serialize_node_full(req, mock_context, include_full_text=False)

        # Should still work but with default metrics
        assert result["id"] == "REQ-p00001"
        assert result["metrics"]["total_assertions"] == 0
        assert result["metrics"]["coverage_pct"] == 0.0
