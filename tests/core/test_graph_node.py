"""Tests for GraphNode - Phase 1 Foundation."""

from elspais.graph import GraphNode, NodeKind
from elspais.graph.builder import GraphBuilder
from elspais.graph.relations import EdgeKind
from tests.core.graph_test_helpers import (
    make_requirement,
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
            "RESULT": "result",
            "USER_JOURNEY": "journey",
            "REMAINDER": "remainder",
        }
        for name, value in expected.items():
            kind = getattr(NodeKind, name)
            assert kind.value == value, f"NodeKind.{name} should have value '{value}'"


class TestGraphNode:
    """Tests for GraphNode dataclass."""

    def test_create_minimal_node(self):
        """Node with id and kind only."""
        node = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)
        assert node.id == "REQ-p00001"
        assert node.kind == NodeKind.REQUIREMENT
        assert node.get_label() == ""  # Default empty
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

    def test_create_with_parse_line(self):
        """parse_line and parse_end_line are accessible via get_field()."""
        node = GraphNode(
            id="REQ-p00001",
            kind=NodeKind.REQUIREMENT,
        )
        node.set_field("parse_line", 10)
        node.set_field("parse_end_line", 25)
        assert node.get_field("parse_line") == 10
        assert node.get_field("parse_end_line") == 25

    def test_create_with_content(self):
        """Content is typed data based on node kind - use builder."""
        builder = GraphBuilder()
        builder.add_parsed_content(
            make_requirement(
                "REQ-p00001",
                title="User Auth",
                level="PRD",
                start_line=1,
            )
        )
        graph = builder.build()
        node = graph.find_by_id("REQ-p00001")
        assert node is not None
        assert node.level == "PRD"

    def test_set_field_get_field(self):
        """Field access."""
        node = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)
        node.set_field("status", "Active")
        assert node.get_field("status") == "Active"
        assert node.get_field("missing") is None

    def test_set_metric_get_metric(self):
        """Metric access."""
        node = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)
        node.set_metric("coverage", 0.85)
        assert node.get_metric("coverage") == 0.85
        assert node.get_metric("missing") is None


class TestGraphNodeEdgeOperations:
    """Tests for edge operations on GraphNode."""

    def test_link_creates_parent_child(self):
        """link() creates bidirectional parent-child relationship."""
        parent = GraphNode(id="REQ-001", kind=NodeKind.REQUIREMENT)
        child = GraphNode(id="REQ-002", kind=NodeKind.REQUIREMENT)

        edge = parent.link(child, EdgeKind.IMPLEMENTS)

        assert child in list(parent.iter_children())
        assert parent in list(child.iter_parents())
        assert edge.kind == EdgeKind.IMPLEMENTS

    def test_unlink_removes_relationship(self):
        """unlink() removes bidirectional parent-child relationship."""
        parent = GraphNode(id="REQ-001", kind=NodeKind.REQUIREMENT)
        child = GraphNode(id="REQ-002", kind=NodeKind.REQUIREMENT)
        parent.link(child, EdgeKind.IMPLEMENTS)

        result = parent.unlink(child)

        assert result is True
        assert child not in list(parent.iter_children())
        assert parent not in list(child.iter_parents())

    def test_unlink_returns_false_for_nonchild(self):
        """unlink() returns False for non-child node."""
        parent = GraphNode(id="REQ-001", kind=NodeKind.REQUIREMENT)
        other = GraphNode(id="REQ-002", kind=NodeKind.REQUIREMENT)

        result = parent.unlink(other)
        assert result is False


class TestGraphNodeTraversal:
    """Tests for traversal methods."""

    def test_walk_preorder(self):
        """walk() yields nodes in pre-order (parent first)."""
        root = GraphNode(id="root", kind=NodeKind.REQUIREMENT)
        child1 = GraphNode(id="child1", kind=NodeKind.REQUIREMENT)
        child2 = GraphNode(id="child2", kind=NodeKind.REQUIREMENT)
        root.link(child1, EdgeKind.IMPLEMENTS)
        root.link(child2, EdgeKind.IMPLEMENTS)

        ids = [n.id for n in root.walk("pre")]
        assert ids == ["root", "child1", "child2"]

    def test_walk_postorder(self):
        """walk(post) yields children before parent."""
        root = GraphNode(id="root", kind=NodeKind.REQUIREMENT)
        child1 = GraphNode(id="child1", kind=NodeKind.REQUIREMENT)
        root.link(child1, EdgeKind.IMPLEMENTS)

        ids = [n.id for n in root.walk("post")]
        assert ids == ["child1", "root"]

    def test_walk_level_order(self):
        """walk(level) yields BFS order."""
        root = GraphNode(id="root", kind=NodeKind.REQUIREMENT)
        child1 = GraphNode(id="child1", kind=NodeKind.REQUIREMENT)
        child2 = GraphNode(id="child2", kind=NodeKind.REQUIREMENT)
        grandchild = GraphNode(id="gc", kind=NodeKind.REQUIREMENT)
        root.link(child1, EdgeKind.IMPLEMENTS)
        root.link(child2, EdgeKind.IMPLEMENTS)
        child1.link(grandchild, EdgeKind.IMPLEMENTS)

        ids = [n.id for n in root.walk("level")]
        assert ids == ["root", "child1", "child2", "gc"]


class TestGraphNodeFieldAccess:
    """Tests for content and metric field access."""

    def test_level_property(self):
        """level property reads from content."""
        node = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)
        node.set_field("level", "PRD")
        assert node.level == "PRD"

    def test_status_property(self):
        """status property reads from content."""
        node = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)
        node.set_field("status", "Active")
        assert node.status == "Active"

    def test_hash_property(self):
        """hash property reads from content."""
        node = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)
        node.set_field("hash", "abcd1234")
        assert node.hash == "abcd1234"


class TestGraphNodeID:
    """Tests for set_id mutation."""

    def test_set_id(self):
        """set_id updates the node ID."""
        node = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)
        node.set_id("REQ-p00002")
        assert node.id == "REQ-p00002"


class TestUUID:
    """Tests for UUID property."""

    def test_uuid_is_32_chars(self):
        """UUID is a 32-character hex string."""
        node = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)
        assert len(node.uuid) == 32

    def test_uuid_is_unique(self):
        """Each node gets a unique UUID."""
        node1 = GraphNode(id="REQ-001", kind=NodeKind.REQUIREMENT)
        node2 = GraphNode(id="REQ-002", kind=NodeKind.REQUIREMENT)
        assert node1.uuid != node2.uuid


class TestEdgeOperations:
    """Tests for edge-related operations."""

    def test_iter_outgoing_edges(self):
        """iter_outgoing_edges yields outgoing edges."""
        parent = GraphNode(id="REQ-001", kind=NodeKind.REQUIREMENT)
        child = GraphNode(id="REQ-002", kind=NodeKind.REQUIREMENT)
        parent.link(child, EdgeKind.IMPLEMENTS)

        edges = list(parent.iter_outgoing_edges())
        assert len(edges) == 1
        assert edges[0].kind == EdgeKind.IMPLEMENTS

    def test_iter_incoming_edges(self):
        """iter_incoming_edges yields incoming edges."""
        parent = GraphNode(id="REQ-001", kind=NodeKind.REQUIREMENT)
        child = GraphNode(id="REQ-002", kind=NodeKind.REQUIREMENT)
        parent.link(child, EdgeKind.IMPLEMENTS)

        edges = list(child.iter_incoming_edges())
        assert len(edges) == 1
        assert edges[0].kind == EdgeKind.IMPLEMENTS

    def test_iter_edges_by_kind(self):
        """iter_edges_by_kind filters outgoing edges."""
        parent = GraphNode(id="REQ-001", kind=NodeKind.REQUIREMENT)
        child1 = GraphNode(id="REQ-002", kind=NodeKind.REQUIREMENT)
        child2 = GraphNode(id="REQ-003", kind=NodeKind.REQUIREMENT)
        parent.link(child1, EdgeKind.IMPLEMENTS)
        parent.link(child2, EdgeKind.REFINES)

        impl_edges = list(parent.iter_edges_by_kind(EdgeKind.IMPLEMENTS))
        assert len(impl_edges) == 1

    def test_remove_edge(self):
        """remove_edge removes a specific edge."""
        parent = GraphNode(id="REQ-001", kind=NodeKind.REQUIREMENT)
        child = GraphNode(id="REQ-002", kind=NodeKind.REQUIREMENT)
        edge = parent.link(child, EdgeKind.IMPLEMENTS)

        result = parent.remove_edge(edge)
        assert result is True
        assert list(parent.iter_outgoing_edges()) == []

    def test_link_with_assertion_targets(self):
        """Link can specify assertion targets."""
        test = GraphNode(id="test:t1", kind=NodeKind.TEST)
        req = GraphNode(id="REQ-001", kind=NodeKind.REQUIREMENT)
        edge = test.link(req, EdgeKind.VERIFIES, assertion_targets=["A", "B"])

        assert edge.assertion_targets == ["A", "B"]

    def test_edge_has_source_and_target(self):
        """Edge source and target are correct."""
        test = GraphNode(id="test:t1", kind=NodeKind.TEST)
        req = GraphNode(id="REQ-001", kind=NodeKind.REQUIREMENT)
        test.link(req, EdgeKind.VERIFIES)

        edges = list(test.iter_outgoing_edges())
        assert edges[0].source is test
        assert edges[0].target is req
