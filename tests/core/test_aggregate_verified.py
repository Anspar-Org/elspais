# Verifies: REQ-d00254-A
"""Aggregate-green fallback credits verified for unmatched // Verifies: edges (CUR-1533)."""

from elspais.graph.annotators import CoverageCreditConfig, annotate_coverage
from tests.core.graph_test_helpers import (
    build_graph,
    make_requirement,
    make_test_ref,
    make_test_result,
)

CREDIT = CoverageCreditConfig(app_dirs=("provenance",), unmatched_credit="verified")


def _build(result_status):
    req = make_requirement("REQ-p00001", assertions=[{"label": "A", "text": "SHALL A"}])
    # Dart-style line-anchored TEST node (no function_name) verifying REQ-p00001-A.
    test = make_test_ref(
        verifies=["REQ-p00001-A"],
        source_path="provenance/test/foo_test.dart",
        start_line=1,
    )
    contents = [req, test]
    if result_status is not None:
        # A RESULT that does NOT match the TEST node's id (Dart can't match).
        contents.append(
            make_test_result(
                "r1",
                status=result_status,
                test_id="test:does/not/match.py::x",
                source_path="build-reports/provenance/TEST.xml",
            )
        )
    return build_graph(*contents)


def test_unmatched_verified_credited_when_app_green():
    g = _build("passed")
    annotate_coverage(g, CREDIT)
    m = g.find_by_id("REQ-p00001").get_metric("rollup_metrics")
    assert m.verified.direct_pct_by_label.get("A") == 1.0
    assert m.verified.has_failures is False
    # lcov_tested untouched (separate dimension)
    assert m.lcov_tested.indirect == 0.0


def test_unmatched_flagged_when_app_red():
    g = _build("failed")
    annotate_coverage(g, CREDIT)
    m = g.find_by_id("REQ-p00001").get_metric("rollup_metrics")
    assert m.verified.has_failures is True


def test_no_results_stays_tested_only():
    g = _build(None)
    annotate_coverage(g, CREDIT)
    m = g.find_by_id("REQ-p00001").get_metric("rollup_metrics")
    assert m.tested.direct_pct_by_label.get("A") == 1.0  # // Verifies: linkage present
    assert m.verified.direct == 0.0  # no app status -> no aggregate credit


def test_default_off_no_credit():
    g = _build("passed")
    annotate_coverage(g)  # no credit config -> off
    m = g.find_by_id("REQ-p00001").get_metric("rollup_metrics")
    assert m.verified.direct == 0.0
