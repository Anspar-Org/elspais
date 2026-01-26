"""
Tests for MCP requirement context tool (show_requirement_context).

Tests the context display tool for auditor review.
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


class TestShowRequirementContext:
    """Tests for show_requirement_context tool."""

    def test_context_returns_data(self, hht_like_fixture):
        """Test show_requirement_context returns requirement data."""
        from elspais.mcp.server import create_server

        mcp = create_server(hht_like_fixture)
        _call_tool(mcp, "refresh_graph")

        result = _call_tool(mcp, "show_requirement_context", req_id="REQ-p00001")

        assert "error" not in result
        assert result["id"] == "REQ-p00001"
        assert "title" in result
        assert "level" in result
        assert "status" in result
        assert "body" in result

    def test_context_not_found(self, hht_like_fixture):
        """Test show_requirement_context returns error for unknown ID."""
        from elspais.mcp.server import create_server

        mcp = create_server(hht_like_fixture)
        _call_tool(mcp, "refresh_graph")

        result = _call_tool(mcp, "show_requirement_context", req_id="REQ-nonexistent")

        assert "error" in result
        assert "not found" in result["error"]

    def test_context_includes_source(self, hht_like_fixture):
        """Test that context includes source file info."""
        from elspais.mcp.server import create_server

        mcp = create_server(hht_like_fixture)
        _call_tool(mcp, "refresh_graph")

        result = _call_tool(mcp, "show_requirement_context", req_id="REQ-p00001")

        assert "source" in result
        assert "file" in result["source"]
        assert "line" in result["source"]

    def test_context_includes_assertions(self, assertions_fixture):
        """Test that context includes assertions by default."""
        from elspais.mcp.server import create_server

        mcp = create_server(assertions_fixture)
        _call_tool(mcp, "refresh_graph")

        result = _call_tool(mcp, "show_requirement_context", req_id="REQ-p00001")

        if "error" not in result:
            assert "assertions" in result
            if result["assertions"]:
                assertion = result["assertions"][0]
                assert "label" in assertion
                assert "text" in assertion
                assert "is_placeholder" in assertion

    def test_context_exclude_assertions(self, assertions_fixture):
        """Test that assertions can be excluded."""
        from elspais.mcp.server import create_server

        mcp = create_server(assertions_fixture)
        _call_tool(mcp, "refresh_graph")

        result = _call_tool(mcp, "show_requirement_context",
                           req_id="REQ-p00001",
                           include_assertions=False)

        if "error" not in result:
            # Should not have assertions key (or it should be empty)
            assert "assertions" not in result or result.get("assertions") is None

    def test_context_includes_metrics(self, assertions_fixture):
        """Test that context includes coverage metrics."""
        from elspais.mcp.server import create_server

        mcp = create_server(assertions_fixture)
        _call_tool(mcp, "refresh_graph")

        result = _call_tool(mcp, "show_requirement_context", req_id="REQ-p00001")

        if "error" not in result:
            assert "metrics" in result
            metrics = result["metrics"]
            assert "total_assertions" in metrics
            assert "covered_assertions" in metrics
            assert "coverage_pct" in metrics
            assert "total_tests" in metrics
            assert "pass_rate_pct" in metrics

    def test_context_exclude_implementers(self, hht_like_fixture):
        """Test that implementers are excluded by default."""
        from elspais.mcp.server import create_server

        mcp = create_server(hht_like_fixture)
        _call_tool(mcp, "refresh_graph")

        result = _call_tool(mcp, "show_requirement_context", req_id="REQ-p00001")

        if "error" not in result:
            # Implementers should not be present by default
            assert "implementers" not in result

    def test_context_include_implementers(self, hht_like_fixture):
        """Test that implementers can be included."""
        from elspais.mcp.server import create_server

        mcp = create_server(hht_like_fixture)
        _call_tool(mcp, "refresh_graph")

        result = _call_tool(mcp, "show_requirement_context",
                           req_id="REQ-p00001",
                           include_implementers=True)

        if "error" not in result:
            assert "implementers" in result
            assert isinstance(result["implementers"], list)

    def test_context_includes_implements_refs(self, hht_like_fixture):
        """Test that context includes implements references."""
        from elspais.mcp.server import create_server

        mcp = create_server(hht_like_fixture)
        _call_tool(mcp, "refresh_graph")

        result = _call_tool(mcp, "show_requirement_context", req_id="REQ-p00001")

        if "error" not in result:
            assert "implements" in result
            # PRD level should have empty implements
            assert isinstance(result["implements"], list)

    def test_context_includes_hash(self, hht_like_fixture):
        """Test that context includes requirement hash."""
        from elspais.mcp.server import create_server

        mcp = create_server(hht_like_fixture)
        _call_tool(mcp, "refresh_graph")

        result = _call_tool(mcp, "show_requirement_context", req_id="REQ-p00001")

        if "error" not in result:
            assert "hash" in result


class TestContextIntegration:
    """Integration tests for context tool."""

    def test_context_matches_serialized_requirement(self, hht_like_fixture):
        """Test that context data is consistent with serialized requirement."""
        from elspais.mcp.server import create_server

        mcp = create_server(hht_like_fixture)
        _call_tool(mcp, "refresh_graph")

        # Get context
        context = _call_tool(mcp, "show_requirement_context", req_id="REQ-p00001")

        # Get requirement via get_requirement tool
        req = _call_tool(mcp, "get_requirement", req_id="REQ-p00001")

        if "error" not in context and "error" not in req:
            # Key fields should match
            assert context["id"] == req["id"]
            assert context["title"] == req["title"]
            assert context["level"] == req["level"]
            assert context["status"] == req["status"]


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
