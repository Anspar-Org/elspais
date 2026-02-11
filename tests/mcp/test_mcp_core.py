# Validates REQ-p00060-A, REQ-p00060-B, REQ-p00060-C, REQ-p00060-E
# Validates REQ-o00060-A, REQ-o00060-B, REQ-o00060-C, REQ-o00060-D
# Validates REQ-o00060-E, REQ-o00060-F
# Validates REQ-o00061-A, REQ-o00061-B, REQ-o00061-C, REQ-o00061-D
# Validates REQ-d00060-A, REQ-d00060-B, REQ-d00060-C, REQ-d00060-D, REQ-d00060-E
# Validates REQ-d00061-A, REQ-d00061-B, REQ-d00061-C, REQ-d00061-D, REQ-d00061-E
# Validates REQ-d00062-A, REQ-d00062-B, REQ-d00062-C, REQ-d00062-D
# Validates REQ-d00062-E, REQ-d00062-F
# Validates REQ-d00063-A, REQ-d00063-B, REQ-d00063-C, REQ-d00063-D, REQ-d00063-E
# Validates REQ-d00064-A, REQ-d00064-B, REQ-d00064-C, REQ-d00064-D, REQ-d00064-E
"""Tests for MCP core tools.

Tests REQ-o00060: MCP Core Query Tools
- get_graph_status()
- refresh_graph()
- search()
- get_requirement()
- get_hierarchy()

All tests verify the iterator-only graph API is used correctly.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from elspais.graph import GraphNode, NodeKind
from elspais.graph.builder import TraceGraph

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def sample_graph():
    """Create a sample TraceGraph for testing."""
    graph = TraceGraph(repo_root=Path("/test/repo"))

    # Create PRD requirement with assertions
    prd_node = GraphNode(
        id="REQ-p00001",
        kind=NodeKind.REQUIREMENT,
        label="Platform Security",
    )
    prd_node._content = {
        "level": "PRD",
        "status": "Active",
        "hash": "abc12345",
    }

    # Add assertions
    assertion_a = GraphNode(
        id="REQ-p00001-A",
        kind=NodeKind.ASSERTION,
        label="SHALL encrypt all data at rest",
    )
    assertion_a._content = {"label": "A"}
    prd_node.add_child(assertion_a)

    assertion_b = GraphNode(
        id="REQ-p00001-B",
        kind=NodeKind.ASSERTION,
        label="SHALL use TLS 1.3 for transit",
    )
    assertion_b._content = {"label": "B"}
    prd_node.add_child(assertion_b)

    # Create OPS requirement that implements PRD
    ops_node = GraphNode(
        id="REQ-o00001",
        kind=NodeKind.REQUIREMENT,
        label="Database Encryption",
    )
    ops_node._content = {
        "level": "OPS",
        "status": "Active",
        "hash": "def67890",
    }

    # Create DEV requirement that implements OPS
    dev_node = GraphNode(
        id="REQ-d00001",
        kind=NodeKind.REQUIREMENT,
        label="AES-256 Implementation",
    )
    dev_node._content = {
        "level": "DEV",
        "status": "Draft",
        "hash": "ghi11111",
    }

    # Link the hierarchy: PRD <- OPS <- DEV
    from elspais.graph.relations import EdgeKind

    prd_node.link(ops_node, EdgeKind.IMPLEMENTS)
    ops_node.link(dev_node, EdgeKind.IMPLEMENTS)

    # Build graph
    graph._roots = [prd_node]
    graph._index = {
        "REQ-p00001": prd_node,
        "REQ-p00001-A": assertion_a,
        "REQ-p00001-B": assertion_b,
        "REQ-o00001": ops_node,
        "REQ-d00001": dev_node,
    }

    return graph


@pytest.fixture
def mcp_server(sample_graph):
    """Create MCP server with sample graph."""
    pytest.importorskip("mcp")

    from elspais.mcp.server import create_server

    return create_server(sample_graph)


# ─────────────────────────────────────────────────────────────────────────────
# Test: get_graph_status() - REQ-d00060
# ─────────────────────────────────────────────────────────────────────────────


class TestGetGraphStatus:
    """Tests for get_graph_status() tool."""

    def test_REQ_d00060_A_returns_node_counts_by_kind(self, sample_graph):
        """REQ-d00060-A: Returns node_counts using graph.nodes_by_kind()."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _get_graph_status

        result = _get_graph_status(sample_graph)

        assert "node_counts" in result
        counts = result["node_counts"]
        assert counts.get("requirement") == 3
        assert counts.get("assertion") == 2

    def test_REQ_d00060_D_returns_root_count(self, sample_graph):
        """REQ-d00060-D: Returns root_count using graph.root_count()."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _get_graph_status

        result = _get_graph_status(sample_graph)

        assert "root_count" in result
        assert result["root_count"] == 1

    def test_REQ_d00060_E_no_full_graph_iteration(self, sample_graph):
        """REQ-d00060-E: Does not iterate full graph for counts."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _get_graph_status

        # Patch all_nodes to track if called
        original_all_nodes = sample_graph.all_nodes
        all_nodes_called = []

        def tracked_all_nodes(*args, **kwargs):
            all_nodes_called.append(True)
            return original_all_nodes(*args, **kwargs)

        sample_graph.all_nodes = tracked_all_nodes

        _get_graph_status(sample_graph)

        # all_nodes should not be called for status
        assert len(all_nodes_called) == 0


# ─────────────────────────────────────────────────────────────────────────────
# Test: search() - REQ-d00061
# ─────────────────────────────────────────────────────────────────────────────


class TestSearch:
    """Tests for search() tool."""

    def test_REQ_d00061_A_iterates_nodes_by_kind(self, sample_graph):
        """REQ-d00061-A: Iterates graph.nodes_by_kind(REQUIREMENT)."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _search

        results = _search(sample_graph, query="Security")

        # Should find REQ-p00001 "Platform Security"
        assert len(results) >= 1
        assert any(r["id"] == "REQ-p00001" for r in results)

    def test_REQ_d00061_B_field_parameter_id(self, sample_graph):
        """REQ-d00061-B: Supports field='id' for ID search."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _search

        results = _search(sample_graph, query="p00001", field="id")

        assert len(results) == 1
        assert results[0]["id"] == "REQ-p00001"

    def test_REQ_d00061_B_field_parameter_title(self, sample_graph):
        """REQ-d00061-B: Supports field='title' for title search."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _search

        results = _search(sample_graph, query="Database", field="title")

        assert len(results) == 1
        assert results[0]["id"] == "REQ-o00001"

    def test_REQ_d00061_C_regex_search(self, sample_graph):
        """REQ-d00061-C: Supports regex=True for regex matching."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _search

        results = _search(sample_graph, query="REQ-[pd]00001", field="id", regex=True)

        # Should match REQ-p00001 and REQ-d00001
        assert len(results) == 2
        ids = {r["id"] for r in results}
        assert "REQ-p00001" in ids
        assert "REQ-d00001" in ids

    def test_REQ_d00061_D_returns_summaries(self, sample_graph):
        """REQ-d00061-D: Returns requirement summaries, not full objects."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _search

        results = _search(sample_graph, query="Security")

        assert len(results) >= 1
        result = results[0]
        # Should have summary fields
        assert "id" in result
        assert "title" in result
        assert "level" in result
        assert "status" in result
        # Should NOT have full details like body
        assert "body" not in result
        assert "assertions" not in result


# ─────────────────────────────────────────────────────────────────────────────
# Test: get_requirement() - REQ-d00062
# ─────────────────────────────────────────────────────────────────────────────


class TestGetRequirement:
    """Tests for get_requirement() tool."""

    def test_REQ_d00062_A_uses_find_by_id(self, sample_graph):
        """REQ-d00062-A: Uses graph.find_by_id() for O(1) lookup."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _get_requirement

        # Patch find_by_id to track calls
        original_find = sample_graph.find_by_id
        find_calls = []

        def tracked_find(req_id):
            find_calls.append(req_id)
            return original_find(req_id)

        sample_graph.find_by_id = tracked_find

        _get_requirement(sample_graph, "REQ-p00001")

        assert "REQ-p00001" in find_calls

    def test_REQ_d00062_B_returns_node_fields(self, sample_graph):
        """REQ-d00062-B: Returns id, title, level, status, hash."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _get_requirement

        result = _get_requirement(sample_graph, "REQ-p00001")

        assert result["id"] == "REQ-p00001"
        assert result["title"] == "Platform Security"
        assert result["level"] == "PRD"
        assert result["status"] == "Active"
        assert result["hash"] == "abc12345"

    def test_REQ_d00062_C_returns_assertions(self, sample_graph):
        """REQ-d00062-C: Returns assertions from iter_children()."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _get_requirement

        result = _get_requirement(sample_graph, "REQ-p00001")

        assert "children" in result
        assertions = [c for c in result["children"] if c["kind"] == "assertion"]
        assert len(assertions) == 2

        labels = {a["label"] for a in assertions}
        assert "A" in labels
        assert "B" in labels

    def test_REQ_d00062_D_returns_relationships(self, sample_graph):
        """REQ-d00062-D: Returns relationships from iter_outgoing_edges()."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _get_requirement

        result = _get_requirement(sample_graph, "REQ-p00001")

        assert "children" in result
        # PRD should have OPS as child (kind=="requirement")
        req_children = [c for c in result["children"] if c["kind"] == "requirement"]
        assert any(c["id"] == "REQ-o00001" for c in req_children)

    def test_REQ_d00062_F_returns_error_for_missing(self, sample_graph):
        """REQ-d00062-F: Returns error for non-existent requirements."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _get_requirement

        result = _get_requirement(sample_graph, "REQ-NONEXISTENT")

        assert "error" in result
        assert "not found" in result["error"].lower()


# ─────────────────────────────────────────────────────────────────────────────
# Test: get_hierarchy() - REQ-d00063
# ─────────────────────────────────────────────────────────────────────────────


class TestGetHierarchy:
    """Tests for get_hierarchy() tool."""

    def test_REQ_d00063_A_returns_ancestors(self, sample_graph):
        """REQ-d00063-A: Returns ancestors by walking iter_parents()."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _get_hierarchy

        result = _get_hierarchy(sample_graph, "REQ-d00001")

        assert "ancestors" in result
        ancestors = result["ancestors"]
        # DEV -> OPS -> PRD (two ancestors)
        ancestor_ids = [a["id"] for a in ancestors]
        assert "REQ-o00001" in ancestor_ids
        assert "REQ-p00001" in ancestor_ids

    def test_REQ_d00063_B_returns_children(self, sample_graph):
        """REQ-d00063-B: Returns children from iter_children()."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _get_hierarchy

        result = _get_hierarchy(sample_graph, "REQ-p00001")

        assert "children" in result
        children = result["children"]
        # PRD has OPS as child, plus assertions
        child_ids = [c["id"] for c in children]
        assert "REQ-o00001" in child_ids

    def test_REQ_d00063_D_returns_summaries(self, sample_graph):
        """REQ-d00063-D: Returns node summaries (id, title, level)."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _get_hierarchy

        result = _get_hierarchy(sample_graph, "REQ-o00001")

        # Check ancestors have summary format
        for ancestor in result.get("ancestors", []):
            assert "id" in ancestor
            assert "title" in ancestor
            assert "level" in ancestor
            # Should NOT have full details
            assert "assertions" not in ancestor

    def test_REQ_d00063_E_handles_multiple_parents(self, sample_graph):
        """REQ-d00063-E: Handles DAG structure with multiple parents."""
        pytest.importorskip("mcp")
        # Add a second parent to the OPS node
        from elspais.graph.relations import EdgeKind
        from elspais.mcp.server import _get_hierarchy

        prd2 = GraphNode(
            id="REQ-p00002",
            kind=NodeKind.REQUIREMENT,
            label="Platform Compliance",
        )
        prd2._content = {"level": "PRD", "status": "Active", "hash": "zzz99999"}
        sample_graph._index["REQ-p00002"] = prd2
        sample_graph._roots.append(prd2)

        # Link OPS to second PRD as well
        ops_node = sample_graph.find_by_id("REQ-o00001")
        prd2.link(ops_node, EdgeKind.IMPLEMENTS)

        result = _get_hierarchy(sample_graph, "REQ-o00001")

        # Should have two ancestors (both PRD nodes)
        ancestors = result["ancestors"]
        ancestor_ids = [a["id"] for a in ancestors]
        assert "REQ-p00001" in ancestor_ids
        assert "REQ-p00002" in ancestor_ids


# ─────────────────────────────────────────────────────────────────────────────
# Test: refresh_graph() - REQ-o00060-B
# ─────────────────────────────────────────────────────────────────────────────


class TestRefreshGraph:
    """Tests for refresh_graph() tool."""

    def test_refresh_rebuilds_graph(self, sample_graph):
        """Refresh should rebuild the graph from spec files."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _refresh_graph

        # This is a functional test - verify refresh returns a valid graph
        with patch("elspais.mcp.server.build_graph") as mock_build:
            mock_build.return_value = sample_graph

            result, new_graph = _refresh_graph(Path("/test/repo"))

            mock_build.assert_called_once()
            assert result["success"] is True

    def test_refresh_full_clears_caches(self, sample_graph):
        """Refresh with full=True should clear all caches."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _refresh_graph

        with patch("elspais.mcp.server.build_graph") as mock_build:
            mock_build.return_value = sample_graph

            result, _ = _refresh_graph(Path("/test/repo"), full=True)

            assert result["success"] is True


# ─────────────────────────────────────────────────────────────────────────────
# Test: get_workspace_info() - REQ-o00061-A
# ─────────────────────────────────────────────────────────────────────────────


class TestGetWorkspaceInfo:
    """Tests for get_workspace_info() tool."""

    def test_REQ_o00061_A_returns_repo_path(self, tmp_path):
        """REQ-o00061-A: Returns repository path."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _get_workspace_info

        result = _get_workspace_info(tmp_path)

        assert "repo_path" in result
        assert result["repo_path"] == str(tmp_path)

    def test_REQ_o00061_A_returns_project_name(self, tmp_path):
        """REQ-o00061-A: Returns project name from directory if not in config."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _get_workspace_info

        result = _get_workspace_info(tmp_path)

        assert "project_name" in result
        # Falls back to directory name when no config
        assert result["project_name"] == tmp_path.name

    def test_REQ_o00061_A_returns_config_summary(self, tmp_path):
        """REQ-o00061-A: Returns configuration summary."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _get_workspace_info

        result = _get_workspace_info(tmp_path)

        assert "config_summary" in result
        summary = result["config_summary"]
        assert "prefix" in summary
        assert "spec_directories" in summary
        assert "testing_enabled" in summary

    def test_REQ_o00061_D_reads_from_config_file(self, tmp_path):
        """REQ-o00061-D: Reads configuration from unified config system."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _get_workspace_info

        # Create a config file
        config_content = """
[project]
name = "TestProject"
type = "core"

[patterns]
prefix = "TST"
"""
        config_file = tmp_path / ".elspais.toml"
        config_file.write_text(config_content)

        result = _get_workspace_info(tmp_path)

        assert result["project_name"] == "TestProject"
        assert result["config_file"] == str(config_file)
        assert result["config_summary"]["prefix"] == "TST"
        assert result["config_summary"]["project_type"] == "core"


# ─────────────────────────────────────────────────────────────────────────────
# Test: get_project_summary() - REQ-o00061-B
# ─────────────────────────────────────────────────────────────────────────────


class TestGetProjectSummary:
    """Tests for get_project_summary() tool."""

    def test_REQ_o00061_B_returns_requirements_by_level(self, sample_graph):
        """REQ-o00061-B: Returns requirement counts by level."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _get_project_summary

        result = _get_project_summary(sample_graph, Path("/test/repo"))

        assert "requirements_by_level" in result
        level_counts = result["requirements_by_level"]

        # Check active/all structure from count_by_level
        assert "active" in level_counts
        assert "all" in level_counts

        # Our sample_graph has 1 PRD, 1 OPS, 1 DEV
        assert level_counts["all"]["PRD"] == 1
        assert level_counts["all"]["OPS"] == 1
        assert level_counts["all"]["DEV"] == 1

    def test_REQ_o00061_B_returns_coverage_stats(self, sample_graph):
        """REQ-o00061-B: Returns coverage statistics."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _get_project_summary

        result = _get_project_summary(sample_graph, Path("/test/repo"))

        assert "coverage" in result
        coverage = result["coverage"]
        assert "total" in coverage
        assert "full_coverage" in coverage
        assert "partial_coverage" in coverage
        assert "no_coverage" in coverage

    def test_REQ_o00061_B_returns_change_metrics(self, sample_graph):
        """REQ-o00061-B: Returns change metrics."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _get_project_summary

        result = _get_project_summary(sample_graph, Path("/test/repo"))

        assert "changes" in result
        changes = result["changes"]
        assert "uncommitted" in changes
        assert "branch_changed" in changes

    def test_REQ_o00061_C_uses_aggregate_functions(self, sample_graph):
        """REQ-o00061-C: Uses aggregate functions from annotators module."""
        pytest.importorskip("mcp")
        from elspais.graph.annotators import (
            count_by_coverage,
            count_by_git_status,
            count_by_level,
        )
        from elspais.mcp.server import _get_project_summary

        # Verify all aggregate functions are used
        expected_levels = count_by_level(sample_graph)
        expected_coverage = count_by_coverage(sample_graph)
        expected_git = count_by_git_status(sample_graph)

        result = _get_project_summary(sample_graph, Path("/test/repo"))

        assert result["requirements_by_level"] == expected_levels
        assert result["coverage"] == expected_coverage
        assert result["changes"] == expected_git

    def test_returns_orphan_and_broken_counts(self, sample_graph):
        """Returns orphan and broken reference counts."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _get_project_summary

        result = _get_project_summary(sample_graph, Path("/test/repo"))

        assert "orphan_count" in result
        assert "broken_reference_count" in result
        assert "total_nodes" in result

    def test_coverage_with_annotated_nodes(self, sample_graph):
        """Coverage stats work with annotated coverage metrics."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _get_project_summary

        # Annotate some nodes with coverage
        prd_node = sample_graph.find_by_id("REQ-p00001")
        prd_node.set_metric("coverage_pct", 100)

        ops_node = sample_graph.find_by_id("REQ-o00001")
        ops_node.set_metric("coverage_pct", 50)

        dev_node = sample_graph.find_by_id("REQ-d00001")
        dev_node.set_metric("coverage_pct", 0)

        result = _get_project_summary(sample_graph, Path("/test/repo"))

        coverage = result["coverage"]
        assert coverage["total"] == 3
        assert coverage["full_coverage"] == 1  # PRD at 100%
        assert coverage["partial_coverage"] == 1  # OPS at 50%
        assert coverage["no_coverage"] == 1  # DEV at 0%


class TestRoundTripFidelity:
    """Tests for round-trip fidelity: flat children, line numbers, edge_kind."""

    @pytest.fixture
    def rich_graph(self):
        """Graph with source locations on assertions and sections."""
        from elspais.graph.GraphNode import SourceLocation
        from elspais.graph.relations import EdgeKind

        graph = TraceGraph(repo_root=Path("/test/repo"))

        # PRD requirement
        prd_node = GraphNode(
            id="REQ-p00001",
            kind=NodeKind.REQUIREMENT,
            label="Platform Security",
            source=SourceLocation(path="spec/prd.md", line=10, end_line=30),
        )
        prd_node._content = {
            "level": "PRD",
            "status": "Active",
            "hash": "abc12345",
            "body_text": "Some body text",
        }

        # Assertion A with source location
        assertion_a = GraphNode(
            id="REQ-p00001-A",
            kind=NodeKind.ASSERTION,
            label="SHALL encrypt all data at rest",
            source=SourceLocation(path="spec/prd.md", line=20),
        )
        assertion_a._content = {"label": "A"}

        # Section (REMAINDER) with source location - comes BEFORE assertions
        section_node = GraphNode(
            id="REQ-p00001:section:0",
            kind=NodeKind.REMAINDER,
            label="Rationale",
            source=SourceLocation(path="spec/prd.md", line=14),
        )
        section_node._content = {
            "heading": "Rationale",
            "text": "This is why we need security.",
            "order": 0,
        }

        # Assertion B with source location
        assertion_b = GraphNode(
            id="REQ-p00001-B",
            kind=NodeKind.ASSERTION,
            label="SHALL use TLS 1.3",
            source=SourceLocation(path="spec/prd.md", line=21),
        )
        assertion_b._content = {"label": "B"}

        # Add children in document order (section at line 14, then assertions at 20, 21)
        prd_node.add_child(section_node)
        prd_node.add_child(assertion_a)
        prd_node.add_child(assertion_b)

        # OPS requirement implementing PRD
        ops_node = GraphNode(
            id="REQ-o00001",
            kind=NodeKind.REQUIREMENT,
            label="Database Encryption",
            source=SourceLocation(path="spec/ops.md", line=1),
        )
        ops_node._content = {
            "level": "OPS",
            "status": "Active",
            "hash": "def67890",
        }

        # Link: OPS implements PRD
        prd_node.link(ops_node, EdgeKind.IMPLEMENTS)

        # DEV requirement refining OPS
        dev_node = GraphNode(
            id="REQ-d00001",
            kind=NodeKind.REQUIREMENT,
            label="AES-256 Implementation",
            source=SourceLocation(path="spec/dev.md", line=1),
        )
        dev_node._content = {
            "level": "DEV",
            "status": "Draft",
            "hash": "ghi11111",
        }

        # Link: DEV refines OPS
        ops_node.link(dev_node, EdgeKind.REFINES)

        graph._roots = [prd_node]
        graph._index = {
            "REQ-p00001": prd_node,
            "REQ-p00001-A": assertion_a,
            "REQ-p00001-B": assertion_b,
            "REQ-p00001:section:0": section_node,
            "REQ-o00001": ops_node,
            "REQ-d00001": dev_node,
        }

        return graph

    def test_children_flat_list_with_kind(self, rich_graph):
        """Children should be a single flat list with 'kind' field."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _get_requirement

        result = _get_requirement(rich_graph, "REQ-p00001")

        assert "children" in result
        assert "assertions" not in result
        assert "remainder" not in result

        kinds = [c["kind"] for c in result["children"]]
        assert "assertion" in kinds
        assert "remainder" in kinds

    def test_children_document_order(self, rich_graph):
        """Children should be in document order (by line number)."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _get_requirement

        result = _get_requirement(rich_graph, "REQ-p00001")

        children = result["children"]
        # Filter to assertions and sections (skip requirement children)
        doc_children = [c for c in children if c["kind"] in ("assertion", "remainder")]

        # Section at line 14 should come before assertions at 20, 21
        lines = [c["line"] for c in doc_children]
        assert lines == sorted(lines), f"Children not in document order: {lines}"
        assert doc_children[0]["kind"] == "remainder"
        assert doc_children[0]["line"] == 14

    def test_assertion_children_have_line(self, rich_graph):
        """Assertion children should include line number."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _get_requirement

        result = _get_requirement(rich_graph, "REQ-p00001")

        assertions = [c for c in result["children"] if c["kind"] == "assertion"]
        for a in assertions:
            assert "line" in a
            assert a["line"] is not None

        # Check specific line numbers
        a_node = next(a for a in assertions if a["label"] == "A")
        assert a_node["line"] == 20
        b_node = next(a for a in assertions if a["label"] == "B")
        assert b_node["line"] == 21

    def test_remainder_children_have_line(self, rich_graph):
        """Remainder (section) children should include line number."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _get_requirement

        result = _get_requirement(rich_graph, "REQ-p00001")

        sections = [c for c in result["children"] if c["kind"] == "remainder"]
        assert len(sections) >= 1
        for s in sections:
            assert "line" in s
            assert s["line"] is not None

    def test_parents_include_edge_kind(self, rich_graph):
        """Parent entries should include edge_kind (IMPLEMENTS or REFINES)."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _get_requirement

        # OPS implements PRD - check from OPS perspective
        result = _get_requirement(rich_graph, "REQ-o00001")
        assert len(result["parents"]) == 1
        parent = result["parents"][0]
        assert parent["id"] == "REQ-p00001"
        assert parent["edge_kind"] == "implements"

    def test_parents_edge_kind_refines(self, rich_graph):
        """REFINES edge kind should be exposed on parent."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _get_requirement

        # DEV refines OPS
        result = _get_requirement(rich_graph, "REQ-d00001")
        assert len(result["parents"]) == 1
        parent = result["parents"][0]
        assert parent["id"] == "REQ-o00001"
        assert parent["edge_kind"] == "refines"


# ─────────────────────────────────────────────────────────────────────────────
# Test: get_project_summary() change metrics - CUR-879
# ─────────────────────────────────────────────────────────────────────────────


class TestGetProjectSummaryChanges:
    """Tests for get_project_summary() change metrics (CUR-879)."""

    def test_REQ_CUR879_D_project_summary_includes_change_metrics(self, sample_graph):
        """REQ-CUR879-D: get_project_summary returns non-zero change metrics."""
        pytest.importorskip("mcp")
        from unittest.mock import patch

        from elspais.graph.GraphNode import SourceLocation
        from elspais.mcp.server import _get_project_summary
        from elspais.utilities.git import GitChangeInfo

        for node_id, path in [
            ("REQ-p00001", "spec/prd.md"),
            ("REQ-o00001", "spec/ops.md"),
            ("REQ-d00001", "spec/dev.md"),
        ]:
            node = sample_graph.find_by_id(node_id)
            if node:
                node.source = SourceLocation(path=path, line=1)

        git_info = GitChangeInfo(
            modified_files={"spec/prd.md"},
            branch_changed_files={"spec/prd.md", "spec/ops.md"},
        )

        with patch("elspais.utilities.git.get_git_changes", return_value=git_info):
            result = _get_project_summary(sample_graph, sample_graph.repo_root)

        assert result["changes"]["uncommitted"] >= 1
        assert result["changes"]["branch_changed"] >= 1


# ─────────────────────────────────────────────────────────────────────────────
# Test: get_changed_requirements() - CUR-879
# ─────────────────────────────────────────────────────────────────────────────


class TestGetChangedRequirements:
    """Tests for get_changed_requirements() tool (CUR-879)."""

    def test_REQ_CUR879_E_get_changed_requirements_returns_changed(self, sample_graph):
        """REQ-CUR879-E: get_changed_requirements returns changed requirements."""
        pytest.importorskip("mcp")
        from unittest.mock import patch

        from elspais.graph.GraphNode import SourceLocation
        from elspais.mcp.server import _get_changed_requirements
        from elspais.utilities.git import GitChangeInfo

        for node_id, path in [
            ("REQ-p00001", "spec/prd.md"),
            ("REQ-o00001", "spec/ops.md"),
            ("REQ-d00001", "spec/dev.md"),
        ]:
            node = sample_graph.find_by_id(node_id)
            if node:
                node.source = SourceLocation(path=path, line=1)

        git_info = GitChangeInfo(
            modified_files={"spec/prd.md"},
            branch_changed_files={"spec/prd.md", "spec/ops.md"},
        )

        with patch("elspais.utilities.git.get_git_changes", return_value=git_info):
            result = _get_changed_requirements(sample_graph)

        assert result["count"] >= 2
        ids = {r["id"] for r in result["requirements"]}
        assert "REQ-p00001" in ids  # modified
        assert "REQ-o00001" in ids  # branch changed

        # Check git_state dict is present
        prd_entry = next(r for r in result["requirements"] if r["id"] == "REQ-p00001")
        assert prd_entry["git_state"]["is_modified"] is True
        assert prd_entry["git_state"]["is_uncommitted"] is True
        assert prd_entry["source"] == "spec/prd.md"

        # Check summary is present
        assert "summary" in result
        assert result["summary"]["uncommitted"] >= 1

    def test_REQ_CUR879_F_get_changed_requirements_empty_when_clean(self, sample_graph):
        """REQ-CUR879-F: get_changed_requirements returns empty when no changes."""
        pytest.importorskip("mcp")
        from unittest.mock import patch

        from elspais.mcp.server import _get_changed_requirements
        from elspais.utilities.git import GitChangeInfo

        git_info = GitChangeInfo()  # No changes

        with patch("elspais.utilities.git.get_git_changes", return_value=git_info):
            result = _get_changed_requirements(sample_graph)

        assert result["count"] == 0
        assert result["requirements"] == []
        assert result["summary"]["uncommitted"] == 0
        assert result["summary"]["branch_changed"] == 0
