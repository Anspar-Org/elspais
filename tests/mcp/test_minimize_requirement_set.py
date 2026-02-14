# Validates REQ-o00069-A, REQ-o00069-B, REQ-o00069-C, REQ-o00069-D, REQ-o00069-E
# Validates REQ-d00077-A, REQ-d00077-B, REQ-d00077-C, REQ-d00077-D, REQ-d00077-E, REQ-d00077-F
"""Tests for _minimize_requirement_set() helper and minimize_requirement_set MCP tool.

Validates REQ-o00069-A, REQ-o00069-B, REQ-o00069-C, REQ-o00069-D, REQ-o00069-E:
  OPS-level specification for minimize_requirement_set feature.

Validates REQ-d00077-A, REQ-d00077-B, REQ-d00077-C, REQ-d00077-D, REQ-d00077-E, REQ-d00077-F:
  DEV-level specification for _minimize_requirement_set helper and MCP wrapper.
"""

from pathlib import Path

import pytest

from elspais.graph import GraphNode, NodeKind
from elspais.graph.builder import TraceGraph
from elspais.graph.relations import EdgeKind

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


def _make_req(req_id: str, label: str, level: str, status: str = "Active") -> GraphNode:
    """Create a REQUIREMENT node with standard content fields."""
    node = GraphNode(id=req_id, kind=NodeKind.REQUIREMENT, label=label)
    node._content = {"level": level, "status": status, "hash": f"h_{req_id}"}
    return node


@pytest.fixture
def empty_graph():
    """An empty TraceGraph with no nodes."""
    return TraceGraph(repo_root=Path("/test/repo"))


@pytest.fixture
def linear_chain_graph():
    """Graph with a linear chain: DEV -> OPS -> PRD (implements edges).

    A (DEV) implements B (OPS) implements C (PRD).
    """
    graph = TraceGraph(repo_root=Path("/test/repo"))

    c = _make_req("REQ-p00001", "PRD Requirement", "PRD")
    b = _make_req("REQ-o00001", "OPS Requirement", "OPS")
    a = _make_req("REQ-d00001", "DEV Requirement", "DEV")

    # A implements B, B implements C
    # source=child (more specific), target=parent (ancestor)
    a.link(b, EdgeKind.IMPLEMENTS)
    b.link(c, EdgeKind.IMPLEMENTS)

    graph._roots = [c]
    graph._index = {
        "REQ-p00001": c,
        "REQ-o00001": b,
        "REQ-d00001": a,
    }
    return graph


@pytest.fixture
def diamond_graph():
    """Graph with a diamond: C implements A and B, both A and B implement P.

    P (PRD)
    ├── A (OPS) implements P
    └── B (OPS) implements P
         └── C (DEV) implements A AND B
    """
    graph = TraceGraph(repo_root=Path("/test/repo"))

    p = _make_req("REQ-p00001", "PRD Top", "PRD")
    a = _make_req("REQ-o00001", "OPS-A", "OPS")
    b = _make_req("REQ-o00002", "OPS-B", "OPS")
    c = _make_req("REQ-d00001", "DEV-C", "DEV")

    # A and B implement P (source=child, target=parent)
    a.link(p, EdgeKind.IMPLEMENTS)
    b.link(p, EdgeKind.IMPLEMENTS)

    # C implements both A and B (source=child, target=parent)
    c.link(a, EdgeKind.IMPLEMENTS)
    c.link(b, EdgeKind.IMPLEMENTS)

    graph._roots = [p]
    graph._index = {
        "REQ-p00001": p,
        "REQ-o00001": a,
        "REQ-o00002": b,
        "REQ-d00001": c,
    }
    return graph


@pytest.fixture
def mixed_edges_graph():
    """Graph with both IMPLEMENTS and REFINES edges.

    B (OPS) --implements--> A (PRD)
    C (DEV) --refines-----> B (OPS)
    """
    graph = TraceGraph(repo_root=Path("/test/repo"))

    a = _make_req("REQ-p00001", "PRD Req", "PRD")
    b = _make_req("REQ-o00001", "OPS Req", "OPS")
    c = _make_req("REQ-d00001", "DEV Req", "DEV")

    # B implements A (source=child, target=parent)
    b.link(a, EdgeKind.IMPLEMENTS)
    # C refines B (source=child, target=parent)
    c.link(b, EdgeKind.REFINES)

    graph._roots = [a]
    graph._index = {
        "REQ-p00001": a,
        "REQ-o00001": b,
        "REQ-d00001": c,
    }
    return graph


@pytest.fixture
def disjoint_graph():
    """Graph with two unconnected requirements (no edges between them)."""
    graph = TraceGraph(repo_root=Path("/test/repo"))

    x = _make_req("REQ-p00001", "Req X", "PRD")
    y = _make_req("REQ-p00002", "Req Y", "PRD")

    graph._roots = [x, y]
    graph._index = {
        "REQ-p00001": x,
        "REQ-p00002": y,
    }
    return graph


# ─────────────────────────────────────────────────────────────────────────────
# Tests: _minimize_requirement_set() helper
# ─────────────────────────────────────────────────────────────────────────────


class TestMinimizeRequirementSetHelper:
    """Tests for _minimize_requirement_set() helper function.

    Validates REQ-o00069-A, REQ-o00069-B, REQ-o00069-C, REQ-o00069-D, REQ-o00069-E:
    Validates REQ-d00077-A, REQ-d00077-B, REQ-d00077-C, REQ-d00077-D, REQ-d00077-E, REQ-d00077-F:
    """

    def test_REQ_o00069_A_empty_input_returns_empty_result(self, empty_graph):
        """REQ-o00069-A: Empty input returns empty result with zero stats."""
        from elspais.mcp.server import _minimize_requirement_set

        result = _minimize_requirement_set(empty_graph, [], {EdgeKind.IMPLEMENTS, EdgeKind.REFINES})

        assert result["minimal_set"] == []
        assert result["pruned"] == []
        assert result["not_found"] == []
        assert result["stats"]["input_count"] == 0
        assert result["stats"]["minimal_count"] == 0
        assert result["stats"]["pruned_count"] == 0

    def test_REQ_o00069_B_single_req_unchanged(self, linear_chain_graph):
        """REQ-o00069-B: Single requirement returns it unchanged in minimal_set."""
        from elspais.mcp.server import _minimize_requirement_set

        result = _minimize_requirement_set(
            linear_chain_graph,
            ["REQ-d00001"],
            {EdgeKind.IMPLEMENTS},
        )

        assert len(result["minimal_set"]) == 1
        assert result["minimal_set"][0]["id"] == "REQ-d00001"
        assert result["pruned"] == []
        assert result["not_found"] == []
        assert result["stats"]["input_count"] == 1
        assert result["stats"]["minimal_count"] == 1
        assert result["stats"]["pruned_count"] == 0

    def test_REQ_o00069_C_linear_chain_prunes_ancestor(self, linear_chain_graph):
        """REQ-o00069-C: Linear chain A->B->C with input {A, C} prunes C (the ancestor).

        A (DEV) implements B (OPS) implements C (PRD).
        Input {A, C}: A is more specific, C is ancestor of A => prune C.
        """
        from elspais.mcp.server import _minimize_requirement_set

        result = _minimize_requirement_set(
            linear_chain_graph,
            ["REQ-d00001", "REQ-p00001"],
            {EdgeKind.IMPLEMENTS},
        )

        minimal_ids = {r["id"] for r in result["minimal_set"]}
        pruned_ids = {r["id"] for r in result["pruned"]}

        assert minimal_ids == {"REQ-d00001"}
        assert pruned_ids == {"REQ-p00001"}
        assert result["stats"]["minimal_count"] == 1
        assert result["stats"]["pruned_count"] == 1

    def test_REQ_o00069_D_diamond_yields_leaf(self, diamond_graph):
        """REQ-o00069-D: Diamond — C impl A+B, both impl P; {A,B,C,P} -> {C}.

        C is the most specific; A, B, and P are all ancestors of C.
        """
        from elspais.mcp.server import _minimize_requirement_set

        result = _minimize_requirement_set(
            diamond_graph,
            ["REQ-o00001", "REQ-o00002", "REQ-d00001", "REQ-p00001"],
            {EdgeKind.IMPLEMENTS},
        )

        minimal_ids = {r["id"] for r in result["minimal_set"]}
        pruned_ids = {r["id"] for r in result["pruned"]}

        assert minimal_ids == {"REQ-d00001"}
        assert pruned_ids == {"REQ-o00001", "REQ-o00002", "REQ-p00001"}
        assert result["stats"]["input_count"] == 4
        assert result["stats"]["minimal_count"] == 1
        assert result["stats"]["pruned_count"] == 3

    def test_REQ_d00077_A_unknown_ids_in_not_found(self, linear_chain_graph):
        """REQ-d00077-A: Unknown IDs appear in not_found list."""
        from elspais.mcp.server import _minimize_requirement_set

        result = _minimize_requirement_set(
            linear_chain_graph,
            ["REQ-d00001", "REQ-NONEXISTENT", "REQ-FAKE123"],
            {EdgeKind.IMPLEMENTS},
        )

        assert "REQ-NONEXISTENT" in result["not_found"]
        assert "REQ-FAKE123" in result["not_found"]
        assert len(result["not_found"]) == 2
        # The valid one should still be in minimal_set
        assert len(result["minimal_set"]) == 1
        assert result["minimal_set"][0]["id"] == "REQ-d00001"

    def test_REQ_d00077_B_implements_only_excludes_refines(self, mixed_edges_graph):
        """REQ-d00077-B: edge_kinds={IMPLEMENTS} does not follow REFINES edges.

        B --implements--> A, C --refines--> B.
        With implements-only: C's ancestors via refines are NOT traversed.
        Input {B, C}: C does not reach B via implements => both kept.
        """
        from elspais.mcp.server import _minimize_requirement_set

        result = _minimize_requirement_set(
            mixed_edges_graph,
            ["REQ-o00001", "REQ-d00001"],
            {EdgeKind.IMPLEMENTS},  # Only IMPLEMENTS
        )

        minimal_ids = {r["id"] for r in result["minimal_set"]}

        # C (DEV) only refines B (OPS), no IMPLEMENTS edge.
        # With implements-only, C has no ancestor among the input set.
        # B has no descendant among the input set via implements.
        # Both should be kept.
        assert minimal_ids == {"REQ-o00001", "REQ-d00001"}
        assert result["pruned"] == []

    def test_REQ_d00077_C_default_edge_kinds_follows_both(self, mixed_edges_graph):
        """REQ-d00077-C: Default edge_kinds={IMPLEMENTS, REFINES} follows both edge types.

        B --implements--> A, C --refines--> B.
        Input {B, C}: C refines B => B is ancestor of C => prune B.
        """
        from elspais.mcp.server import _minimize_requirement_set

        result = _minimize_requirement_set(
            mixed_edges_graph,
            ["REQ-o00001", "REQ-d00001"],
            {EdgeKind.IMPLEMENTS, EdgeKind.REFINES},
        )

        minimal_ids = {r["id"] for r in result["minimal_set"]}
        pruned_ids = {r["id"] for r in result["pruned"]}

        assert minimal_ids == {"REQ-d00001"}
        assert pruned_ids == {"REQ-o00001"}

    def test_REQ_d00077_D_pruned_has_superseded_by(self, linear_chain_graph):
        """REQ-d00077-D: Pruned entries include superseded_by list."""
        from elspais.mcp.server import _minimize_requirement_set

        result = _minimize_requirement_set(
            linear_chain_graph,
            ["REQ-d00001", "REQ-p00001"],
            {EdgeKind.IMPLEMENTS},
        )

        assert len(result["pruned"]) == 1
        pruned_entry = result["pruned"][0]
        assert pruned_entry["id"] == "REQ-p00001"
        assert "superseded_by" in pruned_entry
        assert "REQ-d00001" in pruned_entry["superseded_by"]

    def test_REQ_d00077_E_stats_structure(self, diamond_graph):
        """REQ-d00077-E: Returns stats with input_count, minimal_count, pruned_count."""
        from elspais.mcp.server import _minimize_requirement_set

        result = _minimize_requirement_set(
            diamond_graph,
            ["REQ-o00001", "REQ-d00001", "REQ-NOPE"],
            {EdgeKind.IMPLEMENTS},
        )

        stats = result["stats"]
        assert stats["input_count"] == 3
        assert stats["minimal_count"] == 1  # REQ-d00001
        assert stats["pruned_count"] == 1  # REQ-o00001 pruned

    def test_REQ_o00069_E_no_edges_between_inputs_keeps_all(self, disjoint_graph):
        """REQ-o00069-E: If no edges exist between inputs, all are kept."""
        from elspais.mcp.server import _minimize_requirement_set

        result = _minimize_requirement_set(
            disjoint_graph,
            ["REQ-p00001", "REQ-p00002"],
            {EdgeKind.IMPLEMENTS, EdgeKind.REFINES},
        )

        minimal_ids = {r["id"] for r in result["minimal_set"]}

        assert minimal_ids == {"REQ-p00001", "REQ-p00002"}
        assert result["pruned"] == []
        assert result["stats"]["minimal_count"] == 2
        assert result["stats"]["pruned_count"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# Tests: minimize_requirement_set MCP tool wrapper
# ─────────────────────────────────────────────────────────────────────────────


class TestMinimizeRequirementSetMCPTool:
    """Tests for minimize_requirement_set() MCP tool wrapper.

    Validates REQ-d00077-F:
    """

    def test_REQ_d00077_F_tool_is_registered(self, linear_chain_graph):
        """REQ-d00077-F: minimize_requirement_set is registered as an MCP tool."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import create_server

        server = create_server(linear_chain_graph)

        tool_names = [t.name for t in server._tool_manager._tools.values()]
        assert "minimize_requirement_set" in tool_names

    def test_REQ_d00077_F_wrapper_delegates_to_helper(self, linear_chain_graph):
        """REQ-d00077-F: MCP wrapper delegates to _minimize_requirement_set helper.

        Verifies by patching the helper and calling the inner tool function.
        """
        pytest.importorskip("mcp")
        from unittest.mock import patch

        from elspais.mcp.server import create_server

        server = create_server(linear_chain_graph)

        # Get the tool function from the server's tool manager
        tool_obj = server._tool_manager._tools["minimize_requirement_set"]
        tool_fn = tool_obj.fn

        with patch("elspais.mcp.server._minimize_requirement_set") as mock_helper:
            mock_helper.return_value = {
                "minimal_set": [],
                "pruned": [],
                "not_found": [],
                "stats": {"input_count": 0, "minimal_count": 0, "pruned_count": 0},
            }

            tool_fn(["REQ-d00001"], "implements")

            mock_helper.assert_called_once()
            call_args = mock_helper.call_args
            assert call_args[0][1] == ["REQ-d00001"]
            assert EdgeKind.IMPLEMENTS in call_args[0][2]

    def test_REQ_d00077_F_parses_implements_edge_kind(self, linear_chain_graph):
        """REQ-d00077-F: Parses 'implements' edge_kinds string to {EdgeKind.IMPLEMENTS}."""
        pytest.importorskip("mcp")
        from unittest.mock import patch

        from elspais.mcp.server import create_server

        server = create_server(linear_chain_graph)
        tool_fn = server._tool_manager._tools["minimize_requirement_set"].fn

        with patch("elspais.mcp.server._minimize_requirement_set") as mock_helper:
            mock_helper.return_value = {
                "minimal_set": [],
                "pruned": [],
                "not_found": [],
                "stats": {"input_count": 0, "minimal_count": 0, "pruned_count": 0},
            }

            tool_fn(["REQ-d00001"], "implements")

            parsed_kinds = mock_helper.call_args[0][2]
            assert parsed_kinds == {EdgeKind.IMPLEMENTS}

    def test_REQ_d00077_F_parses_default_edge_kinds(self, linear_chain_graph):
        """REQ-d00077-F: Default edge_kinds='implements,refines' parses both."""
        pytest.importorskip("mcp")
        from unittest.mock import patch

        from elspais.mcp.server import create_server

        server = create_server(linear_chain_graph)
        tool_fn = server._tool_manager._tools["minimize_requirement_set"].fn

        with patch("elspais.mcp.server._minimize_requirement_set") as mock_helper:
            mock_helper.return_value = {
                "minimal_set": [],
                "pruned": [],
                "not_found": [],
                "stats": {"input_count": 0, "minimal_count": 0, "pruned_count": 0},
            }

            tool_fn(["REQ-d00001"])  # Use default edge_kinds

            parsed_kinds = mock_helper.call_args[0][2]
            assert parsed_kinds == {EdgeKind.IMPLEMENTS, EdgeKind.REFINES}
