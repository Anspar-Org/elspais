# Validates REQ-o00071-A, REQ-o00071-B, REQ-o00071-C, REQ-o00071-D
# Validates REQ-d00079-A, REQ-d00079-B, REQ-d00079-C, REQ-d00079-D
"""Tests for _discover_requirements() helper and discover_requirements MCP tool.

Validates REQ-o00071-A, REQ-o00071-B, REQ-o00071-C, REQ-o00071-D:
  OPS-level specification for discover_requirements feature.

Validates REQ-d00079-A, REQ-d00079-B, REQ-d00079-C, REQ-d00079-D:
  DEV-level specification for _discover_requirements helper and MCP wrapper.
"""

from pathlib import Path

import pytest

from elspais.graph import GraphNode, NodeKind
from elspais.graph.builder import TraceGraph
from elspais.graph.relations import Edge, EdgeKind

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
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
    """Set up both tree structure and implements edge.

    Uses add_child() for tree traversal (iter_children/iter_parents) and
    manually creates an outgoing edge from child to parent for
    _minimize_requirement_set() which walks iter_outgoing_edges().
    """
    parent.add_child(child)
    edge = Edge(source=child, target=parent, kind=EdgeKind.IMPLEMENTS)
    child._outgoing_edges.append(edge)
    parent._incoming_edges.append(edge)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def discover_graph():
    """Graph with a multi-level hierarchy for discover_requirements testing.

    Structure (structural parent -> children):

    PRD-root (level=PRD, title="Platform Requirements")
      +-- OPS-auth (level=OPS, title="Auth Module") [implements PRD-root]
      |   +-- DEV-login (level=DEV, title="Auth Login Endpoint") [implements OPS-auth]
      |   +-- DEV-token (level=DEV, title="Auth Token Validation") [implements OPS-auth]
      +-- OPS-data (level=OPS, title="Data Processing") [implements PRD-root]
          +-- DEV-pipeline (level=DEV, title="Pipeline Runner") [implements OPS-data]

    Assertions on OPS-auth:
      OPS-auth-A: "SHALL authenticate users via OAuth"
      OPS-auth-B: "SHALL support MFA tokens"

    Notes:
    - Titles for DEV-login and DEV-token contain "Auth" so that a query
      for "auth" matches all three auth-related nodes (OPS-auth, DEV-login,
      DEV-token), enabling the minimize step to prune OPS-auth.
    - Both tree structure (add_child) and outgoing edges (for minimize)
      are set up via _add_implements_edge().
    """
    graph = TraceGraph(repo_root=Path("/test/repo"))

    # Create requirement nodes
    prd_root = _make_req("PRD-root", "Platform Requirements", "PRD")
    ops_auth = _make_req("OPS-auth", "Auth Module", "OPS")
    ops_data = _make_req("OPS-data", "Data Processing", "OPS")
    dev_login = _make_req("DEV-login", "Auth Login Endpoint", "DEV")
    dev_token = _make_req("DEV-token", "Auth Token Validation", "DEV")
    dev_pipeline = _make_req("DEV-pipeline", "Pipeline Runner", "DEV")

    # Create assertions on OPS-auth
    assert_a = _make_assertion("OPS-auth-A", "A", "SHALL authenticate users via OAuth")
    assert_b = _make_assertion("OPS-auth-B", "B", "SHALL support MFA tokens")

    # Build hierarchy with both tree structure and implement edges
    _add_implements_edge(ops_auth, prd_root)
    _add_implements_edge(ops_data, prd_root)
    _add_implements_edge(dev_login, ops_auth)
    _add_implements_edge(dev_token, ops_auth)
    _add_implements_edge(dev_pipeline, ops_data)

    # Attach assertions as children of OPS-auth (tree only, no typed edge)
    ops_auth.add_child(assert_a)
    ops_auth.add_child(assert_b)

    graph._roots = [prd_root]
    graph._index = {
        "PRD-root": prd_root,
        "OPS-auth": ops_auth,
        "OPS-data": ops_data,
        "DEV-login": dev_login,
        "DEV-token": dev_token,
        "DEV-pipeline": dev_pipeline,
        "OPS-auth-A": assert_a,
        "OPS-auth-B": assert_b,
    }
    return graph


# ─────────────────────────────────────────────────────────────────────────────
# Tests: _discover_requirements() helper — chaining produces correct minimal set
# ─────────────────────────────────────────────────────────────────────────────


class TestDiscoverRequirementsChaining:
    """Tests for _discover_requirements() chaining logic.

    Validates REQ-o00071-A, REQ-o00071-B, REQ-o00071-C, REQ-o00071-D:
    Validates REQ-d00079-A, REQ-d00079-B, REQ-d00079-C, REQ-d00079-D:
    """

    def test_REQ_o00071_B_chaining_prunes_ancestor(self, discover_graph):
        """REQ-o00071-B: Chaining scoped_search -> minimize prunes OPS-auth
        because DEV-login and DEV-token are more specific descendants."""
        from elspais.mcp.server import _discover_requirements

        result = _discover_requirements(discover_graph, "auth", "PRD-root", direction="descendants")

        assert "error" not in result
        result_ids = {r["id"] for r in result["results"]}
        # DEV-login and DEV-token survive (most specific)
        assert "DEV-login" in result_ids
        assert "DEV-token" in result_ids
        # OPS-auth is pruned (ancestor of both DEV nodes)
        assert "OPS-auth" not in result_ids

    def test_REQ_d00079_A_scoped_search_then_minimize(self, discover_graph):
        """REQ-d00079-A: Calls _scoped_search(), extracts IDs, passes to
        _minimize_requirement_set()."""
        from elspais.mcp.server import _discover_requirements

        result = _discover_requirements(discover_graph, "auth", "PRD-root", direction="descendants")

        assert "error" not in result
        # Stats show 3 candidates (OPS-auth, DEV-login, DEV-token) reduced to 2
        assert result["stats"]["candidate_count"] == 3
        assert result["stats"]["minimal_count"] == 2
        assert result["stats"]["pruned_count"] == 1

    def test_REQ_d00079_B_result_structure(self, discover_graph):
        """REQ-d00079-B: Returns {results, pruned, scope_id, direction, stats}."""
        from elspais.mcp.server import _discover_requirements

        result = _discover_requirements(discover_graph, "auth", "PRD-root", direction="descendants")

        assert "error" not in result
        assert "results" in result
        assert "pruned" in result
        assert "scope_id" in result
        assert "direction" in result
        assert "stats" in result
        assert result["scope_id"] == "PRD-root"
        assert result["direction"] == "descendants"

    def test_REQ_o00071_A_minimal_set_items_have_summary_format(self, discover_graph):
        """REQ-o00071-A: Minimal set items use scoped_search summary format
        (id, title, level, status)."""
        from elspais.mcp.server import _discover_requirements

        result = _discover_requirements(discover_graph, "auth", "PRD-root", direction="descendants")

        assert "error" not in result
        for item in result["results"]:
            assert "id" in item
            assert "title" in item
            assert "level" in item
            assert "status" in item


# ─────────────────────────────────────────────────────────────────────────────
# Tests: pruned ancestors get superseded_by metadata
# ─────────────────────────────────────────────────────────────────────────────


class TestDiscoverRequirementsPruning:
    """Tests for pruned ancestor metadata in _discover_requirements().

    Validates REQ-o00071-A, REQ-o00071-B, REQ-o00071-C, REQ-o00071-D:
    Validates REQ-d00079-A, REQ-d00079-B, REQ-d00079-C, REQ-d00079-D:
    """

    def test_REQ_o00071_C_pruned_ancestors_have_superseded_by(self, discover_graph):
        """REQ-o00071-C: Pruned ancestors include superseded_by list of
        more-specific descendants that replaced them."""
        from elspais.mcp.server import _discover_requirements

        result = _discover_requirements(discover_graph, "auth", "PRD-root", direction="descendants")

        assert "error" not in result
        assert len(result["pruned"]) == 1
        pruned_entry = result["pruned"][0]
        assert pruned_entry["id"] == "OPS-auth"
        assert "superseded_by" in pruned_entry
        superseding = set(pruned_entry["superseded_by"])
        assert superseding == {"DEV-login", "DEV-token"}

    def test_REQ_d00079_B_pruned_count_in_stats(self, discover_graph):
        """REQ-d00079-B: Stats include accurate pruned_count."""
        from elspais.mcp.server import _discover_requirements

        result = _discover_requirements(discover_graph, "auth", "PRD-root", direction="descendants")

        assert "error" not in result
        assert result["stats"]["pruned_count"] == 1

    def test_REQ_o00071_B_pruned_entry_has_summary_fields(self, discover_graph):
        """REQ-o00071-B: Pruned entries contain requirement summary fields
        (id, title, level, status) plus superseded_by."""
        from elspais.mcp.server import _discover_requirements

        result = _discover_requirements(discover_graph, "auth", "PRD-root", direction="descendants")

        assert "error" not in result
        pruned_entry = result["pruned"][0]
        assert pruned_entry["id"] == "OPS-auth"
        assert pruned_entry["title"] == "Auth Module"
        assert pruned_entry["level"] == "OPS"
        assert pruned_entry["status"] == "Active"
        assert "superseded_by" in pruned_entry


# ─────────────────────────────────────────────────────────────────────────────
# Tests: pass-through when no ancestors in result set
# ─────────────────────────────────────────────────────────────────────────────


class TestDiscoverRequirementsPassThrough:
    """Tests for pass-through behavior when no ancestor relationships exist.

    Validates REQ-o00071-A, REQ-o00071-B, REQ-o00071-C, REQ-o00071-D:
    Validates REQ-d00079-A, REQ-d00079-B, REQ-d00079-C, REQ-d00079-D:
    """

    def test_REQ_o00071_A_disjoint_results_pass_through(self, discover_graph):
        """REQ-o00071-A: When search results have no ancestor relationships,
        all pass through to the minimal set unchanged."""
        from elspais.mcp.server import _discover_requirements

        # "DEV-" matches DEV-login, DEV-token, DEV-pipeline by ID.
        # None of these are ancestors of each other; all at same level.
        result = _discover_requirements(
            discover_graph, r"^DEV-", "PRD-root", direction="descendants", regex=True
        )

        assert "error" not in result
        result_ids = {r["id"] for r in result["results"]}
        assert result_ids == {"DEV-login", "DEV-token", "DEV-pipeline"}
        assert result["pruned"] == []
        assert result["stats"]["candidate_count"] == 3
        assert result["stats"]["minimal_count"] == 3
        assert result["stats"]["pruned_count"] == 0

    def test_REQ_d00079_A_empty_scoped_search_returns_empty(self, discover_graph):
        """REQ-d00079-A: Empty results from scoped_search propagate as empty."""
        from elspais.mcp.server import _discover_requirements

        result = _discover_requirements(
            discover_graph, "ZZZNOTFOUND", "PRD-root", direction="descendants"
        )

        assert "error" not in result
        assert result["results"] == []
        assert result["pruned"] == []
        assert result["stats"]["candidate_count"] == 0
        assert result["stats"]["minimal_count"] == 0
        assert result["stats"]["pruned_count"] == 0

    def test_REQ_o00071_D_scope_not_found_returns_error(self, discover_graph):
        """REQ-o00071-D: Returns error dict when scope_id does not exist."""
        from elspais.mcp.server import _discover_requirements

        result = _discover_requirements(discover_graph, "anything", "NONEXISTENT-id")

        assert "error" in result
        assert "not found" in result["error"]

    def test_REQ_d00079_C_matched_assertions_preserved_on_minimal_set(self, discover_graph):
        """REQ-d00079-C: matched_assertions from scoped_search are preserved
        on items that survive minimization."""
        from elspais.mcp.server import _discover_requirements

        # "OAuth" matches assertion text on OPS-auth.
        # With include_assertions=True, OPS-auth gets matched_assertions.
        # But OPS-auth also matches by title ("Auth Module" contains "auth"?
        # — no, "OAuth" not in "Auth Module". Let's search for "OAuth" specifically.)
        # OPS-auth-A text: "SHALL authenticate users via OAuth"
        # This assertion match attaches to OPS-auth.
        # DEV-login and DEV-token do NOT match "OAuth" in their titles/IDs.
        # So only OPS-auth appears in scoped_search results.
        # With only one result, minimize has nothing to prune.
        # OPS-auth stays in results with matched_assertions preserved.
        result = _discover_requirements(
            discover_graph, "OAuth", "PRD-root", direction="descendants", include_assertions=True
        )

        assert "error" not in result
        assert len(result["results"]) == 1
        entry = result["results"][0]
        assert entry["id"] == "OPS-auth"
        assert "matched_assertions" in entry
        assert len(entry["matched_assertions"]) == 1
        assert entry["matched_assertions"][0]["id"] == "OPS-auth-A"

    def test_REQ_d00079_C_matched_assertions_survive_pruning(self, discover_graph):
        """REQ-d00079-C: When a result with matched_assertions survives pruning,
        the matched_assertions metadata is fully preserved."""
        from elspais.mcp.server import _discover_requirements

        # "SHALL" matches both assertion texts on OPS-auth.
        # With include_assertions=True and query "SHALL", OPS-auth matches via
        # assertions. DEV-login and DEV-token do not match "SHALL" at all.
        # So the result set is just OPS-auth with matched_assertions.
        # Single result => no pruning => matched_assertions preserved.
        result = _discover_requirements(
            discover_graph, "SHALL", "OPS-auth", direction="descendants", include_assertions=True
        )

        assert "error" not in result
        matching = [r for r in result["results"] if r["id"] == "OPS-auth"]
        assert len(matching) == 1
        entry = matching[0]
        assert "matched_assertions" in entry
        assertion_ids = {a["id"] for a in entry["matched_assertions"]}
        assert assertion_ids == {"OPS-auth-A", "OPS-auth-B"}

    def test_REQ_o00071_A_single_result_passes_through(self, discover_graph):
        """REQ-o00071-A: Single result always passes through unchanged."""
        from elspais.mcp.server import _discover_requirements

        # "Pipeline" matches only DEV-pipeline
        result = _discover_requirements(
            discover_graph, "Pipeline", "PRD-root", direction="descendants"
        )

        assert "error" not in result
        assert len(result["results"]) == 1
        assert result["results"][0]["id"] == "DEV-pipeline"
        assert result["pruned"] == []
        assert result["stats"]["candidate_count"] == 1
        assert result["stats"]["minimal_count"] == 1
        assert result["stats"]["pruned_count"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# Tests: discover_requirements MCP tool wrapper
# ─────────────────────────────────────────────────────────────────────────────


class TestDiscoverRequirementsMCPTool:
    """Tests for discover_requirements() MCP tool wrapper.

    Validates REQ-d00079-D:
    """

    def test_REQ_d00079_D_tool_is_registered(self, discover_graph):
        """REQ-d00079-D: discover_requirements is registered as an MCP tool."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import create_server

        server = create_server(discover_graph)

        tool_names = [t.name for t in server._tool_manager._tools.values()]
        assert "discover_requirements" in tool_names

    def test_REQ_d00079_D_wrapper_delegates_to_helper(self, discover_graph):
        """REQ-d00079-D: MCP wrapper delegates to _discover_requirements helper."""
        pytest.importorskip("mcp")
        from unittest.mock import patch

        from elspais.mcp.server import create_server

        server = create_server(discover_graph)

        tool_obj = server._tool_manager._tools["discover_requirements"]
        tool_fn = tool_obj.fn

        with patch("elspais.mcp.server._discover_requirements") as mock_helper:
            mock_helper.return_value = {
                "results": [],
                "pruned": [],
                "scope_id": "OPS-auth",
                "direction": "descendants",
                "stats": {"candidate_count": 0, "minimal_count": 0, "pruned_count": 0},
            }

            tool_fn("test query", "OPS-auth")

            mock_helper.assert_called_once()
            call_args = mock_helper.call_args
            # First positional arg is graph, second is query, third is scope_id
            assert call_args[0][1] == "test query"
            assert call_args[0][2] == "OPS-auth"

    def test_REQ_d00079_D_wrapper_parses_edge_kinds(self, discover_graph):
        """REQ-d00079-D: MCP wrapper parses edge_kinds string before delegating."""
        pytest.importorskip("mcp")
        from unittest.mock import patch

        from elspais.mcp.server import create_server

        server = create_server(discover_graph)
        tool_fn = server._tool_manager._tools["discover_requirements"].fn

        with patch("elspais.mcp.server._discover_requirements") as mock_helper:
            mock_helper.return_value = {
                "results": [],
                "pruned": [],
                "scope_id": "OPS-auth",
                "direction": "descendants",
                "stats": {"candidate_count": 0, "minimal_count": 0, "pruned_count": 0},
            }

            tool_fn("query", "OPS-auth", edge_kinds="implements")

            parsed_kinds = mock_helper.call_args[0][8]  # edge_kinds is 9th positional arg
            assert parsed_kinds == {EdgeKind.IMPLEMENTS}

    def test_REQ_d00079_D_wrapper_passes_all_parameters(self, discover_graph):
        """REQ-d00079-D: MCP wrapper passes all parameters through to helper."""
        pytest.importorskip("mcp")
        from unittest.mock import patch

        from elspais.mcp.server import create_server

        server = create_server(discover_graph)
        tool_fn = server._tool_manager._tools["discover_requirements"].fn

        with patch("elspais.mcp.server._discover_requirements") as mock_helper:
            mock_helper.return_value = {
                "results": [],
                "pruned": [],
                "scope_id": "OPS-auth",
                "direction": "ancestors",
                "stats": {"candidate_count": 0, "minimal_count": 0, "pruned_count": 0},
            }

            tool_fn(
                "pattern",
                "OPS-auth",
                direction="ancestors",
                field="title",
                regex=True,
                include_assertions=True,
                limit=10,
                edge_kinds="implements,refines",
            )

            mock_helper.assert_called_once()
            args, kwargs = mock_helper.call_args
            # Positional: graph, query, scope_id, direction, field, regex,
            #             include_assertions, limit, edge_kinds
            assert args[1] == "pattern"
            assert args[2] == "OPS-auth"
            assert args[3] == "ancestors"
            assert args[4] == "title"
            assert args[5] is True  # regex
            assert args[6] is True  # include_assertions
            assert args[7] == 10  # limit
            assert args[8] == {EdgeKind.IMPLEMENTS, EdgeKind.REFINES}
