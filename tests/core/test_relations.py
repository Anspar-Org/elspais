"""Tests for relations.py - Edge types and semantics."""

import pytest

from elspais.graph import GraphNode, NodeKind
from elspais.graph.relations import Edge, EdgeKind


class TestEdgeKind:
    """Tests for EdgeKind enum."""

    def test_implements_exists(self):
        assert EdgeKind.IMPLEMENTS.value == "implements"

    def test_refines_exists(self):
        assert EdgeKind.REFINES.value == "refines"

    def test_validates_exists(self):
        assert EdgeKind.VALIDATES.value == "validates"

    def test_addresses_exists(self):
        assert EdgeKind.ADDRESSES.value == "addresses"

    def test_contains_exists(self):
        assert EdgeKind.CONTAINS.value == "contains"


class TestEdge:
    """Tests for Edge dataclass."""

    def test_create_edge(self):
        source = GraphNode(id="REQ-o00001", kind=NodeKind.REQUIREMENT)
        target = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)

        edge = Edge(source=source, target=target, kind=EdgeKind.IMPLEMENTS)

        assert edge.source == source
        assert edge.target == target
        assert edge.kind == EdgeKind.IMPLEMENTS

    def test_edge_with_assertion_targets(self):
        """Edge can target specific assertions."""
        source = GraphNode(id="REQ-o00001", kind=NodeKind.REQUIREMENT)
        target = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)

        edge = Edge(
            source=source,
            target=target,
            kind=EdgeKind.IMPLEMENTS,
            assertion_targets=["A", "B", "C"],
        )

        assert edge.assertion_targets == ["A", "B", "C"]

    def test_edge_equality(self):
        source = GraphNode(id="REQ-o00001", kind=NodeKind.REQUIREMENT)
        target = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)

        edge1 = Edge(source=source, target=target, kind=EdgeKind.IMPLEMENTS)
        edge2 = Edge(source=source, target=target, kind=EdgeKind.IMPLEMENTS)

        assert edge1 == edge2

    def test_edge_inequality_different_kind(self):
        source = GraphNode(id="REQ-o00001", kind=NodeKind.REQUIREMENT)
        target = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)

        edge1 = Edge(source=source, target=target, kind=EdgeKind.IMPLEMENTS)
        edge2 = Edge(source=source, target=target, kind=EdgeKind.REFINES)

        assert edge1 != edge2


class TestEdgeSemantics:
    """Tests for edge semantic differences."""

    def test_implements_rollup_flag(self):
        """IMPLEMENTS edges contribute to coverage rollup."""
        assert EdgeKind.IMPLEMENTS.contributes_to_coverage() is True

    def test_refines_no_rollup_flag(self):
        """REFINES edges do NOT contribute to coverage rollup."""
        assert EdgeKind.REFINES.contributes_to_coverage() is False

    def test_validates_rollup_flag(self):
        """VALIDATES edges (tests) contribute to coverage."""
        assert EdgeKind.VALIDATES.contributes_to_coverage() is True

    def test_addresses_no_rollup_flag(self):
        """ADDRESSES edges (journey links) don't affect coverage."""
        assert EdgeKind.ADDRESSES.contributes_to_coverage() is False

    def test_contains_no_rollup_flag(self):
        """CONTAINS edges (file structure) don't affect coverage."""
        assert EdgeKind.CONTAINS.contributes_to_coverage() is False


class TestNodeEdgeIntegration:
    """Tests for GraphNode edge management."""

    def test_link_with_implements(self):
        parent = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)
        child = GraphNode(id="REQ-o00001", kind=NodeKind.REQUIREMENT)

        edge = parent.link(child, EdgeKind.IMPLEMENTS)

        assert edge.kind == EdgeKind.IMPLEMENTS
        assert child in parent.children
        assert parent in child.parents
        assert edge in parent.outgoing_edges
        assert edge in child.incoming_edges

    def test_link_with_refines(self):
        parent = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)
        child = GraphNode(id="REQ-p00002", kind=NodeKind.REQUIREMENT)

        edge = parent.link(child, EdgeKind.REFINES)

        assert edge.kind == EdgeKind.REFINES
        assert child in parent.children

    def test_link_with_assertion_targets(self):
        parent = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)
        child = GraphNode(id="REQ-o00001", kind=NodeKind.REQUIREMENT)

        edge = parent.link(child, EdgeKind.IMPLEMENTS, assertion_targets=["A", "B"])

        assert edge.assertion_targets == ["A", "B"]

    def test_get_edges_by_kind(self):
        parent = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)
        impl_child = GraphNode(id="REQ-o00001", kind=NodeKind.REQUIREMENT)
        refine_child = GraphNode(id="REQ-p00002", kind=NodeKind.REQUIREMENT)

        parent.link(impl_child, EdgeKind.IMPLEMENTS)
        parent.link(refine_child, EdgeKind.REFINES)

        impl_edges = parent.edges_by_kind(EdgeKind.IMPLEMENTS)
        assert len(impl_edges) == 1
        assert impl_edges[0].target == impl_child

        refine_edges = parent.edges_by_kind(EdgeKind.REFINES)
        assert len(refine_edges) == 1
        assert refine_edges[0].target == refine_child
