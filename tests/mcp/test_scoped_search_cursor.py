# Validates REQ-o00068-F, REQ-d00076-B
"""Tests for cursor protocol integration with scoped_search query type.

Validates REQ-o00068-F, REQ-d00076-B:
  Cursor protocol dispatches scoped_search queries via _materialize_cursor_items,
  and cursor_next/cursor_info correctly track position through scoped results.
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


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def scoped_cursor_graph():
    """Graph with a multi-level hierarchy for scoped search cursor testing.

    Structure:
        PRD-root (level=PRD, title="Platform Requirements")
          +-- OPS-auth (level=OPS, title="Authentication Module") [implements PRD-root]
          |   +-- DEV-login (level=DEV, title="Login Endpoint") [implements OPS-auth]
          |   +-- DEV-token (level=DEV, title="Token Validation") [implements OPS-auth]
          +-- OPS-data (level=OPS, title="Data Processing") [implements PRD-root]
              +-- DEV-pipeline (level=DEV, title="Pipeline Runner") [implements OPS-data]
    """
    graph = TraceGraph(repo_root=Path("/test/repo"))

    # Create requirement nodes
    prd_root = _make_req("PRD-root", "Platform Requirements", "PRD")
    ops_auth = _make_req("OPS-auth", "Authentication Module", "OPS")
    ops_data = _make_req("OPS-data", "Data Processing", "OPS")
    dev_login = _make_req("DEV-login", "Login Endpoint", "DEV")
    dev_token = _make_req("DEV-token", "Token Validation", "DEV")
    dev_pipeline = _make_req("DEV-pipeline", "Pipeline Runner", "DEV")

    # Build hierarchy: parent.link(child, EdgeKind.IMPLEMENTS)
    prd_root.link(ops_auth, EdgeKind.IMPLEMENTS)
    prd_root.link(ops_data, EdgeKind.IMPLEMENTS)
    ops_auth.link(dev_login, EdgeKind.IMPLEMENTS)
    ops_auth.link(dev_token, EdgeKind.IMPLEMENTS)
    ops_data.link(dev_pipeline, EdgeKind.IMPLEMENTS)

    graph._roots = [prd_root]
    graph._index = {
        "PRD-root": prd_root,
        "OPS-auth": ops_auth,
        "OPS-data": ops_data,
        "DEV-login": dev_login,
        "DEV-token": dev_token,
        "DEV-pipeline": dev_pipeline,
    }
    return graph


@pytest.fixture
def scoped_cursor_state(scoped_cursor_graph):
    """Create a state dict suitable for cursor functions with scoped graph."""
    return {"graph": scoped_cursor_graph, "working_dir": Path("/test/repo"), "config": {}}


# ─────────────────────────────────────────────────────────────────────────────
# Tests: open_cursor with scoped_search
# ─────────────────────────────────────────────────────────────────────────────


class TestOpenCursorScopedSearch:
    """Validates REQ-o00068-F, REQ-d00076-B:

    Opening a cursor with query='scoped_search' dispatches to _scoped_search
    and returns the first matching item with correct metadata.
    """

    def test_REQ_o00068_F_open_cursor_scoped_search(self, scoped_cursor_state):
        """REQ-o00068-F: open_cursor with scoped_search query type returns first item."""
        from elspais.mcp.server import _open_cursor

        result = _open_cursor(
            scoped_cursor_state,
            query="scoped_search",
            params={
                "query": "auth",
                "scope_id": "OPS-auth",
                "direction": "descendants",
                "field": "all",
                "regex": False,
                "include_assertions": False,
                "limit": 50,
            },
            batch_size=0,
        )

        assert result["success"] is True
        assert result["query"] == "scoped_search"
        assert result["current"] is not None
        assert result["total"] >= 1
        assert result["position"] == 1
        assert result["remaining"] == result["total"] - 1

    def test_REQ_d00076_B_scoped_search_materializes_results(self, scoped_cursor_state):
        """REQ-d00076-B: _materialize_cursor_items dispatches scoped_search to _scoped_search."""
        from elspais.mcp.server import _materialize_cursor_items

        items = _materialize_cursor_items(
            query="scoped_search",
            params={
                "query": "auth",
                "scope_id": "OPS-auth",
                "direction": "descendants",
                "field": "all",
                "regex": False,
                "include_assertions": False,
                "limit": 50,
            },
            batch_size=0,
            graph=scoped_cursor_state["graph"],
        )

        assert isinstance(items, list)
        assert len(items) >= 1
        # OPS-auth matches "auth" in its ID and should be in the results
        result_ids = {item["id"] for item in items}
        assert "OPS-auth" in result_ids

    def test_REQ_o00068_F_open_cursor_scoped_search_empty(self, scoped_cursor_state):
        """REQ-o00068-F: open_cursor with scoped_search and no matches returns empty."""
        from elspais.mcp.server import _open_cursor

        result = _open_cursor(
            scoped_cursor_state,
            query="scoped_search",
            params={
                "query": "ZZZNOTFOUND",
                "scope_id": "OPS-auth",
                "direction": "descendants",
            },
            batch_size=0,
        )

        assert result["success"] is True
        assert result["current"] is None
        assert result["total"] == 0
        assert result["remaining"] == 0

    def test_REQ_o00068_F_open_cursor_scoped_search_scope_not_found(self, scoped_cursor_state):
        """REQ-o00068-F: open_cursor with non-existent scope_id returns empty results."""
        from elspais.mcp.server import _open_cursor

        result = _open_cursor(
            scoped_cursor_state,
            query="scoped_search",
            params={
                "query": "anything",
                "scope_id": "NONEXISTENT-id",
                "direction": "descendants",
            },
            batch_size=0,
        )

        # _scoped_search returns error dict with no "results" key, so
        # _materialize_cursor_items returns []
        assert result["success"] is True
        assert result["total"] == 0
        assert result["current"] is None


# ─────────────────────────────────────────────────────────────────────────────
# Tests: cursor_next with scoped_search results
# ─────────────────────────────────────────────────────────────────────────────


class TestCursorNextScopedSearch:
    """Validates REQ-o00068-F, REQ-d00076-B:

    cursor_next advances through scoped_search results correctly.
    """

    def test_REQ_o00068_F_cursor_next_advances_through_scoped_results(self, scoped_cursor_state):
        """REQ-o00068-F: cursor_next advances through scoped_search results one at a time."""
        from elspais.mcp.server import _cursor_next, _open_cursor

        # Use regex "." to match all descendants within OPS-auth scope
        open_result = _open_cursor(
            scoped_cursor_state,
            query="scoped_search",
            params={
                "query": ".",
                "scope_id": "OPS-auth",
                "direction": "descendants",
                "regex": True,
            },
            batch_size=0,
        )

        total = open_result["total"]
        assert total >= 2  # OPS-auth + DEV-login + DEV-token at minimum

        # Advance one at a time
        result = _cursor_next(scoped_cursor_state, count=1)
        assert result["success"] is True
        assert result["count"] == 1
        assert len(result["items"]) == 1
        assert result["position"] == 2  # 1 from open + 1 from next

    def test_REQ_d00076_B_cursor_next_collects_all_scoped_items(self, scoped_cursor_state):
        """REQ-d00076-B: Iterating through all scoped_search results collects every match."""
        from elspais.mcp.server import _cursor_next, _open_cursor

        open_result = _open_cursor(
            scoped_cursor_state,
            query="scoped_search",
            params={
                "query": ".",
                "scope_id": "OPS-auth",
                "direction": "descendants",
                "regex": True,
            },
            batch_size=0,
        )

        total = open_result["total"]
        first_item = open_result["current"]

        # Collect remaining items
        collected = [first_item]
        while True:
            result = _cursor_next(scoped_cursor_state, count=1)
            if result["count"] == 0:
                break
            collected.extend(result["items"])

        assert len(collected) == total

        # Verify all expected IDs are present
        collected_ids = {item["id"] for item in collected}
        assert "OPS-auth" in collected_ids
        assert "DEV-login" in collected_ids
        assert "DEV-token" in collected_ids
        # DEV-pipeline is under OPS-data, should NOT be present
        assert "DEV-pipeline" not in collected_ids

    def test_REQ_o00068_F_cursor_next_at_end_returns_empty(self, scoped_cursor_state):
        """REQ-o00068-F: cursor_next past end returns empty items list."""
        from elspais.mcp.server import _cursor_next, _open_cursor

        open_result = _open_cursor(
            scoped_cursor_state,
            query="scoped_search",
            params={
                "query": "Login",
                "scope_id": "OPS-auth",
                "direction": "descendants",
            },
            batch_size=0,
        )

        total = open_result["total"]
        assert total >= 1  # DEV-login matches

        # Consume all remaining items
        _cursor_next(scoped_cursor_state, count=total)

        # Now next should return empty
        result = _cursor_next(scoped_cursor_state, count=1)
        assert result["success"] is True
        assert result["items"] == []
        assert result["count"] == 0
        assert result["remaining"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# Tests: cursor_info with scoped_search results
# ─────────────────────────────────────────────────────────────────────────────


class TestCursorInfoScopedSearch:
    """Validates REQ-o00068-F, REQ-d00076-B:

    cursor_info reports correct position, total, and remaining for
    scoped_search cursor without advancing.
    """

    def test_REQ_o00068_F_cursor_info_reports_correct_position(self, scoped_cursor_state):
        """REQ-o00068-F: cursor_info reports correct position/total/remaining after open."""
        from elspais.mcp.server import _cursor_info, _open_cursor

        open_result = _open_cursor(
            scoped_cursor_state,
            query="scoped_search",
            params={
                "query": ".",
                "scope_id": "OPS-auth",
                "direction": "descendants",
                "regex": True,
            },
            batch_size=0,
        )

        info = _cursor_info(scoped_cursor_state)

        assert info["success"] is True
        assert info["position"] == open_result["position"]
        assert info["total"] == open_result["total"]
        assert info["remaining"] == open_result["remaining"]
        assert info["query"] == "scoped_search"

    def test_REQ_d00076_B_cursor_info_after_next(self, scoped_cursor_state):
        """REQ-d00076-B: cursor_info reflects updated position after cursor_next."""
        from elspais.mcp.server import _cursor_info, _cursor_next, _open_cursor

        open_result = _open_cursor(
            scoped_cursor_state,
            query="scoped_search",
            params={
                "query": ".",
                "scope_id": "OPS-auth",
                "direction": "descendants",
                "regex": True,
            },
            batch_size=0,
        )

        total = open_result["total"]
        assert total >= 2  # Need at least 2 items to advance

        _cursor_next(scoped_cursor_state, count=1)

        info = _cursor_info(scoped_cursor_state)

        assert info["success"] is True
        assert info["position"] == 2  # 1 from open + 1 from next
        assert info["total"] == total
        assert info["remaining"] == total - 2

    def test_REQ_o00068_F_cursor_info_does_not_advance(self, scoped_cursor_state):
        """REQ-o00068-F: Calling cursor_info multiple times does not change position."""
        from elspais.mcp.server import _cursor_info, _open_cursor

        _open_cursor(
            scoped_cursor_state,
            query="scoped_search",
            params={
                "query": ".",
                "scope_id": "OPS-auth",
                "direction": "descendants",
                "regex": True,
            },
            batch_size=0,
        )

        info1 = _cursor_info(scoped_cursor_state)
        info2 = _cursor_info(scoped_cursor_state)

        assert info1["position"] == info2["position"]
        assert info1["total"] == info2["total"]
        assert info1["remaining"] == info2["remaining"]

    def test_REQ_d00076_B_cursor_info_at_end(self, scoped_cursor_state):
        """REQ-d00076-B: cursor_info at end shows remaining=0."""
        from elspais.mcp.server import _cursor_info, _cursor_next, _open_cursor

        open_result = _open_cursor(
            scoped_cursor_state,
            query="scoped_search",
            params={
                "query": "Login",
                "scope_id": "OPS-auth",
                "direction": "descendants",
            },
            batch_size=0,
        )

        total = open_result["total"]
        # Consume all remaining items beyond the first
        if total > 1:
            _cursor_next(scoped_cursor_state, count=total - 1)

        info = _cursor_info(scoped_cursor_state)

        assert info["remaining"] == 0
        assert info["position"] == total
