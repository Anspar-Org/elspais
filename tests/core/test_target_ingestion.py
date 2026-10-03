# Verifies: REQ-d00254-F
"""RESULT nodes carry real source_file + match from their target.

Tests for target-driven result ingestion via the reporter registry.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from elspais.config.schema import (
    ElspaisConfig,
    ScanningConfig,
    TestScanningConfig,
    TestTargetConfig,
)
from elspais.graph.GraphNode import NodeKind
from tests.core.graph_test_helpers import build_graph, grammar_for, make_test_result

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
        match="source",
    )
    g = build_graph(r)
    node = next(iter(g.iter_by_kind(NodeKind.RESULT)))
    assert node.get_field("source_file") == "provenance/test/foo_test.dart"
    assert node.get_field("match") == "source"


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

    builder = GraphBuilder(repo_root=tmp_path, namespace="REQ", resolver=grammar_for("REQ"))
    target = TestTargetConfig(name="flutter", reporter="flutter-machine", match="source")
    count = _ingest_target_results(
        builder, target, _FLUTTER_MACHINE_SAMPLE, tmp_path, namespace="REQ"
    )
    assert count == 1

    graph = builder.build()
    results = list(graph.iter_by_kind(NodeKind.RESULT))
    assert len(results) == 1
    node = results[0]
    assert node.get_field("status") == "passed"
    assert node.get_field("match") == "source"
    # source_file is set (to the suite path from the flutter event)
    assert node.get_field("source_file") == "test/widget_test.dart"


def test_ingest_target_results_returns_zero_for_coverage_reporter(tmp_path: Path):
    """Coverage reporters (kind='coverage') are skipped; returns 0."""
    from elspais.graph.builder import GraphBuilder
    from elspais.graph.factory import _ingest_target_results

    builder = GraphBuilder(repo_root=tmp_path, namespace="REQ", resolver=grammar_for("REQ"))
    target = TestTargetConfig(name="cov", reporter="lcov", match="aggregate")
    count = _ingest_target_results(
        builder, target, "SF:src/foo.dart\nend_of_record\n", tmp_path, namespace="REQ"
    )
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
    builder = GraphBuilder(repo_root=tmp_path, namespace="REQ", resolver=grammar_for("REQ"))
    target = TestTargetConfig(name="flutter", reporter="flutter-machine", match="source")
    _ingest_target_results(builder, target, sample, tmp_path, namespace="REQ")
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
    results_file = tmp_path / ".results" / "flutter" / "results.jsonl"
    results_file.parent.mkdir(parents=True)
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
        match="source",
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


# ---------------------------------------------------------------------------
# (e) Per-file source_path for file-channel reporters (FIX 2+4)
# ---------------------------------------------------------------------------


def test_ingest_two_junit_files_distinct_source_paths(tmp_path: Path):
    """A junit target whose results glob matches TWO xml files produces RESULT nodes
    with non-empty, DISTINCT source_path per file (no id collision).

    Verifies: REQ-d00254-F
    """
    from elspais.graph.factory import build_graph as _factory_build_graph

    # Write two minimal JUnit XML files
    folder = tmp_path / ".results" / "junit"
    folder.mkdir(parents=True)
    xml1 = folder / "results1.xml"
    xml1.write_text(
        '<?xml version="1.0"?>'
        '<testsuite name="suite1" tests="1">'
        '<testcase name="test_a" classname="tests.a" time="0.1"/>'
        "</testsuite>\n",
        encoding="utf-8",
    )
    xml2 = folder / "results2.xml"
    xml2.write_text(
        '<?xml version="1.0"?>'
        '<testsuite name="suite2" tests="1">'
        '<testcase name="test_b" classname="tests.b" time="0.2"/>'
        "</testsuite>\n",
        encoding="utf-8",
    )

    target = TestTargetConfig(
        name="junit",
        reporter="junit",
        results="results*.xml",
        match="aggregate",
    )
    # enabled=True is required so the build_graph target ingestion loop runs
    cfg = ElspaisConfig(
        scanning=ScanningConfig(test=TestScanningConfig(targets=[target], enabled=True))
    )
    graph = _factory_build_graph(
        config=cfg.model_dump(by_alias=True),
        repo_root=tmp_path,
    )

    result_nodes = list(graph.iter_by_kind(NodeKind.RESULT))
    assert len(result_nodes) == 2, f"Expected 2 RESULT nodes, got {len(result_nodes)}"

    source_paths = {n.get_field("source_path") for n in result_nodes}
    # Each result must have a non-empty source_path
    assert "" not in source_paths, "source_path must be non-empty for file-channel results"
    assert None not in source_paths, "source_path must not be None for file-channel results"
    # The two results must have distinct source_paths (no collision)
    assert len(source_paths) == 2, f"source_paths must be distinct per file, got: {source_paths}"


# ---------------------------------------------------------------------------
# (f) One scenario declared in a shared file, executed through runner files
# ---------------------------------------------------------------------------

_SHARED_CONFIG = """\
version = 5

[project]
name = "shared"
namespace = "REQ"

[levels.dev]
rank = 1
letter = "d"
implements = ["dev"]

[id-patterns]
canonical = "{namespace}-{level.letter}{component}"

[id-patterns.component]
style = "numeric"
digits = 5
leading_zeros = true

[scanning.spec]
directories = ["spec"]

[scanning.test]
enabled = true
directories = ["test"]
file_patterns = ["*.dart"]

[[scanning.test.targets]]
name = "flutter"
reporter = "flutter-machine"
results = "machine.jsonl"
match = "source"

[rules.format]
require_hash = false
require_assertions = false
require_status = false
"""

_SHARED_SPEC = """\
# Requirements

---

### REQ-d00001: Boot

**Level**: dev | **Status**: Active

## Assertions

A. The system SHALL give two stores one identity.

*End* *Boot*
---
"""

# The scenario is declared on line 3 and cites from inside its body.
_SHARED_FILE = "test/support/boot_conformance.dart"
_SHARED_DART = """\
void bootConformance() {
  group('boot', () {
    test('two stores share one identity', () {
      // Verifies: REQ-d00001-A
      expect(1, 1);
    });
  });
}
"""
_SHARED_LINE = 3

_RUNNER_A = "test/a/a_test.dart"
_RUNNER_A_DART = """\
import '../support/boot_conformance.dart';

void main() {
  bootConformance();
}
"""

# A decoy test is declared on the same line number as the scenario.
_RUNNER_B = "test/b/b_test.dart"
_RUNNER_B_DART = """\
import '../support/boot_conformance.dart';
void main() {
  test('decoy', () {
    // Verifies: REQ-d00001-A
    expect(2, 2);
  });
  bootConformance();
}
"""


def _machine_run(root: Path, runner: str, declared: str, outcome: str, suite_id: int) -> str:
    """The machine events of one runner file executing the shared scenario."""
    import json

    test_id = suite_id + 1
    return "\n".join(
        [
            json.dumps(
                {
                    "suite": {"id": suite_id, "platform": "vm", "path": str(root / runner)},
                    "type": "suite",
                }
            ),
            json.dumps(
                {
                    "test": {
                        "id": test_id,
                        "name": "boot two stores share one identity",
                        "suiteID": suite_id,
                        "groupIDs": [],
                        "line": _SHARED_LINE,
                        "column": 5,
                        "url": f"file://{root / declared}",
                        "root_line": 4,
                        "root_column": 3,
                        "root_url": f"file://{root / runner}",
                    },
                    "type": "testStart",
                }
            ),
            json.dumps(
                {
                    "testID": test_id,
                    "result": outcome,
                    "skipped": False,
                    "hidden": False,
                    "type": "testDone",
                }
            ),
        ]
    )


def _shared_scenario_project(root: Path, outcome_b: str):
    """Build a project whose scenario two runner files executed.

    Runner A's run passed; runner B's run had ``outcome_b``.
    Returns the federated graph and the repository's configuration.
    """
    from elspais.graph.factory import build_graph as _factory_build_graph

    files = {
        ".elspais.toml": _SHARED_CONFIG,
        "spec/requirements.md": _SHARED_SPEC,
        _SHARED_FILE: _SHARED_DART,
        _RUNNER_A: _RUNNER_A_DART,
        _RUNNER_B: _RUNNER_B_DART,
    }
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    out = root / ".results" / "flutter"
    out.mkdir(parents=True)
    (out / "machine.jsonl").write_text(
        _machine_run(root, _RUNNER_A, _SHARED_FILE, "success", 1)
        + "\n"
        + _machine_run(root, _RUNNER_B, _SHARED_FILE, outcome_b, 10)
        + "\n",
        encoding="utf-8",
    )
    graph = _factory_build_graph(repo_root=root)
    (entry,) = list(graph.iter_repos())
    return graph, entry.config


def _test_at(graph, rel: str):
    (node,) = [
        t
        for t in graph.iter_by_kind(NodeKind.TEST)
        if t.file_node() is not None and t.file_node().get_field("relative_path") == rel
    ]
    return node


def _results_of(test_node) -> set[str]:
    return {c.id for c in test_node.iter_children() if c.kind == NodeKind.RESULT}


def _result_run_by(graph, runner: str):
    (node,) = [
        r for r in graph.iter_by_kind(NodeKind.RESULT) if r.get_field("runner_file") == runner
    ]
    return node


@pytest.fixture(scope="module", params=["success", "failure"], ids=["b-passed", "b-failed"])
def shared_scenario(request, tmp_path_factory):
    root = tmp_path_factory.mktemp("shared") / "proj"
    graph, config = _shared_scenario_project(root, request.param)
    return request.param, graph, config


# Verifies: REQ-d00254-G, REQ-d00254-Z
def test_each_run_binds_to_the_scenario_where_it_is_declared(shared_scenario):
    from elspais.graph.relations import EdgeKind

    _outcome, graph, _config = shared_scenario
    scenario = _test_at(graph, _SHARED_FILE)
    a = _result_run_by(graph, _RUNNER_A)
    b = _result_run_by(graph, _RUNNER_B)

    assert scenario.get_field("parse_line") == _SHARED_LINE
    yielded = {e.target.id for e in scenario.iter_outgoing_edges() if e.kind == EdgeKind.YIELDS}
    assert yielded == {a.id, b.id}
    for result in (a, b):
        assert result.get_field("match_scope") == "test"
        assert result.get_field("source_file") == _SHARED_FILE
        assert result.get_field("line") == _SHARED_LINE
        # A record naming its declaration never falls back to the runner file.
        assert result.get_field("root_file") is None
        assert result.get_field("root_line") is None


# Verifies: REQ-d00254-Z
def test_no_run_binds_to_a_runner_test_on_the_same_line(shared_scenario):
    _outcome, graph, _config = shared_scenario
    decoy = _test_at(graph, _RUNNER_B)

    assert decoy.get_field("parse_line") == _SHARED_LINE
    assert _results_of(decoy) == set()


# Verifies: REQ-d00294-G
def test_each_result_records_the_runner_file_that_executed_it(shared_scenario):
    _outcome, graph, _config = shared_scenario
    results = list(graph.iter_by_kind(NodeKind.RESULT))

    assert sorted(r.get_field("runner_file") for r in results) == [_RUNNER_A, _RUNNER_B]
    assert {r.get_field("source_file") for r in results} == {_SHARED_FILE}


# Verifies: REQ-d00294-E
def test_the_scenario_is_passing_only_when_every_run_passed(shared_scenario):
    from elspais.graph.metrics import tested_and_passing

    outcome, graph, _config = shared_scenario
    rollup = graph.find_by_id("REQ-d00001").get_metric("rollup_metrics")
    passing = tested_and_passing(rollup)

    assert rollup.tested.covered == 1.0
    if outcome == "success":
        assert passing.covered == 1.0
        assert passing.has_failures is False
    else:
        assert passing.covered == 0
        assert passing.has_failures is True


# Verifies: REQ-d00294-G
def test_a_failed_run_is_reported_with_the_runner_that_executed_it(shared_scenario):
    from elspais.commands.health import check_test_results

    outcome, graph, config = shared_scenario
    check = check_test_results(graph, config)
    messages = [f.message for f in check.findings]

    if outcome == "success":
        assert check.passed is True
        assert not any("(run by" in m for m in messages)
    else:
        assert check.passed is False
        (message,) = messages
        assert f"(run by {_RUNNER_B})" in message
        assert _RUNNER_A not in message


# Verifies: REQ-d00294-G
def test_a_failed_test_its_own_suite_ran_names_no_runner(tmp_path: Path):
    """Where the declaring file is the file that ran, the report names it once."""
    from elspais.commands.health import check_test_results
    from elspais.graph.factory import build_graph as _factory_build_graph

    root = tmp_path / "proj"
    _graph, config = _shared_scenario_project(root, "success")
    out = root / ".results" / "flutter" / "machine.jsonl"
    # Runner B's own decoy, declared and run in b_test.dart, fails.
    out.write_text(_machine_run(root, _RUNNER_B, _RUNNER_B, "failure", 1) + "\n", encoding="utf-8")

    graph = _factory_build_graph(repo_root=root)
    result = next(iter(graph.iter_by_kind(NodeKind.RESULT)))
    assert result.get_field("source_file") == _RUNNER_B
    assert result.get_field("runner_file") == _RUNNER_B

    (finding,) = check_test_results(graph, config).findings

    assert "(run by" not in finding.message


# ---------------------------------------------------------------------------
# Results keep matching when the tree moves
# ---------------------------------------------------------------------------


def _recorded_run(root: Path, *, outcome: str = "success") -> None:
    """Write the shared-scenario project at *root* and record one run of its target.

    The run is started and finished as the runner does, so its Result
    Fingerprint records the root it executed in. The reporter writes absolute
    paths under that root.
    """
    from elspais.config import load_config
    from elspais.utilities.fingerprint import finish_run, start_run

    files = {
        ".elspais.toml": _SHARED_CONFIG,
        "spec/requirements.md": _SHARED_SPEC,
        _SHARED_FILE: _SHARED_DART,
        _RUNNER_A: _RUNNER_A_DART,
        _RUNNER_B: _RUNNER_B_DART,
    }
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    config = load_config(root / ".elspais.toml")
    folder = start_run(root, config, "flutter")
    (folder / "machine.jsonl").write_text(
        _machine_run(root, _RUNNER_A, _SHARED_FILE, outcome, 1) + "\n", encoding="utf-8"
    )
    finish_run(root, config, "flutter")


def _relocate(source: Path, destination: Path, how: str) -> None:
    import shutil

    destination.parent.mkdir(parents=True, exist_ok=True)
    if how == "copy":
        shutil.copytree(source, destination, symlinks=True)
    else:
        source.rename(destination)


def _rewrite_fingerprint(folder: Path, change) -> None:
    import json

    from elspais.utilities.fingerprint import FINGERPRINT_NAME

    path = folder / FINGERPRINT_NAME
    data = json.loads(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def _build_at(root: Path):
    from elspais.config import load_config
    from elspais.graph.factory import build_graph as _factory_build_graph

    return _factory_build_graph(repo_root=root), load_config(root / ".elspais.toml")


# Verifies: REQ-d00311-P
def test_the_result_fingerprint_records_the_root_its_run_executed_in(tmp_path: Path):
    from elspais.utilities.fingerprint import read_fingerprint

    root = tmp_path / "proj"
    _recorded_run(root)

    fingerprint = read_fingerprint(root / ".results" / "flutter")

    assert fingerprint["root"] == str(root.resolve())


# Verifies: REQ-d00311-Q
@pytest.mark.parametrize("how", ["copy", "move"])
def test_results_of_a_moved_tree_bind_to_their_tests(tmp_path: Path, how: str):
    from elspais.commands.health import check_unmatched_results
    from elspais.graph.metrics import tested_and_passing

    original = tmp_path / "first" / "proj"
    _recorded_run(original)
    before, _ = _build_at(original)
    passing_before = tested_and_passing(
        before.find_by_id("REQ-d00001").get_metric("rollup_metrics")
    ).covered

    moved = tmp_path / "second" / "elsewhere"
    _relocate(original, moved, how)
    graph, config = _build_at(moved)

    (result,) = list(graph.iter_by_kind(NodeKind.RESULT))
    assert result.get_field("match_scope") == "test"
    assert result.get_field("source_file") == _SHARED_FILE
    assert result.get_field("runner_file") == _RUNNER_A
    assert check_unmatched_results(graph, config).passed is True
    rollup = graph.find_by_id("REQ-d00001").get_metric("rollup_metrics")
    assert passing_before == 1.0
    assert tested_and_passing(rollup).covered == passing_before


# Verifies: REQ-d00311-Q
def test_a_fingerprint_recording_no_root_reads_paths_against_the_current_root(tmp_path: Path):
    """Without a recorded root, a path from the old tree is outside the repository."""
    from elspais.commands.health import check_unmatched_results

    original = tmp_path / "first" / "proj"
    _recorded_run(original)
    moved = tmp_path / "second" / "proj"
    _relocate(original, moved, "copy")
    _rewrite_fingerprint(moved / ".results" / "flutter", lambda data: data.pop("root", None))

    graph, config = _build_at(moved)

    (result,) = list(graph.iter_by_kind(NodeKind.RESULT))
    assert result.get_field("source_file") == str(original / _SHARED_FILE)
    assert result.get_field("match_scope") != "test"
    assert check_unmatched_results(graph, config).passed is False


# Verifies: REQ-d00311-Q
def test_a_path_under_neither_root_stays_absolute_and_unmatched(tmp_path: Path):
    from elspais.commands.health import check_unmatched_results

    original = tmp_path / "first" / "proj"
    _recorded_run(original)
    moved = tmp_path / "second" / "proj"
    _relocate(original, moved, "copy")
    elsewhere = tmp_path / "third"
    _rewrite_fingerprint(
        moved / ".results" / "flutter", lambda data: data.update(root=str(elsewhere))
    )

    graph, config = _build_at(moved)

    (result,) = list(graph.iter_by_kind(NodeKind.RESULT))
    assert result.get_field("source_file") == str(original / _SHARED_FILE)
    assert result.get_field("match_scope") != "test"
    assert check_unmatched_results(graph, config).passed is False
