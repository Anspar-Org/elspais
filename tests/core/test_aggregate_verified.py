# Verifies: REQ-d00254-A
"""A test with no result of its own draws no verdict from its application.

The test node below declares ``Verifies:`` and is scanned, so its assertion is
tested; what never arrives is a result naming that test. The application it
belongs to reports green, red, or nothing at all, and none of the three says
anything about this test -- the assertion stays awaiting a result in every
case.
"""

import pytest

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
        # A RESULT belonging to the same application, but naming another test.
        contents.append(
            make_test_result(
                "r1",
                status=result_status,
                test_id="test:does/not/match.py::x",
                source_path="build-reports/provenance/TEST.xml",
            )
        )
    return build_graph(*contents)


@pytest.mark.parametrize("app_status", ["passed", "failed", None])
def test_app_verdict_never_reaches_a_test_of_its_own(app_status):
    """Green, red and silent all leave the assertion awaiting a result.

    ``unmatched_credit = "verified"`` is armed and the application's aggregate
    status is computed, so the arming is not what withholds the credit: the
    verdict simply belongs to other tests.
    """
    g = _build(app_status)
    annotate_coverage(g, CREDIT)
    m = g.find_by_id("REQ-p00001").get_metric("rollup_metrics")

    # The `Verifies:` linkage is live -- this assertion IS tested.
    assert m.tested.direct_pct_by_label.get("A") == 1.0
    # ...and no verdict was inferred for it, in either direction.
    assert m.verified.direct == 0.0
    assert m.verified.indirect == 0.0
    assert m.verified.has_failures is False
    # lcov_tested untouched (separate dimension)
    assert m.lcov_tested.indirect == 0.0


def test_unarmed_credit_is_no_different():
    """Without the aggregate credit configured at all, the answer is the same
    -- there is no configuration under which a sibling's verdict is borrowed."""
    g = _build("passed")
    annotate_coverage(g)  # no credit config
    m = g.find_by_id("REQ-p00001").get_metric("rollup_metrics")
    assert m.tested.direct_pct_by_label.get("A") == 1.0
    assert m.verified.direct == 0.0
    assert m.verified.has_failures is False
