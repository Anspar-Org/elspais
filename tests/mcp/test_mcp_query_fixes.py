# Implements: REQ-d00061-B
"""Tests for MCP query bug fixes.

Tests three fixes:
1. Level normalization to config type keys
2. Keywords wiring into build_graph()
3. Body field search support

Validates REQ-d00061-B: search field="body" support.
"""

from __future__ import annotations

from typing import Any

import pytest

from elspais.graph import NodeKind
from elspais.graph.builder import TraceGraph
from elspais.graph.GraphNode import GraphNode

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def graph_with_body():
    """Graph with requirement nodes that have body_text content."""
    graph = TraceGraph()

    req1 = GraphNode(
        id="REQ-p00001",
        kind=NodeKind.REQUIREMENT,
        label="Authentication System",
    )
    req1._content = {
        "level": "prd",
        "status": "Active",
        "hash": "abc12345",
        "body_text": "The system SHALL provide OAuth2 authentication.",
        "keywords": ["authentication", "oauth2", "system"],
    }
    graph._index["REQ-p00001"] = req1
    graph._roots.append(req1)

    req2 = GraphNode(
        id="REQ-o00001",
        kind=NodeKind.REQUIREMENT,
        label="Database Operations",
    )
    req2._content = {
        "level": "ops",
        "status": "Active",
        "hash": "def67890",
        "body_text": "Database operations SHALL support transactions.",
        "keywords": ["database", "operations", "transactions"],
    }
    graph._index["REQ-o00001"] = req2
    graph._roots.append(req2)

    req3 = GraphNode(
        id="REQ-d00001",
        kind=NodeKind.REQUIREMENT,
        label="API Endpoint",
    )
    req3._content = {
        "level": "dev",
        "status": "Deprecated",
        "hash": "ghi11111",
        "body_text": "The API endpoint SHALL handle pagination.",
        "keywords": ["api", "endpoint", "pagination"],
    }
    graph._index["REQ-d00001"] = req3
    graph._roots.append(req3)

    return graph


# ─────────────────────────────────────────────────────────────────────────────
# Fix 1: Level Normalization
# ─────────────────────────────────────────────────────────────────────────────


class TestLevelNormalization:
    """Tests for level normalization to config type keys.

    Validates that the parser normalizes raw level text to canonical
    config type keys (lowercase).
    """

    def test_resolve_level_maps_uppercase(self):
        """resolve_level() maps uppercase 'PRD' to 'prd'."""
        from elspais.utilities.patterns import PatternConfig

        config = PatternConfig.from_dict(
            {
                "types": {
                    "prd": {"id": "p", "name": "PRD", "level": 1},
                    "ops": {"id": "o", "name": "OPS", "level": 2},
                    "dev": {"id": "d", "name": "DEV", "level": 3},
                },
            }
        )
        assert config.resolve_level("PRD") == "prd"
        assert config.resolve_level("OPS") == "ops"
        assert config.resolve_level("DEV") == "dev"

    def test_resolve_level_maps_mixed_case(self):
        """resolve_level() maps mixed case 'Dev' to 'dev'."""
        from elspais.utilities.patterns import PatternConfig

        config = PatternConfig.from_dict(
            {
                "types": {
                    "prd": {"id": "p", "name": "PRD", "level": 1},
                    "ops": {"id": "o", "name": "OPS", "level": 2},
                    "dev": {"id": "d", "name": "DEV", "level": 3},
                },
            }
        )
        assert config.resolve_level("Dev") == "dev"
        assert config.resolve_level("Prd") == "prd"

    def test_resolve_level_unknown_returns_none(self):
        """resolve_level() returns None for unrecognized levels."""
        from elspais.utilities.patterns import PatternConfig

        config = PatternConfig.from_dict(
            {
                "types": {
                    "prd": {"id": "p", "name": "PRD", "level": 1},
                },
            }
        )
        assert config.resolve_level("UNKNOWN") is None
        assert config.resolve_level("xyz") is None

    def test_parser_normalizes_level(self):
        """Parser stores canonical config type key, not raw text."""
        from elspais.graph.parsers.requirement import RequirementParser
        from elspais.utilities.patterns import PatternConfig

        config = PatternConfig.from_dict(
            {
                "types": {
                    "prd": {"id": "p", "name": "PRD", "level": 1},
                    "ops": {"id": "o", "name": "OPS", "level": 2},
                    "dev": {"id": "d", "name": "DEV", "level": 3},
                },
            }
        )
        parser = RequirementParser(config)

        # Simulate parsing a requirement with uppercase level
        text = (
            "## REQ-p00001: Test Requirement\n"
            "**Level**: PRD | **Status**: Active\n"
            "\n"
            "Some body text.\n"
            "\n"
            "*End* *Test Requirement*\n"
        )
        data = parser._parse_requirement("REQ-p00001", "Test Requirement", text)
        assert data["level"] == "prd"

    def test_count_by_level_with_config(self, graph_with_body):
        """count_by_level() uses config-derived keys when config is provided."""
        from elspais.graph.annotators import count_by_level

        config: dict[str, Any] = {
            "patterns": {
                "types": {
                    "prd": {"id": "p"},
                    "ops": {"id": "o"},
                    "dev": {"id": "d"},
                },
            },
        }
        counts = count_by_level(graph_with_body, config=config)

        # Keys should be lowercase (from config)
        assert "prd" in counts["all"]
        assert "ops" in counts["all"]
        assert "dev" in counts["all"]
        assert counts["all"]["prd"] == 1
        assert counts["all"]["ops"] == 1
        assert counts["all"]["dev"] == 1
        # Deprecated excluded from active
        assert counts["active"]["dev"] == 0

    def test_count_by_level_without_config(self, graph_with_body):
        """count_by_level() uses uppercase defaults when no config is provided."""
        from elspais.graph.annotators import count_by_level

        counts = count_by_level(graph_with_body)

        # Default keys are uppercase for backward compat
        assert "PRD" in counts["all"]
        assert "OPS" in counts["all"]
        assert "DEV" in counts["all"]

    def test_group_by_level_with_config(self, graph_with_body):
        """group_by_level() uses config-derived keys when config is provided."""
        from elspais.graph.annotators import group_by_level

        config: dict[str, Any] = {
            "patterns": {
                "types": {
                    "prd": {"id": "p"},
                    "ops": {"id": "o"},
                    "dev": {"id": "d"},
                },
            },
        }
        groups = group_by_level(graph_with_body, config=config)

        assert "prd" in groups
        assert "ops" in groups
        assert "dev" in groups
        assert len(groups["prd"]) == 1
        assert len(groups["ops"]) == 1
        assert len(groups["dev"]) == 1


# ─────────────────────────────────────────────────────────────────────────────
# Fix 2: Keywords Wiring
# ─────────────────────────────────────────────────────────────────────────────


class TestKeywordsWiring:
    """Tests for annotate_keywords() wiring into build_graph().

    Validates that build_graph() automatically populates keyword fields.
    """

    def test_annotate_keywords_populates_fields(self):
        """annotate_keywords() sets keywords on nodes."""
        from elspais.graph.annotators import annotate_keywords

        graph = TraceGraph()
        node = GraphNode(
            id="REQ-p00001",
            kind=NodeKind.REQUIREMENT,
            label="OAuth Authentication System",
        )
        graph._index["REQ-p00001"] = node
        graph._roots.append(node)

        annotate_keywords(graph)

        keywords = node.get_field("keywords", [])
        assert len(keywords) > 0
        assert "oauth" in keywords
        assert "authentication" in keywords
        assert "system" in keywords


# ─────────────────────────────────────────────────────────────────────────────
# Fix 3: Body Field Search
# ─────────────────────────────────────────────────────────────────────────────


class TestBodyFieldSearch:
    """Tests for body field search support.

    Validates REQ-d00061-B: search supports field="body".
    """

    def test_REQ_d00061_B_search_body_field(self, graph_with_body):
        """REQ-d00061-B: Search with field='body' matches body_text content."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _search

        results = _search(graph_with_body, "OAuth2", field="body")
        assert len(results) == 1
        assert results[0]["id"] == "REQ-p00001"

    def test_REQ_d00061_B_search_body_case_insensitive(self, graph_with_body):
        """REQ-d00061-B: Body search is case-insensitive."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _search

        results = _search(graph_with_body, "oauth2", field="body")
        assert len(results) == 1

    def test_REQ_d00061_B_search_body_no_match(self, graph_with_body):
        """REQ-d00061-B: Body search returns empty for non-matching query."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _search

        results = _search(graph_with_body, "nonexistent", field="body")
        assert len(results) == 0

    def test_REQ_d00061_B_search_all_includes_body(self, graph_with_body):
        """REQ-d00061-B: Search with field='all' also matches body_text."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _search

        # "transactions" is only in body_text of REQ-o00001
        results = _search(graph_with_body, "transactions", field="all")
        assert len(results) >= 1
        ids = [r["id"] for r in results]
        assert "REQ-o00001" in ids

    def test_REQ_d00061_B_search_body_regex(self, graph_with_body):
        """REQ-d00061-B: Body search supports regex mode."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _search

        results = _search(graph_with_body, r"SHALL\s+provide", field="body", regex=True)
        assert len(results) == 1
        assert results[0]["id"] == "REQ-p00001"

    def test_REQ_d00061_B_search_body_returns_list(self, graph_with_body):
        """REQ-d00061-B: Body search returns list (per REQ-d00061-D)."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _search

        results = _search(graph_with_body, "SHALL", field="body")
        assert isinstance(results, list)
        # All 3 requirements have SHALL in body
        assert len(results) == 3
