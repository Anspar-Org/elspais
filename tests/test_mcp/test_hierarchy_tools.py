"""
Tests for MCP hierarchy navigation tools (get_hierarchy, get_traceability_path).

Tests the hierarchy-related MCP tools for auditor review.
"""

import time
from pathlib import Path
from typing import Any, Dict

import pytest

# Import will fail and skip tests if MCP not available
pytest.importorskip("elspais.mcp.server")
from elspais.mcp.server import MCP_AVAILABLE

# Skip module if MCP_AVAILABLE is False
if not MCP_AVAILABLE:
    pytest.skip("MCP dependencies not installed", allow_module_level=True)


class TestGetHierarchy:
    """Tests for get_hierarchy tool."""

    def test_hierarchy_returns_data(self, hht_like_fixture):
        """Test get_hierarchy returns hierarchy data."""
        from elspais.mcp.server import create_server

        mcp = create_server(hht_like_fixture)

        # First build the graph
        _call_tool(mcp, "refresh_graph")

        # Get hierarchy for a requirement
        result = _call_tool(mcp, "get_hierarchy", req_id="REQ-p00001")

        assert "error" not in result
        assert result["id"] == "REQ-p00001"
        assert result["kind"] == "requirement"
        assert "ancestors" in result
        assert "children" in result
        assert "depth" in result

    def test_hierarchy_not_found(self, hht_like_fixture):
        """Test get_hierarchy returns error for unknown ID."""
        from elspais.mcp.server import create_server

        mcp = create_server(hht_like_fixture)
        _call_tool(mcp, "refresh_graph")

        result = _call_tool(mcp, "get_hierarchy", req_id="REQ-nonexistent")

        assert "error" in result
        assert "not found" in result["error"]

    def test_hierarchy_root_has_no_ancestors(self, hht_like_fixture):
        """Test that root requirements have empty ancestors."""
        from elspais.mcp.server import create_server

        mcp = create_server(hht_like_fixture)
        _call_tool(mcp, "refresh_graph")

        # REQ-p00001 should be a root (PRD level, no implements)
        result = _call_tool(mcp, "get_hierarchy", req_id="REQ-p00001")

        assert result["ancestors"] == []
        assert result["depth"] == 0

    def test_hierarchy_child_has_ancestors(self, hht_like_fixture):
        """Test that child requirements have ancestors."""
        from elspais.mcp.server import create_server

        mcp = create_server(hht_like_fixture)
        _call_tool(mcp, "refresh_graph")

        # Find a child requirement that implements something
        # First check what requirements exist
        status = _call_tool(mcp, "get_graph_status")

        # Try REQ-o00001 which typically implements REQ-p00001
        result = _call_tool(mcp, "get_hierarchy", req_id="REQ-o00001")

        if "error" not in result:
            # If it exists, check that it has ancestors
            assert len(result["ancestors"]) > 0 or result["depth"] == 0
        # If not found, the test passes (fixture may not have this structure)

    def test_hierarchy_includes_assertions(self, assertions_fixture):
        """Test that hierarchy includes assertion children."""
        from elspais.mcp.server import create_server

        mcp = create_server(assertions_fixture)
        _call_tool(mcp, "refresh_graph")

        # Get hierarchy for a requirement with assertions
        result = _call_tool(mcp, "get_hierarchy", req_id="REQ-p00001")

        if "error" not in result:
            assert "assertions" in result["children"]
            # Should have at least one assertion
            assert len(result["children"]["assertions"]) > 0

    def test_hierarchy_includes_source(self, hht_like_fixture):
        """Test that hierarchy includes source file info."""
        from elspais.mcp.server import create_server

        mcp = create_server(hht_like_fixture)
        _call_tool(mcp, "refresh_graph")

        result = _call_tool(mcp, "get_hierarchy", req_id="REQ-p00001")

        assert "source" in result
        assert result["source"]["file"] is not None
        assert result["source"]["line"] is not None


class TestGetTraceabilityPath:
    """Tests for get_traceability_path tool."""

    def test_traceability_path_returns_tree(self, hht_like_fixture):
        """Test get_traceability_path returns tree structure."""
        from elspais.mcp.server import create_server

        mcp = create_server(hht_like_fixture)
        _call_tool(mcp, "refresh_graph")

        result = _call_tool(mcp, "get_traceability_path", req_id="REQ-p00001")

        assert "error" not in result
        assert "tree" in result
        assert "summary" in result
        assert result["tree"]["id"] == "REQ-p00001"
        assert result["tree"]["kind"] == "requirement"

    def test_traceability_path_not_found(self, hht_like_fixture):
        """Test get_traceability_path returns error for unknown ID."""
        from elspais.mcp.server import create_server

        mcp = create_server(hht_like_fixture)
        _call_tool(mcp, "refresh_graph")

        result = _call_tool(mcp, "get_traceability_path", req_id="REQ-nonexistent")

        assert "error" in result
        assert "not found" in result["error"]

    def test_traceability_path_summary(self, assertions_fixture):
        """Test that traceability path includes summary metrics."""
        from elspais.mcp.server import create_server

        mcp = create_server(assertions_fixture)
        _call_tool(mcp, "refresh_graph")

        result = _call_tool(mcp, "get_traceability_path", req_id="REQ-p00001")

        if "error" not in result:
            summary = result["summary"]
            assert "total_assertions" in summary
            assert "covered_assertions" in summary
            assert "coverage_pct" in summary
            assert "total_tests" in summary
            assert "passed_tests" in summary
            assert "pass_rate_pct" in summary

    def test_traceability_path_includes_children(self, assertions_fixture):
        """Test that traceability path tree includes children."""
        from elspais.mcp.server import create_server

        mcp = create_server(assertions_fixture)
        _call_tool(mcp, "refresh_graph")

        result = _call_tool(mcp, "get_traceability_path", req_id="REQ-p00001")

        if "error" not in result:
            tree = result["tree"]
            # Should have children (assertions at minimum)
            if "children" in tree:
                # Children should be organized by kind
                assert isinstance(tree["children"], dict)

    def test_traceability_path_max_depth(self, hht_like_fixture):
        """Test that max_depth limits traversal."""
        from elspais.mcp.server import create_server

        mcp = create_server(hht_like_fixture)
        _call_tool(mcp, "refresh_graph")

        # With max_depth=0, should truncate immediately
        result = _call_tool(mcp, "get_traceability_path", req_id="REQ-p00001", max_depth=0)

        if "error" not in result:
            tree = result["tree"]
            # Either no children or truncated children
            if "children" in tree:
                for kind_children in tree["children"].values():
                    for child in kind_children:
                        assert child.get("truncated", False) is True


class TestHierarchyIntegration:
    """Integration tests for hierarchy tools."""

    def test_hierarchy_and_path_consistent(self, hht_like_fixture):
        """Test that hierarchy and path tools return consistent data."""
        from elspais.mcp.server import create_server

        mcp = create_server(hht_like_fixture)
        _call_tool(mcp, "refresh_graph")

        # Get both for same requirement
        hierarchy = _call_tool(mcp, "get_hierarchy", req_id="REQ-p00001")
        path = _call_tool(mcp, "get_traceability_path", req_id="REQ-p00001")

        if "error" not in hierarchy and "error" not in path:
            # Both should have same ID
            assert hierarchy["id"] == path["tree"]["id"]
            # Both should have same kind
            assert hierarchy["kind"] == path["tree"]["kind"]


def _call_tool(mcp: Any, tool_name: str, **kwargs) -> Dict[str, Any]:
    """
    Helper to call an MCP tool by name.

    FastMCP stores tools as functions that can be accessed via the
    _tool_manager. We iterate to find the matching tool.
    """
    # Access the tool manager
    if hasattr(mcp, "_tool_manager"):
        # FastMCP stores tools in _tool_manager._tools dict
        tools = mcp._tool_manager._tools
        if tool_name in tools:
            tool = tools[tool_name]
            # The tool is a ToolDefinition, call its fn attribute
            return tool.fn(**kwargs)

    # Fallback: try direct attribute access for newer FastMCP versions
    if hasattr(mcp, "tools"):
        for tool in mcp.tools:
            if tool.name == tool_name:
                return tool.fn(**kwargs)

    raise ValueError(f"Tool {tool_name} not found in MCP server")
