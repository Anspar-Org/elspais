"""Tests for MCP keyword search tools.

Tests Phase 4.3: MCP Keyword Integration
- search() tool enhanced with keyword field
- find_by_keywords() MCP tool
- get_all_keywords() MCP tool for keyword discovery
"""

import pytest

from elspais.graph import NodeKind
from elspais.graph.builder import TraceGraph
from elspais.graph.GraphNode import GraphNode

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def keyword_graph(tmp_path):
    """Create a graph with keywords annotated."""
    graph = TraceGraph(repo_root=tmp_path)

    # Requirement 1: Authentication
    req1 = GraphNode(
        id="REQ-p00001",
        kind=NodeKind.REQUIREMENT,
        label="OAuth Authentication",
    )
    req1._content = {"level": "PRD", "status": "Active", "keywords": ["oauth", "authentication"]}
    graph._index["REQ-p00001"] = req1
    graph._roots.append(req1)

    a1 = GraphNode(
        id="REQ-p00001-A",
        kind=NodeKind.ASSERTION,
        label="Support GitHub OAuth provider",
    )
    a1._content = {"label": "A"}
    graph._index["REQ-p00001-A"] = a1
    req1.add_child(a1)

    # Requirement 2: API
    req2 = GraphNode(
        id="REQ-o00001",
        kind=NodeKind.REQUIREMENT,
        label="REST API Endpoints",
    )
    req2._content = {"level": "OPS", "status": "Active", "keywords": ["rest", "api", "endpoints"]}
    graph._index["REQ-o00001"] = req2
    graph._roots.append(req2)

    # Requirement 3: Also about API
    req3 = GraphNode(
        id="REQ-d00001",
        kind=NodeKind.REQUIREMENT,
        label="API Rate Limiting",
    )
    req3._content = {"level": "DEV", "status": "Active", "keywords": ["api", "rate", "limiting"]}
    graph._index["REQ-d00001"] = req3
    graph._roots.append(req3)

    return graph


# ─────────────────────────────────────────────────────────────────────────────
# Test: find_by_keywords MCP Tool
# ─────────────────────────────────────────────────────────────────────────────


class TestFindByKeywordsMCP:
    """Tests for the find_by_keywords MCP tool."""

    def test_finds_requirements_by_keyword(self, keyword_graph):
        """Find requirements containing specified keywords."""
        from elspais.mcp.server import _find_by_keywords

        result = _find_by_keywords(keyword_graph, keywords=["api"])

        assert result["success"] is True
        assert "results" in result
        assert len(result["results"]) == 2  # REQ-o00001 and REQ-d00001

        result_ids = [r["id"] for r in result["results"]]
        assert "REQ-o00001" in result_ids
        assert "REQ-d00001" in result_ids

    def test_filters_by_multiple_keywords(self, keyword_graph):
        """AND logic: only results with ALL keywords."""
        from elspais.mcp.server import _find_by_keywords

        result = _find_by_keywords(keyword_graph, keywords=["api", "rate"])

        assert result["success"] is True
        assert len(result["results"]) == 1  # Only REQ-d00001 has both

        assert result["results"][0]["id"] == "REQ-d00001"

    def test_returns_empty_for_no_match(self, keyword_graph):
        """Returns empty results when no keywords match."""
        from elspais.mcp.server import _find_by_keywords

        result = _find_by_keywords(keyword_graph, keywords=["nonexistent"])

        assert result["success"] is True
        assert result["results"] == []
        assert result["count"] == 0

    def test_case_insensitive_search(self, keyword_graph):
        """Keyword search is case-insensitive."""
        from elspais.mcp.server import _find_by_keywords

        result = _find_by_keywords(keyword_graph, keywords=["API"])

        assert result["success"] is True
        assert len(result["results"]) == 2

    def test_returns_requirement_summaries(self, keyword_graph):
        """Results include requirement summary info."""
        from elspais.mcp.server import _find_by_keywords

        result = _find_by_keywords(keyword_graph, keywords=["oauth"])

        assert result["success"] is True
        assert len(result["results"]) == 1

        req = result["results"][0]
        assert req["id"] == "REQ-p00001"
        assert req["title"] == "OAuth Authentication"
        assert "level" in req
        assert "status" in req


# ─────────────────────────────────────────────────────────────────────────────
# Test: get_all_keywords MCP Tool
# ─────────────────────────────────────────────────────────────────────────────


class TestGetAllKeywordsMCP:
    """Tests for the get_all_keywords MCP tool."""

    def test_returns_all_unique_keywords(self, keyword_graph):
        """Get all unique keywords from the graph."""
        from elspais.mcp.server import _get_all_keywords

        result = _get_all_keywords(keyword_graph)

        assert result["success"] is True
        assert "keywords" in result

        keywords = result["keywords"]
        assert "api" in keywords
        assert "oauth" in keywords
        assert "rate" in keywords
        assert "authentication" in keywords

    def test_returns_sorted_keywords(self, keyword_graph):
        """Keywords are returned in alphabetical order."""
        from elspais.mcp.server import _get_all_keywords

        result = _get_all_keywords(keyword_graph)

        keywords = result["keywords"]
        assert keywords == sorted(keywords)

    def test_returns_count(self, keyword_graph):
        """Result includes total keyword count."""
        from elspais.mcp.server import _get_all_keywords

        result = _get_all_keywords(keyword_graph)

        assert "count" in result
        assert result["count"] == len(result["keywords"])


# ─────────────────────────────────────────────────────────────────────────────
# Test: search() Enhanced with Keywords
# ─────────────────────────────────────────────────────────────────────────────


class TestSearchWithKeywords:
    """Tests for enhanced search() with keyword field."""

    def test_search_by_keywords_field(self, keyword_graph):
        """Search requirements by keywords field."""
        from elspais.mcp.server import _search

        result = _search(keyword_graph, query="api", field="keywords")

        assert len(result) >= 2
        result_ids = [r["id"] for r in result]
        assert "REQ-o00001" in result_ids
        assert "REQ-d00001" in result_ids


# ─────────────────────────────────────────────────────────────────────────────
# Test: MCP Tool Registration
# ─────────────────────────────────────────────────────────────────────────────


class TestMCPKeywordToolRegistration:
    """Tests that keyword tools are registered with MCP."""

    def test_keyword_tools_registered(self, keyword_graph, tmp_path):
        """Keyword tools are registered as MCP tools."""
        pytest.importorskip("mcp")
        pytest.importorskip("mcp.server.fastmcp")

        from elspais.mcp.server import MCP_AVAILABLE, create_server

        if not MCP_AVAILABLE:
            pytest.skip("MCP dependencies not installed")

        server = create_server(graph=keyword_graph, working_dir=tmp_path)

        tool_names = [t.name for t in server._tool_manager._tools.values()]

        assert "find_by_keywords" in tool_names
        assert "get_all_keywords" in tool_names
