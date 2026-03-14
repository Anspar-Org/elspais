"""Tests for GraphNode - Phase 1 Foundation."""

import pytest

from elspais.graph import GraphNode, NodeKind, SourceLocation
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

        parent.link(child, EdgeKind.STRUCTURES)

        assert parent.has_child(child)
        assert child.has_parent(parent)

    def test_add_child_is_idempotent(self):
        parent = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)
        child = GraphNode(id="REQ-p00001-A", kind=NodeKind.ASSERTION)

        parent.link(child, EdgeKind.STRUCTURES)
        parent.link(child, EdgeKind.STRUCTURES)  # Add again

        assert parent.child_count() == 1
        assert child.parent_count() == 1

    def test_depth_for_root(self):
        node = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)
        assert node.depth == 0

    def test_depth_for_child(self):
        parent = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)
        child = GraphNode(id="REQ-o00001", kind=NodeKind.REQUIREMENT)
        parent.link(child, EdgeKind.STRUCTURES)

        assert child.depth == 1

    def test_depth_for_grandchild(self):
        grandparent = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)
        parent = GraphNode(id="REQ-o00001", kind=NodeKind.REQUIREMENT)
        child = GraphNode(id="REQ-d00001", kind=NodeKind.REQUIREMENT)

        grandparent.link(parent, EdgeKind.STRUCTURES)
        parent.link(child, EdgeKind.STRUCTURES)

        assert child.depth == 2

    def test_depth_dag_uses_minimum(self):
        """With multiple parents, depth is minimum path to root."""
        root = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)
        mid = GraphNode(id="REQ-o00001", kind=NodeKind.REQUIREMENT)
        leaf = GraphNode(id="REQ-d00001", kind=NodeKind.REQUIREMENT)

        root.link(mid, EdgeKind.STRUCTURES)
        root.link(leaf, EdgeKind.STRUCTURES)  # Direct child of root
        mid.link(leaf, EdgeKind.STRUCTURES)  # Also child of mid

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

        root.link(child1, EdgeKind.STRUCTURES)
        root.link(child2, EdgeKind.STRUCTURES)
        child1.link(grandchild, EdgeKind.STRUCTURES)

        ids = [n.id for n in root.walk("pre")]
        assert ids == ["root", "c1", "gc", "c2"]

    def test_walk_postorder(self):
        root = GraphNode(id="root", kind=NodeKind.REQUIREMENT)
        child1 = GraphNode(id="c1", kind=NodeKind.REQUIREMENT)
        child2 = GraphNode(id="c2", kind=NodeKind.REQUIREMENT)

        root.link(child1, EdgeKind.STRUCTURES)
        root.link(child2, EdgeKind.STRUCTURES)

        ids = [n.id for n in root.walk("post")]
        assert ids == ["c1", "c2", "root"]

    def test_walk_level(self):
        root = GraphNode(id="root", kind=NodeKind.REQUIREMENT)
        child1 = GraphNode(id="c1", kind=NodeKind.REQUIREMENT)
        child2 = GraphNode(id="c2", kind=NodeKind.REQUIREMENT)
        grandchild = GraphNode(id="gc", kind=NodeKind.REQUIREMENT)

        root.link(child1, EdgeKind.STRUCTURES)
        root.link(child2, EdgeKind.STRUCTURES)
        child1.link(grandchild, EdgeKind.STRUCTURES)

        ids = [n.id for n in root.walk("level")]
        assert ids == ["root", "c1", "c2", "gc"]

    def test_ancestors(self):
        grandparent = GraphNode(id="gp", kind=NodeKind.REQUIREMENT)
        parent = GraphNode(id="p", kind=NodeKind.REQUIREMENT)
        child = GraphNode(id="c", kind=NodeKind.REQUIREMENT)

        grandparent.link(parent, EdgeKind.STRUCTURES)
        parent.link(child, EdgeKind.STRUCTURES)

        ancestors = list(child.ancestors())
        assert len(ancestors) == 2
        assert parent in ancestors
        assert grandparent in ancestors

    def test_find_by_kind(self):
        root = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)
        assertion = GraphNode(id="REQ-p00001-A", kind=NodeKind.ASSERTION)
        code = GraphNode(id="code:auth.py:10", kind=NodeKind.CODE)

        root.link(assertion, EdgeKind.STRUCTURES)
        assertion.link(code, EdgeKind.STRUCTURES)

        assertions = list(root.find_by_kind(NodeKind.ASSERTION))
        assert len(assertions) == 1
        assert assertions[0].id == "REQ-p00001-A"

    def test_find_with_predicate(self):
        root = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT, label="Auth")
        child = GraphNode(id="REQ-o00001", kind=NodeKind.REQUIREMENT, label="OAuth")

        root.link(child, EdgeKind.STRUCTURES)

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
        root.link(child, EdgeKind.STRUCTURES)

        found = list(root.find(lambda n: n.kind == NodeKind.CODE))
        assert found == []


# Validates REQ-d00127-A, REQ-d00127-B, REQ-d00127-C, REQ-d00127-D, REQ-d00127-E:
class TestGraphNodeAPIChanges:
    """Validates REQ-d00127-A: add_child removed,
    REQ-d00127-B: unlink replaces remove_child,
    REQ-d00127-C: filtered traversal,
    REQ-d00127-D: file_node convenience,
    REQ-d00127-E: YIELDS edge for TEST_RESULT.
    """

    # --- REQ-d00127-A: add_child removed ---

    def test_REQ_d00127_A_add_child_does_not_exist(self):
        """GraphNode SHALL NOT have add_child()."""
        node = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)
        assert not hasattr(node, "add_child")

    def test_REQ_d00127_A_link_creates_parent_child(self):
        """All parent-child relationships via link() with EdgeKind."""
        parent = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)
        child = GraphNode(id="REQ-p00001-A", kind=NodeKind.ASSERTION)

        parent.link(child, EdgeKind.STRUCTURES)

        assert parent.has_child(child)
        assert child.has_parent(parent)
        # Edge is created
        edges = list(parent.iter_outgoing_edges())
        assert len(edges) == 1
        assert edges[0].kind == EdgeKind.STRUCTURES

    # --- REQ-d00127-B: unlink replaces remove_child ---

    def test_REQ_d00127_B_remove_child_does_not_exist(self):
        """GraphNode SHALL NOT have remove_child()."""
        node = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)
        assert not hasattr(node, "remove_child")

    def test_REQ_d00127_B_unlink_severs_all_edges(self):
        """unlink() severs all edges between nodes and removes caches."""
        parent = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)
        child = GraphNode(id="REQ-p00001-A", kind=NodeKind.ASSERTION)

        parent.link(child, EdgeKind.STRUCTURES)
        assert parent.has_child(child)

        result = parent.unlink(child)
        assert result is True
        assert not parent.has_child(child)
        assert not child.has_parent(parent)
        assert list(parent.iter_outgoing_edges()) == []
        assert list(child.iter_incoming_edges()) == []

    def test_REQ_d00127_B_unlink_returns_false_for_nonchild(self):
        """unlink() returns False when node is not a child."""
        parent = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)
        other = GraphNode(id="REQ-p00002", kind=NodeKind.REQUIREMENT)

        result = parent.unlink(other)
        assert result is False

    # --- REQ-d00127-C: filtered traversal ---

    def test_REQ_d00127_C_iter_children_unfiltered(self):
        """iter_children() without edge_kinds returns all children."""
        parent = GraphNode(id="p", kind=NodeKind.REQUIREMENT)
        c1 = GraphNode(id="c1", kind=NodeKind.ASSERTION)
        c2 = GraphNode(id="c2", kind=NodeKind.REQUIREMENT)

        parent.link(c1, EdgeKind.STRUCTURES)
        parent.link(c2, EdgeKind.IMPLEMENTS)

        children = list(parent.iter_children())
        assert len(children) == 2

    def test_REQ_d00127_C_iter_children_filtered(self):
        """iter_children(edge_kinds=...) filters by edge kind."""
        parent = GraphNode(id="p", kind=NodeKind.REQUIREMENT)
        c1 = GraphNode(id="c1", kind=NodeKind.ASSERTION)
        c2 = GraphNode(id="c2", kind=NodeKind.REQUIREMENT)

        parent.link(c1, EdgeKind.STRUCTURES)
        parent.link(c2, EdgeKind.IMPLEMENTS)

        structs = list(parent.iter_children(edge_kinds={EdgeKind.STRUCTURES}))
        assert len(structs) == 1
        assert structs[0].id == "c1"

        impls = list(parent.iter_children(edge_kinds={EdgeKind.IMPLEMENTS}))
        assert len(impls) == 1
        assert impls[0].id == "c2"

    def test_REQ_d00127_C_iter_parents_unfiltered(self):
        """iter_parents() without edge_kinds returns all parents."""
        child = GraphNode(id="c", kind=NodeKind.ASSERTION)
        p1 = GraphNode(id="p1", kind=NodeKind.REQUIREMENT)
        p2 = GraphNode(id="p2", kind=NodeKind.REQUIREMENT)

        p1.link(child, EdgeKind.STRUCTURES)
        p2.link(child, EdgeKind.IMPLEMENTS)

        parents = list(child.iter_parents())
        assert len(parents) == 2

    def test_REQ_d00127_C_iter_parents_filtered(self):
        """iter_parents(edge_kinds=...) filters by incoming edge kind."""
        child = GraphNode(id="c", kind=NodeKind.ASSERTION)
        p1 = GraphNode(id="p1", kind=NodeKind.REQUIREMENT)
        p2 = GraphNode(id="p2", kind=NodeKind.REQUIREMENT)

        p1.link(child, EdgeKind.STRUCTURES)
        p2.link(child, EdgeKind.IMPLEMENTS)

        struct_parents = list(child.iter_parents(edge_kinds={EdgeKind.STRUCTURES}))
        assert len(struct_parents) == 1
        assert struct_parents[0].id == "p1"

    def test_REQ_d00127_C_walk_unfiltered(self):
        """walk() without edge_kinds returns all descendants."""
        root = GraphNode(id="r", kind=NodeKind.REQUIREMENT)
        c1 = GraphNode(id="c1", kind=NodeKind.ASSERTION)
        c2 = GraphNode(id="c2", kind=NodeKind.REQUIREMENT)
        gc = GraphNode(id="gc", kind=NodeKind.ASSERTION)

        root.link(c1, EdgeKind.STRUCTURES)
        root.link(c2, EdgeKind.IMPLEMENTS)
        c2.link(gc, EdgeKind.STRUCTURES)

        ids = [n.id for n in root.walk()]
        assert ids == ["r", "c1", "c2", "gc"]

    def test_REQ_d00127_C_walk_filtered(self):
        """walk(edge_kinds=...) only traverses matching edges at each level."""
        root = GraphNode(id="r", kind=NodeKind.REQUIREMENT)
        c1 = GraphNode(id="c1", kind=NodeKind.ASSERTION)
        c2 = GraphNode(id="c2", kind=NodeKind.REQUIREMENT)
        gc = GraphNode(id="gc", kind=NodeKind.ASSERTION)

        root.link(c1, EdgeKind.STRUCTURES)
        root.link(c2, EdgeKind.IMPLEMENTS)
        c2.link(gc, EdgeKind.STRUCTURES)

        # Only follow STRUCTURES edges
        ids = [n.id for n in root.walk(edge_kinds={EdgeKind.STRUCTURES})]
        assert ids == ["r", "c1"]  # c2 not reachable via STRUCTURES

        # Only follow IMPLEMENTS edges
        ids = [n.id for n in root.walk(edge_kinds={EdgeKind.IMPLEMENTS})]
        assert ids == ["r", "c2"]  # gc not reachable via IMPLEMENTS from c2

    def test_REQ_d00127_C_walk_filtered_postorder(self):
        """walk(order='post', edge_kinds=...) filters correctly."""
        root = GraphNode(id="r", kind=NodeKind.REQUIREMENT)
        c1 = GraphNode(id="c1", kind=NodeKind.ASSERTION)
        c2 = GraphNode(id="c2", kind=NodeKind.REQUIREMENT)

        root.link(c1, EdgeKind.STRUCTURES)
        root.link(c2, EdgeKind.IMPLEMENTS)

        ids = [n.id for n in root.walk(order="post", edge_kinds={EdgeKind.STRUCTURES})]
        assert ids == ["c1", "r"]

    def test_REQ_d00127_C_walk_filtered_level(self):
        """walk(order='level', edge_kinds=...) filters correctly."""
        root = GraphNode(id="r", kind=NodeKind.REQUIREMENT)
        c1 = GraphNode(id="c1", kind=NodeKind.ASSERTION)
        c2 = GraphNode(id="c2", kind=NodeKind.REQUIREMENT)

        root.link(c1, EdgeKind.STRUCTURES)
        root.link(c2, EdgeKind.IMPLEMENTS)

        ids = [n.id for n in root.walk(order="level", edge_kinds={EdgeKind.STRUCTURES})]
        assert ids == ["r", "c1"]

    def test_REQ_d00127_C_ancestors_unfiltered(self):
        """ancestors() without edge_kinds returns all ancestors."""
        gp = GraphNode(id="gp", kind=NodeKind.REQUIREMENT)
        p = GraphNode(id="p", kind=NodeKind.REQUIREMENT)
        c = GraphNode(id="c", kind=NodeKind.REQUIREMENT)

        gp.link(p, EdgeKind.IMPLEMENTS)
        p.link(c, EdgeKind.STRUCTURES)

        anc = [n.id for n in c.ancestors()]
        assert "p" in anc
        assert "gp" in anc

    def test_REQ_d00127_C_ancestors_filtered(self):
        """ancestors(edge_kinds=...) only follows matching incoming edges."""
        gp = GraphNode(id="gp", kind=NodeKind.REQUIREMENT)
        p = GraphNode(id="p", kind=NodeKind.REQUIREMENT)
        c = GraphNode(id="c", kind=NodeKind.REQUIREMENT)

        gp.link(p, EdgeKind.IMPLEMENTS)
        p.link(c, EdgeKind.STRUCTURES)

        # Only follow STRUCTURES edges upward
        anc = [n.id for n in c.ancestors(edge_kinds={EdgeKind.STRUCTURES})]
        assert anc == ["p"]  # gp not reachable via STRUCTURES

    # --- REQ-d00127-D: file_node convenience ---

    def test_REQ_d00127_D_file_node_returns_none_without_file(self):
        """file_node() returns None when no FILE ancestor exists."""
        req = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)
        assertion = GraphNode(id="REQ-p00001-A", kind=NodeKind.ASSERTION)
        req.link(assertion, EdgeKind.STRUCTURES)

        assert req.file_node() is None
        assert assertion.file_node() is None

    def test_REQ_d00127_D_file_node_one_hop(self):
        """file_node() finds FILE parent one hop up via CONTAINS."""
        file_node = GraphNode(id="file:spec/prd.md", kind=NodeKind.FILE)
        req = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)
        file_node.link(req, EdgeKind.CONTAINS)

        result = req.file_node()
        assert result is not None
        assert result.id == "file:spec/prd.md"
        assert result.kind == NodeKind.FILE

    def test_REQ_d00127_D_file_node_two_hops(self):
        """file_node() finds FILE ancestor two hops up (assertion -> req -> file)."""
        file_node = GraphNode(id="file:spec/prd.md", kind=NodeKind.FILE)
        req = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)
        assertion = GraphNode(id="REQ-p00001-A", kind=NodeKind.ASSERTION)

        file_node.link(req, EdgeKind.CONTAINS)
        req.link(assertion, EdgeKind.STRUCTURES)

        result = assertion.file_node()
        assert result is not None
        assert result.id == "file:spec/prd.md"

    def test_REQ_d00127_D_file_node_on_file_node_returns_none(self):
        """file_node() on a FILE node returns None (no FILE parent)."""
        file_node = GraphNode(id="file:spec/prd.md", kind=NodeKind.FILE)
        assert file_node.file_node() is None

    # --- REQ-d00127-E: YIELDS edge for TEST_RESULT ---

    def test_REQ_d00127_E_yields_edge_direction(self):
        """TEST_RESULT linked from TEST via YIELDS (TEST -> TEST_RESULT)."""
        test = GraphNode(id="test:auth", kind=NodeKind.TEST)
        result = GraphNode(id="result:auth:1", kind=NodeKind.TEST_RESULT)

        test.link(result, EdgeKind.YIELDS)

        assert test.has_child(result)
        assert result.has_parent(test)
        edges = list(test.iter_outgoing_edges())
        assert len(edges) == 1
        assert edges[0].kind == EdgeKind.YIELDS
        assert edges[0].source is test
        assert edges[0].target is result

    def test_REQ_d00127_E_yields_not_contains(self):
        """YIELDS edge kind is used, not CONTAINS, for TEST->TEST_RESULT."""
        test = GraphNode(id="test:auth", kind=NodeKind.TEST)
        result = GraphNode(id="result:auth:1", kind=NodeKind.TEST_RESULT)

        test.link(result, EdgeKind.YIELDS)

        # No CONTAINS edges
        contains_edges = list(test.iter_edges_by_kind(EdgeKind.CONTAINS))
        assert len(contains_edges) == 0
        # One YIELDS edge
        yields_edges = list(test.iter_edges_by_kind(EdgeKind.YIELDS))
        assert len(yields_edges) == 1
