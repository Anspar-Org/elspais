# Verifies: REQ-d00249-D, REQ-d00249-E, REQ-p00019-J
"""Missing-results and staleness behavior in tests.results / tests.results_stale."""
from __future__ import annotations

import copy
import os
import time
from collections.abc import Sequence
from pathlib import Path

from elspais.commands.health import check_test_results, check_test_results_stale
from elspais.graph.builder import TraceGraph
from elspais.graph.federated import FederatedGraph, RepoEntry
from elspais.graph.GraphNode import FileType, GraphNode, NodeKind, make_file_id


def _make_file_node(path: Path, file_type: FileType) -> GraphNode:
    node = GraphNode(
        id=make_file_id("REQ", str(path.name)),
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


def _member_config(name: str, namespace: str, targets: Sequence[str]) -> dict:
    """A repo config declaring one test target per name in ``targets``."""
    return {
        "project": {"name": name, "namespace": namespace},
        "scanning": {
            "test": {
                "targets": [
                    {"name": t, "results": f"{t}/*.json", "reporter": "junit"} for t in targets
                ]
            }
        },
    }


def _federation(*configs: dict) -> FederatedGraph:
    """A federation of one empty TraceGraph per supplied member config."""
    return FederatedGraph(
        [
            RepoEntry(
                name=cfg["project"]["name"],
                graph=TraceGraph(),
                config=cfg,
                repo_root=Path("/repo") / cfg["project"]["name"],
            )
            for cfg in configs
        ]
    )


def test_missing_results_fails_with_warning(tmp_path: Path):
    spec = tmp_path / "spec.md"
    spec.write_text("# REQ-p00001\n")
    spec_node = _make_file_node(spec, FileType.SPEC)
    graph = _graph_with_files(spec_node)
    config = {
        "scanning": {
            "test": {
                "targets": [{"name": "unit", "results": "results/*.json", "reporter": "junit"}]
            }
        }
    }
    chk = check_test_results(graph, config=config)
    assert chk.name == "tests.results"
    assert chk.passed is False
    assert chk.severity == "warning"


# Verifies: REQ-d00249-D, REQ-p00019-J
def test_associate_targets_reported_when_host_configures_none():
    """Where results live is the member's fact, not the invoking project's.

    The host declares no test targets and the associate declares three. Read
    from the invoking config alone this federation looks unconfigured, and the
    reader is sent looking for a missing configuration instead of missing
    results.
    """
    host = _member_config("host", "HOST", [])
    assoc = _member_config("lib", "LIB", ["unit", "integration", "e2e"])
    graph = _federation(host, assoc)

    chk = check_test_results(graph, config=host)

    assert chk.name == "tests.results"
    assert chk.passed is False
    assert chk.severity == "warning"
    assert "Test targets configured (3)" in (chk.message or "")
    assert "No test targets configured" not in (chk.message or "")
    # One member contributed, so nothing is spread across repositories.
    assert "across" not in (chk.message or "")


# Verifies: REQ-d00249-D, REQ-p00019-J
def test_targets_from_two_members_are_summed_and_counted_as_repositories():
    """A total drawn from two members says so, rather than implying one repo."""
    host = _member_config("host", "HOST", ["unit"])
    assoc = _member_config("lib", "LIB", ["contract", "e2e"])
    graph = _federation(host, assoc)

    chk = check_test_results(graph, config=host)

    assert chk.passed is False
    assert "Test targets configured (3)" in (chk.message or "")
    assert "across 2 repositories" in (chk.message or "")


# Verifies: REQ-d00249-D, REQ-p00019-J
def test_single_repo_federation_reports_only_its_own_targets():
    """A lone repository's answer is unchanged: its own count, no spread."""
    cfg = _member_config("solo", "SOLO", ["unit", "e2e"])
    graph = FederatedGraph.from_single(TraceGraph(), config=cfg, repo_root=Path("."))

    chk = check_test_results(graph, config=cfg)

    assert chk.passed is False
    assert chk.severity == "warning"
    assert "Test targets configured (2)" in (chk.message or "")
    assert "across" not in (chk.message or "")


# Verifies: REQ-p00019-J
def test_host_targets_counted_once_when_invoking_config_is_the_host_config():
    """The invoking config IS a member's config; counting it twice inflates.

    A deep copy is passed so the host is recognised by what it declares rather
    than by object identity.
    """
    host = _member_config("host", "HOST", ["unit", "e2e"])
    assoc = _member_config("lib", "LIB", [])
    graph = _federation(host, assoc)

    chk = check_test_results(graph, config=copy.deepcopy(host))

    assert chk.passed is False
    assert "Test targets configured (2)" in (chk.message or "")
    assert "across" not in (chk.message or "")


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
