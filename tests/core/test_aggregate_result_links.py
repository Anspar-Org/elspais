# Verifies: REQ-d00254-A
"""Tests for aggregate result-crediting mode (link_results_to_tests=False).

When elspais is configured for aggregate/Dart result-crediting, RESULT nodes
must NOT produce YIELDS pending links.  This avoids spurious broken references
for unmatched per-test IDs that were never intended to match scanner TEST nodes.

The RESULT node is still created and iterable (feeds the green/red aggregate
signal); only the YIELDS link is suppressed.
"""
from __future__ import annotations

from pathlib import Path

from elspais.graph.builder import GraphBuilder, TraceGraph
from elspais.graph.GraphNode import FileType, GraphNode, NodeKind
from elspais.graph.relations import EdgeKind
from tests.core.graph_test_helpers import (
    make_test_result,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_with_flag(link_results: bool) -> TraceGraph:
    """Build a graph with an unmatched test_id result.

    The test_id deliberately matches no scanner TEST node (simulating a
    Dart/Flutter result whose per-test classname/name is lossy).
    """
    builder = GraphBuilder(
        repo_root=Path("."),
        link_results_to_tests=link_results,
    )

    result_content = make_test_result(
        "result-dart-1",
        status="passed",
        test_id="test:does/not/exist.py::x",
        name="x",
        classname="does.not.exist",
        source_path="build-reports/app/TEST.xml",
    )

    # Create FILE node for the result file (mirrors what factory.py does)
    file_id = "file:build-reports/app/TEST.xml"
    file_node = GraphNode(
        id=file_id,
        kind=NodeKind.FILE,
        label="TEST.xml",
    )
    file_node.set_field("file_type", FileType.RESULT)
    file_node.set_field("relative_path", "build-reports/app/TEST.xml")
    file_node.set_field("absolute_path", "/repo/build-reports/app/TEST.xml")
    file_node.set_field("repo", None)
    builder.register_file_node(file_node)

    builder.add_parsed_content(result_content, file_node=file_node)
    return builder.build()


# ---------------------------------------------------------------------------
# Test 1: aggregate mode (link_results_to_tests=False)
# ---------------------------------------------------------------------------


class TestAggregateMode:
    """Verifies: REQ-d00254-A"""

    def test_result_node_exists_in_aggregate_mode(self):
        """RESULT node must be created even in aggregate mode (feeds green signal)."""
        graph = _build_with_flag(link_results=False)
        result = graph.find_by_id("result-dart-1")
        assert result is not None, "RESULT node must exist for aggregate green signal"
        assert result.kind == NodeKind.RESULT

    def test_result_iterable_by_kind_in_aggregate_mode(self):
        """RESULT node must appear in iter_by_kind(RESULT) for annotator scan."""
        graph = _build_with_flag(link_results=False)
        result_nodes = list(graph.iter_by_kind(NodeKind.RESULT))
        result_ids = {n.id for n in result_nodes}
        assert (
            "result-dart-1" in result_ids
        ), "RESULT node must be iterable by kind so _compute_app_status can find it"

    def test_no_broken_reference_in_aggregate_mode(self):
        """Aggregate mode must NOT produce a broken reference for unmatched test_id."""
        graph = _build_with_flag(link_results=False)
        assert (
            not graph.has_broken_references()
        ), "Aggregate mode: unmatched RESULT should never create a broken reference"

    def test_result_has_no_yields_edge_in_aggregate_mode(self):
        """RESULT node must have no outgoing YIELDS edge in aggregate mode."""
        graph = _build_with_flag(link_results=False)
        result = graph.find_by_id("result-dart-1")
        assert result is not None
        yields_edges = [e for e in result.iter_outgoing_edges() if e.kind == EdgeKind.YIELDS]
        assert len(yields_edges) == 0, "Aggregate mode: RESULT must not have outgoing YIELDS edge"


# ---------------------------------------------------------------------------
# Test 2: default mode (link_results_to_tests=True) -- regression guard
# ---------------------------------------------------------------------------


class TestDefaultMode:
    """Verifies: REQ-d00254-A

    Regression guard: default behavior must be unchanged.
    An unmatched test_id MUST still produce a broken reference.
    """

    def test_unmatched_result_still_broken_ref_in_default_mode(self):
        """Default mode (link_results_to_tests=True): unmatched test_id is a broken ref."""
        graph = _build_with_flag(link_results=True)

        # RESULT node still exists
        result = graph.find_by_id("result-dart-1")
        assert result is not None, "RESULT node must exist in default mode too"

        # But the unmatched YIELDS target is a broken reference
        assert (
            graph.has_broken_references()
        ), "Default mode: unmatched test_id must still produce a broken reference"
        broken_targets = {br.target_id for br in graph.broken_references()}
        assert (
            "test:does/not/exist.py::x" in broken_targets
        ), "Broken reference must target the unmatched test_id"
