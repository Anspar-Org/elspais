# Verifies: REQ-d00215-A
"""lcov_tested assertion-level crediting (CUR-1533)."""

from elspais.graph.annotators import CoverageCreditConfig, annotate_coverage
from tests.core.graph_test_helpers import (
    build_graph,
    make_code_ref,
    make_requirement,
    make_test_result,
)


def _build(*, covered, result_status="passed", credit_mode="verified", min_frac=0.0):
    req = make_requirement("REQ-p00001", assertions=[{"label": "A", "text": "SHALL A"}])
    code = make_code_ref(
        implements=["REQ-p00001-A"],
        source_path="provenance/lib/foo.dart",
        start_line=10,
        end_line=12,
    )
    contents = [req, code]
    if result_status is not None:
        contents.append(
            make_test_result(
                "r1", status=result_status, source_path="build-reports/provenance/TEST.xml"
            )
        )
    g = build_graph(*contents)
    fn = g.find_by_id("file:provenance/lib/foo.dart")
    # lines 10,11,12; `covered` selects which are hit
    fn.set_field("line_coverage", {ln: (1 if ln in covered else 0) for ln in (10, 11, 12)})
    credit = CoverageCreditConfig(
        app_dirs=("provenance",),
        coverage_dirs=("provenance",),
        assertion_credit=credit_mode,
        min_coverage_fraction=min_frac,
    )
    annotate_coverage(g, credit)
    return g.find_by_id("REQ-p00001").get_metric("rollup_metrics")


def test_lcov_tested_credited_any_execution_green():
    m = _build(covered={10})  # 1 of 3 lines
    assert m.lcov_tested.direct_pct_by_label.get("A") == 1 / 3
    assert "A" in m.lcov_tested.direct_labels
    assert m.lcov_tested.has_failures is False
    # not folded into verified
    assert m.verified.direct == 0.0


def test_lcov_tested_flagged_when_app_red():
    m = _build(covered={10}, result_status="failed")
    assert "A" in m.lcov_tested.direct_labels
    assert m.lcov_tested.has_failures is True


def test_lcov_tested_zero_coverage_not_credited():
    m = _build(covered=set())
    assert m.lcov_tested.direct_labels == set()


def test_lcov_tested_tested_mode_never_fails():
    m = _build(covered={10}, result_status="failed", credit_mode="tested")
    assert "A" in m.lcov_tested.direct_labels
    assert m.lcov_tested.has_failures is False


def test_lcov_tested_threshold_blocks_partial():
    m = _build(covered={10}, min_frac=0.5)  # 1/3 < 0.5
    assert m.lcov_tested.direct_labels == set()


def test_lcov_tested_off_by_default():
    m = _build(covered={10}, credit_mode="off")
    assert m.lcov_tested.direct == 0.0
