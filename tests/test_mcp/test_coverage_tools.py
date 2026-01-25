"""
Tests for MCP coverage query tools (get_coverage_breakdown, list_by_criteria).

Tests the coverage-related MCP tools for auditor review.
"""

from pathlib import Path
from typing import Any, Dict

import pytest

# Import will fail and skip tests if MCP not available
pytest.importorskip("elspais.mcp.server")
from elspais.mcp.server import MCP_AVAILABLE

# Skip module if MCP_AVAILABLE is False
if not MCP_AVAILABLE:
    pytest.skip("MCP dependencies not installed", allow_module_level=True)


class TestGetCoverageBreakdown:
    """Tests for get_coverage_breakdown tool."""

    def test_coverage_breakdown_returns_data(self, assertions_fixture):
        """Test get_coverage_breakdown returns coverage data."""
        from elspais.mcp.server import create_server

        mcp = create_server(assertions_fixture)
        _call_tool(mcp, "refresh_graph")

        result = _call_tool(mcp, "get_coverage_breakdown", req_id="REQ-p00001")

        assert "error" not in result
        assert result["id"] == "REQ-p00001"
        assert "assertions" in result
        assert "gaps" in result
        assert "summary" in result

    def test_coverage_breakdown_not_found(self, hht_like_fixture):
        """Test get_coverage_breakdown returns error for unknown ID."""
        from elspais.mcp.server import create_server

        mcp = create_server(hht_like_fixture)
        _call_tool(mcp, "refresh_graph")

        result = _call_tool(mcp, "get_coverage_breakdown", req_id="REQ-nonexistent")

        assert "error" in result
        assert "not found" in result["error"]

    def test_coverage_breakdown_assertions_structure(self, assertions_fixture):
        """Test that assertions have expected structure."""
        from elspais.mcp.server import create_server

        mcp = create_server(assertions_fixture)
        _call_tool(mcp, "refresh_graph")

        result = _call_tool(mcp, "get_coverage_breakdown", req_id="REQ-p00001")

        if "error" not in result and result["assertions"]:
            assertion = result["assertions"][0]
            assert "id" in assertion
            assert "label" in assertion
            assert "covered" in assertion
            assert "coverage_source" in assertion
            assert "implementing_code" in assertion
            assert "validating_tests" in assertion

    def test_coverage_breakdown_summary_metrics(self, assertions_fixture):
        """Test that summary includes all expected metrics."""
        from elspais.mcp.server import create_server

        mcp = create_server(assertions_fixture)
        _call_tool(mcp, "refresh_graph")

        result = _call_tool(mcp, "get_coverage_breakdown", req_id="REQ-p00001")

        if "error" not in result:
            summary = result["summary"]
            assert "total_assertions" in summary
            assert "covered_assertions" in summary
            assert "coverage_pct" in summary
            assert "direct_covered" in summary
            assert "explicit_covered" in summary
            assert "inferred_covered" in summary

    def test_coverage_breakdown_gaps_uncovered(self, assertions_fixture):
        """Test that gaps list uncovered assertions."""
        from elspais.mcp.server import create_server

        mcp = create_server(assertions_fixture)
        _call_tool(mcp, "refresh_graph")

        result = _call_tool(mcp, "get_coverage_breakdown", req_id="REQ-p00001")

        if "error" not in result:
            # Gaps should be a list of assertion IDs
            assert isinstance(result["gaps"], list)
            # Each gap should match an uncovered assertion
            uncovered = [a["id"] for a in result["assertions"] if not a["covered"]]
            assert set(result["gaps"]) == set(uncovered)


class TestListByCriteria:
    """Tests for list_by_criteria tool."""

    def test_list_no_filters(self, hht_like_fixture):
        """Test list_by_criteria with no filters returns all requirements."""
        from elspais.mcp.server import create_server

        mcp = create_server(hht_like_fixture)
        _call_tool(mcp, "refresh_graph")

        result = _call_tool(mcp, "list_by_criteria")

        assert "error" not in result
        assert "count" in result
        assert "requirements" in result
        assert result["count"] == len(result["requirements"])
        assert result["count"] > 0

    def test_list_filter_by_level(self, hht_like_fixture):
        """Test list_by_criteria with level filter."""
        from elspais.mcp.server import create_server

        mcp = create_server(hht_like_fixture)
        _call_tool(mcp, "refresh_graph")

        result = _call_tool(mcp, "list_by_criteria", level="PRD")

        if result["count"] > 0:
            # All results should be PRD level
            for req in result["requirements"]:
                assert req["level"].upper() == "PRD"

    def test_list_filter_by_status(self, hht_like_fixture):
        """Test list_by_criteria with status filter."""
        from elspais.mcp.server import create_server

        mcp = create_server(hht_like_fixture)
        _call_tool(mcp, "refresh_graph")

        result = _call_tool(mcp, "list_by_criteria", status="Active")

        if result["count"] > 0:
            # All results should be Active status
            for req in result["requirements"]:
                assert req["status"].lower() == "active"

    def test_list_filter_coverage_below(self, hht_like_fixture):
        """Test list_by_criteria with coverage_below filter."""
        from elspais.mcp.server import create_server

        mcp = create_server(hht_like_fixture)
        _call_tool(mcp, "refresh_graph")

        # All requirements without test coverage (0%) should be below 50%
        result = _call_tool(mcp, "list_by_criteria", coverage_below=50.0)

        if result["count"] > 0:
            for req in result["requirements"]:
                assert req["coverage_pct"] < 50.0

    def test_list_filter_has_gaps(self, assertions_fixture):
        """Test list_by_criteria with has_gaps filter."""
        from elspais.mcp.server import create_server

        mcp = create_server(assertions_fixture)
        _call_tool(mcp, "refresh_graph")

        # Find requirements with gaps (uncovered assertions)
        result = _call_tool(mcp, "list_by_criteria", has_gaps=True)

        if result["count"] > 0:
            for req in result["requirements"]:
                # Should have more total than covered
                assert req["total_assertions"] > req["covered_assertions"]

    def test_list_combined_filters(self, hht_like_fixture):
        """Test list_by_criteria with multiple filters."""
        from elspais.mcp.server import create_server

        mcp = create_server(hht_like_fixture)
        _call_tool(mcp, "refresh_graph")

        result = _call_tool(mcp, "list_by_criteria", level="PRD", status="Active")

        if result["count"] > 0:
            for req in result["requirements"]:
                assert req["level"].upper() == "PRD"
                assert req["status"].lower() == "active"

    def test_list_returns_filters_in_response(self, hht_like_fixture):
        """Test that list_by_criteria echoes filters in response."""
        from elspais.mcp.server import create_server

        mcp = create_server(hht_like_fixture)
        _call_tool(mcp, "refresh_graph")

        result = _call_tool(mcp, "list_by_criteria", level="PRD", coverage_below=100.0)

        assert "filters" in result
        assert result["filters"]["level"] == "PRD"
        assert result["filters"]["coverage_below"] == 100.0

    def test_list_includes_source_info(self, hht_like_fixture):
        """Test that list results include source file info."""
        from elspais.mcp.server import create_server

        mcp = create_server(hht_like_fixture)
        _call_tool(mcp, "refresh_graph")

        result = _call_tool(mcp, "list_by_criteria")

        if result["count"] > 0:
            # At least some should have source info
            has_source = any("source" in req for req in result["requirements"])
            assert has_source


class TestCoverageIntegration:
    """Integration tests for coverage tools."""

    def test_breakdown_and_list_consistent(self, assertions_fixture):
        """Test that breakdown and list tools return consistent data."""
        from elspais.mcp.server import create_server

        mcp = create_server(assertions_fixture)
        _call_tool(mcp, "refresh_graph")

        # Get list of all requirements
        list_result = _call_tool(mcp, "list_by_criteria")

        if list_result["count"] > 0:
            # Pick first requirement
            req_id = list_result["requirements"][0]["id"]
            list_coverage = list_result["requirements"][0]["coverage_pct"]

            # Get breakdown for same requirement
            breakdown = _call_tool(mcp, "get_coverage_breakdown", req_id=req_id)

            if "error" not in breakdown:
                # Coverage should match
                assert breakdown["summary"]["coverage_pct"] == list_coverage


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
