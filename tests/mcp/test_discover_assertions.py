# Verifies: REQ-o00065
"""Tests for _discover_assertions() helper in the MCP server.

Validates REQ-o00065: Suggestion engine — assertion-level search and discovery.
"""

from pathlib import Path

import pytest

from elspais.config import ConfigLoader
from elspais.graph import GraphNode, NodeKind
from elspais.graph.builder import TraceGraph
from elspais.graph.federated import FederatedGraph
from elspais.graph.relations import Edge, EdgeKind
from elspais.mcp.server import _discover_assertions

# ─────────────────────────────────────────────────────────────────────────────
# Helpers (reused from test_discover_requirements.py)
# ─────────────────────────────────────────────────────────────────────────────


def _make_req(req_id: str, label: str, level: str, status: str = "Active") -> GraphNode:
    """Create a REQUIREMENT node with standard content fields."""
    node = GraphNode(id=req_id, kind=NodeKind.REQUIREMENT, label=label)
    node._content = {"level": level, "status": status, "hash": f"h_{req_id}"}
    return node


def _make_assertion(assertion_id: str, label_field: str, text: str) -> GraphNode:
    """Create an ASSERTION node with label field and text (get_label)."""
    node = GraphNode(id=assertion_id, kind=NodeKind.ASSERTION, label=text)
    node.set_field("label", label_field)
    return node


def _add_implements_edge(child: GraphNode, parent: GraphNode) -> None:
    """Set up both tree structure and implements edge."""
    parent.link(child, EdgeKind.STRUCTURES)
    edge = Edge(source=child, target=parent, kind=EdgeKind.IMPLEMENTS)
    child._outgoing_edges.append(edge)
    parent._incoming_edges.append(edge)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


def _wrap_federated(graph: TraceGraph) -> FederatedGraph:
    """Wrap a TraceGraph in a FederatedGraph for the MCP helpers."""
    config = ConfigLoader.from_dict({})
    return FederatedGraph.from_single(graph, config, Path("/test/repo"))


@pytest.fixture
def assertion_graph():
    """Graph with assertions on multiple requirements for discover_assertions testing.

    Structure:

    PRD-root (level=PRD, title="Platform Requirements")
      +-- OPS-auth (level=OPS, title="Auth Module") [implements PRD-root]
      |   assertions:
      |     OPS-auth-A: "SHALL authenticate users via OAuth"
      |     OPS-auth-B: "SHALL support MFA tokens"
      |   +-- DEV-login (level=DEV, title="Auth Login Endpoint") [implements OPS-auth]
      |       assertions:
      |         DEV-login-A: "SHALL validate OAuth tokens on every request"
      +-- OPS-data (level=OPS, title="Data Processing") [implements PRD-root]
          assertions:
            OPS-data-A: "SHALL process records in batch mode"
            OPS-data-B: "SHALL log all pipeline errors"
          +-- DEV-pipeline (level=DEV, title="Pipeline Runner") [implements OPS-data]
    """
    graph = TraceGraph(repo_root=Path("/test/repo"))

    # Requirements
    prd_root = _make_req("PRD-root", "Platform Requirements", "PRD")
    ops_auth = _make_req("OPS-auth", "Auth Module", "OPS")
    ops_data = _make_req("OPS-data", "Data Processing", "OPS")
    dev_login = _make_req("DEV-login", "Auth Login Endpoint", "DEV")
    dev_pipeline = _make_req("DEV-pipeline", "Pipeline Runner", "DEV")

    # Assertions on OPS-auth
    auth_a = _make_assertion("OPS-auth-A", "A", "SHALL authenticate users via OAuth")
    auth_b = _make_assertion("OPS-auth-B", "B", "SHALL support MFA tokens")

    # Assertions on DEV-login
    login_a = _make_assertion("DEV-login-A", "A", "SHALL validate OAuth tokens on every request")

    # Assertions on OPS-data
    data_a = _make_assertion("OPS-data-A", "A", "SHALL process records in batch mode")
    data_b = _make_assertion("OPS-data-B", "B", "SHALL log all pipeline errors")

    # Build hierarchy
    _add_implements_edge(ops_auth, prd_root)
    _add_implements_edge(ops_data, prd_root)
    _add_implements_edge(dev_login, ops_auth)
    _add_implements_edge(dev_pipeline, ops_data)

    # Attach assertions
    ops_auth.link(auth_a, EdgeKind.STRUCTURES)
    ops_auth.link(auth_b, EdgeKind.STRUCTURES)
    dev_login.link(login_a, EdgeKind.STRUCTURES)
    ops_data.link(data_a, EdgeKind.STRUCTURES)
    ops_data.link(data_b, EdgeKind.STRUCTURES)

    graph._roots = [prd_root]
    graph._index = {
        "PRD-root": prd_root,
        "OPS-auth": ops_auth,
        "OPS-data": ops_data,
        "DEV-login": dev_login,
        "DEV-pipeline": dev_pipeline,
        "OPS-auth-A": auth_a,
        "OPS-auth-B": auth_b,
        "DEV-login-A": login_a,
        "OPS-data-A": data_a,
        "OPS-data-B": data_b,
    }
    return _wrap_federated(graph)


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestDiscoverAssertionsGlobal:
    """Tests for _discover_assertions() with empty scope_id (global search)."""

    def test_global_search_returns_assertions_from_matching_requirements(self, assertion_graph):
        """Global search for 'OAuth' returns assertions from requirements
        whose title or assertion text matches."""
        result = _discover_assertions(assertion_graph, "OAuth")

        assert "error" not in result
        assert "assertions" in result
        assert "stats" in result
        returned_ids = {a["id"] for a in result["assertions"]}
        # OPS-auth matches via assertion text ("OAuth"), DEV-login matches
        # via assertion text ("OAuth tokens"). Both contribute all assertions.
        assert "OPS-auth-A" in returned_ids
        assert "OPS-auth-B" in returned_ids
        assert "DEV-login-A" in returned_ids
        assert result["stats"]["assertions_returned"] == len(result["assertions"])
        assert result["stats"]["requirements_matched"] > 0

    def test_direct_match_assertions_flagged_and_scored_higher(self, assertion_graph):
        """Assertions whose text directly matched the query have direct_match=True
        and higher score than sibling assertions that only inherited relevance."""
        result = _discover_assertions(assertion_graph, "OAuth")

        assertions_by_id = {a["id"]: a for a in result["assertions"]}
        # OPS-auth-A text contains "OAuth" => direct_match=True
        assert assertions_by_id["OPS-auth-A"]["direct_match"] is True
        # OPS-auth-B text is "SHALL support MFA tokens" => no "OAuth" => direct_match=False
        assert assertions_by_id["OPS-auth-B"]["direct_match"] is False
        # Direct match should have higher score than sibling
        assert assertions_by_id["OPS-auth-A"]["score"] > assertions_by_id["OPS-auth-B"]["score"]

    def test_all_assertions_from_matching_requirement_returned(self, assertion_graph):
        """All assertions from a matching requirement are returned, not just
        the ones that directly matched the query text."""
        result = _discover_assertions(assertion_graph, "OAuth")

        # OPS-auth matched via assertion "OAuth". Both OPS-auth-A and OPS-auth-B
        # should be in results even though only A mentions "OAuth".
        returned_ids = {a["id"] for a in result["assertions"]}
        assert "OPS-auth-A" in returned_ids
        assert "OPS-auth-B" in returned_ids

    def test_assertion_entry_has_required_fields(self, assertion_graph):
        """Each assertion entry has all required fields."""
        result = _discover_assertions(assertion_graph, "OAuth")

        assert len(result["assertions"]) > 0
        for entry in result["assertions"]:
            assert "id" in entry
            assert "label" in entry
            assert "text" in entry
            assert "requirement_id" in entry
            assert "requirement_title" in entry
            assert "level" in entry
            assert "score" in entry
            assert "direct_match" in entry


class TestDiscoverAssertionsScoped:
    """Tests for _discover_assertions() with non-empty scope_id."""

    def test_scoped_search_minimizes_and_flattens(self, assertion_graph):
        """Scoped search delegates to _discover_requirements with minimize,
        then flattens surviving requirements' assertions."""
        result = _discover_assertions(
            assertion_graph, "auth", scope_id="PRD-root", direction="descendants"
        )

        assert "error" not in result
        assert "assertions" in result
        # "auth" matches OPS-auth (title), DEV-login (title contains "Auth").
        # Minimize prunes OPS-auth (ancestor of DEV-login).
        # DEV-login has assertion DEV-login-A.
        returned_ids = {a["id"] for a in result["assertions"]}
        assert "DEV-login-A" in returned_ids
        assert result["stats"]["assertions_returned"] > 0

    def test_scoped_search_scope_not_found_returns_error(self, assertion_graph):
        """Scoped search with non-existent scope_id returns error."""
        result = _discover_assertions(assertion_graph, "auth", scope_id="NONEXISTENT-id")

        assert "error" in result


class TestDiscoverAssertionsSorting:
    """Tests for result ordering and limits."""

    def test_results_sorted_by_score_descending(self, assertion_graph):
        """Results are sorted by score in descending order."""
        result = _discover_assertions(assertion_graph, "OAuth")

        scores = [a["score"] for a in result["assertions"]]
        assert scores == sorted(scores, reverse=True)

    def test_limit_parameter_respected(self, assertion_graph):
        """Limit parameter caps the number of returned assertions."""
        result = _discover_assertions(assertion_graph, "SHALL", limit=2)

        # "SHALL" appears in many assertion texts, but limit=2
        assert len(result["assertions"]) <= 2

    def test_limit_caps_final_assertion_list(self, assertion_graph):
        """The assertions list is truncated to the limit after scoring."""
        full_result = _discover_assertions(assertion_graph, "SHALL", limit=100)
        limited_result = _discover_assertions(assertion_graph, "SHALL", limit=2)

        assert len(full_result["assertions"]) > 2
        assert len(limited_result["assertions"]) == 2
        assert limited_result["stats"]["assertions_returned"] == 2


class TestDiscoverAssertionsEdgeCases:
    """Tests for edge cases and empty results."""

    def test_empty_query_returns_no_results(self, assertion_graph):
        """Empty query string returns empty assertions list."""
        result = _discover_assertions(assertion_graph, "")

        assert "assertions" in result
        assert result["assertions"] == []
        assert result["stats"]["requirements_matched"] == 0
        assert result["stats"]["assertions_returned"] == 0

    def test_no_matches_returns_empty_with_stats(self, assertion_graph):
        """Query that matches nothing returns empty assertions with zeroed stats."""
        result = _discover_assertions(assertion_graph, "ZZZNOTFOUND")

        assert result["assertions"] == []
        assert result["stats"]["requirements_matched"] == 0
        assert result["stats"]["assertions_returned"] == 0
