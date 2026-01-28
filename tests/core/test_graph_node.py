"""Tests for GraphNode - Phase 1 Foundation."""

import pytest

from elspais.graph import GraphNode, NodeKind, SourceLocation
from elspais.graph.builder import GraphBuilder

from tests.core.graph_test_helpers import (
    make_requirement,
    children_string,
    parents_string,
    walk_string,
    ancestors_string,
)


class TestNodeKind:
    """Tests for NodeKind enum."""

    def test_all_node_kinds_exist(self):
        """All expected node kinds exist with correct values."""
        expected = {
            "REQUIREMENT": "requirement",
            "ASSERTION": "assertion",
            "CODE": "code",
            "TEST": "test",
            "TEST_RESULT": "result",
            "USER_JOURNEY": "journey",
            "REMAINDER": "remainder",
        }
        for name, value in expected.items():
            kind = getattr(NodeKind, name)
            assert kind.value == value, f"NodeKind.{name} should have value '{value}'"


class TestSourceLocation:
    """Tests for SourceLocation dataclass."""

    def test_create_minimal(self):
        loc = SourceLocation(path="spec/prd.md", line=1)
        assert loc.path == "spec/prd.md"
        assert loc.line == 1
        assert loc.end_line is None
        assert loc.repo is None

    def test_create_with_end_line(self):
        loc = SourceLocation(path="spec/prd.md", line=10, end_line=25)
        assert loc.end_line == 25

    def test_create_with_repo(self):
        loc = SourceLocation(path="spec/prd.md", line=1, repo="CAL")
        assert loc.repo == "CAL"

    def test_str_without_repo(self):
        loc = SourceLocation(path="spec/prd.md", line=10)
        assert str(loc) == "spec/prd.md:10"

    def test_str_with_repo(self):
        loc = SourceLocation(path="spec/prd.md", line=10, repo="CAL")
        assert str(loc) == "CAL:spec/prd.md:10"

    def test_absolute_path(self):
        from pathlib import Path

        loc = SourceLocation(path="spec/prd.md", line=1)
        abs_path = loc.absolute(Path("/home/user/repo"))
        assert abs_path == Path("/home/user/repo/spec/prd.md")


class TestGraphNode:
    """Tests for GraphNode dataclass."""

    def test_create_minimal_node(self):
        """Node with id and kind only."""
        node = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)
        assert node.id == "REQ-p00001"
        assert node.kind == NodeKind.REQUIREMENT
        assert node.get_label() == ""  # Default empty
        assert node.source is None
        assert node.child_count() == 0
        assert node.parent_count() == 0
        assert node.is_root
        assert node.is_leaf

    def test_create_with_label(self):
        node = GraphNode(
            id="REQ-p00001",
            kind=NodeKind.REQUIREMENT,
            label="User Authentication",
        )
        assert node.get_label() == "User Authentication"

    def test_create_with_source(self):
        source = SourceLocation(path="spec/prd.md", line=10)
        node = GraphNode(
            id="REQ-p00001",
            kind=NodeKind.REQUIREMENT,
            source=source,
        )
        assert node.source == source
        assert node.source.line == 10

    def test_create_with_content(self):
        """Content is typed data based on node kind - use builder."""
        builder = GraphBuilder()
        builder.add_parsed_content(
            make_requirement(
                "REQ-p00001",
                title="Auth",
                status="Active",
            )
        )
        graph = builder.build()
        node = graph.find_by_id("REQ-p00001")

        assert node is not None
        assert node.get_field("status") == "Active"
        # Title is stored in label, not content
        assert node.get_label() == "Auth"

    def test_add_child(self):
        parent = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)
        child = GraphNode(id="REQ-p00001-A", kind=NodeKind.ASSERTION)

        parent.add_child(child)

        assert parent.has_child(child)
        assert child.has_parent(parent)

    def test_add_child_is_idempotent(self):
        parent = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)
        child = GraphNode(id="REQ-p00001-A", kind=NodeKind.ASSERTION)

        parent.add_child(child)
        parent.add_child(child)  # Add again

        assert parent.child_count() == 1
        assert child.parent_count() == 1

    def test_depth_for_root(self):
        node = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)
        assert node.depth == 0

    def test_depth_for_child(self):
        parent = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)
        child = GraphNode(id="REQ-o00001", kind=NodeKind.REQUIREMENT)
        parent.add_child(child)

        assert child.depth == 1

    def test_depth_for_grandchild(self):
        grandparent = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)
        parent = GraphNode(id="REQ-o00001", kind=NodeKind.REQUIREMENT)
        child = GraphNode(id="REQ-d00001", kind=NodeKind.REQUIREMENT)

        grandparent.add_child(parent)
        parent.add_child(child)

        assert child.depth == 2

    def test_depth_dag_uses_minimum(self):
        """With multiple parents, depth is minimum path to root."""
        root = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)
        mid = GraphNode(id="REQ-o00001", kind=NodeKind.REQUIREMENT)
        leaf = GraphNode(id="REQ-d00001", kind=NodeKind.REQUIREMENT)

        root.add_child(mid)
        root.add_child(leaf)  # Direct child of root
        mid.add_child(leaf)  # Also child of mid

        # leaf has two parents: root (depth 1) and mid (depth 2)
        # Should use minimum = 1
        assert leaf.depth == 1


class TestGraphNodeTraversal:
    """Tests for GraphNode traversal methods."""

    def test_walk_preorder(self):
        root = GraphNode(id="root", kind=NodeKind.REQUIREMENT)
        child1 = GraphNode(id="c1", kind=NodeKind.REQUIREMENT)
        child2 = GraphNode(id="c2", kind=NodeKind.REQUIREMENT)
        grandchild = GraphNode(id="gc", kind=NodeKind.REQUIREMENT)

        root.add_child(child1)
        root.add_child(child2)
        child1.add_child(grandchild)

        ids = [n.id for n in root.walk("pre")]
        assert ids == ["root", "c1", "gc", "c2"]

    def test_walk_postorder(self):
        root = GraphNode(id="root", kind=NodeKind.REQUIREMENT)
        child1 = GraphNode(id="c1", kind=NodeKind.REQUIREMENT)
        child2 = GraphNode(id="c2", kind=NodeKind.REQUIREMENT)

        root.add_child(child1)
        root.add_child(child2)

        ids = [n.id for n in root.walk("post")]
        assert ids == ["c1", "c2", "root"]

    def test_walk_level(self):
        root = GraphNode(id="root", kind=NodeKind.REQUIREMENT)
        child1 = GraphNode(id="c1", kind=NodeKind.REQUIREMENT)
        child2 = GraphNode(id="c2", kind=NodeKind.REQUIREMENT)
        grandchild = GraphNode(id="gc", kind=NodeKind.REQUIREMENT)

        root.add_child(child1)
        root.add_child(child2)
        child1.add_child(grandchild)

        ids = [n.id for n in root.walk("level")]
        assert ids == ["root", "c1", "c2", "gc"]

    def test_ancestors(self):
        grandparent = GraphNode(id="gp", kind=NodeKind.REQUIREMENT)
        parent = GraphNode(id="p", kind=NodeKind.REQUIREMENT)
        child = GraphNode(id="c", kind=NodeKind.REQUIREMENT)

        grandparent.add_child(parent)
        parent.add_child(child)

        ancestors = list(child.ancestors())
        assert len(ancestors) == 2
        assert parent in ancestors
        assert grandparent in ancestors

    def test_find_by_kind(self):
        root = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)
        assertion = GraphNode(id="REQ-p00001-A", kind=NodeKind.ASSERTION)
        code = GraphNode(id="code:auth.py:10", kind=NodeKind.CODE)

        root.add_child(assertion)
        assertion.add_child(code)

        assertions = list(root.find_by_kind(NodeKind.ASSERTION))
        assert len(assertions) == 1
        assert assertions[0].id == "REQ-p00001-A"

    def test_find_with_predicate(self):
        root = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT, label="Auth")
        child = GraphNode(id="REQ-o00001", kind=NodeKind.REQUIREMENT, label="OAuth")

        root.add_child(child)

        found = list(root.find(lambda n: "Auth" in n.get_label()))
        assert len(found) == 2  # Both contain "Auth"


class TestGraphNodeAdditionalCoverage:
    """Additional coverage tests for GraphNode."""

    def test_uuid_is_unique_per_node(self):
        """Each node gets a unique UUID."""
        node1 = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)
        node2 = GraphNode(id="REQ-p00002", kind=NodeKind.REQUIREMENT)
        node3 = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)  # Same id

        # All UUIDs should be unique even with same node id
        assert node1.uuid != node2.uuid
        assert node1.uuid != node3.uuid
        assert node2.uuid != node3.uuid
        # UUID is 32 hex chars
        assert len(node1.uuid) == 32

    def test_set_and_get_field(self):
        """Test field setter and getter."""
        node = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)

        node.set_field("level", "PRD")
        node.set_field("status", "Active")

        assert node.get_field("level") == "PRD"
        assert node.get_field("status") == "Active"
        assert node.get_field("nonexistent") is None
        assert node.get_field("nonexistent", "default") == "default"

    def test_set_and_get_metric(self):
        """Test metric setter and getter."""
        node = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)

        node.set_metric("coverage", 75.5)
        node.set_metric("test_count", 3)

        assert node.get_metric("coverage") == 75.5
        assert node.get_metric("test_count") == 3
        assert node.get_metric("nonexistent") is None
        assert node.get_metric("nonexistent", 0) == 0

    def test_walk_invalid_order_raises(self):
        """Invalid walk order raises ValueError."""
        node = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)

        with pytest.raises(ValueError, match="Unknown traversal order"):
            list(node.walk("invalid"))

    def test_ancestors_empty_for_root(self):
        """Root node has no ancestors."""
        root = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)

        ancestors = list(root.ancestors())
        assert ancestors == []

    def test_find_returns_empty_when_no_match(self):
        """find() returns empty iterator when predicate never matches."""
        root = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)
        child = GraphNode(id="REQ-o00001", kind=NodeKind.REQUIREMENT)
        root.add_child(child)

        found = list(root.find(lambda n: n.kind == NodeKind.CODE))
        assert found == []
