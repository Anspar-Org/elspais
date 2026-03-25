# tests/mcp/test_assertion_badge_links.py
"""Tests for assertion badge link filtering (IMP vs REF separation).

Implements: REQ-d00064
"""
from unittest.mock import MagicMock

from elspais.graph.GraphNode import GraphNode, NodeKind
from elspais.graph.relations import EdgeKind
from elspais.mcp.server import (
    _get_assertion_code_map,
    _get_assertion_refines_map,
    _iter_assertion_coverage,
)


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


def _make_graph_with_req():
    """Build a FederatedGraph mock containing REQ-001 with mixed edges."""
    req = _make_req_with_mixed_edges()
    graph = MagicMock()
    graph.find_by_id.return_value = req
    return graph


class TestGetAssertionCodeMapFiltered:
    """_get_assertion_code_map with edge_kind='implements'."""

    def test_implements_filter_returns_only_implements_refs(self):
        graph = _make_graph_with_req()
        result = _get_assertion_code_map(graph, "REQ-001", edge_kind="implements")
        assert result["success"]
        a_ids = {r["id"] for r in result["assertion_code"]["A"]["code_refs"]}
        assert "CODE-impl" in a_ids
        # CODE-blanket excluded (direct_only=True when edge_kind is set)
        assert "CODE-blanket" not in a_ids

    def test_no_filter_returns_all_code(self):
        graph = _make_graph_with_req()
        result = _get_assertion_code_map(graph, "REQ-001")
        assert result["success"]
        all_ids = set()
        for label_data in result["assertion_code"].values():
            for r in label_data["code_refs"]:
                all_ids.add(r["id"])
        assert "CODE-impl" in all_ids
        assert "CODE-blanket" in all_ids


class TestGetAssertionRefinesMap:
    """_get_assertion_refines_map returns REFINES->REQUIREMENT links."""

    def test_returns_refining_requirements(self):
        graph = _make_graph_with_req()
        result = _get_assertion_refines_map(graph, "REQ-001")
        assert result["success"]
        b_refs = result["assertion_refines"]["B"]["refines_refs"]
        assert len(b_refs) == 1
        assert b_refs[0]["id"] == "REQ-child"
        assert b_refs[0]["title"] == "Child requirement refining B"

    def test_unrefined_assertion_has_empty_list(self):
        graph = _make_graph_with_req()
        result = _get_assertion_refines_map(graph, "REQ-001")
        assert result["success"]
        a_refs = result["assertion_refines"]["A"]["refines_refs"]
        assert a_refs == []

    def test_not_found_returns_error(self):
        graph = MagicMock()
        graph.find_by_id.return_value = None
        result = _get_assertion_refines_map(graph, "NOPE")
        assert not result["success"]
        assert "error" in result


class TestApiCodeCoverageQueryParam:
    """Verify edge_kind='implements' filters results correctly."""

    def test_kind_implements_filters_results(self):
        """Calling with edge_kind='implements' excludes blanket refs."""
        graph = _make_graph_with_req()
        result = _get_assertion_code_map(graph, "REQ-001", edge_kind="implements")
        all_ids = set()
        for label_data in result["assertion_code"].values():
            for r in label_data["code_refs"]:
                all_ids.add(r["id"])
        assert "CODE-blanket" not in all_ids
        assert "CODE-impl" in all_ids
