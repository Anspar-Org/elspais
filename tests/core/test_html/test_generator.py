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

        assert "Requirements Traceability" in result

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


class TestHTMLGeneratorStats:
    """Tests for statistics computation."""

    def test_counts_levels(self, sample_graph):
        """Counts requirements by level."""
        generator = HTMLGenerator(sample_graph)

        result = generator.generate()

        # Should show counts in header
        assert "PRD:" in result
        assert "OPS:" in result
        assert "DEV:" in result

    def test_shows_total_count(self, sample_graph):
        """Shows total requirement count."""
        generator = HTMLGenerator(sample_graph)

        result = generator.generate()

        # Total count should be shown
        assert "CORE:" in result


class TestHTMLGeneratorTreeStructure:
    """Tests for hierarchical tree structure."""

    def test_includes_tree_toggles(self, sample_graph):
        """Includes expand/collapse toggles."""
        generator = HTMLGenerator(sample_graph)

        result = generator.generate()

        assert "tree-toggle" in result

    def test_includes_depth_data(self, sample_graph):
        """Includes depth data for indentation."""
        generator = HTMLGenerator(sample_graph)

        result = generator.generate()

        assert 'data-depth="0"' in result  # Root
        assert 'data-depth="1"' in result  # First level children

    def test_includes_parent_id(self, sample_graph):
        """Includes parent ID for hierarchy."""
        generator = HTMLGenerator(sample_graph)

        result = generator.generate()

        assert "data-parent" in result


class TestHTMLGeneratorCoverage:
    """Tests for coverage indicators."""

    def test_includes_coverage_data(self, sample_graph):
        """Includes coverage status data."""
        generator = HTMLGenerator(sample_graph)

        result = generator.generate()

        assert "data-coverage" in result

    def test_coverage_values(self, sample_graph):
        """Coverage has valid values."""
        generator = HTMLGenerator(sample_graph)

        result = generator.generate()

        # Should have coverage filter options
        assert "none" in result.lower()
        assert "partial" in result.lower()
        assert "full" in result.lower()


class TestHTMLGeneratorFiltering:
    """Tests for filtering features."""

    def test_includes_filter_inputs(self, sample_graph):
        """Includes filter input fields."""
        generator = HTMLGenerator(sample_graph)

        result = generator.generate()

        assert "filter-id" in result
        assert "filter-title" in result

    def test_includes_filter_dropdowns(self, sample_graph):
        """Includes filter dropdown selects."""
        generator = HTMLGenerator(sample_graph)

        result = generator.generate()

        assert "filter-level" in result
        assert "filter-status" in result

    def test_includes_toggle_checkboxes(self, sample_graph):
        """Includes toggle checkboxes."""
        generator = HTMLGenerator(sample_graph)

        result = generator.generate()

        assert "toggle-leaf" in result
        assert "toggle-deprecated" in result


class TestHTMLGeneratorTopics:
    """Tests for topic extraction."""

    def test_extracts_topic_from_path(self, sample_graph):
        """Extracts topic from file path."""
        generator = HTMLGenerator(sample_graph)

        result = generator.generate()

        # Topics should be derived from filenames
        assert "data-topic" in result


class TestHTMLGeneratorViewModes:
    """Tests for view mode support."""

    def test_includes_view_mode_buttons(self, sample_graph):
        """Includes view mode toggle buttons."""
        generator = HTMLGenerator(sample_graph)

        result = generator.generate()

        assert "Flat View" in result
        assert "Hierarchical View" in result

    def test_includes_view_mode_javascript(self, sample_graph):
        """Includes JavaScript for view mode switching."""
        generator = HTMLGenerator(sample_graph)

        result = generator.generate()

        assert "setViewMode" in result


class TestHTMLGeneratorLegend:
    """Tests for legend modal."""

    def test_includes_legend_button(self, sample_graph):
        """Includes legend button."""
        generator = HTMLGenerator(sample_graph)

        result = generator.generate()

        assert "Legend" in result

    def test_includes_legend_modal(self, sample_graph):
        """Includes legend modal content."""
        generator = HTMLGenerator(sample_graph)

        result = generator.generate()

        assert "legend-modal" in result
        assert "Coverage Status" in result


class TestHTMLGeneratorAssertions:
    """Tests for assertion letter badges."""

    def test_assertion_badge_class(self, sample_graph):
        """Has assertion badge CSS class."""
        generator = HTMLGenerator(sample_graph)

        result = generator.generate()

        assert "assertion-badge" in result


class TestHTMLGeneratorGitIntegration:
    """Tests for git change detection integration."""

    def test_includes_git_data_attributes(self, sample_graph):
        """Includes git state data attributes."""
        generator = HTMLGenerator(sample_graph)

        result = generator.generate()

        assert "data-is-changed" in result
        assert "data-is-uncommitted" in result

    def test_includes_git_filter_buttons(self, sample_graph):
        """Includes git filter buttons."""
        generator = HTMLGenerator(sample_graph)

        result = generator.generate()

        assert "Uncommitted" in result
        assert "Changed vs Main" in result
