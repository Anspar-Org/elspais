# Validates REQ-o00070-A, REQ-o00070-B, REQ-o00070-C, REQ-o00070-D, REQ-o00070-E
# Validates REQ-d00078-A, REQ-d00078-B, REQ-d00078-C, REQ-d00078-D, REQ-d00078-E, REQ-d00078-F
"""Tests for _collect_scope_ids(), _scoped_search() helper, and scoped_search MCP tool.

Validates REQ-o00070-A, REQ-o00070-B, REQ-o00070-C, REQ-o00070-D, REQ-o00070-E:
  OPS-level specification for scoped_search feature.

Validates REQ-d00078-A, REQ-d00078-B, REQ-d00078-C, REQ-d00078-D, REQ-d00078-E, REQ-d00078-F:
  DEV-level specification for _collect_scope_ids, _scoped_search helper, and MCP wrapper.
"""

from pathlib import Path

import pytest

from elspais.graph import GraphNode, NodeKind
from elspais.graph.builder import TraceGraph
from elspais.graph.relations import EdgeKind

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


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def scoped_graph():
    """Graph with a multi-level hierarchy for scoped search testing.

    Structure (structural parent -> children via link()):

    PRD-root (level=PRD, title="Platform Requirements")
      +-- OPS-auth (level=OPS, title="Authentication Module") [implements PRD-root]
      |   +-- DEV-login (level=DEV, title="Login Endpoint") [implements OPS-auth]
      |   +-- DEV-token (level=DEV, title="Token Validation") [implements OPS-auth]
      +-- OPS-data (level=OPS, title="Data Processing") [implements PRD-root]
          +-- DEV-pipeline (level=DEV, title="Pipeline Runner") [implements OPS-data]

    Assertions on OPS-auth:
      OPS-auth-A: "SHALL authenticate users via OAuth"
      OPS-auth-B: "SHALL support MFA tokens"
    """
    graph = TraceGraph(repo_root=Path("/test/repo"))

    # Create requirement nodes
    prd_root = _make_req("PRD-root", "Platform Requirements", "PRD")
    ops_auth = _make_req("OPS-auth", "Authentication Module", "OPS")
    ops_data = _make_req("OPS-data", "Data Processing", "OPS")
    dev_login = _make_req("DEV-login", "Login Endpoint", "DEV")
    dev_token = _make_req("DEV-token", "Token Validation", "DEV")
    dev_pipeline = _make_req("DEV-pipeline", "Pipeline Runner", "DEV")

    # Create assertions on OPS-auth
    assert_a = _make_assertion("OPS-auth-A", "A", "SHALL authenticate users via OAuth")
    assert_b = _make_assertion("OPS-auth-B", "B", "SHALL support MFA tokens")

    # Build hierarchy: parent.link(child, EdgeKind.IMPLEMENTS)
    # This makes child a structural child of parent (iter_children yields child)
    prd_root.link(ops_auth, EdgeKind.IMPLEMENTS)
    prd_root.link(ops_data, EdgeKind.IMPLEMENTS)
    ops_auth.link(dev_login, EdgeKind.IMPLEMENTS)
    ops_auth.link(dev_token, EdgeKind.IMPLEMENTS)
    ops_data.link(dev_pipeline, EdgeKind.IMPLEMENTS)

    # Attach assertions as children of OPS-auth
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
# Tests: _collect_scope_ids()
# ─────────────────────────────────────────────────────────────────────────────


class TestCollectScopeIds:
    """Tests for _collect_scope_ids() helper.

    Validates REQ-o00070-A, REQ-o00070-D, REQ-d00078-A, REQ-d00078-B:
    """

    def test_REQ_d00078_A_descendants_via_iter_children(self, scoped_graph):
        """REQ-d00078-A: BFS via iter_children() collects all descendants."""
        from elspais.mcp.server import _collect_scope_ids

        result = _collect_scope_ids(scoped_graph, "OPS-auth", "descendants")

        # OPS-auth's structural children: DEV-login, DEV-token, plus assertions
        assert result is not None
        assert "OPS-auth" in result
        assert "DEV-login" in result
        assert "DEV-token" in result
        # Assertions are also children
        assert "OPS-auth-A" in result
        assert "OPS-auth-B" in result
        # Siblings/ancestors excluded
        assert "OPS-data" not in result
        assert "PRD-root" not in result
        assert "DEV-pipeline" not in result

    def test_REQ_d00078_A_ancestors_via_iter_parents(self, scoped_graph):
        """REQ-d00078-A: Walk via iter_parents() collects all ancestors."""
        from elspais.mcp.server import _collect_scope_ids

        result = _collect_scope_ids(scoped_graph, "DEV-login", "ancestors")

        assert result is not None
        assert "DEV-login" in result
        assert "OPS-auth" in result
        assert "PRD-root" in result
        # Siblings/other branches excluded
        assert "DEV-token" not in result
        assert "OPS-data" not in result
        assert "DEV-pipeline" not in result

    def test_REQ_d00078_B_scope_id_included(self, scoped_graph):
        """REQ-d00078-B: The scope_id itself is always included in the result set."""
        from elspais.mcp.server import _collect_scope_ids

        descendants = _collect_scope_ids(scoped_graph, "OPS-auth", "descendants")
        ancestors = _collect_scope_ids(scoped_graph, "OPS-auth", "ancestors")

        assert descendants is not None
        assert "OPS-auth" in descendants
        assert ancestors is not None
        assert "OPS-auth" in ancestors

    def test_REQ_d00078_B_dag_dedup(self, scoped_graph):
        """REQ-d00078-B: Uses visited set so nodes are not duplicated in DAG."""
        from elspais.mcp.server import _collect_scope_ids

        # Collecting from root should reach all nodes exactly once
        result = _collect_scope_ids(scoped_graph, "PRD-root", "descendants")
        assert result is not None
        # Each ID appears exactly once (it's a set)
        assert isinstance(result, set)

    def test_REQ_o00070_D_scope_id_not_found_returns_none(self, scoped_graph):
        """REQ-o00070-D: Returns None when scope_id does not exist in graph."""
        from elspais.mcp.server import _collect_scope_ids

        result = _collect_scope_ids(scoped_graph, "NONEXISTENT-id", "descendants")

        assert result is None

    def test_REQ_d00078_A_leaf_node_descendants_empty(self, scoped_graph):
        """REQ-d00078-A: Leaf node with no children returns only itself for descendants."""
        from elspais.mcp.server import _collect_scope_ids

        result = _collect_scope_ids(scoped_graph, "DEV-login", "descendants")

        assert result is not None
        assert result == {"DEV-login"}

    def test_REQ_d00078_A_root_node_ancestors_empty(self, scoped_graph):
        """REQ-d00078-A: Root node with no parents returns only itself for ancestors."""
        from elspais.mcp.server import _collect_scope_ids

        result = _collect_scope_ids(scoped_graph, "PRD-root", "ancestors")

        assert result is not None
        assert result == {"PRD-root"}


# ─────────────────────────────────────────────────────────────────────────────
# Tests: _scoped_search() helper
# ─────────────────────────────────────────────────────────────────────────────


class TestScopedSearch:
    """Tests for _scoped_search() helper function.

    Validates REQ-o00070-A, REQ-o00070-B, REQ-o00070-C, REQ-o00070-D, REQ-o00070-E:
    Validates REQ-d00078-C, REQ-d00078-D, REQ-d00078-E:
    """

    def test_REQ_o00070_B_descendants_excludes_siblings(self, scoped_graph):
        """REQ-o00070-B: Descendants-only search excludes sibling and ancestor matches."""
        from elspais.mcp.server import _scoped_search

        # Search within OPS-auth descendants for "Endpoint" (matches DEV-login)
        result = _scoped_search(scoped_graph, "Endpoint", "OPS-auth", direction="descendants")

        assert "error" not in result
        result_ids = {r["id"] for r in result["results"]}
        assert "DEV-login" in result_ids
        # DEV-pipeline is under OPS-data (sibling), must be excluded
        assert "DEV-pipeline" not in result_ids
        # PRD-root is ancestor, must be excluded
        assert "PRD-root" not in result_ids

    def test_REQ_o00070_B_descendants_excludes_ancestor_matches(self, scoped_graph):
        """REQ-o00070-B: Descendants search from OPS-auth does not include PRD-root."""
        from elspais.mcp.server import _scoped_search

        # "Platform" matches PRD-root title but PRD-root is an ancestor, not descendant
        result = _scoped_search(scoped_graph, "Platform", "OPS-auth", direction="descendants")

        assert "error" not in result
        result_ids = {r["id"] for r in result["results"]}
        assert "PRD-root" not in result_ids
        assert len(result["results"]) == 0

    def test_REQ_o00070_B_ancestors_excludes_descendant_siblings(self, scoped_graph):
        """REQ-o00070-B: Ancestors-only search excludes descendant and sibling matches."""
        from elspais.mcp.server import _scoped_search

        # Search ancestors of DEV-login for "Platform" (matches PRD-root)
        result = _scoped_search(scoped_graph, "Platform", "DEV-login", direction="ancestors")

        assert "error" not in result
        result_ids = {r["id"] for r in result["results"]}
        assert "PRD-root" in result_ids
        # DEV-token is a sibling, must be excluded
        assert "DEV-token" not in result_ids
        # DEV-pipeline is in another branch, must be excluded
        assert "DEV-pipeline" not in result_ids

    def test_REQ_o00070_A_scope_id_included_when_matching(self, scoped_graph):
        """REQ-o00070-A: The scope_id itself is included in results when it matches the query."""
        from elspais.mcp.server import _scoped_search

        # "Authentication" matches OPS-auth title; OPS-auth is the scope_id
        result = _scoped_search(scoped_graph, "Authentication", "OPS-auth", direction="descendants")

        assert "error" not in result
        result_ids = {r["id"] for r in result["results"]}
        assert "OPS-auth" in result_ids

    def test_REQ_o00070_D_scope_id_not_found_returns_error(self, scoped_graph):
        """REQ-o00070-D: Returns error dict when scope_id does not exist."""
        from elspais.mcp.server import _scoped_search

        result = _scoped_search(scoped_graph, "anything", "NONEXISTENT-id")

        assert "error" in result
        assert "not found" in result["error"]

    def test_REQ_d00078_C_empty_scope_returns_empty_results(self, scoped_graph):
        """REQ-d00078-C: Empty scope set returns empty results (scope node exists but
        has no children/parents in that direction)."""
        from elspais.mcp.server import _scoped_search

        # DEV-login has no structural children; searching descendants for anything
        # that doesn't match DEV-login itself returns empty
        result = _scoped_search(scoped_graph, "ZZZNOTFOUND", "DEV-login", direction="descendants")

        assert "error" not in result
        assert result["results"] == []

    def test_REQ_d00078_D_assertion_matching_adds_matched_assertions(self, scoped_graph):
        """REQ-d00078-D: When include_assertions=True and an assertion matches,
        the parent requirement gets matched_assertions field."""
        from elspais.mcp.server import _scoped_search

        # "OAuth" matches assertion text "SHALL authenticate users via OAuth"
        result = _scoped_search(
            scoped_graph,
            "OAuth",
            "PRD-root",
            direction="descendants",
            include_assertions=True,
        )

        assert "error" not in result
        # OPS-auth should appear because its assertion matches
        matching = [r for r in result["results"] if r["id"] == "OPS-auth"]
        assert len(matching) == 1
        entry = matching[0]
        assert "matched_assertions" in entry
        assert len(entry["matched_assertions"]) == 1
        assert entry["matched_assertions"][0]["id"] == "OPS-auth-A"

    def test_REQ_d00078_D_assertion_matching_multiple(self, scoped_graph):
        """REQ-d00078-D: Multiple matching assertions are all returned."""
        from elspais.mcp.server import _scoped_search

        # "SHALL" appears in both assertion texts
        result = _scoped_search(
            scoped_graph,
            "SHALL",
            "OPS-auth",
            direction="descendants",
            include_assertions=True,
        )

        assert "error" not in result
        matching = [r for r in result["results"] if r["id"] == "OPS-auth"]
        assert len(matching) == 1
        entry = matching[0]
        assert "matched_assertions" in entry
        assertion_ids = {a["id"] for a in entry["matched_assertions"]}
        assert assertion_ids == {"OPS-auth-A", "OPS-auth-B"}

    def test_REQ_d00078_D_no_matched_assertions_field_when_none_match(self, scoped_graph):
        """REQ-d00078-D: No matched_assertions field when assertions don't match."""
        from elspais.mcp.server import _scoped_search

        # "Login" matches DEV-login title but no assertion text
        result = _scoped_search(
            scoped_graph,
            "Login",
            "OPS-auth",
            direction="descendants",
            include_assertions=True,
        )

        assert "error" not in result
        login_results = [r for r in result["results"] if r["id"] == "DEV-login"]
        assert len(login_results) == 1
        assert "matched_assertions" not in login_results[0]

    def test_REQ_o00070_E_field_parameter_title(self, scoped_graph):
        """REQ-o00070-E: field='title' restricts search to title only."""
        from elspais.mcp.server import _scoped_search

        # "OPS-auth" appears in the ID but not in the title ("Authentication Module")
        result = _scoped_search(
            scoped_graph, "OPS-auth", "PRD-root", direction="descendants", field="title"
        )

        assert "error" not in result
        result_ids = {r["id"] for r in result["results"]}
        # Should NOT match because "OPS-auth" is in the ID, not the title
        assert "OPS-auth" not in result_ids

    def test_REQ_o00070_E_field_parameter_id(self, scoped_graph):
        """REQ-o00070-E: field='id' restricts search to ID only."""
        from elspais.mcp.server import _scoped_search

        # "Authentication" appears in the title but not in the ID "OPS-auth"
        result = _scoped_search(
            scoped_graph, "Authentication", "PRD-root", direction="descendants", field="id"
        )

        assert "error" not in result
        result_ids = {r["id"] for r in result["results"]}
        # Should NOT match because "Authentication" is in the title, not the ID
        assert "OPS-auth" not in result_ids

    def test_REQ_o00070_E_regex_parameter(self, scoped_graph):
        """REQ-o00070-E: regex=True uses regex matching."""
        from elspais.mcp.server import _scoped_search

        # Use regex to match IDs starting with "DEV-"
        result = _scoped_search(
            scoped_graph, r"^DEV-", "PRD-root", direction="descendants", regex=True
        )

        assert "error" not in result
        result_ids = {r["id"] for r in result["results"]}
        assert "DEV-login" in result_ids
        assert "DEV-token" in result_ids
        assert "DEV-pipeline" in result_ids
        # OPS and PRD nodes should not match the regex
        assert "OPS-auth" not in result_ids
        assert "OPS-data" not in result_ids
        assert "PRD-root" not in result_ids

    def test_REQ_o00070_E_regex_with_field(self, scoped_graph):
        """REQ-o00070-E: regex + field parameters work together."""
        from elspais.mcp.server import _scoped_search

        # Regex matching title field for words ending in "Module"
        result = _scoped_search(
            scoped_graph,
            r"Module$",
            "PRD-root",
            direction="descendants",
            field="title",
            regex=True,
        )

        assert "error" not in result
        result_ids = {r["id"] for r in result["results"]}
        assert result_ids == {"OPS-auth"}

    def test_REQ_d00078_E_limit_respected(self, scoped_graph):
        """REQ-d00078-E: The limit parameter caps the number of results returned."""
        from elspais.mcp.server import _scoped_search

        # Search from PRD-root descendants for a broad match (matches all)
        result_limited = _scoped_search(
            scoped_graph, "OPS", "PRD-root", direction="descendants", limit=1
        )

        assert "error" not in result_limited
        assert len(result_limited["results"]) == 1

        # Without limit (default 50), should return all matches
        result_all = _scoped_search(
            scoped_graph, "OPS", "PRD-root", direction="descendants", limit=50
        )

        assert "error" not in result_all
        assert len(result_all["results"]) >= 2  # OPS-auth and OPS-data at minimum

    def test_REQ_d00078_E_result_includes_metadata(self, scoped_graph):
        """REQ-d00078-E: Results dict includes scope_id and direction metadata."""
        from elspais.mcp.server import _scoped_search

        result = _scoped_search(scoped_graph, "Login", "OPS-auth", direction="descendants")

        assert "error" not in result
        assert result["scope_id"] == "OPS-auth"
        assert result["direction"] == "descendants"

    def test_REQ_d00078_C_requirement_summary_format(self, scoped_graph):
        """REQ-d00078-C: Results contain requirement summaries (id, title, level, status)."""
        from elspais.mcp.server import _scoped_search

        result = _scoped_search(scoped_graph, "Login", "OPS-auth", direction="descendants")

        assert "error" not in result
        assert len(result["results"]) == 1
        entry = result["results"][0]
        assert entry["id"] == "DEV-login"
        assert entry["title"] == "Login Endpoint"
        assert entry["level"] == "DEV"
        assert entry["status"] == "Active"

    def test_REQ_o00070_A_descendants_full_subtree(self, scoped_graph):
        """REQ-o00070-A: Searching from PRD-root with broad query finds all descendants."""
        from elspais.mcp.server import _scoped_search

        # Every requirement node's ID or title should contain at least one of these
        # Use a regex that matches any requirement ID pattern
        result = _scoped_search(scoped_graph, r".", "PRD-root", direction="descendants", regex=True)

        assert "error" not in result
        result_ids = {r["id"] for r in result["results"]}
        # Should find all REQUIREMENT nodes (not assertions)
        assert "PRD-root" in result_ids
        assert "OPS-auth" in result_ids
        assert "OPS-data" in result_ids
        assert "DEV-login" in result_ids
        assert "DEV-token" in result_ids
        assert "DEV-pipeline" in result_ids
        # Assertions are not REQUIREMENT nodes, so not in results
        assert "OPS-auth-A" not in result_ids
        assert "OPS-auth-B" not in result_ids


# ─────────────────────────────────────────────────────────────────────────────
# Tests: scoped_search MCP tool wrapper
# ─────────────────────────────────────────────────────────────────────────────


class TestScopedSearchMCPTool:
    """Tests for scoped_search() MCP tool wrapper.

    Validates REQ-d00078-F:
    """

    def test_REQ_d00078_F_tool_is_registered(self, scoped_graph):
        """REQ-d00078-F: scoped_search is registered as an MCP tool."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import create_server

        server = create_server(scoped_graph)

        tool_names = [t.name for t in server._tool_manager._tools.values()]
        assert "scoped_search" in tool_names

    def test_REQ_d00078_F_wrapper_delegates_to_helper(self, scoped_graph):
        """REQ-d00078-F: MCP wrapper delegates to _scoped_search helper."""
        pytest.importorskip("mcp")
        from unittest.mock import patch

        from elspais.mcp.server import create_server

        server = create_server(scoped_graph)

        tool_obj = server._tool_manager._tools["scoped_search"]
        tool_fn = tool_obj.fn

        with patch("elspais.mcp.server._scoped_search") as mock_helper:
            mock_helper.return_value = {
                "results": [],
                "scope_id": "OPS-auth",
                "direction": "descendants",
            }

            tool_fn("test query", "OPS-auth")

            mock_helper.assert_called_once()
            call_args = mock_helper.call_args
            # First positional arg is graph, second is query, third is scope_id
            assert call_args[0][1] == "test query"
            assert call_args[0][2] == "OPS-auth"

    def test_REQ_d00078_F_wrapper_passes_all_parameters(self, scoped_graph):
        """REQ-d00078-F: MCP wrapper passes all parameters through to helper."""
        pytest.importorskip("mcp")
        from unittest.mock import patch

        from elspais.mcp.server import create_server

        server = create_server(scoped_graph)

        tool_obj = server._tool_manager._tools["scoped_search"]
        tool_fn = tool_obj.fn

        with patch("elspais.mcp.server._scoped_search") as mock_helper:
            mock_helper.return_value = {
                "results": [],
                "scope_id": "OPS-auth",
                "direction": "ancestors",
            }

            tool_fn(
                "pattern",
                "OPS-auth",
                direction="ancestors",
                field="title",
                regex=True,
                include_assertions=True,
                limit=10,
            )

            mock_helper.assert_called_once()
            args, kwargs = mock_helper.call_args
            # Positional: graph, query, scope_id, direction, field, regex, include_assertions, limit
            assert args[1] == "pattern"
            assert args[2] == "OPS-auth"
