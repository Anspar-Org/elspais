"""Tests for TraceGraph.clone() method."""

import pytest

from elspais.graph import NodeKind
from elspais.graph.builder import TraceGraph
from elspais.graph.GraphNode import GraphNode


@pytest.fixture
def simple_graph():
    """Create a simple graph with parent-child relationships."""
    graph = TraceGraph(repo_root="/tmp/test")

    # Add root requirement
    req_node = GraphNode(
        id="REQ-p00001",
        kind=NodeKind.REQUIREMENT,
        label="Test Requirement",
    )
    req_node._content = {"level": "PRD", "status": "Active"}
    graph._index["REQ-p00001"] = req_node
    graph._roots.append(req_node)

    # Add assertion child
    assertion = GraphNode(
        id="REQ-p00001-A",
        kind=NodeKind.ASSERTION,
        label="Test assertion text",
    )
    assertion._content = {"label": "A"}
    graph._index["REQ-p00001-A"] = assertion
    req_node.add_child(assertion)

    return graph


class TestTraceGraphClone:
    """Tests for TraceGraph.clone() method."""

    def test_clone_creates_independent_copy(self, simple_graph):
        """Clone creates a fully independent copy."""
        cloned = simple_graph.clone()

        # Same node count
        assert cloned.node_count() == simple_graph.node_count()

        # But different object identity
        assert cloned is not simple_graph
        assert cloned._index is not simple_graph._index
        assert cloned._roots is not simple_graph._roots

    def test_clone_preserves_node_data(self, simple_graph):
        """Cloned graph has same node data."""
        cloned = simple_graph.clone()

        original_node = simple_graph.find_by_id("REQ-p00001")
        cloned_node = cloned.find_by_id("REQ-p00001")

        assert cloned_node is not None
        assert cloned_node.id == original_node.id
        assert cloned_node.kind == original_node.kind
        assert cloned_node.get_label() == original_node.get_label()
        assert cloned_node.get_field("level") == original_node.get_field("level")

    def test_clone_preserves_relationships(self, simple_graph):
        """Cloned graph preserves parent-child relationships."""
        cloned = simple_graph.clone()

        cloned_req = cloned.find_by_id("REQ-p00001")
        cloned_assertion = cloned.find_by_id("REQ-p00001-A")

        # Check parent-child relationship
        children = list(cloned_req.iter_children())
        assert len(children) == 1
        assert children[0].id == "REQ-p00001-A"

        parents = list(cloned_assertion.iter_parents())
        assert len(parents) == 1
        assert parents[0].id == "REQ-p00001"

    def test_clone_mutations_are_independent(self, simple_graph):
        """Mutations to clone don't affect original."""
        cloned = simple_graph.clone()

        # Modify the cloned node
        cloned_node = cloned.find_by_id("REQ-p00001")
        cloned_node.set_field("status", "Deprecated")

        # Original should be unchanged
        original_node = simple_graph.find_by_id("REQ-p00001")
        assert original_node.get_field("status") == "Active"

    def test_clone_handles_circular_references(self, simple_graph):
        """Clone handles circular parent-child references."""
        # The graph already has parent->child->parent references
        # which deepcopy handles via its memo dictionary
        cloned = simple_graph.clone()

        cloned_req = cloned.find_by_id("REQ-p00001")

        # Navigate: parent -> child -> parent
        child = list(cloned_req.iter_children())[0]
        parent_back = list(child.iter_parents())[0]

        # Should be the same object (within the clone)
        assert parent_back is cloned_req

    def test_clone_preserves_roots(self, simple_graph):
        """Clone preserves root nodes."""
        cloned = simple_graph.clone()

        assert cloned.root_count() == simple_graph.root_count()

        original_roots = list(simple_graph.iter_roots())
        cloned_roots = list(cloned.iter_roots())

        assert len(cloned_roots) == len(original_roots)
        assert cloned_roots[0].id == original_roots[0].id

    def test_clone_preserves_repo_root(self, simple_graph):
        """Clone preserves repo_root attribute."""
        cloned = simple_graph.clone()
        assert str(cloned.repo_root) == str(simple_graph.repo_root)
