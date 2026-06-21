# Verifies: REQ-d00254-A
"""Precise file-granular matching credits verified by real test-file path."""

from elspais.graph.annotators import CoverageCreditConfig, annotate_coverage
from tests.core.graph_test_helpers import (
    build_graph,
    make_requirement,
    make_test_ref,
    make_test_result,
)


def _g(result_status):
    req = make_requirement("REQ-p00001", assertions=[{"label": "A", "text": "SHALL A"}])
    test = make_test_ref(
        verifies=["REQ-p00001-A"], source_path="provenance/test/foo_test.dart", start_line=1
    )
    res = make_test_result(
        "r1", status=result_status, source_file="provenance/test/foo_test.dart", match="precise"
    )
    return build_graph(req, test, res)


def test_precise_credits_verified_on_pass():
    g = _g("passed")
    annotate_coverage(g, CoverageCreditConfig())
    m = g.find_by_id("REQ-p00001").get_metric("rollup_metrics")
    assert m.verified.direct_pct_by_label.get("A") == 1.0
    assert m.verified.has_failures is False


def test_precise_flags_on_fail():
    g = _g("failed")
    annotate_coverage(g, CoverageCreditConfig())
    m = g.find_by_id("REQ-p00001").get_metric("rollup_metrics")
    assert m.verified.has_failures is True
    assert m.verified.direct_pct_by_label.get("A", 0.0) == 0.0


def test_precise_skipped_only_grants_no_credit():
    """Skipped tests must NOT grant verified credit (regression guard)."""
    g = _g("skipped")
    annotate_coverage(g, CoverageCreditConfig())
    m = g.find_by_id("REQ-p00001").get_metric("rollup_metrics")
    assert m.verified.has_failures is False
    assert m.verified.direct_pct_by_label.get("A", 0.0) == 0.0
