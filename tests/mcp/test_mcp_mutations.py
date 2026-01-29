"""Tests for MCP mutation tools.

Tests REQ-o00062: MCP Graph Mutation Tools
Tests REQ-d00065: Mutation Tool Delegation

All mutation tools must:
- Delegate to TraceGraph mutation methods (REQ-o00062-D, REQ-d00065-D)
- Return MutationEntry for audit (REQ-o00062-E)
- Require confirm=True for destructive operations (REQ-o00062-F)
"""

from pathlib import Path

import pytest

from elspais.graph import GraphNode, NodeKind
from elspais.graph.builder import TraceGraph
from elspais.graph.mutations import BrokenReference
from elspais.graph.relations import EdgeKind

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def mutation_graph():
    """Create a TraceGraph with mutation support for testing."""
    graph = TraceGraph(repo_root=Path("/test/repo"))

    # Create PRD requirement with assertions
    prd_node = GraphNode(
        id="REQ-p00001",
        kind=NodeKind.REQUIREMENT,
        label="Platform Security",
    )
    prd_node._content = {
        "level": "PRD",
        "status": "Active",
        "hash": "abc12345",
        "body": "The platform shall be secure.",
    }

    # Add assertions
    assertion_a = GraphNode(
        id="REQ-p00001-A",
        kind=NodeKind.ASSERTION,
        label="SHALL encrypt all data at rest",
    )
    assertion_a._content = {"label": "A", "text": "SHALL encrypt all data at rest"}
    prd_node.add_child(assertion_a)

    assertion_b = GraphNode(
        id="REQ-p00001-B",
        kind=NodeKind.ASSERTION,
        label="SHALL use TLS 1.3 for transit",
    )
    assertion_b._content = {"label": "B", "text": "SHALL use TLS 1.3 for transit"}
    prd_node.add_child(assertion_b)

    # Create OPS requirement that implements PRD
    ops_node = GraphNode(
        id="REQ-o00001",
        kind=NodeKind.REQUIREMENT,
        label="Database Encryption",
    )
    ops_node._content = {
        "level": "OPS",
        "status": "Active",
        "hash": "def67890",
        "body": "Database encryption operations.",
    }

    # Link PRD -> OPS
    prd_node.link(ops_node, EdgeKind.IMPLEMENTS)

    # Build graph
    graph._roots = [prd_node]
    graph._index = {
        "REQ-p00001": prd_node,
        "REQ-p00001-A": assertion_a,
        "REQ-p00001-B": assertion_b,
        "REQ-o00001": ops_node,
    }

    return graph


# ─────────────────────────────────────────────────────────────────────────────
# Test: Node Mutations - REQ-o00062-A
# ─────────────────────────────────────────────────────────────────────────────


class TestMutateRenameNode:
    """Tests for mutate_rename_node() tool."""

    def test_REQ_d00065_A_delegates_to_graph_rename_node(self, mutation_graph):
        """REQ-d00065-A: Delegates to graph.rename_node()."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_rename_node

        result = _mutate_rename_node(mutation_graph, "REQ-o00001", "REQ-o00099")

        assert result["success"] is True
        # Verify node was renamed in graph
        assert mutation_graph.find_by_id("REQ-o00099") is not None
        assert mutation_graph.find_by_id("REQ-o00001") is None

    def test_REQ_o00062_E_returns_mutation_entry(self, mutation_graph):
        """REQ-o00062-E: Returns MutationEntry for audit."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_rename_node

        result = _mutate_rename_node(mutation_graph, "REQ-o00001", "REQ-o00099")

        assert "mutation" in result
        mutation = result["mutation"]
        assert mutation["operation"] == "rename_node"
        assert mutation["target_id"] == "REQ-o00001"
        assert "before_state" in mutation
        assert "after_state" in mutation

    def test_rename_nonexistent_node_returns_error(self, mutation_graph):
        """Renaming non-existent node returns error."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_rename_node

        result = _mutate_rename_node(mutation_graph, "REQ-NONEXISTENT", "REQ-NEW")

        assert result["success"] is False
        assert "error" in result


class TestMutateUpdateTitle:
    """Tests for mutate_update_title() tool."""

    def test_delegates_to_graph_update_title(self, mutation_graph):
        """Delegates to graph.update_title()."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_update_title

        result = _mutate_update_title(mutation_graph, "REQ-p00001", "Updated Platform Security")

        assert result["success"] is True
        node = mutation_graph.find_by_id("REQ-p00001")
        assert node.get_label() == "Updated Platform Security"

    def test_returns_mutation_entry(self, mutation_graph):
        """Returns MutationEntry for audit."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_update_title

        result = _mutate_update_title(mutation_graph, "REQ-p00001", "New Title")

        assert "mutation" in result
        mutation = result["mutation"]
        assert mutation["operation"] == "update_title"


class TestMutateChangeStatus:
    """Tests for mutate_change_status() tool."""

    def test_delegates_to_graph_change_status(self, mutation_graph):
        """Delegates to graph.change_status()."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_change_status

        result = _mutate_change_status(mutation_graph, "REQ-p00001", "Deprecated")

        assert result["success"] is True
        node = mutation_graph.find_by_id("REQ-p00001")
        assert node.status == "Deprecated"

    def test_returns_mutation_entry(self, mutation_graph):
        """Returns MutationEntry for audit."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_change_status

        result = _mutate_change_status(mutation_graph, "REQ-p00001", "Draft")

        assert "mutation" in result
        assert result["mutation"]["operation"] == "change_status"


class TestMutateAddRequirement:
    """Tests for mutate_add_requirement() tool."""

    def test_REQ_d00065_B_delegates_to_graph_add_requirement(self, mutation_graph):
        """REQ-d00065-B: Delegates to graph.add_requirement()."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_add_requirement

        result = _mutate_add_requirement(
            mutation_graph,
            req_id="REQ-d00001",
            title="New DEV Requirement",
            level="DEV",
            status="Draft",
            parent_id="REQ-o00001",
            edge_kind="IMPLEMENTS",
        )

        assert result["success"] is True
        node = mutation_graph.find_by_id("REQ-d00001")
        assert node is not None
        assert node.get_label() == "New DEV Requirement"

    def test_returns_mutation_entry(self, mutation_graph):
        """Returns MutationEntry for audit."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_add_requirement

        result = _mutate_add_requirement(
            mutation_graph,
            req_id="REQ-d00002",
            title="Another Requirement",
            level="DEV",
            status="Draft",
        )

        assert "mutation" in result
        assert result["mutation"]["operation"] == "add_requirement"


class TestMutateDeleteRequirement:
    """Tests for mutate_delete_requirement() tool."""

    def test_REQ_o00062_F_requires_confirm_true(self, mutation_graph):
        """REQ-o00062-F: Requires confirm=True for destructive operations."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_delete_requirement

        # Without confirm=True, should NOT delete
        result = _mutate_delete_requirement(mutation_graph, "REQ-o00001", confirm=False)

        assert result["success"] is False
        assert "confirm" in result["error"].lower()
        # Node should still exist
        assert mutation_graph.find_by_id("REQ-o00001") is not None

    def test_REQ_d00065_C_deletes_when_confirmed(self, mutation_graph):
        """REQ-d00065-C: Calls graph.delete_requirement() only if confirm=True."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_delete_requirement

        result = _mutate_delete_requirement(mutation_graph, "REQ-o00001", confirm=True)

        assert result["success"] is True
        assert mutation_graph.find_by_id("REQ-o00001") is None

    def test_returns_mutation_entry(self, mutation_graph):
        """Returns MutationEntry for audit."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_delete_requirement

        result = _mutate_delete_requirement(mutation_graph, "REQ-o00001", confirm=True)

        assert "mutation" in result
        assert result["mutation"]["operation"] == "delete_requirement"


# ─────────────────────────────────────────────────────────────────────────────
# Test: Assertion Mutations - REQ-o00062-B
# ─────────────────────────────────────────────────────────────────────────────


class TestMutateAddAssertion:
    """Tests for mutate_add_assertion() tool."""

    def test_delegates_to_graph_add_assertion(self, mutation_graph):
        """Delegates to graph.add_assertion()."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_add_assertion

        result = _mutate_add_assertion(
            mutation_graph,
            req_id="REQ-p00001",
            label="C",
            text="SHALL log all access attempts",
        )

        assert result["success"] is True
        assertion = mutation_graph.find_by_id("REQ-p00001-C")
        assert assertion is not None
        assert assertion.get_label() == "SHALL log all access attempts"

    def test_returns_mutation_entry(self, mutation_graph):
        """Returns MutationEntry for audit."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_add_assertion

        result = _mutate_add_assertion(mutation_graph, "REQ-p00001", "C", "New assertion text")

        assert "mutation" in result
        assert result["mutation"]["operation"] == "add_assertion"


class TestMutateUpdateAssertion:
    """Tests for mutate_update_assertion() tool."""

    def test_delegates_to_graph_update_assertion(self, mutation_graph):
        """Delegates to graph.update_assertion()."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_update_assertion

        result = _mutate_update_assertion(
            mutation_graph, "REQ-p00001-A", "SHALL encrypt ALL data at rest using AES-256"
        )

        assert result["success"] is True
        assertion = mutation_graph.find_by_id("REQ-p00001-A")
        assert "AES-256" in assertion.get_label()

    def test_returns_mutation_entry(self, mutation_graph):
        """Returns MutationEntry for audit."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_update_assertion

        result = _mutate_update_assertion(mutation_graph, "REQ-p00001-A", "Updated text")

        assert "mutation" in result
        assert result["mutation"]["operation"] == "update_assertion"


class TestMutateDeleteAssertion:
    """Tests for mutate_delete_assertion() tool."""

    def test_requires_confirm_true(self, mutation_graph):
        """Requires confirm=True for destructive operations."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_delete_assertion

        result = _mutate_delete_assertion(mutation_graph, "REQ-p00001-A", confirm=False)

        assert result["success"] is False
        assert mutation_graph.find_by_id("REQ-p00001-A") is not None

    def test_deletes_when_confirmed(self, mutation_graph):
        """Deletes assertion when confirmed."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_delete_assertion

        # Store original assertion ID before deletion
        original_text = mutation_graph.find_by_id("REQ-p00001-A").get_label()

        result = _mutate_delete_assertion(mutation_graph, "REQ-p00001-A", confirm=True)

        assert result["success"] is True
        # After deletion with compact=True, REQ-p00001-A now has what was REQ-p00001-B
        # Check that the original assertion text is no longer at A
        if mutation_graph.find_by_id("REQ-p00001-A"):
            # A still exists but has different content (was B, now compacted to A)
            assert mutation_graph.find_by_id("REQ-p00001-A").get_label() != original_text

    def test_returns_mutation_entry(self, mutation_graph):
        """Returns MutationEntry for audit."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_delete_assertion

        result = _mutate_delete_assertion(mutation_graph, "REQ-p00001-A", confirm=True)

        assert "mutation" in result
        assert result["mutation"]["operation"] == "delete_assertion"


class TestMutateRenameAssertion:
    """Tests for mutate_rename_assertion() tool."""

    def test_delegates_to_graph_rename_assertion(self, mutation_graph):
        """Delegates to graph.rename_assertion()."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_rename_assertion

        result = _mutate_rename_assertion(mutation_graph, "REQ-p00001-A", "X")

        assert result["success"] is True
        assert mutation_graph.find_by_id("REQ-p00001-X") is not None
        assert mutation_graph.find_by_id("REQ-p00001-A") is None

    def test_returns_mutation_entry(self, mutation_graph):
        """Returns MutationEntry for audit."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_rename_assertion

        result = _mutate_rename_assertion(mutation_graph, "REQ-p00001-A", "X")

        assert "mutation" in result
        assert result["mutation"]["operation"] == "rename_assertion"


# ─────────────────────────────────────────────────────────────────────────────
# Test: Edge Mutations - REQ-o00062-C
# ─────────────────────────────────────────────────────────────────────────────


class TestMutateAddEdge:
    """Tests for mutate_add_edge() tool."""

    def test_delegates_to_graph_add_edge(self, mutation_graph):
        """Delegates to graph.add_edge()."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_add_edge

        # Add a new DEV requirement first
        dev_node = GraphNode(
            id="REQ-d00001",
            kind=NodeKind.REQUIREMENT,
            label="DEV Requirement",
        )
        dev_node._content = {"level": "DEV", "status": "Draft"}
        mutation_graph._index["REQ-d00001"] = dev_node

        result = _mutate_add_edge(
            mutation_graph,
            source_id="REQ-d00001",
            target_id="REQ-o00001",
            edge_kind="IMPLEMENTS",
        )

        assert result["success"] is True

    def test_returns_mutation_entry(self, mutation_graph):
        """Returns MutationEntry for audit."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_add_edge

        # Setup node
        dev_node = GraphNode(
            id="REQ-d00002",
            kind=NodeKind.REQUIREMENT,
            label="Another DEV",
        )
        dev_node._content = {"level": "DEV", "status": "Draft"}
        mutation_graph._index["REQ-d00002"] = dev_node

        result = _mutate_add_edge(mutation_graph, "REQ-d00002", "REQ-o00001", "IMPLEMENTS")

        assert "mutation" in result
        assert result["mutation"]["operation"] == "add_edge"


class TestMutateChangeEdgeKind:
    """Tests for mutate_change_edge_kind() tool."""

    def test_delegates_to_graph_change_edge_kind(self, mutation_graph):
        """Delegates to graph.change_edge_kind()."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_change_edge_kind

        # Change IMPLEMENTS to REFINES
        result = _mutate_change_edge_kind(mutation_graph, "REQ-o00001", "REQ-p00001", "REFINES")

        assert result["success"] is True

    def test_returns_mutation_entry(self, mutation_graph):
        """Returns MutationEntry for audit."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_change_edge_kind

        result = _mutate_change_edge_kind(mutation_graph, "REQ-o00001", "REQ-p00001", "REFINES")

        assert "mutation" in result
        assert result["mutation"]["operation"] == "change_edge_kind"


class TestMutateDeleteEdge:
    """Tests for mutate_delete_edge() tool."""

    def test_requires_confirm_true(self, mutation_graph):
        """Requires confirm=True for destructive operations."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_delete_edge

        result = _mutate_delete_edge(mutation_graph, "REQ-o00001", "REQ-p00001", confirm=False)

        assert result["success"] is False

    def test_deletes_when_confirmed(self, mutation_graph):
        """Deletes edge when confirmed."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_delete_edge

        result = _mutate_delete_edge(mutation_graph, "REQ-o00001", "REQ-p00001", confirm=True)

        assert result["success"] is True

    def test_returns_mutation_entry(self, mutation_graph):
        """Returns MutationEntry for audit."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_delete_edge

        result = _mutate_delete_edge(mutation_graph, "REQ-o00001", "REQ-p00001", confirm=True)

        assert "mutation" in result
        assert result["mutation"]["operation"] == "delete_edge"


class TestMutateFixBrokenReference:
    """Tests for mutate_fix_broken_reference() tool."""

    def test_delegates_to_graph_fix_broken_reference(self, mutation_graph):
        """Delegates to graph.fix_broken_reference()."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_fix_broken_reference

        # Create a broken reference scenario first
        mutation_graph._broken_references.append(
            BrokenReference(
                source_id="REQ-o00001",
                target_id="REQ-MISSING",
                edge_kind=EdgeKind.IMPLEMENTS,
            )
        )

        result = _mutate_fix_broken_reference(
            mutation_graph, "REQ-o00001", "REQ-MISSING", "REQ-p00001"
        )

        assert result["success"] is True

    def test_returns_mutation_entry(self, mutation_graph):
        """Returns MutationEntry for audit."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_fix_broken_reference

        mutation_graph._broken_references.append(
            BrokenReference(
                source_id="REQ-o00001",
                target_id="REQ-BAD",
                edge_kind=EdgeKind.IMPLEMENTS,
            )
        )

        result = _mutate_fix_broken_reference(mutation_graph, "REQ-o00001", "REQ-BAD", "REQ-p00001")

        assert "mutation" in result
        assert result["mutation"]["operation"] == "fix_broken_reference"


# ─────────────────────────────────────────────────────────────────────────────
# Test: Undo Operations - REQ-o00062-G
# ─────────────────────────────────────────────────────────────────────────────


class TestUndoLastMutation:
    """Tests for undo_last_mutation() tool."""

    def test_REQ_o00062_G_delegates_to_graph_undo_last(self, mutation_graph):
        """REQ-o00062-G: Reverses mutations using graph.undo_last()."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_update_title, _undo_last_mutation

        # Make a mutation
        _mutate_update_title(mutation_graph, "REQ-p00001", "Changed Title")
        assert mutation_graph.find_by_id("REQ-p00001").get_label() == "Changed Title"

        # Undo it
        result = _undo_last_mutation(mutation_graph)

        assert result["success"] is True
        assert mutation_graph.find_by_id("REQ-p00001").get_label() == "Platform Security"

    def test_returns_undone_mutation_entry(self, mutation_graph):
        """Returns the mutation that was undone."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_update_title, _undo_last_mutation

        _mutate_update_title(mutation_graph, "REQ-p00001", "New Title")
        result = _undo_last_mutation(mutation_graph)

        assert "mutation" in result
        assert result["mutation"]["operation"] == "update_title"


class TestUndoToMutation:
    """Tests for undo_to_mutation() tool."""

    def test_REQ_o00062_G_delegates_to_graph_undo_to(self, mutation_graph):
        """REQ-o00062-G: Reverses mutations using graph.undo_to()."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import (
            _mutate_change_status,
            _mutate_update_title,
            _undo_to_mutation,
        )

        # Make multiple mutations
        _mutate_update_title(mutation_graph, "REQ-p00001", "Title 1")
        result2 = _mutate_update_title(mutation_graph, "REQ-p00001", "Title 2")
        mutation_id = result2["mutation"]["id"]  # We'll undo back to (and including) this
        _mutate_change_status(mutation_graph, "REQ-p00001", "Deprecated")

        # Undo back to (and including) second mutation
        # This undoes mutations 3 and 2, leaving mutation 1
        result = _undo_to_mutation(mutation_graph, mutation_id)

        assert result["success"] is True
        assert result["mutations_undone"] == 2
        # Should have the state after first mutation (Title 1, Active)
        node = mutation_graph.find_by_id("REQ-p00001")
        assert node.get_label() == "Title 1"
        assert node.status == "Active"


class TestGetMutationLog:
    """Tests for get_mutation_log() tool."""

    def test_returns_mutation_history(self, mutation_graph):
        """Returns list of mutation entries."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import (
            _get_mutation_log,
            _mutate_change_status,
            _mutate_update_title,
        )

        _mutate_update_title(mutation_graph, "REQ-p00001", "Title Change")
        _mutate_change_status(mutation_graph, "REQ-p00001", "Draft")

        result = _get_mutation_log(mutation_graph)

        assert "mutations" in result
        assert len(result["mutations"]) == 2

    def test_respects_limit_parameter(self, mutation_graph):
        """Respects limit parameter."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import (
            _get_mutation_log,
            _mutate_change_status,
            _mutate_update_title,
        )

        _mutate_update_title(mutation_graph, "REQ-p00001", "Title 1")
        _mutate_update_title(mutation_graph, "REQ-p00001", "Title 2")
        _mutate_change_status(mutation_graph, "REQ-p00001", "Draft")

        result = _get_mutation_log(mutation_graph, limit=2)

        assert len(result["mutations"]) == 2


# ─────────────────────────────────────────────────────────────────────────────
# Test: Inspection Tools
# ─────────────────────────────────────────────────────────────────────────────


class TestGetOrphanedNodes:
    """Tests for get_orphaned_nodes() tool."""

    def test_returns_orphaned_node_list(self, mutation_graph):
        """Returns list of orphaned nodes."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _get_orphaned_nodes

        # Delete edge to create orphan
        mutation_graph._orphaned_ids.add("REQ-o00001")

        result = _get_orphaned_nodes(mutation_graph)

        assert "orphans" in result
        assert "REQ-o00001" in [o["id"] for o in result["orphans"]]


class TestGetBrokenReferences:
    """Tests for get_broken_references() tool."""

    def test_returns_broken_reference_list(self, mutation_graph):
        """Returns list of broken references."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _get_broken_references

        mutation_graph._broken_references.append(
            BrokenReference(
                source_id="REQ-o00001",
                target_id="REQ-MISSING",
                edge_kind=EdgeKind.IMPLEMENTS,
            )
        )

        result = _get_broken_references(mutation_graph)

        assert "broken_references" in result
        assert len(result["broken_references"]) == 1
        assert result["broken_references"][0]["source_id"] == "REQ-o00001"
        assert result["broken_references"][0]["target_id"] == "REQ-MISSING"


# ─────────────────────────────────────────────────────────────────────────────
# Test: Serialization - REQ-d00064
# ─────────────────────────────────────────────────────────────────────────────


class TestSerializeMutationEntry:
    """Tests for serialize_mutation_entry() function."""

    def test_serializes_all_fields(self, mutation_graph):
        """Serializes all MutationEntry fields."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_update_title

        result = _mutate_update_title(mutation_graph, "REQ-p00001", "New Title")

        mutation = result["mutation"]
        assert "id" in mutation
        assert "operation" in mutation
        assert "target_id" in mutation
        assert "before_state" in mutation
        assert "after_state" in mutation
        assert "timestamp" in mutation

    def test_handles_affects_hash_flag(self, mutation_graph):
        """Includes affects_hash flag for assertion mutations."""
        pytest.importorskip("mcp")
        from elspais.mcp.server import _mutate_update_assertion

        result = _mutate_update_assertion(mutation_graph, "REQ-p00001-A", "New assertion text")

        mutation = result["mutation"]
        assert "affects_hash" in mutation
        assert mutation["affects_hash"] is True
