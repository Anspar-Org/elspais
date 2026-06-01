# Implements: REQ-d00252
"""Validates REQ-d00252-F.

Coverage reports summarize integrated requirements grouped by the owning
associate, with a federation total. This exercises the data helper
``integrates_by_associate`` (and the optional ``integrates_total`` aggregate).
"""
import shutil
from pathlib import Path

from elspais.config import get_config
from elspais.graph.annotators import annotate_coverage
from elspais.graph.factory import build_graph
from elspais.graph.GraphNode import GraphNode, NodeKind
from elspais.graph.metrics import integrates_by_associate, integrates_total
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


def _build_with_verified_library(tmp_path):
    """Federate the e2e-integrates fixture and give the library REQ a passing
    test so its own verified dimension is non-zero (proven recipe copied from
    test_integrates_propagation.py)."""
    fed = _federate(tmp_path)
    lib_req = fed._repos["library"].graph._index["LIB-d00007"]
    lib_graph = fed._repos["library"].graph

    test = GraphNode(id="LIB-test-1", kind=NodeKind.TEST, label="test_append_only")
    result = GraphNode(id="LIB-test-1::result", kind=NodeKind.RESULT, label="result")
    result.set_field("status", "passed")
    test.link(result, EdgeKind.YIELDS)
    lib_req.link(test, EdgeKind.VERIFIES, ["A"])  # REQ --VERIFIES(A)--> TEST
    lib_graph._index[test.id] = test
    annotate_coverage(lib_graph)  # recompute library's own metrics
    return fed


def test_REQ_d00252_F_groups_by_associate(tmp_path):
    fed = _build_with_verified_library(tmp_path)
    rows = integrates_by_associate(fed)
    by_name = {r.associate: r for r in rows}
    assert "library" in by_name
    lib = by_name["library"]
    assert lib.requirement_count == 1  # APP-d00001 integrates LIB-d00007
    assert lib.implemented_covered >= 1 and lib.implemented_total >= 1
    assert lib.verified_covered >= 1 and lib.verified_total >= 1


def test_REQ_d00252_F_total_aggregates(tmp_path):
    fed = _build_with_verified_library(tmp_path)
    rows = integrates_by_associate(fed)
    total = integrates_total(rows)
    assert total.associate == "total"
    assert total.requirement_count == sum(r.requirement_count for r in rows)
    assert total.implemented_covered == sum(r.implemented_covered for r in rows)
    assert total.implemented_total == sum(r.implemented_total for r in rows)
    assert total.verified_covered == sum(r.verified_covered for r in rows)
    assert total.verified_total == sum(r.verified_total for r in rows)
    # The federation has exactly one integration.
    assert total.requirement_count == 1
    assert total.verified_covered >= 1


def test_REQ_d00252_F_no_integrates_yields_empty(tmp_path):
    """A federation with no INTEGRATES edges produces no rows."""
    fed = _federate(tmp_path)
    # Remove the only INTEGRATES edge so nothing integrates an associate.
    app_req = fed._repos["app"].graph._index["APP-d00001"]
    lib_req = fed._repos["library"].graph._index["LIB-d00007"]
    app_req.unlink(lib_req)
    rows = integrates_by_associate(fed)
    assert rows == []
    total = integrates_total(rows)
    assert total.requirement_count == 0
    assert total.implemented_total == 0 and total.verified_total == 0
