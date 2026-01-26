"""
Tests for MCP graph tools (get_graph_status, refresh_graph).

Tests the graph-related MCP tools for status checking and refresh.
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


class TestGetGraphStatus:
    """Tests for get_graph_status tool."""

    def test_status_no_graph(self, hht_like_fixture):
        """Test status when no graph has been built."""
        from elspais.mcp.server import create_server

        mcp = create_server(hht_like_fixture)

        # Find and call the tool
        result = _call_tool(mcp, "get_graph_status")

        assert result["is_stale"] is True
        assert result["has_graph"] is False
        assert result["node_counts"] == {}
        assert result["total_nodes"] == 0
        assert result["last_built"] is None

    def test_status_with_graph(self, hht_like_fixture):
        """Test status after graph has been built."""
        from elspais.mcp.server import create_server

        mcp = create_server(hht_like_fixture)

        # First build the graph via refresh
        _call_tool(mcp, "refresh_graph")

        # Now check status
        result = _call_tool(mcp, "get_graph_status")

        assert result["is_stale"] is False
        assert result["has_graph"] is True
        assert result["total_nodes"] > 0
        assert "requirement" in result["node_counts"]
        assert result["last_built"] is not None

    def test_status_stale_files(self, tmp_path):
        """Test status reports stale files correctly."""
        from elspais.mcp.server import create_server

        # Create minimal project
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        config_file = tmp_path / ".elspais.toml"
        config_file.write_text("""
[project]
name = "test"
""")

        req_file = spec_dir / "requirements.md"
        req_file.write_text("""
# REQ-p00001: Test Requirement

**Level**: PRD | **Status**: Active

The system SHALL work.

*End* *Test Requirement* | **Hash**: a1b2c3d4
""")

        mcp = create_server(tmp_path)

        # Build graph
        _call_tool(mcp, "refresh_graph")

        # Modify file
        time.sleep(0.01)
        req_file.write_text("""
# REQ-p00001: Modified Requirement

**Level**: PRD | **Status**: Active

Modified text.

*End* *Modified Requirement* | **Hash**: d4c3b2a1
""")

        # Check status
        result = _call_tool(mcp, "get_graph_status")

        assert result["is_stale"] is True
        assert len(result["stale_files"]) == 1
        assert "requirements.md" in result["stale_files"][0]


class TestRefreshGraph:
    """Tests for refresh_graph tool."""

    def test_refresh_builds_graph(self, hht_like_fixture):
        """Test refresh creates the graph."""
        from elspais.mcp.server import create_server

        mcp = create_server(hht_like_fixture)

        result = _call_tool(mcp, "refresh_graph")

        assert result["refreshed"] is True
        assert result["total_nodes"] > 0
        assert "requirement" in result["node_counts"]
        assert result["validation"]["is_valid"] is not None
        assert result["last_built"] is not None

    def test_refresh_returns_validation(self, hht_like_fixture):
        """Test refresh returns validation info."""
        from elspais.mcp.server import create_server

        mcp = create_server(hht_like_fixture)

        result = _call_tool(mcp, "refresh_graph")

        assert "validation" in result
        assert "is_valid" in result["validation"]
        assert "error_count" in result["validation"]
        assert "warning_count" in result["validation"]

    def test_refresh_force_rebuilds(self, hht_like_fixture):
        """Test refresh with full=True forces rebuild."""
        from elspais.mcp.server import create_server

        mcp = create_server(hht_like_fixture)

        # First build
        result1 = _call_tool(mcp, "refresh_graph")
        built1 = result1["last_built"]

        # Wait a bit
        time.sleep(0.01)

        # Force rebuild
        result2 = _call_tool(mcp, "refresh_graph", full=True)
        built2 = result2["last_built"]

        # Should have different timestamps
        assert built2 > built1

    def test_refresh_detects_staleness(self, tmp_path):
        """Test refresh correctly reports was_stale."""
        from elspais.mcp.server import create_server

        # Create minimal project
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        config_file = tmp_path / ".elspais.toml"
        config_file.write_text("""
[project]
name = "test"
""")

        req_file = spec_dir / "requirements.md"
        req_file.write_text("""
# REQ-p00001: Test Requirement

**Level**: PRD | **Status**: Active

The system SHALL work.

*End* *Test Requirement* | **Hash**: a1b2c3d4
""")

        mcp = create_server(tmp_path)

        # First build - was_stale should be True (no graph yet)
        result1 = _call_tool(mcp, "refresh_graph")
        assert result1["was_stale"] is True

        # Second call without changes - was_stale should be False
        result2 = _call_tool(mcp, "refresh_graph")
        assert result2["was_stale"] is False

        # Modify file and refresh
        time.sleep(0.01)
        req_file.write_text("""
# REQ-p00001: Modified

**Level**: PRD | **Status**: Active

Modified text.

*End* *Modified* | **Hash**: d4c3b2a1
""")

        result3 = _call_tool(mcp, "refresh_graph")
        assert result3["was_stale"] is True


class TestGraphNodeCounts:
    """Tests for node count accuracy in graph tools."""

    def test_node_counts_include_assertions(self, assertions_fixture):
        """Test that node counts include assertion nodes."""
        from elspais.mcp.server import create_server

        mcp = create_server(assertions_fixture)

        result = _call_tool(mcp, "refresh_graph")

        assert "assertion" in result["node_counts"]
        assert result["node_counts"]["assertion"] > 0


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
