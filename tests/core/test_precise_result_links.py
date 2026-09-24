# Verifies: REQ-d00254-G
"""Source matching wires real RESULT->TEST YIELDS edges.

``match = "source"`` resolves a result by the real path of the test file that
produced it, and the edge it wires is what the viewer reads: the per-assertion
test map (``_get_assertion_test_map`` -> ``_serialize_test_info``) walks a TEST
node's RESULT *children*, so without those edges the VER panel is empty. These
tests pin the edges into place, and pin them apart from crediting -- an edge
shows a reader what ran, and only a result that resolved to the test itself
carries a verdict about that test's assertions.
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
    test = make_test_ref(
        verifies=["REQ-p00001-A"], source_path=FILE, start_line=1, function_name="t"
    )
    # flutter-machine results carry no test_id; they match by real source_file.
    # This one carries no line either, so it binds by naming the file's one
    # scanned test (REQ-d00284-B).
    res = make_test_result(
        "r1", status=result_status, source_file=result_file, match="source", test_id=None, name="t"
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


# Verifies: REQ-d00284-B, REQ-d00294-E
def test_lineless_records_of_the_one_test_in_a_file_are_its_own():
    """A file holding one scanned test, whose line-less records name one test,
    holds that test's results: the name picks out exactly one test. Each is
    the test's own, so the failure takes the assertion out of passing."""
    req = make_requirement("REQ-p00001", assertions=[{"label": "A", "text": "SHALL A"}])
    test = make_test_ref(
        verifies=["REQ-p00001-A"], source_path=FILE, start_line=1, function_name="t"
    )
    passed = make_test_result("ok", status="passed", source_file=FILE, match="source", name="t")
    failed = make_test_result("bad", status="failed", source_file=FILE, match="source", name="t")
    g = build_graph(req, test, passed, failed)

    test_node = _the_test_node(g)
    res_ids = {c.id for c in test_node.iter_children() if c.kind == NodeKind.RESULT}
    assert res_ids == {"ok", "bad"}
    assert {g.find_by_id(r).get_field("match_scope") for r in res_ids} == {"test"}

    annotate_coverage(g, CoverageCreditConfig())
    m = g.find_by_id("REQ-p00001").get_metric("rollup_metrics")
    assert m.tested.total_by_label.get("A") == 1.0
    assert m.verified.has_failures is True


# Verifies: REQ-d00254-A, REQ-d00284-B+C
def test_a_lineless_record_naming_another_test_binds_to_none():
    """Every line-less record in the file names one test, but not the scanned
    one: a filtered run that ran only an unscanned sibling. The scanned test
    never ran, so the record is not its result and is reported unmatched."""
    req = make_requirement("REQ-p00001", assertions=[{"label": "A", "text": "SHALL A"}])
    test = make_test_ref(
        verifies=["REQ-p00001-A"], source_path=FILE, start_line=1, function_name="t"
    )
    other = make_test_result("bad", status="failed", source_file=FILE, match="source", name="u")
    g = build_graph(req, test, other)

    test_node = _the_test_node(g)
    assert [c for c in test_node.iter_children() if c.kind == NodeKind.RESULT] == []
    assert "'u' does not name" in (g.find_by_id("bad").get_field("unbound_reason") or "")


# Verifies: REQ-d00254-A, REQ-d00284-B
def test_lineless_records_naming_two_tests_bind_to_neither():
    """Line-less records naming two different tests, in a file where one test
    was scanned, say an unscanned test ran there too. Which record is the
    scanned test's cannot be told, so neither binds and neither is a verdict
    about A: a sibling's failure is never handed to the scanned test."""
    req = make_requirement("REQ-p00001", assertions=[{"label": "A", "text": "SHALL A"}])
    test = make_test_ref(verifies=["REQ-p00001-A"], source_path=FILE, start_line=1)
    passed = make_test_result("ok", status="passed", source_file=FILE, match="source", name="a")
    failed = make_test_result("bad", status="failed", source_file=FILE, match="source", name="b")
    g = build_graph(req, test, passed, failed)

    test_node = _the_test_node(g)
    assert [c for c in test_node.iter_children() if c.kind == NodeKind.RESULT] == []
    assert "2 different tests" in (g.find_by_id("bad").get_field("unbound_reason") or "")

    annotate_coverage(g, CoverageCreditConfig())
    m = g.find_by_id("REQ-p00001").get_metric("rollup_metrics")
    assert m.tested.total_by_label.get("A") == 1.0
    assert m.verified.has_failures is False
    assert m.verified.total_by_label.get("A", 0.0) == 0.0
