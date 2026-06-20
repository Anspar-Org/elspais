# Verifies: REQ-d00215-A
"""RESULT nodes record their source result-file path (CUR-1533)."""

from elspais.graph.GraphNode import NodeKind
from tests.core.graph_test_helpers import build_graph, make_test_result


def test_result_node_records_source_path():
    result = make_test_result(
        "result:1",
        status="passed",
        test_id="test:tests/foo_test.dart:1",
        source_path="build-reports/provenance/TEST-provenance.xml",
    )
    graph = build_graph(result)
    nodes = [n for n in graph.all_nodes() if n.kind == NodeKind.RESULT]
    assert len(nodes) == 1
    assert nodes[0].get_field("source_path") == "build-reports/provenance/TEST-provenance.xml"
