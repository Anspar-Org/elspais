# tests/mcp/test_assertion_badge_links.py
"""Tests for assertion badge link filtering (IMP vs REF separation).

Implements: REQ-d00064
"""
import pytest
from elspais.graph.GraphNode import GraphNode, NodeKind
from elspais.graph.relations import EdgeKind
from elspais.mcp.server import _iter_assertion_coverage


def _make_req_with_mixed_edges():
    """Build a REQ with assertions linked via both IMPLEMENTS and REFINES.

    Structure:
        REQ-001 (REQUIREMENT)
          +-- REQ-001-A (ASSERTION, label="A")
          +-- REQ-001-B (ASSERTION, label="B")

    Edges from REQ-001:
        --IMPLEMENTS--> CODE-impl    (assertion_targets=["A"])
        --IMPLEMENTS--> CODE-blanket (no assertion_targets = blanket)
        --REFINES-->    REQ-child    (assertion_targets=["B"])
    """
    req = GraphNode("REQ-001", NodeKind.REQUIREMENT)
    req.set_field("title", "Test requirement")

    a_node = GraphNode("REQ-001-A", NodeKind.ASSERTION)
    a_node.set_field("label", "A")
    req.link(a_node, EdgeKind.STRUCTURES)

    b_node = GraphNode("REQ-001-B", NodeKind.ASSERTION)
    b_node.set_field("label", "B")
    req.link(b_node, EdgeKind.STRUCTURES)

    code_impl = GraphNode("CODE-impl", NodeKind.CODE)
    code_impl.set_field("parse_line", 10)
    req.link(code_impl, EdgeKind.IMPLEMENTS, assertion_targets=["A"])

    code_blanket = GraphNode("CODE-blanket", NodeKind.CODE)
    code_blanket.set_field("parse_line", 30)
    req.link(code_blanket, EdgeKind.IMPLEMENTS)  # no assertion_targets

    req_child = GraphNode("REQ-child", NodeKind.REQUIREMENT)
    req_child.set_field("title", "Child requirement refining B")
    req.link(req_child, EdgeKind.REFINES, assertion_targets=["B"])

    return req


class TestIterAssertionCoverageFiltered:
    """Tests for _iter_assertion_coverage with edge_kinds filtering."""

    def test_no_filter_code_returns_all_code_nodes(self):
        """Without edge_kinds filter, all CODE nodes are returned."""
        req = _make_req_with_mixed_edges()
        results = list(_iter_assertion_coverage(req, NodeKind.CODE))
        node_ids = {node.id for node, _labels in results}
        assert node_ids == {"CODE-impl", "CODE-blanket"}

    def test_implements_filter_code_excludes_blanket_when_direct(self):
        """IMPLEMENTS + direct_only skips blanket edges."""
        req = _make_req_with_mixed_edges()
        results = list(_iter_assertion_coverage(
            req, NodeKind.CODE, edge_kinds={EdgeKind.IMPLEMENTS}, direct_only=True
        ))
        node_ids = {node.id for node, _labels in results}
        assert "CODE-impl" in node_ids
        assert "CODE-blanket" not in node_ids

    def test_implements_filter_returns_correct_labels(self):
        """Direct-only IMPLEMENTS returns only the targeted assertion labels."""
        req = _make_req_with_mixed_edges()
        results = list(_iter_assertion_coverage(
            req, NodeKind.CODE, edge_kinds={EdgeKind.IMPLEMENTS}, direct_only=True
        ))
        for node, labels in results:
            if node.id == "CODE-impl":
                assert labels == ["A"]

    def test_refines_filter_returns_requirement_nodes(self):
        """REFINES filter with REQUIREMENT kind_filter returns refining REQs."""
        req = _make_req_with_mixed_edges()
        results = list(_iter_assertion_coverage(
            req, NodeKind.REQUIREMENT, edge_kinds={EdgeKind.REFINES}, direct_only=True
        ))
        node_ids = {node.id for node, _labels in results}
        assert "REQ-child" in node_ids
        assert len(node_ids) == 1

    def test_refines_filter_returns_correct_labels(self):
        """REFINES edges carry the correct assertion_targets."""
        req = _make_req_with_mixed_edges()
        results = list(_iter_assertion_coverage(
            req, NodeKind.REQUIREMENT, edge_kinds={EdgeKind.REFINES}, direct_only=True
        ))
        for node, labels in results:
            if node.id == "REQ-child":
                assert labels == ["B"]

    def test_refines_filter_on_code_returns_nothing(self):
        """REFINES filter with CODE kind_filter returns nothing (REFINES targets REQs)."""
        req = _make_req_with_mixed_edges()
        results = list(_iter_assertion_coverage(
            req, NodeKind.CODE, edge_kinds={EdgeKind.REFINES}
        ))
        assert results == []
