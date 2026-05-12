# Verifies: REQ-d00249-D, REQ-d00249-E
"""Staleness handling in check_test_results."""
from __future__ import annotations

import os
import time
from pathlib import Path

from elspais.commands.health import check_test_results
from elspais.graph.builder import TraceGraph
from elspais.graph.federated import FederatedGraph
from elspais.graph.GraphNode import FileType, GraphNode, NodeKind, make_file_id


def _make_file_node(path: Path, file_type: FileType) -> GraphNode:
    node = GraphNode(
        id=make_file_id(str(path.name)),
        kind=NodeKind.FILE,
    )
    node.set_field("file_type", file_type)
    node.set_field("absolute_path", str(path))
    node.set_field("relative_path", path.name)
    return node


def _graph_with_files(*nodes: GraphNode) -> FederatedGraph:
    tg = TraceGraph()
    for n in nodes:
        tg._index[n.id] = n
    return FederatedGraph.from_single(tg, config=None, repo_root=Path("."))


def test_missing_results_warns(tmp_path: Path):
    spec = tmp_path / "spec.md"
    spec.write_text("# REQ-p00001\n")
    spec_node = _make_file_node(spec, FileType.SPEC)
    graph = _graph_with_files(spec_node)
    config = {"scanning": {"result": {"file_patterns": ["results/*.json"]}}}
    chk = check_test_results(graph, config=config)
    assert chk.name == "tests.results"
    assert chk.severity == "warning"
    msg = (chk.message or "").lower()
    assert "missing" in msg or "no test" in msg or "results" in msg


def test_no_result_files_configured_remains_info():
    graph = _graph_with_files()
    chk = check_test_results(graph, config=None)
    assert chk.severity == "info"


def test_fresh_results_no_stale_finding(tmp_path: Path):
    spec = tmp_path / "spec.md"
    spec.write_text("# REQ-p00001\n")
    older = time.time() - 60
    os.utime(spec, (older, older))

    result_file = tmp_path / "pytest.json"
    result_file.write_text("{}")

    spec_node = _make_file_node(spec, FileType.SPEC)
    result_node = _make_file_node(result_file, FileType.RESULT)
    content_result = GraphNode(id="result:dummy", kind=NodeKind.RESULT)
    content_result.set_field("status", "passed")

    graph = _graph_with_files(spec_node, result_node, content_result)

    chk = check_test_results(graph, config={"scanning": {"result": {"file_patterns": ["*.json"]}}})
    assert "stale" not in chk.message.lower()
    assert all("stale" not in (f.message or "").lower() for f in chk.findings)


def test_stale_results_emits_stale_finding(tmp_path: Path):
    spec = tmp_path / "spec.md"
    spec.write_text("# REQ-p00001\n")

    result_file = tmp_path / "pytest.json"
    result_file.write_text("{}")
    older = time.time() - 3600
    os.utime(result_file, (older, older))

    spec_node = _make_file_node(spec, FileType.SPEC)
    result_node = _make_file_node(result_file, FileType.RESULT)
    content_result = GraphNode(id="result:dummy", kind=NodeKind.RESULT)
    content_result.set_field("status", "passed")

    graph = _graph_with_files(spec_node, result_node, content_result)

    chk = check_test_results(graph, config={"scanning": {"result": {"file_patterns": ["*.json"]}}})
    has_stale = (
        any("stale" in (f.message or "").lower() for f in chk.findings)
        or "stale" in (chk.message or "").lower()
    )
    finding_msgs = [f.message for f in chk.findings]
    assert has_stale, (
        f"expected stale finding, got message={chk.message!r}, " f"findings={finding_msgs}"
    )
