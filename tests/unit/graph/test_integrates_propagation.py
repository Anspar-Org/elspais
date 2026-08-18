# Verifies: REQ-d00252, REQ-d00258-N
"""Validates REQ-d00252-D.

A consumer REQ inherits the library REQ's implemented + passing coverage,
where "passing" is what the library's declared tests returned
(REQ-d00258-N `tested_and_passing()`) -- line coverage credits none of it.
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

    # Library REQ has assertion A. Give it CODE that implements A so its
    # `implemented` dimension populates (test Verifies alone is NOT implemented
    # evidence -- REQ-d00084-D), plus a passing test so its verified populates.
    code = GraphNode(id="LIB-code-1", kind=NodeKind.CODE, label="append_only")
    lib_req.link(code, EdgeKind.IMPLEMENTS, ["A"])  # REQ --IMPLEMENTS(A)--> CODE
    lib_graph._index[code.id] = code
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
    assert own.verified.covered == 0


def test_REQ_d00252_D_no_integrates_yields_zero(tmp_path):
    """A requirement with no INTEGRATES edge inherits nothing."""
    fed = _federate(tmp_path)
    lib_req = fed._repos["library"].graph._index["LIB-d00007"]
    rollup = integrates_rollup(lib_req)
    assert rollup.implemented_total == 0 and rollup.verified_total == 0


# Verifies: REQ-d00258-N
def test_REQ_d00252_D_lcov_only_credit_does_not_propagate_as_passing(tmp_path):
    """A library REQ whose only evidence is line-coverage credit propagates NO
    passing coverage to the consumer. The library's lines were executed; no
    test declared against its assertion returned a verdict, and a consumer
    told the integration is passing on that basis would be reading an
    annotation nobody wrote. The denominator still propagates, so the consumer
    sees 0 of 1 rather than nothing at all.
    """
    fed = _federate(tmp_path)
    app_req = fed._repos["app"].graph._index["APP-d00001"]
    lib_req = fed._repos["library"].graph._index["LIB-d00007"]

    # Library REQ has assertion A. Give it ONLY lcov_tested credit -- with
    # no result from a `Verifies` test, its raw `verified` dimension stays
    # at zero.
    lib_req.set_metric(
        "rollup_metrics",
        RollupMetrics(
            total_assertions=1,
            verified=CoverageDimension(total=1),
            lcov_tested=CoverageDimension(
                total=1,
                immediate_direct_by_label={"A": 1.0},
            ),
        ),
    )

    rollup = integrates_rollup(app_req)
    assert rollup.verified_covered == 0
    assert rollup.verified_total == 1
    assert rollup.has_failures is False


# Verifies: REQ-d00258-N
def test_REQ_d00252_D_library_failures_propagate_to_consumer(tmp_path):
    """A library whose suite is partly red must never read clean downstream.
    Assertion B's declared test passed, so the integration reads covered on
    the count alone; A's failed, so the rollup must also carry
    has_failures=True for the consumer to flag.
    """
    fed = _federate(tmp_path)
    app_req = fed._repos["app"].graph._index["APP-d00001"]
    lib_req = fed._repos["library"].graph._index["LIB-d00007"]

    lib_req.set_metric(
        "rollup_metrics",
        RollupMetrics(
            total_assertions=2,
            # B's declared test passed; A's failed.
            verified=CoverageDimension(
                total=2,
                has_failures=True,
                failing_labels={"A"},
                immediate_direct_by_label={"B": 1.0},
            ),
        ),
    )

    rollup = integrates_rollup(app_req)
    assert rollup.verified_covered >= 1  # B's pass still reads covered...
    assert rollup.has_failures is True  # ...but the failure flag survives
