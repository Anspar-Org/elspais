# Validates REQ-o00068-A, REQ-o00068-B, REQ-o00068-C, REQ-o00068-D, REQ-o00068-E, REQ-o00068-F
# Validates REQ-d00076-A, REQ-d00076-B, REQ-d00076-C, REQ-d00076-D
# Validates REQ-d00076-E, REQ-d00076-F, REQ-d00076-G
"""Tests for MCP cursor protocol.

Tests REQ-o00068: MCP Cursor Protocol
- CursorState
- _open_cursor()
- _cursor_next()
- _cursor_info()
- _materialize_cursor_items()

All tests verify correct incremental iteration over MCP query results.
"""

from pathlib import Path

import pytest

from elspais.graph import EdgeKind, GraphNode, NodeKind
from elspais.graph.builder import TraceGraph

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def cursor_graph():
    """Create a 3-level TraceGraph for cursor protocol tests.

    Hierarchy:
        PRD: REQ-p00001 "Platform Security" (level=PRD, status=Active)
          +-- Assertion A: "SHALL encrypt all data at rest"
          +-- Assertion B: "SHALL use TLS for transit"
          +-- OPS: REQ-o00010 "Security Operations" (implements PRD)
               +-- Assertion C: "SHALL rotate keys monthly"
               +-- DEV: REQ-d00020 "Encryption Module" (implements OPS)
                    +-- Assertion D: "SHALL use AES-256"
                    +-- Assertion E: "SHALL support key rotation API"

    Test node linked to assertion A for coverage testing.
    """
    graph = TraceGraph(repo_root=Path("/test/repo"))

    # --- PRD requirement ---
    req_prd = GraphNode(
        id="REQ-p00001",
        kind=NodeKind.REQUIREMENT,
        label="Platform Security",
    )
    req_prd._content = {"level": "PRD", "status": "Active", "hash": "abc12345"}

    # PRD assertions
    assertion_a = GraphNode(
        id="REQ-p00001-A",
        kind=NodeKind.ASSERTION,
        label="SHALL encrypt all data at rest",
    )
    assertion_a._content = {"label": "A", "text": "SHALL encrypt all data at rest"}
    req_prd.add_child(assertion_a)

    assertion_b = GraphNode(
        id="REQ-p00001-B",
        kind=NodeKind.ASSERTION,
        label="SHALL use TLS for transit",
    )
    assertion_b._content = {"label": "B", "text": "SHALL use TLS for transit"}
    req_prd.add_child(assertion_b)

    # --- OPS requirement ---
    req_ops = GraphNode(
        id="REQ-o00010",
        kind=NodeKind.REQUIREMENT,
        label="Security Operations",
    )
    req_ops._content = {"level": "OPS", "status": "Active", "hash": "def67890"}

    # OPS assertion
    assertion_c = GraphNode(
        id="REQ-o00010-C",
        kind=NodeKind.ASSERTION,
        label="SHALL rotate keys monthly",
    )
    assertion_c._content = {"label": "C", "text": "SHALL rotate keys monthly"}
    req_ops.add_child(assertion_c)

    # OPS implements PRD (parent-child + typed edge)
    req_prd.add_child(req_ops)
    req_ops.link(req_prd, EdgeKind.IMPLEMENTS)

    # --- DEV requirement ---
    req_dev = GraphNode(
        id="REQ-d00020",
        kind=NodeKind.REQUIREMENT,
        label="Encryption Module",
    )
    req_dev._content = {"level": "DEV", "status": "Active", "hash": "ghi11111"}

    # DEV assertions
    assertion_d = GraphNode(
        id="REQ-d00020-D",
        kind=NodeKind.ASSERTION,
        label="SHALL use AES-256",
    )
    assertion_d._content = {"label": "D", "text": "SHALL use AES-256"}
    req_dev.add_child(assertion_d)

    assertion_e = GraphNode(
        id="REQ-d00020-E",
        kind=NodeKind.ASSERTION,
        label="SHALL support key rotation API",
    )
    assertion_e._content = {"label": "E", "text": "SHALL support key rotation API"}
    req_dev.add_child(assertion_e)

    # DEV implements OPS (parent-child + typed edge)
    req_ops.add_child(req_dev)
    req_dev.link(req_ops, EdgeKind.IMPLEMENTS)

    # --- TEST node linked to assertion A for coverage ---
    test_node = GraphNode(
        id="test:test_enc.py::test_encryption",
        kind=NodeKind.TEST,
        label="test_encryption",
    )
    test_node._content = {"file": "test_enc.py", "name": "test_encryption"}
    assertion_a.link(test_node, EdgeKind.VALIDATES)

    # Register all nodes in graph index
    graph._index = {
        "REQ-p00001": req_prd,
        "REQ-p00001-A": assertion_a,
        "REQ-p00001-B": assertion_b,
        "REQ-o00010": req_ops,
        "REQ-o00010-C": assertion_c,
        "REQ-d00020": req_dev,
        "REQ-d00020-D": assertion_d,
        "REQ-d00020-E": assertion_e,
        "test:test_enc.py::test_encryption": test_node,
    }
    graph._roots = [req_prd]

    return graph


@pytest.fixture
def cursor_state(cursor_graph):
    """Create a state dict suitable for cursor functions."""
    return {"graph": cursor_graph, "working_dir": Path("/test/repo"), "config": {}}


# ─────────────────────────────────────────────────────────────────────────────
# Tests for CursorState - REQ-d00076-A
# ─────────────────────────────────────────────────────────────────────────────


class TestCursorState:
    """Validates REQ-d00076-A: CursorState stores query, params, batch_size, items, position."""

    def test_REQ_d00076_A_cursor_state_fields(self):
        """REQ-d00076-A: CursorState fields with position default 0."""
        from elspais.mcp.server import CursorState

        state = CursorState(
            query="subtree",
            params={"root_id": "REQ-p00001"},
            batch_size=0,
            items=[{"id": "REQ-p00001"}],
        )

        assert state.query == "subtree"
        assert state.params == {"root_id": "REQ-p00001"}
        assert state.batch_size == 0
        assert state.items == [{"id": "REQ-p00001"}]
        assert state.position == 0


# ─────────────────────────────────────────────────────────────────────────────
# Tests for _open_cursor() - REQ-o00068-A, REQ-o00068-D, REQ-d00076-C, REQ-d00076-D
# ─────────────────────────────────────────────────────────────────────────────


class TestOpenCursor:
    """Validates REQ-o00068-A, REQ-o00068-D, REQ-d00076-C, REQ-d00076-D: Opening cursors."""

    def test_REQ_o00068_A_open_cursor_returns_first_item(self, cursor_state):
        """REQ-o00068-A: Open cursor returns non-None current with id."""
        from elspais.mcp.server import _open_cursor

        result = _open_cursor(
            cursor_state,
            query="subtree",
            params={"root_id": "REQ-p00001"},
            batch_size=0,
        )

        assert result["success"] is True
        assert result["current"] is not None
        assert "id" in result["current"]

    def test_REQ_d00076_D_open_cursor_returns_metadata(self, cursor_state):
        """REQ-d00076-D: Response has all required metadata fields."""
        from elspais.mcp.server import _open_cursor

        result = _open_cursor(
            cursor_state,
            query="subtree",
            params={"root_id": "REQ-p00001"},
            batch_size=0,
        )

        assert "success" in result
        assert "query" in result
        assert "batch_size" in result
        assert "total" in result
        assert "position" in result
        assert "remaining" in result
        assert result["query"] == "subtree"
        assert result["batch_size"] == 0
        assert result["total"] > 0
        assert result["position"] == 1
        assert result["remaining"] == result["total"] - 1

    def test_REQ_o00068_D_new_cursor_replaces_previous(self, cursor_state):
        """REQ-o00068-D: Open two cursors sequentially, verify second replaces first."""
        from elspais.mcp.server import _open_cursor

        _open_cursor(
            cursor_state,
            query="subtree",
            params={"root_id": "REQ-p00001"},
            batch_size=0,
        )

        _open_cursor(
            cursor_state,
            query="search",
            params={"query": "Security"},
            batch_size=0,
        )

        assert cursor_state["cursor"].query == "search"

    def test_REQ_d00076_C_cursor_stored_in_state(self, cursor_state):
        """REQ-d00076-C: After open_cursor, state['cursor'] is a CursorState instance."""
        from elspais.mcp.server import CursorState, _open_cursor

        _open_cursor(
            cursor_state,
            query="subtree",
            params={"root_id": "REQ-p00001"},
            batch_size=0,
        )

        assert "cursor" in cursor_state
        assert isinstance(cursor_state["cursor"], CursorState)

    def test_REQ_o00068_A_open_cursor_empty_results(self, cursor_state):
        """REQ-o00068-A: Open cursor with non-existent root_id, verify current is None, total=0."""
        from elspais.mcp.server import _open_cursor

        result = _open_cursor(
            cursor_state,
            query="subtree",
            params={"root_id": "REQ-nonexistent"},
            batch_size=0,
        )

        assert result["success"] is True
        assert result["current"] is None
        assert result["total"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# Tests for _cursor_next() - REQ-o00068-B, REQ-d00076-E
# ─────────────────────────────────────────────────────────────────────────────


class TestCursorNext:
    """Validates REQ-o00068-B, REQ-d00076-E: Advancing cursor."""

    def test_REQ_o00068_B_cursor_next_returns_items(self, cursor_state):
        """REQ-o00068-B: Open cursor, call next(count=1), verify returns 1 item."""
        from elspais.mcp.server import _cursor_next, _open_cursor

        _open_cursor(
            cursor_state,
            query="subtree",
            params={"root_id": "REQ-p00001"},
            batch_size=0,
        )

        result = _cursor_next(cursor_state, count=1)

        assert result["success"] is True
        assert result["count"] == 1
        assert len(result["items"]) == 1

    def test_REQ_d00076_E_cursor_next_advances_position(self, cursor_state):
        """REQ-d00076-E: After next(count=2), position advances by 2."""
        from elspais.mcp.server import _cursor_next, _open_cursor

        _open_cursor(
            cursor_state,
            query="subtree",
            params={"root_id": "REQ-p00001"},
            batch_size=0,
        )

        # Position starts at 1 after open (first item consumed)
        pos_before = cursor_state["cursor"].position

        _cursor_next(cursor_state, count=2)

        assert cursor_state["cursor"].position == pos_before + 2

    def test_REQ_d00076_E_cursor_next_at_end_returns_empty(self, cursor_state):
        """REQ-d00076-E: Advance past all items, verify empty items list."""
        from elspais.mcp.server import _cursor_next, _open_cursor

        _open_cursor(
            cursor_state,
            query="subtree",
            params={"root_id": "REQ-p00001"},
            batch_size=0,
        )

        total = cursor_state["cursor"].items
        # Advance past all items
        _cursor_next(cursor_state, count=len(total))

        result = _cursor_next(cursor_state, count=1)

        assert result["success"] is True
        assert result["items"] == []
        assert result["count"] == 0
        assert result["remaining"] == 0

    def test_REQ_o00068_B_cursor_next_no_active_cursor(self, cursor_state):
        """REQ-o00068-B: Call next without opening, verify error message."""
        from elspais.mcp.server import _cursor_next

        result = _cursor_next(cursor_state, count=1)

        assert result["success"] is False
        assert "error" in result
        assert "no active cursor" in result["error"].lower()


# ─────────────────────────────────────────────────────────────────────────────
# Tests for _cursor_info() - REQ-o00068-C, REQ-d00076-F
# ─────────────────────────────────────────────────────────────────────────────


class TestCursorInfo:
    """Validates REQ-o00068-C, REQ-d00076-F: Cursor info without advancing."""

    def test_REQ_o00068_C_cursor_info_returns_position(self, cursor_state):
        """REQ-o00068-C: Open cursor, call info, verify position/total/remaining match."""
        from elspais.mcp.server import _cursor_info, _open_cursor

        open_result = _open_cursor(
            cursor_state,
            query="subtree",
            params={"root_id": "REQ-p00001"},
            batch_size=0,
        )

        info_result = _cursor_info(cursor_state)

        assert info_result["success"] is True
        assert info_result["position"] == open_result["position"]
        assert info_result["total"] == open_result["total"]
        assert info_result["remaining"] == open_result["remaining"]

    def test_REQ_d00076_F_cursor_info_does_not_advance(self, cursor_state):
        """REQ-d00076-F: Call info twice, position unchanged."""
        from elspais.mcp.server import _cursor_info, _open_cursor

        _open_cursor(
            cursor_state,
            query="subtree",
            params={"root_id": "REQ-p00001"},
            batch_size=0,
        )

        info1 = _cursor_info(cursor_state)
        info2 = _cursor_info(cursor_state)

        assert info1["position"] == info2["position"]
        assert info1["total"] == info2["total"]
        assert info1["remaining"] == info2["remaining"]

    def test_REQ_d00076_F_cursor_info_includes_query_metadata(self, cursor_state):
        """REQ-d00076-F: Verify response has 'query' and 'batch_size' fields."""
        from elspais.mcp.server import _cursor_info, _open_cursor

        _open_cursor(
            cursor_state,
            query="subtree",
            params={"root_id": "REQ-p00001"},
            batch_size=5,
        )

        info = _cursor_info(cursor_state)

        assert info["query"] == "subtree"
        assert info["batch_size"] == 5

    def test_REQ_o00068_C_cursor_info_no_active_cursor(self, cursor_state):
        """REQ-o00068-C: Call info without opening, verify error."""
        from elspais.mcp.server import _cursor_info

        result = _cursor_info(cursor_state)

        assert result["success"] is False
        assert "error" in result
        assert "no active cursor" in result["error"].lower()


# ─────────────────────────────────────────────────────────────────────────────
# Tests for _materialize_cursor_items() - REQ-d00076-B, REQ-o00068-E, REQ-o00068-F
# ─────────────────────────────────────────────────────────────────────────────


class TestMaterializeCursorItems:
    """Validates REQ-d00076-B, REQ-o00068-E, REQ-o00068-F:

    Query dispatch and batch_size reshaping.
    """

    def test_REQ_o00068_F_materialize_subtree_query(self, cursor_graph):
        """REQ-o00068-F: query='subtree' with root_id, verify returns non-empty list."""
        from elspais.mcp.server import _materialize_cursor_items

        items = _materialize_cursor_items(
            query="subtree",
            params={"root_id": "REQ-p00001"},
            batch_size=0,
            graph=cursor_graph,
        )

        assert isinstance(items, list)
        assert len(items) > 0
        # First item should be the root requirement
        assert items[0]["id"] == "REQ-p00001"

    def test_REQ_o00068_F_materialize_search_query(self, cursor_graph):
        """REQ-o00068-F: query='search' with query='Security', verify returns matching items."""
        from elspais.mcp.server import _materialize_cursor_items

        items = _materialize_cursor_items(
            query="search",
            params={"query": "Security"},
            batch_size=0,
            graph=cursor_graph,
        )

        assert isinstance(items, list)
        assert len(items) > 0
        # All results should have 'Security' in their title
        for item in items:
            assert "security" in item["title"].lower()

    def test_REQ_o00068_F_materialize_hierarchy_query(self, cursor_graph):
        """REQ-o00068-F: query='hierarchy' with req_id, verify returns items with _section keys."""
        from elspais.mcp.server import _materialize_cursor_items

        items = _materialize_cursor_items(
            query="hierarchy",
            params={"req_id": "REQ-o00010"},
            batch_size=0,
            graph=cursor_graph,
        )

        assert isinstance(items, list)
        assert len(items) > 0
        # Each item should have a _section key
        for item in items:
            assert "_section" in item
            assert item["_section"] in ("ancestor", "child")

    def test_REQ_o00068_F_materialize_unknown_query(self, cursor_graph):
        """REQ-o00068-F: query='unknown', verify returns empty list."""
        from elspais.mcp.server import _materialize_cursor_items

        items = _materialize_cursor_items(
            query="unknown",
            params={},
            batch_size=0,
            graph=cursor_graph,
        )

        assert items == []

    def test_REQ_o00068_E_batch_size_minus_one_assertions_first_class(self, cursor_graph):
        """REQ-o00068-E: batch_size=-1 emits assertions as items."""
        from elspais.mcp.server import _materialize_cursor_items

        items = _materialize_cursor_items(
            query="subtree",
            params={"root_id": "REQ-p00001"},
            batch_size=-1,
            graph=cursor_graph,
        )

        # Find assertion items (they have 'label' key from _serialize_assertion)
        assertion_items = [i for i in items if "label" in i]
        assert len(assertion_items) >= 1

        # Assertions should be separate items, not nested inside requirements
        req_items = [i for i in items if i.get("kind") == "requirement"]
        for req_item in req_items:
            assert "assertions" not in req_item

    def test_REQ_o00068_E_batch_size_zero_assertions_inline(self, cursor_graph):
        """REQ-o00068-E: batch_size=0 inlines assertions and coverage."""
        from elspais.mcp.server import _materialize_cursor_items

        items = _materialize_cursor_items(
            query="subtree",
            params={"root_id": "REQ-p00001"},
            batch_size=0,
            graph=cursor_graph,
        )

        # Find requirement items
        req_items = [i for i in items if i.get("kind") == "requirement"]
        assert len(req_items) >= 1

        for req_item in req_items:
            assert "assertions" in req_item
            assert isinstance(req_item["assertions"], list)
            assert "coverage" in req_item
            assert isinstance(req_item["coverage"], dict)

    def test_REQ_o00068_E_batch_size_one_with_children(self, cursor_graph):
        """REQ-o00068-E: batch_size=1, subtree query: requirement items have 'children' list."""
        from elspais.mcp.server import _materialize_cursor_items

        items = _materialize_cursor_items(
            query="subtree",
            params={"root_id": "REQ-p00001"},
            batch_size=1,
            graph=cursor_graph,
        )

        # Find the root requirement which has child requirements
        root_item = next(i for i in items if i["id"] == "REQ-p00001")
        assert "children" in root_item
        assert isinstance(root_item["children"], list)

    def test_REQ_d00076_G_reuses_existing_serializers(self, cursor_graph):
        """REQ-d00076-G: Items match existing serializer output."""
        from elspais.mcp.server import _materialize_cursor_items

        items = _materialize_cursor_items(
            query="subtree",
            params={"root_id": "REQ-p00001"},
            batch_size=0,
            graph=cursor_graph,
        )

        # Find a requirement with inline assertions
        req_with_assertions = next(
            i for i in items if i.get("kind") == "requirement" and len(i.get("assertions", [])) > 0
        )

        # Each assertion should have id, label, text keys (from _serialize_assertion)
        for assertion in req_with_assertions["assertions"]:
            assert "id" in assertion
            assert "label" in assertion
            assert "text" in assertion


# ─────────────────────────────────────────────────────────────────────────────
# Tests for full cursor lifecycle - REQ-o00068-A through REQ-o00068-C
# ─────────────────────────────────────────────────────────────────────────────


class TestCursorFullWorkflow:
    """Validates REQ-o00068-A through REQ-o00068-C: Complete cursor lifecycle."""

    def test_REQ_o00068_A_full_iteration_lifecycle(self, cursor_state):
        """REQ-o00068-A: Full open->info->iterate->end lifecycle."""
        from elspais.mcp.server import _cursor_info, _cursor_next, _open_cursor

        # Step 1: Open cursor
        open_result = _open_cursor(
            cursor_state,
            query="subtree",
            params={"root_id": "REQ-p00001"},
            batch_size=0,
        )
        assert open_result["success"] is True
        total = open_result["total"]
        assert total > 0

        # Step 2: Get info (should not advance)
        info = _cursor_info(cursor_state)
        assert info["position"] == 1  # open consumed first item
        assert info["total"] == total

        # Step 3: Iterate through remaining items one at a time
        collected_items = []
        while True:
            result = _cursor_next(cursor_state, count=1)
            assert result["success"] is True
            if result["count"] == 0:
                break
            collected_items.extend(result["items"])

        # Step 4: Verify we reached the end
        final_info = _cursor_info(cursor_state)
        assert final_info["remaining"] == 0
        assert final_info["position"] == total

        # We should have collected total - 1 items via next (first was in open)
        assert len(collected_items) == total - 1
