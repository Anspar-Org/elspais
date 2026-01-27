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

    def test_all_edge_kinds_exist(self):
        """All expected edge kinds exist with correct values."""
        expected = {
            "IMPLEMENTS": "implements",
            "REFINES": "refines",
            "VALIDATES": "validates",
            "ADDRESSES": "addresses",
            "CONTAINS": "contains",
        }
        for name, value in expected.items():
            kind = getattr(EdgeKind, name)
            assert kind.value == value, f"EdgeKind.{name} should have value '{value}'"


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

    def test_edge_inequality_different_assertion_targets(self):
        """Edges with different assertion_targets are not equal."""
        source = GraphNode(id="REQ-o00001", kind=NodeKind.REQUIREMENT)
        target = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)

        edge1 = Edge(
            source=source,
            target=target,
            kind=EdgeKind.IMPLEMENTS,
            assertion_targets=["A", "B"],
        )
        edge2 = Edge(
            source=source,
            target=target,
            kind=EdgeKind.IMPLEMENTS,
            assertion_targets=["A", "C"],
        )

        assert edge1 != edge2

    def test_edge_equality_with_non_edge(self):
        """Edge compared with non-Edge returns NotImplemented."""
        source = GraphNode(id="REQ-o00001", kind=NodeKind.REQUIREMENT)
        target = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)

        edge = Edge(source=source, target=target, kind=EdgeKind.IMPLEMENTS)

        # Comparing with non-Edge should not raise, should return False
        assert edge != "not an edge"
        assert edge != 42
        assert edge != None


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

        # Verify relationships via string helpers (exact equality)
        assert children_string(parent) == "REQ-o00001"
        assert parents_string(child) == "REQ-p00001"
        # Verify edge kind (exact equality)
        assert outgoing_edges_string(parent) == "REQ-p00001->REQ-o00001:implements"
        assert incoming_edges_string(child) == "REQ-p00001->REQ-o00001:implements"

    def test_refines_relationship(self):
        """Child refining parent creates refines edge."""
        builder = GraphBuilder()
        builder.add_parsed_content(make_requirement("REQ-p00001"))
        builder.add_parsed_content(make_requirement("REQ-p00002", refines=["REQ-p00001"]))
        graph = builder.build()

        parent = graph.find_by_id("REQ-p00001")
        child = graph.find_by_id("REQ-p00002")

        # Verify relationships (exact equality)
        assert children_string(parent) == "REQ-p00002"
        assert outgoing_edges_string(parent) == "REQ-p00001->REQ-p00002:refines"

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
