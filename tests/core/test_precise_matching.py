# Verifies: REQ-d00254-A, REQ-d00254-G
"""A source result that names no test credits nothing and flags nothing.

``match = "source"`` binds a result at the most precise scope available. The
results below carry no line and name a file holding two tests, so they resolve
to the file and no further -- they name every test written in it and therefore
none of them, and no test holds them. A result that
binds at neither step nor test scope contributes no verdict, and the assertion
its file's test declares stays awaiting one.
"""

import pytest

from elspais.graph.annotators import CoverageCreditConfig, annotate_coverage
from elspais.graph.relations import EdgeKind
from tests.core.graph_test_helpers import (
    build_graph,
    make_requirement,
    make_test_ref,
    make_test_result,
)


def _g(result_status):
    req = make_requirement("REQ-p00001", assertions=[{"label": "A", "text": "SHALL A"}])
    test = make_test_ref(
        verifies=["REQ-p00001-A"],
        source_path="provenance/test/foo_test.dart",
        start_line=1,
        function_name="first",
    )
    sibling = make_test_ref(
        verifies=[],
        source_path="provenance/test/foo_test.dart",
        start_line=20,
        function_name="second",
    )
    res = make_test_result(
        "r1", status=result_status, source_file="provenance/test/foo_test.dart", match="source"
    )
    return build_graph(req, test, sibling, res)


@pytest.mark.parametrize("result_status", ["passed", "failed", "skipped"])
def test_file_scope_result_grants_no_verdict(result_status):
    """Pass, fail and skip alike: the result reached the file, not the test."""
    g = _g(result_status)
    annotate_coverage(g, CoverageCreditConfig())

    # The result did arrive, and bound to no test: it names the file only.
    r1 = g.find_by_id("r1")
    assert r1.get_field("match_scope") is None
    assert list(r1.iter_parents(edge_kinds={EdgeKind.YIELDS})) == []
    assert "recorded no line" in r1.get_field("unbound_reason")
    m = g.find_by_id("REQ-p00001").get_metric("rollup_metrics")
    # The `Verifies:` linkage is live, so the assertion IS tested...
    assert m.tested.total_by_label.get("A") == 1.0
    # ...and awaiting a result: neither credited nor blamed.
    assert m.verified.total_by_label.get("A", 0.0) == 0.0
    assert m.verified.has_failures is False
