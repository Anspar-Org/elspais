# Validates REQ-p00006-A, REQ-p00006-B
# Validates REQ-p00050-B
# Validates REQ-d00052-A, REQ-d00052-D, REQ-d00052-E, REQ-d00052-F
"""Tests for HTML Generator."""

import pytest

from elspais.html.generator import HTMLGenerator
from tests.core.graph_test_helpers import build_graph, make_journey, make_requirement


@pytest.fixture
def sample_graph():
    """Create a sample graph for testing."""
    return build_graph(
        make_requirement(
            "REQ-p00001",
            level="PRD",
            title="Product Requirement",
            assertions=[{"label": "A", "text": "First assertion"}],
            hash_value="abc12345",
            source_path="spec/prd.md",
        ),
        make_requirement(
            "REQ-o00001",
            level="OPS",
            title="Operations Requirement",
            implements=["REQ-p00001"],
            hash_value="def67890",
            source_path="spec/ops.md",
        ),
        make_requirement(
            "REQ-d00001",
            level="DEV",
            title="Dev Requirement",
            implements=["REQ-o00001"],
            hash_value="ghi13579",
            source_path="spec/dev.md",
        ),
    )


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

    def test_REQ_p00006_A_generate_includes_requirements_in_embedded_json(self, sample_graph):
        """Includes requirement IDs in embedded JSON node-index."""
        generator = HTMLGenerator(sample_graph)

        result = generator.generate(embed_content=True)

        # Requirement IDs are in the embedded node-index JSON, not in table rows
        assert '"REQ-p00001"' in result
        assert '"REQ-o00001"' in result
        assert '"REQ-d00001"' in result
        assert 'id="node-index"' in result

    def test_generate_includes_styles(self, sample_graph):
        """Includes CSS styles."""
        generator = HTMLGenerator(sample_graph)

        result = generator.generate()

        assert "<style>" in result or "css" in result.lower()

    def test_generate_includes_package_version(self, sample_graph):
        """Includes actual elspais package version, not hardcoded 'v1'."""
        from elspais import __version__

        generator = HTMLGenerator(sample_graph)

        result = generator.generate()

        # Should contain the actual version (e.g., "0.27.0"), not just "v1"
        assert f"v{__version__}" in result
        # Verify it's not the old hardcoded value
        assert 'class="version-badge">v1<' not in result

    def test_version_can_be_overridden(self, sample_graph):
        """Custom version can be passed to generator."""
        generator = HTMLGenerator(sample_graph, version="99.99.99")

        result = generator.generate()

        assert "v99.99.99" in result


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

        # Total count should be shown (Core badge shows non-associated count)
        assert "Core:" in result


class TestHTMLGeneratorTreeStructure:
    """Tests for hierarchical tree structure."""

    def test_includes_tree_toggles(self, sample_graph):
        """Includes expand/collapse toggles."""
        generator = HTMLGenerator(sample_graph)

        result = generator.generate()

        assert "tree-toggle" in result

    def test_REQ_p00006_A_includes_depth_data_in_embedded_json(self, sample_graph):
        """Includes depth/hierarchy data in embedded tree-data JSON."""
        generator = HTMLGenerator(sample_graph)

        result = generator.generate(embed_content=True)

        # Depth data is now in the embedded tree-data JSON, not on table <tr> elements
        assert 'id="tree-data"' in result
        assert '"level": "PRD"' in result  # Root level
        assert '"level": "OPS"' in result  # First level children

    def test_includes_parent_id(self, sample_graph):
        """Includes parent ID for hierarchy."""
        generator = HTMLGenerator(sample_graph)

        result = generator.generate()

        assert "data-parent" in result


class TestHTMLGeneratorCoverage:
    """Tests for coverage indicators."""

    def test_REQ_p00006_A_includes_coverage_data_in_embedded_json(self, sample_graph):
        """Includes coverage data in embedded coverage-index JSON."""
        generator = HTMLGenerator(sample_graph)

        result = generator.generate(embed_content=True)

        # Coverage data is now in the embedded coverage-index JSON
        assert 'id="coverage-index"' in result

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

    def test_REQ_d00052_A_includes_toolbar_filter_dropdowns(self, sample_graph):
        """Includes toolbar filter dropdowns for status and coverage."""
        generator = HTMLGenerator(sample_graph)

        result = generator.generate()

        # Table column filters replaced by toolbar dropdowns
        assert "edit-filter-status" in result
        assert "edit-filter-coverage" in result

    def test_REQ_d00052_D_includes_toolbar_git_filter_buttons(self, sample_graph):
        """Includes toolbar git filter buttons."""
        generator = HTMLGenerator(sample_graph)

        result = generator.generate()

        # Level/status column filters replaced by toolbar git filter buttons
        assert "edit-btn-uncommitted" in result
        assert "edit-btn-changed" in result

    def test_REQ_d00052_E_includes_leaf_toggle_checkbox(self, sample_graph):
        """Includes leaf-only toggle checkbox in toolbar."""
        generator = HTMLGenerator(sample_graph)

        result = generator.generate()

        # Only leaf toggle remains; deprecated toggle removed
        assert "edit-toggle-leaf" in result


class TestHTMLGeneratorTopics:
    """Tests for topic extraction."""

    def test_REQ_p00006_A_topic_data_in_embedded_node_index(self, sample_graph):
        """Topic data is available in embedded node-index JSON."""
        generator = HTMLGenerator(sample_graph)

        result = generator.generate(embed_content=True)

        # Topics are now in the embedded node-index JSON, not data-topic attributes
        assert 'id="node-index"' in result
        # Source path info (from which topics are derived) is in the JSON
        assert "spec/prd.md" in result


class TestHTMLGeneratorNavPanel:
    """Tests for nav panel tab support (replaces flat/hierarchical view modes)."""

    def test_REQ_d00052_F_includes_nav_panel_tabs(self, sample_graph):
        """Includes Req and Journeys nav panel tabs."""
        generator = HTMLGenerator(sample_graph)

        result = generator.generate()

        # Flat/Hierarchical view modes replaced by nav-panel tabs
        assert "switchNavTab" in result
        assert 'data-kind="req"' in result
        assert 'data-kind="journey"' in result

    def test_REQ_p00006_A_includes_three_panel_layout(self, sample_graph):
        """Includes 3-panel layout containers."""
        generator = HTMLGenerator(sample_graph)

        result = generator.generate()

        assert "nav-tree-container" in result
        assert "card-stack-panel" in result
        assert "file-viewer-panel" in result or "file-viewer" in result


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

    def test_REQ_d00052_D_git_state_in_embedded_json(self, sample_graph):
        """Git state data is in embedded node-index JSON."""
        generator = HTMLGenerator(sample_graph)

        result = generator.generate(embed_content=True)

        # Git data attributes were on table rows; now in embedded node-index JSON
        assert 'id="node-index"' in result
        # The node-index contains serialized node data including git state
        assert "application/json" in result

    def test_REQ_d00052_D_includes_git_filter_buttons(self, sample_graph):
        """Includes git filter buttons in toolbar."""
        generator = HTMLGenerator(sample_graph)

        result = generator.generate()

        assert "Uncommitted" in result
        assert "Changed" in result  # Was "Changed vs Main", now just "Changed"


class TestHTMLGeneratorJourneyBadges:
    """Tests for journey REQ pill badges in trace view.

    Validates REQ-o00050-C: TraceGraphBuilder SHALL handle all relationship
    linking including addresses.
    """

    def test_REQ_o00050_C_journey_with_addresses_shows_badges(self):
        """Journey with ADDRESSES edges renders ref badges in HTML."""
        graph = build_graph(
            make_requirement("REQ-p00001", level="PRD", title="Product Req"),
            make_journey(
                "JNY-Dev-01",
                title="Dev Workflow",
                actor="Developer",
                goal="Implement feature",
                addresses=["REQ-p00001"],
            ),
        )
        generator = HTMLGenerator(graph)

        result = generator.generate()

        assert "journey-ref-badge" in result
        assert "REQ-p00001" in result
        assert "switchToReqTab" in result

    def test_REQ_o00050_C_journey_without_addresses_no_refs_section(self):
        """Journey without ADDRESSES edges omits refs section in HTML."""
        graph = build_graph(
            make_journey(
                "JNY-Dev-02",
                title="Simple Journey",
                actor="Developer",
                goal="Do something",
            ),
        )
        generator = HTMLGenerator(graph)

        result = generator.generate()

        assert '<span class="journey-ref-badge"' not in result
