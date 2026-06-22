# Verifies: REQ-d00254-A
"""RESULT nodes record their source result-file path (CUR-1533)."""

from elspais.graph.GraphNode import NodeKind
from elspais.graph.parsers import ParsedContent
from tests.core.graph_test_helpers import MockSourceContext, build_graph, make_test_result


def test_result_node_records_source_path():
    result = make_test_result(
        "result:1",
        status="passed",
        test_id="test:tests/foo_test.dart:1",
        source_path="build-reports/provenance/TEST-provenance.xml",
    )
    graph = build_graph(result)
    nodes = list(graph.iter_by_kind(NodeKind.RESULT))
    assert len(nodes) == 1
    assert nodes[0].get_field("source_path") == "build-reports/provenance/TEST-provenance.xml"


def test_result_source_path_prefers_parsed_data_over_context():
    content = ParsedContent(
        content_type="test_result",
        start_line=1,
        end_line=1,
        raw_text="",
        parsed_data={
            "id": "result:2",
            "status": "passed",
            "test_id": "test:tests/foo_test.dart:1",
            "source_path": "build-reports/reaction/TEST-reaction.xml",
        },
    )
    content.source_context = MockSourceContext(source_id="some/other/path.xml")
    graph = build_graph(content)
    nodes = list(graph.iter_by_kind(NodeKind.RESULT))
    assert len(nodes) == 1
    assert nodes[0].get_field("source_path") == "build-reports/reaction/TEST-reaction.xml"
