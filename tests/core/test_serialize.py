"""Tests for Graph Serialization module."""

import pytest
from pathlib import Path

from elspais.graph.GraphNode import GraphNode, NodeKind, SourceLocation
from elspais.graph.builder import TraceGraph
from elspais.graph.relations import EdgeKind
from elspais.graph.serialize import (
    serialize_node,
    serialize_graph,
    to_markdown,
    to_csv,
)


@pytest.fixture
def sample_graph():
    """Create a sample graph for testing."""
    # Create a simple graph with PRD -> OPS -> DEV hierarchy
    prd = GraphNode(
        id="REQ-p00001",
        kind=NodeKind.REQUIREMENT,
        label="Product Requirement",
        source=SourceLocation(path="spec/prd.md", line=10, end_line=20),
        content={"level": "PRD", "status": "Active", "hash": "abc12345"},
    )

    ops = GraphNode(
        id="REQ-o00001",
        kind=NodeKind.REQUIREMENT,
        label="Operations Requirement",
        source=SourceLocation(path="spec/ops.md", line=5, end_line=15),
        content={"level": "OPS", "status": "Active", "hash": "def67890"},
    )

    dev = GraphNode(
        id="REQ-d00001",
        kind=NodeKind.REQUIREMENT,
        label="Dev Requirement",
        source=SourceLocation(path="spec/dev.md", line=1, end_line=10),
        content={"level": "DEV", "status": "Active", "hash": "ghi13579"},
    )

    # Create assertions
    assertion_a = GraphNode(
        id="REQ-p00001-A",
        kind=NodeKind.ASSERTION,
        label="First assertion",
        content={"label": "A"},
    )
    prd.add_child(assertion_a)

    # Link hierarchy
    prd.link(ops, EdgeKind.IMPLEMENTS)
    ops.link(dev, EdgeKind.IMPLEMENTS)

    # Build graph
    graph = TraceGraph(
        roots=[prd],
        repo_root=Path("/test/repo"),
        _index={
            "REQ-p00001": prd,
            "REQ-o00001": ops,
            "REQ-d00001": dev,
            "REQ-p00001-A": assertion_a,
        },
    )

    return graph


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
            metrics={"coverage_pct": 75.0, "total_tests": 5},
        )

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
        node = GraphNode(
            id="REQ-test",
            kind=NodeKind.REQUIREMENT,
            label='Title with, comma',
            content={"level": "PRD", "status": "Active"},
        )
        graph = TraceGraph(
            roots=[node],
            repo_root=Path.cwd(),
            _index={"REQ-test": node},
        )

        result = to_csv(graph)

        # Comma should be escaped with quotes
        assert '"Title with, comma"' in result or "Title with comma" in result
