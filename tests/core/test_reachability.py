# Validates: REQ-d00071-A
"""Tests for TraceGraph reachability methods.

Tests is_reachable_to_requirement(), iter_unlinked(), and iter_structural_orphans().
"""
from __future__ import annotations

from elspais.graph.builder import TraceGraph
from elspais.graph.GraphNode import GraphNode, NodeKind
from elspais.graph.relations import Stereotype

from .graph_test_helpers import (
    build_graph,
    make_requirement,
    make_test_ref,
)


def _make_graph_with_linked_and_unlinked_tests() -> TraceGraph:
    """Build a graph with linked, unlinked, and orphan TEST nodes.

    Structure:
    - REQ-p00001 (PRD requirement)
    - file:tests/linked.py -> TEST (test:tests/linked.py:1) --VALIDATES--> REQ-p00001
    - file:tests/unlinked.py -> TEST (test:tests/unlinked.py:1) (no traceability edges)
    - TEST (orphan_test) with no FILE parent (structural orphan)
    """
    graph = build_graph(
        make_requirement("REQ-p00001", title="Parent Req", level="PRD"),
        make_test_ref(
            validates=["REQ-p00001"],
            source_path="tests/linked.py",
            start_line=1,
            end_line=5,
        ),
        make_test_ref(
            validates=[],
            source_path="tests/unlinked.py",
            start_line=1,
            end_line=5,
        ),
    )

    # Add a structural orphan TEST node (no FILE parent)
    orphan_test = GraphNode(id="test:orphan:1", kind=NodeKind.TEST, label="Orphan Test")
    graph._index["test:orphan:1"] = orphan_test

    return graph


class TestIsReachableToRequirement:
    """Tests for TraceGraph.is_reachable_to_requirement()."""

    def test_linked_test_is_reachable(self):
        """A TEST node that VALIDATES a REQUIREMENT is reachable."""
        graph = _make_graph_with_linked_and_unlinked_tests()
        linked = graph.find_by_id("test:tests/linked.py:1")
        assert linked is not None
        assert graph.is_reachable_to_requirement(linked)

    def test_unlinked_test_is_not_reachable(self):
        """A TEST node with no traceability edges is not reachable."""
        graph = _make_graph_with_linked_and_unlinked_tests()
        unlinked = graph.find_by_id("test:tests/unlinked.py:1")
        assert unlinked is not None
        assert not graph.is_reachable_to_requirement(unlinked)

    def test_requirement_is_reachable_to_itself_via_ancestor(self):
        """A child requirement that IMPLEMENTS a parent is reachable."""
        graph = build_graph(
            make_requirement("REQ-p00001", title="Parent", level="PRD"),
            make_requirement("REQ-o00001", title="Child", level="OPS", implements=["REQ-p00001"]),
        )
        child = graph.find_by_id("REQ-o00001")
        assert child is not None
        assert graph.is_reachable_to_requirement(child)

    def test_structural_parent_not_counted(self):
        """CONTAINS edges (structural) don't count for traceability reachability."""
        graph = _make_graph_with_linked_and_unlinked_tests()
        # The unlinked test HAS a FILE parent via CONTAINS, but that's structural
        unlinked = graph.find_by_id("test:tests/unlinked.py:1")
        assert unlinked is not None
        # Even though FILE -> TEST via CONTAINS, it's not reachable to a REQUIREMENT
        assert not graph.is_reachable_to_requirement(unlinked)


class TestIterUnlinked:
    """Tests for TraceGraph.iter_unlinked()."""

    def test_unlinked_test_is_yielded(self):
        """A TEST with FILE parent but no requirement link is unlinked."""
        graph = _make_graph_with_linked_and_unlinked_tests()
        unlinked_ids = {n.id for n in graph.iter_unlinked(NodeKind.TEST)}
        assert "test:tests/unlinked.py:1" in unlinked_ids

    def test_linked_test_is_not_yielded(self):
        """A TEST that VALIDATES a REQUIREMENT is not unlinked."""
        graph = _make_graph_with_linked_and_unlinked_tests()
        unlinked_ids = {n.id for n in graph.iter_unlinked(NodeKind.TEST)}
        assert "test:tests/linked.py:1" not in unlinked_ids

    def test_orphan_test_is_not_yielded(self):
        """A TEST without a FILE parent is NOT unlinked (it's a structural orphan)."""
        graph = _make_graph_with_linked_and_unlinked_tests()
        unlinked_ids = {n.id for n in graph.iter_unlinked(NodeKind.TEST)}
        # Orphan has no FILE parent, so iter_unlinked skips it
        assert "test:orphan:1" not in unlinked_ids

    def test_empty_kind_returns_empty(self):
        """Querying an unused kind returns no results."""
        graph = _make_graph_with_linked_and_unlinked_tests()
        assert list(graph.iter_unlinked(NodeKind.USER_JOURNEY)) == []


class TestIterStructuralOrphans:
    """Tests for TraceGraph.iter_structural_orphans()."""

    def test_orphan_test_is_structural_orphan(self):
        """A TEST node with no FILE ancestor is a structural orphan."""
        graph = _make_graph_with_linked_and_unlinked_tests()
        orphan_ids = {n.id for n in graph.iter_structural_orphans()}
        assert "test:orphan:1" in orphan_ids

    def test_linked_test_is_not_structural_orphan(self):
        """A TEST with a FILE parent is not a structural orphan."""
        graph = _make_graph_with_linked_and_unlinked_tests()
        orphan_ids = {n.id for n in graph.iter_structural_orphans()}
        assert "test:tests/linked.py:1" not in orphan_ids

    def test_file_nodes_are_skipped(self):
        """FILE nodes are never structural orphans."""
        graph = _make_graph_with_linked_and_unlinked_tests()
        orphan_ids = {n.id for n in graph.iter_structural_orphans()}
        file_ids = {nid for nid in orphan_ids if nid.startswith("file:")}
        assert len(file_ids) == 0

    def test_instance_nodes_are_skipped(self):
        """INSTANCE stereotype nodes (virtual) are not structural orphans."""
        graph = _make_graph_with_linked_and_unlinked_tests()
        # Add an INSTANCE node (no file parent, but should be skipped)
        instance = GraphNode(id="REQ-inst::REQ-p00001", kind=NodeKind.REQUIREMENT)
        instance.set_field("stereotype", Stereotype.INSTANCE)
        graph._index["REQ-inst::REQ-p00001"] = instance

        orphan_ids = {n.id for n in graph.iter_structural_orphans()}
        assert "REQ-inst::REQ-p00001" not in orphan_ids
