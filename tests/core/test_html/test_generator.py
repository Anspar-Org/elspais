"""Tests for HTML Generator."""

import pytest
from pathlib import Path

from elspais.graph.GraphNode import GraphNode, NodeKind, SourceLocation
from elspais.graph.builder import TraceGraph
from elspais.graph.relations import EdgeKind
from elspais.html.generator import HTMLGenerator


@pytest.fixture
def sample_graph():
    """Create a sample graph for testing."""
    # Create a simple graph with PRD -> OPS -> DEV hierarchy
    prd = GraphNode(
        id="REQ-p00001",
        kind=NodeKind.REQUIREMENT,
        label="Product Requirement",
        source=SourceLocation(path="spec/prd.md", line=10, end_line=20),
    )
    prd._content = {"level": "PRD", "status": "Active", "hash": "abc12345"}

    ops = GraphNode(
        id="REQ-o00001",
        kind=NodeKind.REQUIREMENT,
        label="Operations Requirement",
        source=SourceLocation(path="spec/ops.md", line=5, end_line=15),
    )
    ops._content = {"level": "OPS", "status": "Active", "hash": "def67890"}

    dev = GraphNode(
        id="REQ-d00001",
        kind=NodeKind.REQUIREMENT,
        label="Dev Requirement",
        source=SourceLocation(path="spec/dev.md", line=1, end_line=10),
    )
    dev._content = {"level": "DEV", "status": "Active", "hash": "ghi13579"}

    # Create assertions
    assertion_a = GraphNode(
        id="REQ-p00001-A",
        kind=NodeKind.ASSERTION,
        label="First assertion",
    )
    assertion_a._content = {"label": "A"}
    prd.add_child(assertion_a)

    # Link hierarchy
    prd.link(ops, EdgeKind.IMPLEMENTS)
    ops.link(dev, EdgeKind.IMPLEMENTS)

    # Build graph
    graph = TraceGraph(repo_root=Path("/test/repo"))
    graph._roots = [prd]
    graph._index = {
        "REQ-p00001": prd,
        "REQ-o00001": ops,
        "REQ-d00001": dev,
        "REQ-p00001-A": assertion_a,
    }

    return graph


class TestHTMLGeneratorBasic:
    """Basic tests for HTMLGenerator."""

    def test_generate_returns_html(self, sample_graph):
        """Generates HTML string."""
        generator = HTMLGenerator(sample_graph)

        result = generator.generate()

        assert isinstance(result, str)
        assert "<html" in result.lower()
        assert "</html>" in result.lower()

    def test_generate_includes_title(self, sample_graph):
        """Includes title in HTML."""
        generator = HTMLGenerator(sample_graph)

        result = generator.generate()

        assert "Traceability Matrix" in result

    def test_generate_includes_requirements(self, sample_graph):
        """Includes requirement IDs in HTML."""
        generator = HTMLGenerator(sample_graph)

        result = generator.generate()

        assert "REQ-p00001" in result
        assert "REQ-o00001" in result
        assert "REQ-d00001" in result

    def test_generate_includes_styles(self, sample_graph):
        """Includes CSS styles."""
        generator = HTMLGenerator(sample_graph)

        result = generator.generate()

        assert "<style>" in result or "css" in result.lower()


class TestHTMLGeneratorEmbedContent:
    """Tests for embedded content mode."""

    def test_embed_content_includes_json(self, sample_graph):
        """Embedded mode includes JSON data."""
        generator = HTMLGenerator(sample_graph)

        result = generator.generate(embed_content=True)

        # Should have embedded data
        assert "requirement-content" in result or "data-" in result


class TestHTMLGeneratorHierarchy:
    """Tests for hierarchy display."""

    def test_shows_hierarchy_structure(self, sample_graph):
        """Shows requirement hierarchy."""
        generator = HTMLGenerator(sample_graph)

        result = generator.generate()

        # All levels should be present
        assert "PRD" in result or "prd" in result.lower()
        assert "OPS" in result or "ops" in result.lower()
        assert "DEV" in result or "dev" in result.lower()

    def test_shows_requirement_titles(self, sample_graph):
        """Shows requirement titles."""
        generator = HTMLGenerator(sample_graph)

        result = generator.generate()

        assert "Product Requirement" in result
        assert "Operations Requirement" in result
