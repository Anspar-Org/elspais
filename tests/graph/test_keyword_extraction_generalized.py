"""Tests for generalized keyword extraction across all node kinds.

Tests for MASTER_PLAN: Generalize Keyword Search API for All Node Kinds
- annotate_keywords() SHALL annotate all node kinds with text content
- find_by_keywords() SHALL accept optional kind parameter
- collect_all_keywords() SHALL accept optional kind parameter
"""

import pytest

from elspais.graph import NodeKind
from elspais.graph.builder import TraceGraph
from elspais.graph.GraphNode import GraphNode

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def multi_kind_graph():
    """Create a graph with multiple node kinds for generalized keyword tests."""
    graph = TraceGraph(repo_root="/tmp/test")

    # REQUIREMENT node
    req_node = GraphNode(
        id="REQ-p00001",
        kind=NodeKind.REQUIREMENT,
        label="User Authentication System",
    )
    req_node._content = {"level": "PRD", "status": "Active"}
    graph._index["REQ-p00001"] = req_node
    graph._roots.append(req_node)

    # ASSERTION child
    assertion_a = GraphNode(
        id="REQ-p00001-A",
        kind=NodeKind.ASSERTION,
        label="The system SHALL support OAuth2 authentication",
    )
    assertion_a._content = {"label": "A"}
    graph._index["REQ-p00001-A"] = assertion_a
    req_node.add_child(assertion_a)

    # USER_JOURNEY node
    journey = GraphNode(
        id="UJ-001",
        kind=NodeKind.USER_JOURNEY,
        label="Login Flow Journey",
    )
    journey._content = {
        "actor": "Developer",
        "goal": "Authenticate via GitHub",
        "description": "User clicks login button and completes OAuth flow",
    }
    graph._index["UJ-001"] = journey
    graph._roots.append(journey)

    # TEST node
    test_node = GraphNode(
        id="TEST-auth-001",
        kind=NodeKind.TEST,
        label="test_oauth_login_success",
    )
    test_node._content = {}
    graph._index["TEST-auth-001"] = test_node
    graph._roots.append(test_node)

    # CODE node
    code_node = GraphNode(
        id="CODE-auth-handler",
        kind=NodeKind.CODE,
        label="Code at src/auth/handler.py:42",
    )
    code_node._content = {}
    graph._index["CODE-auth-handler"] = code_node
    graph._roots.append(code_node)

    # REMAINDER node
    remainder = GraphNode(
        id="REMAINDER-intro",
        kind=NodeKind.REMAINDER,
        label="Introduction text...",
    )
    remainder._content = {
        "raw_text": "This specification defines security requirements for authentication",
    }
    graph._index["REMAINDER-intro"] = remainder
    graph._roots.append(remainder)

    return graph


# ─────────────────────────────────────────────────────────────────────────────
# Test: annotate_keywords() for all node kinds
# ─────────────────────────────────────────────────────────────────────────────


class TestAnnotateKeywordsAllKinds:
    """Tests for annotate_keywords() operating on all node kinds."""

    def test_REQ_d00069_A_annotates_assertion_nodes(self, multi_kind_graph):
        """annotate_keywords() SHALL annotate ASSERTION nodes with keywords."""
        from elspais.graph.annotators import annotate_keywords

        annotate_keywords(multi_kind_graph)

        assertion_node = multi_kind_graph._index["REQ-p00001-A"]
        keywords = assertion_node.get_field("keywords", [])

        # Assertion text: "The system SHALL support OAuth2 authentication"
        assert "oauth2" in keywords
        assert "authentication" in keywords
        assert "support" in keywords

    def test_REQ_d00069_B_annotates_user_journey_nodes(self, multi_kind_graph):
        """annotate_keywords() SHALL annotate USER_JOURNEY nodes from actor/goal/description."""
        from elspais.graph.annotators import annotate_keywords

        annotate_keywords(multi_kind_graph)

        journey = multi_kind_graph._index["UJ-001"]
        keywords = journey.get_field("keywords", [])

        # Actor: "Developer", Goal: "Authenticate via GitHub"
        # Description: "User clicks login button and completes OAuth flow"
        assert "developer" in keywords
        assert "authenticate" in keywords
        assert "github" in keywords
        assert "oauth" in keywords
        assert "login" in keywords

    def test_REQ_d00069_C_annotates_test_nodes(self, multi_kind_graph):
        """annotate_keywords() SHALL annotate TEST nodes from label."""
        from elspais.graph.annotators import annotate_keywords

        annotate_keywords(multi_kind_graph)

        test_node = multi_kind_graph._index["TEST-auth-001"]
        keywords = test_node.get_field("keywords", [])

        # Label: "test_oauth_login_success"
        assert "test_oauth_login_success" in keywords or "oauth" in keywords

    def test_REQ_d00069_D_annotates_remainder_nodes(self, multi_kind_graph):
        """annotate_keywords() SHALL annotate REMAINDER nodes from raw_text."""
        from elspais.graph.annotators import annotate_keywords

        annotate_keywords(multi_kind_graph)

        remainder = multi_kind_graph._index["REMAINDER-intro"]
        keywords = remainder.get_field("keywords", [])

        # raw_text: "This specification defines security requirements for authentication"
        assert "security" in keywords
        assert "requirements" in keywords
        assert "authentication" in keywords

    def test_REQ_d00069_E_annotates_code_nodes(self, multi_kind_graph):
        """annotate_keywords() SHALL annotate CODE nodes from label."""
        from elspais.graph.annotators import annotate_keywords

        annotate_keywords(multi_kind_graph)

        code_node = multi_kind_graph._index["CODE-auth-handler"]
        keywords = code_node.get_field("keywords", [])

        # Label: "Code at src/auth/handler.py:42"
        # Should extract meaningful terms
        assert "code" in keywords or "auth" in keywords or "handler" in keywords


# ─────────────────────────────────────────────────────────────────────────────
# Test: find_by_keywords() with kind parameter
# ─────────────────────────────────────────────────────────────────────────────


class TestFindByKeywordsWithKind:
    """Tests for find_by_keywords() with optional kind parameter."""

    def test_REQ_d00070_A_find_by_keywords_with_kind_filters_by_kind(self, multi_kind_graph):
        """find_by_keywords(kind=X) SHALL only return nodes of that kind."""
        from elspais.graph.annotators import annotate_keywords, find_by_keywords

        annotate_keywords(multi_kind_graph)

        # Search for "authentication" filtered to ASSERTION only
        results = find_by_keywords(multi_kind_graph, ["authentication"], kind=NodeKind.ASSERTION)

        # Should only return ASSERTION nodes
        for node in results:
            assert node.kind == NodeKind.ASSERTION

        # Should find our assertion
        result_ids = [n.id for n in results]
        assert "REQ-p00001-A" in result_ids

    def test_REQ_d00070_B_find_by_keywords_kind_none_searches_all(self, multi_kind_graph):
        """find_by_keywords(kind=None) SHALL search all node kinds."""
        from elspais.graph.annotators import annotate_keywords, find_by_keywords

        annotate_keywords(multi_kind_graph)

        # Search for "authentication" across all nodes
        results = find_by_keywords(multi_kind_graph, ["authentication"], kind=None)

        # Should return nodes from multiple kinds
        result_kinds = {n.kind for n in results}

        # REQUIREMENT, ASSERTION, and REMAINDER all mention authentication
        assert len(result_kinds) >= 2

    def test_REQ_d00070_C_find_by_keywords_default_is_none(self, multi_kind_graph):
        """find_by_keywords() without kind parameter SHALL default to None (all kinds)."""
        from elspais.graph.annotators import annotate_keywords, find_by_keywords

        annotate_keywords(multi_kind_graph)

        # Call without kind parameter - should search all
        results = find_by_keywords(multi_kind_graph, ["authentication"])

        # Should return nodes from multiple kinds
        result_kinds = {n.kind for n in results}
        assert len(result_kinds) >= 2

    def test_REQ_d00070_D_find_assertions_by_keywords(self, multi_kind_graph):
        """find_by_keywords(kind=ASSERTION) enables assertion keyword search."""
        from elspais.graph.annotators import annotate_keywords, find_by_keywords

        annotate_keywords(multi_kind_graph)

        # Search assertions for "oauth2"
        results = find_by_keywords(multi_kind_graph, ["oauth2"], kind=NodeKind.ASSERTION)

        assert len(results) >= 1
        assert all(n.kind == NodeKind.ASSERTION for n in results)


# ─────────────────────────────────────────────────────────────────────────────
# Test: collect_all_keywords() with kind parameter
# ─────────────────────────────────────────────────────────────────────────────


class TestCollectAllKeywordsWithKind:
    """Tests for collect_all_keywords() with optional kind parameter."""

    def test_REQ_d00071_A_collect_keywords_with_kind_filters_by_kind(self, multi_kind_graph):
        """collect_all_keywords(kind=X) SHALL only collect from that kind."""
        from elspais.graph.annotators import annotate_keywords, collect_all_keywords

        annotate_keywords(multi_kind_graph)

        # Collect keywords only from USER_JOURNEY nodes
        keywords = collect_all_keywords(multi_kind_graph, kind=NodeKind.USER_JOURNEY)

        # Should have journey-specific keywords
        assert "developer" in keywords
        assert "github" in keywords

        # Should NOT have keywords only found in other node kinds
        # (unless they coincidentally appear in journey text)

    def test_REQ_d00071_B_collect_keywords_kind_none_collects_all(self, multi_kind_graph):
        """collect_all_keywords(kind=None) SHALL collect from all node kinds."""
        from elspais.graph.annotators import annotate_keywords, collect_all_keywords

        annotate_keywords(multi_kind_graph)

        # Collect from all kinds
        all_keywords = collect_all_keywords(multi_kind_graph, kind=None)

        # Should have keywords from multiple node kinds
        assert "developer" in all_keywords  # From USER_JOURNEY
        assert "security" in all_keywords  # From REMAINDER

    def test_REQ_d00071_C_collect_keywords_default_is_none(self, multi_kind_graph):
        """collect_all_keywords() without kind parameter SHALL default to None."""
        from elspais.graph.annotators import annotate_keywords, collect_all_keywords

        annotate_keywords(multi_kind_graph)

        # Call without kind parameter
        all_keywords = collect_all_keywords(multi_kind_graph)

        # Should collect from all kinds
        assert "developer" in all_keywords  # From USER_JOURNEY
        assert "security" in all_keywords  # From REMAINDER
