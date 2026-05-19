# Verifies: REQ-d00249-D, REQ-d00249-E
"""Missing-results and staleness behavior in tests.results / tests.results_stale."""
from __future__ import annotations

import os
import time
from pathlib import Path

from elspais.commands.health import check_test_results, check_test_results_stale
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
    return FederatedGraph.from_single(
        tg, config={"project": {"name": "test", "namespace": "REQ"}}, repo_root=Path(".")
    )


def test_missing_results_fails_with_warning(tmp_path: Path):
    spec = tmp_path / "spec.md"
    spec.write_text("# REQ-p00001\n")
    spec_node = _make_file_node(spec, FileType.SPEC)
    graph = _graph_with_files(spec_node)
    config = {"scanning": {"result": {"file_patterns": ["results/*.json"]}}}
    chk = check_test_results(graph, config=config)
    assert chk.name == "tests.results"
    assert chk.passed is False
    assert chk.severity == "warning"


def test_no_result_files_configured_remains_info():
    graph = _graph_with_files()
    chk = check_test_results(graph, config=None)
    assert chk.name == "tests.results"
    assert chk.passed is True
    assert chk.severity == "info"


def test_fresh_results_stale_check_passes(tmp_path: Path):
    spec = tmp_path / "spec.md"
    spec.write_text("# REQ-p00001\n")
    older = time.time() - 60
    os.utime(spec, (older, older))

    result_file = tmp_path / "pytest.json"
    result_file.write_text("{}")

    spec_node = _make_file_node(spec, FileType.SPEC)
    result_node = _make_file_node(result_file, FileType.RESULT)

    graph = _graph_with_files(spec_node, result_node)

    chk = check_test_results_stale(graph)
    assert chk.name == "tests.results_stale"
    assert chk.passed is True
    assert chk.severity == "info"


def test_stale_results_emits_named_warning(tmp_path: Path):
    spec = tmp_path / "spec.md"
    spec.write_text("# REQ-p00001\n")

    result_file = tmp_path / "pytest.json"
    result_file.write_text("{}")
    older = time.time() - 3600
    os.utime(result_file, (older, older))

    spec_node = _make_file_node(spec, FileType.SPEC)
    result_node = _make_file_node(result_file, FileType.RESULT)

    graph = _graph_with_files(spec_node, result_node)

    chk = check_test_results_stale(graph)
    assert chk.name == "tests.results_stale"
    assert chk.passed is False
    assert chk.severity == "warning"
    assert "stale" in (chk.message or "").lower()


def test_stale_check_skipped_when_no_results(tmp_path: Path):
    spec = tmp_path / "spec.md"
    spec.write_text("# REQ-p00001\n")
    spec_node = _make_file_node(spec, FileType.SPEC)
    graph = _graph_with_files(spec_node)
    chk = check_test_results_stale(graph)
    assert chk.name == "tests.results_stale"
    assert chk.passed is True
    assert chk.severity == "info"
