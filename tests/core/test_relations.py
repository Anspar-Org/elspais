"""Tests for relations.py - Edge types and semantics."""

import pytest

from elspais.graph import GraphNode, NodeKind
from elspais.graph.builder import GraphBuilder
from elspais.graph.relations import Edge, EdgeKind
from tests.core.graph_test_helpers import (
    make_requirement,
    children_string,
    parents_string,
    outgoing_edges_string,
    incoming_edges_string,
)


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
    """Tests for GraphNode edge management via GraphBuilder."""

    def test_implements_relationship(self):
        """Child implementing parent creates correct edges and relationships."""
        builder = GraphBuilder()
        builder.add_parsed_content(make_requirement("REQ-p00001"))
        builder.add_parsed_content(make_requirement("REQ-o00001", implements=["REQ-p00001"]))
        graph = builder.build()

        parent = graph.find_by_id("REQ-p00001")
        child = graph.find_by_id("REQ-o00001")

        # Verify relationships via string helpers
        assert "REQ-o00001" in children_string(parent)
        assert "REQ-p00001" in parents_string(child)
        # Verify edge kind
        assert "REQ-p00001->REQ-o00001:implements" in outgoing_edges_string(parent)
        assert "REQ-p00001->REQ-o00001:implements" in incoming_edges_string(child)

    def test_refines_relationship(self):
        """Child refining parent creates refines edge."""
        builder = GraphBuilder()
        builder.add_parsed_content(make_requirement("REQ-p00001"))
        builder.add_parsed_content(make_requirement("REQ-p00002", refines=["REQ-p00001"]))
        graph = builder.build()

        parent = graph.find_by_id("REQ-p00001")
        child = graph.find_by_id("REQ-p00002")

        # Verify relationships
        assert "REQ-p00002" in children_string(parent)
        assert "REQ-p00001->REQ-p00002:refines" in outgoing_edges_string(parent)

    def test_multiple_edge_kinds(self):
        """Graph can have both implements and refines edges from same parent."""
        builder = GraphBuilder()
        builder.add_parsed_content(make_requirement("REQ-p00001"))
        builder.add_parsed_content(make_requirement("REQ-o00001", implements=["REQ-p00001"]))
        builder.add_parsed_content(make_requirement("REQ-p00002", refines=["REQ-p00001"]))
        graph = builder.build()

        parent = graph.find_by_id("REQ-p00001")

        # Both children linked
        assert "REQ-o00001" in children_string(parent)
        assert "REQ-p00002" in children_string(parent)

        # Different edge kinds
        edges_str = outgoing_edges_string(parent)
        assert "REQ-p00001->REQ-o00001:implements" in edges_str
        assert "REQ-p00001->REQ-p00002:refines" in edges_str

    def test_iter_edges_by_kind(self):
        """iter_edges_by_kind filters correctly."""
        builder = GraphBuilder()
        builder.add_parsed_content(make_requirement("REQ-p00001"))
        builder.add_parsed_content(make_requirement("REQ-o00001", implements=["REQ-p00001"]))
        builder.add_parsed_content(make_requirement("REQ-p00002", refines=["REQ-p00001"]))
        graph = builder.build()

        parent = graph.find_by_id("REQ-p00001")

        impl_edges = list(parent.iter_edges_by_kind(EdgeKind.IMPLEMENTS))
        assert len(impl_edges) == 1
        assert impl_edges[0].target.id == "REQ-o00001"

        refine_edges = list(parent.iter_edges_by_kind(EdgeKind.REFINES))
        assert len(refine_edges) == 1
        assert refine_edges[0].target.id == "REQ-p00002"
