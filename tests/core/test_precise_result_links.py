# Verifies: REQ-d00254-G
"""Source matching wires real RESULT->TEST YIELDS edges.

Part B (CUR-1533) credited the ``verified`` *metric* for ``match = "source"``
results via a source_file path-index in the annotator, but never created the
RESULT->TEST graph edges that ``match = "source"`` promises ("file-granular
RESULT->TEST verification by real path"). The viewer's per-assertion test map
(``_get_assertion_test_map`` -> ``_serialize_test_info``) reads a TEST node's
RESULT *children*, so without those edges the per-assertion VER panel is always
empty even when the metric shows verified. These tests pin the edges into place.
"""

from __future__ import annotations

from elspais.graph.annotators import CoverageCreditConfig, annotate_coverage
from elspais.graph.GraphNode import NodeKind
from elspais.graph.relations import EdgeKind
from elspais.mcp.server import _get_assertion_test_map
from tests.core.graph_test_helpers import (
    build_graph,
    make_requirement,
    make_test_ref,
    make_test_result,
)

FILE = "provenance/test/foo_test.dart"


def _graph(result_status: str = "passed", result_file: str = FILE):
    req = make_requirement("REQ-p00001", assertions=[{"label": "A", "text": "SHALL A"}])
    test = make_test_ref(verifies=["REQ-p00001-A"], source_path=FILE, start_line=1)
    # flutter-machine results carry no test_id; they match by real source_file.
    res = make_test_result(
        "r1", status=result_status, source_file=result_file, match="source", test_id=None
    )
    return build_graph(req, test, res)


def _the_test_node(graph):
    tests = list(graph.iter_by_kind(NodeKind.TEST))
    assert len(tests) == 1, f"expected one TEST node, got {len(tests)}"
    return tests[0]


def test_precise_result_is_child_of_matching_test():
    """A precise RESULT whose source_file matches a TEST's file becomes its child."""
    g = _graph("passed")
    test_node = _the_test_node(g)
    result_children = [c for c in test_node.iter_children() if c.kind == NodeKind.RESULT]
    assert len(result_children) == 1
    assert result_children[0].id == "r1"
    # The edge is a YIELDS edge (TEST -> RESULT), same as test_id-based linking.
    yields_targets = [
        e.target.id for e in test_node.iter_outgoing_edges() if e.kind == EdgeKind.YIELDS
    ]
    assert "r1" in yields_targets


def test_precise_result_surfaces_in_assertion_test_map():
    """The viewer's per-assertion test map exposes the passing result (VER panel)."""
    g = _graph("passed")
    tmap = _get_assertion_test_map(g, "REQ-p00001")
    assert tmap["success"] is True
    tests = tmap["assertion_tests"]["A"]["tests"]
    assert len(tests) == 1
    results = tests[0]["results"]
    assert len(results) == 1, "per-assertion VER panel should show the precise result"
    assert results[0]["status"] == "passed"


def test_precise_result_non_matching_file_does_not_link():
    """A precise RESULT whose source_file matches no TEST creates no edge."""
    g = _graph("passed", result_file="provenance/test/other_test.dart")
    test_node = _the_test_node(g)
    result_children = [c for c in test_node.iter_children() if c.kind == NodeKind.RESULT]
    assert result_children == []


def test_edges_do_not_change_file_level_metric_semantics():
    """REQ-d00254-G stays file-level: any failure in a precise file flags it and
    withholds credit, even though the passing RESULT is now a TEST child for the
    viewer. The edges are presentation; crediting runs through source_file_index."""
    req = make_requirement("REQ-p00001", assertions=[{"label": "A", "text": "SHALL A"}])
    test = make_test_ref(verifies=["REQ-p00001-A"], source_path=FILE, start_line=1)
    passed = make_test_result("ok", status="passed", source_file=FILE, match="source")
    failed = make_test_result("bad", status="failed", source_file=FILE, match="source")
    g = build_graph(req, test, passed, failed)

    # Both results are wired to the test node (viewer sees the full picture).
    test_node = _the_test_node(g)
    res_ids = {c.id for c in test_node.iter_children() if c.kind == NodeKind.RESULT}
    assert res_ids == {"ok", "bad"}

    # But the metric follows file-level G: any failure flags, no credit.
    annotate_coverage(g, CoverageCreditConfig())
    m = g.find_by_id("REQ-p00001").get_metric("rollup_metrics")
    assert m.verified.has_failures is True
    assert m.verified.direct_pct_by_label.get("A", 0.0) == 0.0
