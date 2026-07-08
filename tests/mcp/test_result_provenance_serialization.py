# Verifies: REQ-d00254-F
"""_serialize_test_info exposes per-result results-file provenance.

Each serialized RESULT carries ``result_file``/``result_line`` (the results
ARTIFACT, e.g. junit.xml and its <testcase> line) alongside the existing
``file``/``line`` (the TEST's source). When a RESULT was built without those
fields (e.g. a reporter with no results file), the serializer falls back to
the source-derived file/line so viewers still render a link.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from elspais.graph import EdgeKind, GraphNode, NodeKind
from elspais.graph.builder import TraceGraph
from elspais.graph.GraphNode import FileType
from elspais.mcp.server import _serialize_test_info


@pytest.fixture()
def provenance_graph():
    """TEST with two RESULT children: one with provenance, one without."""
    graph = TraceGraph(repo_root=Path("/test/repo"))

    file_node = GraphNode(
        id="file:tests/test_login.py", kind=NodeKind.FILE, label="test_login.py"
    )
    file_node.set_field("file_type", FileType.TEST)
    file_node.set_field("relative_path", "tests/test_login.py")

    test_node = GraphNode(
        id="test:tests/test_login.py::test_login", kind=NodeKind.TEST, label="test_login"
    )
    test_node.set_field("parse_line", 42)
    test_node.set_field("name", "test_login")
    file_node.link(test_node, EdgeKind.CONTAINS)

    with_prov = GraphNode(id="r-with-prov", kind=NodeKind.RESULT, label="r-with-prov")
    with_prov.set_field("status", "passed")
    with_prov.set_field("parse_line", 3)
    with_prov.set_field("result_file", "results/junit.xml")
    with_prov.set_field("result_line", 7)
    test_node.link(with_prov, EdgeKind.YIELDS)

    without_prov = GraphNode(id="r-no-prov", kind=NodeKind.RESULT, label="r-no-prov")
    without_prov.set_field("status", "failed")
    without_prov.set_field("parse_line", 9)
    test_node.link(without_prov, EdgeKind.YIELDS)

    graph._index[file_node.id] = file_node
    graph._index[test_node.id] = test_node
    graph._index[with_prov.id] = with_prov
    graph._index[without_prov.id] = without_prov
    return graph


def _serialized_results(graph) -> dict[str, dict]:
    test_node = graph.find_by_id("test:tests/test_login.py::test_login")
    info = _serialize_test_info(test_node, graph)
    return {r["id"]: r for r in info["results"]}


# Verifies: REQ-d00254-F
def test_result_file_and_line_exposed_per_result(provenance_graph):
    """A RESULT with stored provenance surfaces it verbatim."""
    entry = _serialized_results(provenance_graph)["r-with-prov"]
    assert entry["result_file"] == "results/junit.xml"
    assert entry["result_line"] == 7
    # file/line keep pointing at the TEST's source, not the artifact.
    assert entry["file"] == "tests/test_login.py"
    assert entry["line"] == 3


# Verifies: REQ-d00254-F
def test_result_without_provenance_falls_back_to_source(provenance_graph):
    """A RESULT built without result_file/result_line falls back to file/line."""
    entry = _serialized_results(provenance_graph)["r-no-prov"]
    assert entry["result_file"] == entry["file"] == "tests/test_login.py"
    assert entry["result_line"] == entry["line"] == 9
