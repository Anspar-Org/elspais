"""Tests for Graph Serialization module."""

import pytest
from pathlib import Path

from elspais.graph.GraphNode import GraphNode, NodeKind, SourceLocation
from elspais.graph.builder import GraphBuilder, TraceGraph
from elspais.graph.relations import EdgeKind
from elspais.graph.serialize import (
    serialize_node,
    serialize_graph,
    to_markdown,
    to_csv,
)
from tests.core.graph_test_helpers import make_requirement


@pytest.fixture
def sample_graph():
    """Create a sample graph for testing."""
    builder = GraphBuilder(repo_root=Path("/test/repo"))

    # PRD with assertions
    builder.add_parsed_content(make_requirement(
        "REQ-p00001",
        title="Product Requirement",
        level="PRD",
        status="Active",
        source_path="spec/prd.md",
        start_line=10,
        end_line=20,
        hash_value="abc12345",
        assertions=[{"label": "A", "text": "First assertion"}],
    ))

    # OPS implements PRD
    builder.add_parsed_content(make_requirement(
        "REQ-o00001",
        title="Operations Requirement",
        level="OPS",
        status="Active",
        source_path="spec/ops.md",
        start_line=5,
        end_line=15,
        hash_value="def67890",
        implements=["REQ-p00001"],
    ))

    # DEV implements OPS
    builder.add_parsed_content(make_requirement(
        "REQ-d00001",
        title="Dev Requirement",
        level="DEV",
        status="Active",
        source_path="spec/dev.md",
        start_line=1,
        end_line=10,
        hash_value="ghi13579",
        implements=["REQ-o00001"],
    ))

    return builder.build()


class TestSerializeNode:
    """Tests for serialize_node function."""

    def test_serialize_requirement(self, sample_graph):
        """Serializes requirement node to dict."""
        node = sample_graph.find_by_id("REQ-p00001")

        result = serialize_node(node)

        assert result["id"] == "REQ-p00001"
        assert result["kind"] == "REQUIREMENT"
        assert result["label"] == "Product Requirement"
        assert result["content"]["level"] == "PRD"
        assert result["content"]["status"] == "Active"

    def test_serialize_node_with_source(self, sample_graph):
        """Includes source location in serialization."""
        node = sample_graph.find_by_id("REQ-p00001")

        result = serialize_node(node)

        assert "source" in result
        assert result["source"]["path"] == "spec/prd.md"
        assert result["source"]["line"] == 10
        assert result["source"]["end_line"] == 20

    def test_serialize_node_with_children(self, sample_graph):
        """Includes child IDs in serialization."""
        node = sample_graph.find_by_id("REQ-p00001")

        result = serialize_node(node)

        assert "children" in result
        assert "REQ-p00001-A" in result["children"]

    def test_serialize_node_with_metrics(self):
        """Includes metrics in serialization."""
        node = GraphNode(
            id="REQ-test",
            kind=NodeKind.REQUIREMENT,
            label="Test",
        )
        # Set metrics after construction (private field has init=False)
        node._metrics = {"coverage_pct": 75.0, "total_tests": 5}

        result = serialize_node(node)

        assert result["metrics"]["coverage_pct"] == 75.0
        assert result["metrics"]["total_tests"] == 5

    def test_serialize_assertion(self, sample_graph):
        """Serializes assertion node."""
        node = sample_graph.find_by_id("REQ-p00001-A")

        result = serialize_node(node)

        assert result["id"] == "REQ-p00001-A"
        assert result["kind"] == "ASSERTION"
        assert result["content"]["label"] == "A"


class TestSerializeGraph:
    """Tests for serialize_graph function."""

    def test_serialize_graph_includes_nodes(self, sample_graph):
        """Serializes all nodes in graph."""
        result = serialize_graph(sample_graph)

        assert "nodes" in result
        assert len(result["nodes"]) == 4  # 3 reqs + 1 assertion

    def test_serialize_graph_includes_metadata(self, sample_graph):
        """Includes graph metadata."""
        result = serialize_graph(sample_graph)

        assert "metadata" in result
        assert result["metadata"]["node_count"] == 4
        assert result["metadata"]["root_count"] == 1

    def test_serialize_graph_includes_roots(self, sample_graph):
        """Lists root node IDs."""
        result = serialize_graph(sample_graph)

        assert "roots" in result
        assert "REQ-p00001" in result["roots"]


class TestToMarkdown:
    """Tests for to_markdown function."""

    def test_generates_markdown_header(self, sample_graph):
        """Generates markdown with header."""
        result = to_markdown(sample_graph)

        assert "# Traceability Matrix" in result

    def test_generates_requirement_rows(self, sample_graph):
        """Generates rows for requirements."""
        result = to_markdown(sample_graph)

        assert "REQ-p00001" in result
        assert "Product Requirement" in result

    def test_includes_hierarchy(self, sample_graph):
        """Shows hierarchy in markdown."""
        result = to_markdown(sample_graph)

        # Should show hierarchy structure
        assert "REQ-o00001" in result
        assert "REQ-d00001" in result


class TestToCsv:
    """Tests for to_csv function."""

    def test_generates_csv_header(self, sample_graph):
        """Generates CSV with header row."""
        result = to_csv(sample_graph)

        lines = result.strip().split("\n")
        header = lines[0]
        assert "id" in header.lower()
        assert "level" in header.lower()
        assert "title" in header.lower() or "label" in header.lower()

    def test_generates_csv_rows(self, sample_graph):
        """Generates CSV rows for requirements."""
        result = to_csv(sample_graph)

        assert "REQ-p00001" in result
        assert "REQ-o00001" in result
        assert "REQ-d00001" in result

    def test_csv_handles_commas(self):
        """Escapes commas in values."""
        builder = GraphBuilder()
        builder.add_parsed_content(make_requirement(
            "REQ-test",
            title="Title with, comma",
            level="PRD",
            status="Active",
        ))
        graph = builder.build()

        result = to_csv(graph)

        # Comma should be escaped with quotes
        assert '"Title with, comma"' in result or "Title with comma" in result
