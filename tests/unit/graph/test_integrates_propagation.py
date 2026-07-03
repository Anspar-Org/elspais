# Verifies: REQ-d00252, REQ-d00258-B
"""Validates REQ-d00252-D.

A consumer REQ inherits the library REQ's implemented + passing coverage,
where "passing" is the result-verified/line-coverage-credited union
(REQ-d00258-B `tested_and_passing()`).
"""

import shutil
from pathlib import Path

from elspais.config import get_config
from elspais.graph.annotators import annotate_coverage
from elspais.graph.factory import build_graph
from elspais.graph.GraphNode import GraphNode, NodeKind
from elspais.graph.metrics import CoverageDimension, RollupMetrics, integrates_rollup
from elspais.graph.relations import EdgeKind

FIX = Path(__file__).parents[2] / "fixtures" / "e2e-integrates"


def _federate(tmp_path):
    dest = tmp_path / "proj"
    shutil.copytree(FIX, dest)
    return build_graph(
        config=get_config(None, dest / "app"),
        repo_root=dest / "app",
        scan_code=False,
        scan_tests=False,
    )


def test_REQ_d00252_D_consumer_inherits_library_coverage(tmp_path):
    fed = _federate(tmp_path)
    app_req = fed._repos["app"].graph._index["APP-d00001"]
    lib_req = fed._repos["library"].graph._index["LIB-d00007"]
    lib_graph = fed._repos["library"].graph

    # Library REQ has assertion A; give it a passing test so its own verified populates.
    test = GraphNode(id="LIB-test-1", kind=NodeKind.TEST, label="test_append_only")
    result = GraphNode(id="LIB-test-1::result", kind=NodeKind.RESULT, label="result")
    result.set_field("status", "passed")
    test.link(result, EdgeKind.YIELDS)
    lib_req.link(test, EdgeKind.VERIFIES, ["A"])  # REQ --VERIFIES(A)--> TEST
    lib_graph._index[test.id] = test
    annotate_coverage(lib_graph)  # recompute library's own metrics

    rollup = integrates_rollup(app_req)
    assert rollup.implemented_covered >= 1
    assert rollup.verified_covered >= 1  # library's passing test propagates
    assert rollup.verified_total >= 1

    # The consumer's OWN persisted verified stays zero (its assertion A is untested locally).
    own = app_req.get_metric("rollup_metrics")
    assert own.verified.indirect == 0


def test_REQ_d00252_D_no_integrates_yields_zero(tmp_path):
    """A requirement with no INTEGRATES edge inherits nothing."""
    fed = _federate(tmp_path)
    lib_req = fed._repos["library"].graph._index["LIB-d00007"]
    rollup = integrates_rollup(lib_req)
    assert rollup.implemented_total == 0 and rollup.verified_total == 0


def test_REQ_d00252_D_lcov_only_credit_propagates_as_passing(tmp_path):
    """A library REQ whose only evidence is line-coverage credit (lcov_tested,
    no Verifies:-based result) still propagates as passing coverage to the
    consumer (REQ-d00258-B `tested_and_passing()` union, not raw `verified`).
    """
    fed = _federate(tmp_path)
    app_req = fed._repos["app"].graph._index["APP-d00001"]
    lib_req = fed._repos["library"].graph._index["LIB-d00007"]

    # Library REQ has assertion A. Give it ONLY lcov_tested credit -- no
    # Verifies:-based result, so its raw `verified` dimension stays at zero.
    lib_req.set_metric(
        "rollup_metrics",
        RollupMetrics(
            total_assertions=1,
            lcov_tested=CoverageDimension(
                total=1,
                direct=1.0,
                indirect=1.0,
                direct_labels={"A"},
                indirect_labels={"A"},
                direct_pct_by_label={"A": 1.0},
                indirect_pct_by_label={"A": 1.0},
            ),
        ),
    )

    rollup = integrates_rollup(app_req)
    assert rollup.verified_covered >= 1  # lcov-only credit propagates as passing
    assert rollup.verified_total >= 1
    assert rollup.has_failures is False


def test_REQ_d00252_D_library_failures_propagate_to_consumer(tmp_path):
    """A library assertion with a FAILING Verifies-test result but full lcov
    credit reads as covered in the tested_and_passing() union (max per-label
    fraction), so the covered count alone would show 100% passing. The rollup
    must also carry has_failures=True so a red library suite is never
    displayed as clean to INTEGRATES consumers (REQ-d00258-B).
    """
    fed = _federate(tmp_path)
    app_req = fed._repos["app"].graph._index["APP-d00001"]
    lib_req = fed._repos["library"].graph._index["LIB-d00007"]

    lib_req.set_metric(
        "rollup_metrics",
        RollupMetrics(
            total_assertions=1,
            # Failed Verifies-result: zero verified coverage, has_failures set.
            verified=CoverageDimension(total=1, has_failures=True),
            # Full line-coverage credit on the same assertion.
            lcov_tested=CoverageDimension(
                total=1,
                direct=1.0,
                indirect=1.0,
                direct_labels={"A"},
                indirect_labels={"A"},
                direct_pct_by_label={"A": 1.0},
                indirect_pct_by_label={"A": 1.0},
            ),
        ),
    )

    rollup = integrates_rollup(app_req)
    assert rollup.verified_covered >= 1  # union max() still reads covered...
    assert rollup.has_failures is True  # ...but the failure flag survives
