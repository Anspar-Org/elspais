# Verifies: REQ-d00254-C
"""RESULT nodes carry real source_file + match from their target.

Tests for target-driven result ingestion via the reporter registry.
"""
from __future__ import annotations

from pathlib import Path

from elspais.config.schema import (
    ElspaisConfig,
    ScanningConfig,
    TestScanningConfig,
    TestTargetConfig,
)
from elspais.graph.GraphNode import NodeKind
from tests.core.graph_test_helpers import build_graph, make_test_result

# ---------------------------------------------------------------------------
# (a) make_test_result / _add_test_result -- source_file + match on RESULT node
# ---------------------------------------------------------------------------


def test_result_records_source_file_and_match():
    # make_test_result is extended (this task) to accept source_file + match
    r = make_test_result(
        "res:1",
        status="passed",
        source_path="build-reports/x.xml",
        source_file="provenance/test/foo_test.dart",
        match="precise",
    )
    g = build_graph(r)
    node = next(iter(g.iter_by_kind(NodeKind.RESULT)))
    assert node.get_field("source_file") == "provenance/test/foo_test.dart"
    assert node.get_field("match") == "precise"


def test_result_default_source_file_and_match():
    """When source_file and match are not supplied, they default to source_path
    and 'aggregate' respectively."""
    r = make_test_result(
        "res:2",
        status="passed",
        source_path="build-reports/y.xml",
    )
    g = build_graph(r)
    node = next(iter(g.iter_by_kind(NodeKind.RESULT)))
    # source_file falls back to the source_path when not explicitly set
    assert node.get_field("source_file") == "build-reports/y.xml"
    assert node.get_field("match") == "aggregate"


# ---------------------------------------------------------------------------
# (b) _ingest_target_results integration test
# ---------------------------------------------------------------------------

# Minimal flutter-machine output: one suite, one test passing.
_FLUTTER_MACHINE_SAMPLE = (
    '{"type":"suite","suite":{"id":0,"platform":"vm","path":"test/widget_test.dart"}}\n'
    '{"type":"testStart","test":{"id":1,"name":"my widget renders","suiteID":0,'
    '"line":10,"column":5,"metadata":{},"root_line":10,"root_column":5}}\n'
    '{"type":"testDone","testID":1,"result":"success","hidden":false,"time":42}\n'
)


def test_ingest_target_results_flutter_machine(tmp_path: Path):
    """_ingest_target_results adds RESULT nodes for a flutter-machine report."""
    from elspais.graph.builder import GraphBuilder
    from elspais.graph.factory import _ingest_target_results

    builder = GraphBuilder(repo_root=tmp_path)
    target = TestTargetConfig(name="flutter", reporter="flutter-machine", match="precise")
    count = _ingest_target_results(builder, target, _FLUTTER_MACHINE_SAMPLE, tmp_path)
    assert count == 1

    graph = builder.build()
    results = list(graph.iter_by_kind(NodeKind.RESULT))
    assert len(results) == 1
    node = results[0]
    assert node.get_field("status") == "passed"
    assert node.get_field("match") == "precise"
    # source_file is set (to the suite path from the flutter event)
    assert node.get_field("source_file") == "test/widget_test.dart"


def test_ingest_target_results_returns_zero_for_coverage_reporter(tmp_path: Path):
    """Coverage reporters (kind='coverage') are skipped; returns 0."""
    from elspais.graph.builder import GraphBuilder
    from elspais.graph.factory import _ingest_target_results

    builder = GraphBuilder(repo_root=tmp_path)
    target = TestTargetConfig(name="cov", reporter="lcov", match="aggregate")
    count = _ingest_target_results(builder, target, "SF:src/foo.dart\nend_of_record\n", tmp_path)
    assert count == 0
    graph = builder.build()
    assert list(graph.iter_by_kind(NodeKind.RESULT)) == []


def test_ingest_target_results_source_file_repo_relative(tmp_path: Path):
    """Absolute source_path from parser is normalized to repo-relative source_file."""
    from elspais.graph.builder import GraphBuilder
    from elspais.graph.factory import _ingest_target_results

    # Write a flutter event with an absolute path under tmp_path
    abs_path = str(tmp_path / "test" / "foo_test.dart")
    sample = (
        f'{{"type":"suite","suite":{{"id":0,"platform":"vm","path":"{abs_path}"}}}}\n'
        '{"type":"testStart","test":{"id":1,"name":"passes","suiteID":0,"line":1,"column":1,"metadata":{}}}\n'
        '{"type":"testDone","testID":1,"result":"success","hidden":false,"time":10}\n'
    )
    builder = GraphBuilder(repo_root=tmp_path)
    target = TestTargetConfig(name="flutter", reporter="flutter-machine", match="precise")
    _ingest_target_results(builder, target, sample, tmp_path)
    graph = builder.build()
    node = next(iter(graph.iter_by_kind(NodeKind.RESULT)))
    # source_file should be repo-relative, not absolute
    assert node.get_field("source_file") == "test/foo_test.dart"


# ---------------------------------------------------------------------------
# (c) run_configured_targets
# ---------------------------------------------------------------------------


def _cfg_with_targets(targets: list[TestTargetConfig]) -> ElspaisConfig:
    return ElspaisConfig(scanning=ScanningConfig(test=TestScanningConfig(targets=targets)))


def test_run_configured_targets_no_targets_returns_empty(tmp_path: Path):
    from elspais.commands.test_runner import run_configured_targets

    cfg = _cfg_with_targets([])
    results, captured = run_configured_targets(cfg, tmp_path)
    assert results == []
    assert captured == {}


def test_run_configured_targets_stdout_channel_captured(tmp_path: Path):
    """A stdout-channel reporter's output is captured into the map."""
    from elspais.commands.test_runner import run_configured_targets

    # flutter-machine is a stdout-channel reporter
    # Build a single-line JSON event that is parseable (content doesn't matter
    # for the capture test — we just need to verify the map key + stdout capture)
    one_line = '{"type":"allSuites","count":0}'
    target = TestTargetConfig(
        name="flutter",
        reporter="flutter-machine",
        command=f"echo '{one_line}'",
        match="aggregate",
    )
    cfg = _cfg_with_targets([target])
    results, captured = run_configured_targets(cfg, tmp_path)
    assert len(results) == 1
    assert results[0].returncode == 0
    assert "flutter" in captured
    assert one_line in captured["flutter"]


def test_run_configured_targets_file_channel_not_captured(tmp_path: Path):
    """A file-channel reporter is NOT captured into the map (output passes through)."""
    from elspais.commands.test_runner import run_configured_targets

    target = TestTargetConfig(
        name="junit",
        reporter="junit",
        command="true",
        match="aggregate",
    )
    cfg = _cfg_with_targets([target])
    results, captured = run_configured_targets(cfg, tmp_path)
    assert len(results) == 1
    assert results[0].returncode == 0
    assert "junit" not in captured


def test_run_configured_targets_target_without_command_skipped(tmp_path: Path):
    """Targets with empty command are not run."""
    from elspais.commands.test_runner import run_configured_targets

    target = TestTargetConfig(name="noop", reporter="flutter-machine", command="")
    cfg = _cfg_with_targets([target])
    results, captured = run_configured_targets(cfg, tmp_path)
    assert results == []
    assert captured == {}


def test_run_configured_targets_fail_fast(tmp_path: Path):
    """fail_fast=True stops after first non-zero exit."""
    from elspais.commands.test_runner import run_configured_targets

    marker = tmp_path / "marker.txt"
    targets = [
        TestTargetConfig(name="bad", reporter="flutter-machine", command="false"),
        TestTargetConfig(name="never", reporter="flutter-machine", command=f"touch {marker}"),
    ]
    cfg = _cfg_with_targets(targets)
    results, _ = run_configured_targets(cfg, tmp_path, fail_fast=True)
    assert len(results) == 1
    assert results[0].name == "bad"
    assert not marker.exists()


def test_run_configured_targets_cwd_outside_repo_rejected(tmp_path: Path):
    """cwd that escapes the repo root is rejected with returncode -1."""
    from elspais.commands.test_runner import run_configured_targets

    outside = tmp_path / "elsewhere"
    outside.mkdir()
    repo = tmp_path / "repo"
    repo.mkdir()
    target = TestTargetConfig(
        name="escape",
        reporter="flutter-machine",
        command="true",
        cwd=str(outside),
    )
    cfg = _cfg_with_targets([target])
    results, _ = run_configured_targets(cfg, repo)
    assert len(results) == 1
    assert results[0].returncode == -1
    assert "outside the repo root" in results[0].error


# ---------------------------------------------------------------------------
# (d) scan_tests=False gate
# ---------------------------------------------------------------------------


def test_target_results_not_ingested_when_scan_tests_false(tmp_path: Path):
    """When scan_tests=False, target result ingestion must be suppressed.

    Verifies: REQ-d00254-C
    """
    from elspais.graph.factory import build_graph as _factory_build_graph

    # Write a minimal flutter-machine result file that would normally produce a RESULT node
    results_file = tmp_path / "results.jsonl"
    results_file.write_text(
        '{"type":"suite","suite":{"id":0,"platform":"vm","path":"test/foo_test.dart"}}\n'
        '{"type":"testStart","test":{"id":1,"name":"passes","suiteID":0,'
        '"line":1,"column":1,"metadata":{}}}\n'
        '{"type":"testDone","testID":1,"result":"success","hidden":false,"time":5}\n',
        encoding="utf-8",
    )
    target = TestTargetConfig(
        name="flutter",
        reporter="flutter-machine",
        results="results.jsonl",
        match="precise",
    )
    cfg = _cfg_with_targets([target])
    graph = _factory_build_graph(
        config=cfg.model_dump(by_alias=True),
        repo_root=tmp_path,
        scan_tests=False,
    )
    result_nodes = list(graph.iter_by_kind(NodeKind.RESULT))
    assert result_nodes == [], (
        "build_graph(scan_tests=False) must not ingest target results, "
        f"but got {len(result_nodes)} RESULT node(s)"
    )
