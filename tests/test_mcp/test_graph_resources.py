"""
Tests for MCP graph resources.

Tests the graph-related MCP resources for read-only graph data access.
"""

import json
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


class TestGraphStatusResource:
    """Tests for graph://status resource."""

    def test_status_no_graph(self, hht_like_fixture):
        """Test status resource when no graph has been built."""
        from elspais.mcp.server import create_server

        mcp = create_server(hht_like_fixture)

        result = _call_resource(mcp, "graph://status")

        assert result["is_stale"] is True
        assert result["has_graph"] is False
        assert result["node_counts"] == {}
        assert result["total_nodes"] == 0
        assert result["last_built"] is None

    def test_status_with_graph(self, hht_like_fixture):
        """Test status resource after graph has been built."""
        from elspais.mcp.server import create_server

        mcp = create_server(hht_like_fixture)

        # Build graph first via tool
        _call_tool(mcp, "refresh_graph")

        result = _call_resource(mcp, "graph://status")

        assert result["is_stale"] is False
        assert result["has_graph"] is True
        assert result["total_nodes"] > 0
        assert "requirement" in result["node_counts"]
        assert result["last_built"] is not None


class TestGraphValidationResource:
    """Tests for graph://validation resource."""

    def test_validation_valid_graph(self, hht_like_fixture):
        """Test validation resource returns validation results."""
        from elspais.mcp.server import create_server

        mcp = create_server(hht_like_fixture)

        result = _call_resource(mcp, "graph://validation")

        assert "is_valid" in result
        assert "errors" in result
        assert "warnings" in result
        assert "summary" in result
        assert "error_count" in result["summary"]
        assert "warning_count" in result["summary"]

    def test_validation_with_broken_links(self, broken_links_fixture):
        """Test validation resource detects broken links."""
        from elspais.mcp.server import create_server

        mcp = create_server(broken_links_fixture)

        result = _call_resource(mcp, "graph://validation")

        # Should have some errors/warnings from broken links
        assert result["summary"]["error_count"] > 0 or result["summary"]["warning_count"] > 0


class TestTraceabilityResource:
    """Tests for traceability://{req_id} resource."""

    def test_traceability_basic(self, hht_like_fixture):
        """Test traceability resource returns tree structure."""
        from elspais.mcp.server import create_server

        mcp = create_server(hht_like_fixture)

        # First build the graph
        _call_tool(mcp, "refresh_graph")

        # Get traceability for a known requirement
        result = _call_resource(mcp, "traceability://REQ-p00001")

        assert "tree" in result
        assert "summary" in result
        assert result["tree"]["id"] == "REQ-p00001"
        assert result["tree"]["kind"] == "requirement"

    def test_traceability_not_found(self, hht_like_fixture):
        """Test traceability resource handles missing requirement."""
        from elspais.mcp.server import create_server

        mcp = create_server(hht_like_fixture)
        _call_tool(mcp, "refresh_graph")

        result = _call_resource(mcp, "traceability://REQ-nonexistent")

        assert "error" in result
        assert "not found" in result["error"]

    def test_traceability_includes_summary(self, assertions_fixture):
        """Test traceability resource includes summary metrics."""
        from elspais.mcp.server import create_server

        mcp = create_server(assertions_fixture)
        _call_tool(mcp, "refresh_graph")

        # Use a requirement ID from assertions fixture
        result = _call_resource(mcp, "traceability://REQ-p00001")

        assert "summary" in result
        assert "total_assertions" in result["summary"]
        assert "covered_assertions" in result["summary"]
        assert "coverage_pct" in result["summary"]


class TestCoverageResource:
    """Tests for coverage://{req_id} resource."""

    def test_coverage_basic(self, hht_like_fixture):
        """Test coverage resource returns coverage breakdown."""
        from elspais.mcp.server import create_server

        mcp = create_server(hht_like_fixture)
        _call_tool(mcp, "refresh_graph")

        result = _call_resource(mcp, "coverage://REQ-p00001")

        assert "id" in result
        assert "label" in result
        assert "assertions" in result
        assert "gaps" in result
        assert "summary" in result
        assert result["id"] == "REQ-p00001"

    def test_coverage_not_found(self, hht_like_fixture):
        """Test coverage resource handles missing requirement."""
        from elspais.mcp.server import create_server

        mcp = create_server(hht_like_fixture)
        _call_tool(mcp, "refresh_graph")

        result = _call_resource(mcp, "coverage://REQ-nonexistent")

        assert "error" in result
        assert "not found" in result["error"]

    def test_coverage_assertion_details(self, assertions_fixture):
        """Test coverage resource includes assertion-level details."""
        from elspais.mcp.server import create_server

        mcp = create_server(assertions_fixture)
        _call_tool(mcp, "refresh_graph")

        result = _call_resource(mcp, "coverage://REQ-p00001")

        # Check assertion-level info
        if result["assertions"]:
            assertion = result["assertions"][0]
            assert "id" in assertion
            assert "label" in assertion
            assert "covered" in assertion
            assert "implementing_code" in assertion
            assert "validating_tests" in assertion


class TestHierarchyAncestorsResource:
    """Tests for hierarchy://{req_id}/ancestors resource."""

    def test_ancestors_basic(self, hht_like_fixture):
        """Test ancestors resource returns ancestor chain."""
        from elspais.mcp.server import create_server

        mcp = create_server(hht_like_fixture)
        _call_tool(mcp, "refresh_graph")

        result = _call_resource(mcp, "hierarchy://REQ-o00001/ancestors")

        assert "id" in result
        assert "depth" in result
        assert "ancestor_count" in result
        assert "ancestors" in result
        assert result["id"] == "REQ-o00001"

    def test_ancestors_not_found(self, hht_like_fixture):
        """Test ancestors resource handles missing requirement."""
        from elspais.mcp.server import create_server

        mcp = create_server(hht_like_fixture)
        _call_tool(mcp, "refresh_graph")

        result = _call_resource(mcp, "hierarchy://REQ-nonexistent/ancestors")

        assert "error" in result
        assert "not found" in result["error"]

    def test_ancestors_root_has_none(self, hht_like_fixture):
        """Test root requirement has no ancestors."""
        from elspais.mcp.server import create_server

        mcp = create_server(hht_like_fixture)
        _call_tool(mcp, "refresh_graph")

        # REQ-p00001 is a root PRD requirement
        result = _call_resource(mcp, "hierarchy://REQ-p00001/ancestors")

        assert result["ancestor_count"] == 0
        assert result["ancestors"] == []


class TestHierarchyDescendantsResource:
    """Tests for hierarchy://{req_id}/descendants resource."""

    def test_descendants_basic(self, hht_like_fixture):
        """Test descendants resource returns all descendants."""
        from elspais.mcp.server import create_server

        mcp = create_server(hht_like_fixture)
        _call_tool(mcp, "refresh_graph")

        result = _call_resource(mcp, "hierarchy://REQ-p00001/descendants")

        assert "id" in result
        assert "descendant_count" in result
        assert "counts_by_kind" in result
        assert "descendants" in result
        assert result["id"] == "REQ-p00001"

    def test_descendants_not_found(self, hht_like_fixture):
        """Test descendants resource handles missing requirement."""
        from elspais.mcp.server import create_server

        mcp = create_server(hht_like_fixture)
        _call_tool(mcp, "refresh_graph")

        result = _call_resource(mcp, "hierarchy://REQ-nonexistent/descendants")

        assert "error" in result
        assert "not found" in result["error"]

    def test_descendants_includes_assertions(self, assertions_fixture):
        """Test descendants includes assertion nodes."""
        from elspais.mcp.server import create_server

        mcp = create_server(assertions_fixture)
        _call_tool(mcp, "refresh_graph")

        result = _call_resource(mcp, "hierarchy://REQ-p00001/descendants")

        # Should have assertion nodes in counts
        if result["counts_by_kind"]:
            assert "assertion" in result["counts_by_kind"]

    def test_descendants_structure(self, hht_like_fixture):
        """Test descendants have correct structure."""
        from elspais.mcp.server import create_server

        mcp = create_server(hht_like_fixture)
        _call_tool(mcp, "refresh_graph")

        result = _call_resource(mcp, "hierarchy://REQ-p00001/descendants")

        if result["descendants"]:
            descendant = result["descendants"][0]
            assert "id" in descendant
            assert "kind" in descendant
            assert "label" in descendant
            assert "parent" in descendant


def _call_tool(mcp: Any, tool_name: str, **kwargs) -> Dict[str, Any]:
    """
    Helper to call an MCP tool by name.
    """
    if hasattr(mcp, "_tool_manager"):
        tools = mcp._tool_manager._tools
        if tool_name in tools:
            tool = tools[tool_name]
            return tool.fn(**kwargs)

    if hasattr(mcp, "tools"):
        for tool in mcp.tools:
            if tool.name == tool_name:
                return tool.fn(**kwargs)

    raise ValueError(f"Tool {tool_name} not found in MCP server")


def _call_resource(mcp: Any, uri: str) -> Dict[str, Any]:
    """
    Helper to call an MCP resource by URI.

    FastMCP stores static resources in _resource_manager._resources dict
    and parameterized resources in _resource_manager._templates dict.
    """
    import re

    # Access the resource manager
    if hasattr(mcp, "_resource_manager"):
        # Try exact match in static resources first
        resources = mcp._resource_manager._resources
        if uri in resources:
            resource = resources[uri]
            result_str = resource.fn()
            return json.loads(result_str)

        # Try pattern matching in templates for parameterized URIs
        templates = mcp._resource_manager._templates
        for pattern, template in templates.items():
            # Convert pattern to regex for matching
            # e.g., "traceability://{req_id}" -> match "traceability://REQ-p00001"
            if "{" in pattern:
                # Extract parameter names
                param_names = re.findall(r"\{(\w+)\}", pattern)
                # Convert pattern to regex
                regex_pattern = re.escape(pattern)
                for param_name in param_names:
                    regex_pattern = regex_pattern.replace(
                        re.escape("{" + param_name + "}"), r"([^/]+)"
                    )
                regex_pattern = "^" + regex_pattern + "$"

                match = re.match(regex_pattern, uri)
                if match:
                    # Extract parameter values
                    kwargs = dict(zip(param_names, match.groups()))
                    result_str = template.fn(**kwargs)
                    return json.loads(result_str)

    raise ValueError(f"Resource {uri} not found in MCP server")
