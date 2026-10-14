"""Tests for runs of a test target declaring units: what a run executes, retains and records.

Each test creates a small project on disk whose target runs a stand-in test
runner. The runner reads the test files it is handed, finds each test, and
writes one result line per test in the *Evidence Snapshot* line form. A test
whose body holds ``FAIL`` fails, and one whose body holds ``SILENT`` writes
no result at all.

The environment steers it further: ``RUNNER_ALSO`` names a test file it
executes beside the ones it is handed, writing a result for that file's first
test alone; ``RUNNER_EXTRA_FAIL`` adds a failed result that names a file and
no line; ``RUNNER_EXIT`` makes it exit non-zero whatever its results;
``RUNNER_NO_RESULTS`` writes no results file; ``RUNNER_COVERAGE`` writes line
coverage of ``src/lib.py``, the lines ``RUNNER_COVERAGE_LINES``
names, executed by the contexts ``RUNNER_CONTEXT`` names.
"""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import pytest

from elspais.commands.test_runner import run_configured_targets, settle_units
from elspais.config import validate_config
from elspais.graph.factory import build_graph
from elspais.graph.GraphNode import NodeKind
from elspais.utilities.evidence import SnapshotRefused, derive_snapshot
from elspais.utilities.fingerprint import (
    RETAINED_RESULTS_NAME,
    SELECTION_NAME,
    forget_probes,
    target_folder,
)
from elspais.utilities.retention import read_ledger

_SPEC = """# REQ-d00001: Module

**Level**: DEV | **Status**: Active | **Implements**: -

## Assertions

A. The module SHALL work.

*End* *Module* | **Hash**: 00000000
"""

_RUNNER = """
import json, os, pathlib, re, sys
out = pathlib.Path(os.environ["ELSPAIS_TARGET_OUTPUT"])
paths = []
for arg in sys.argv[1:]:
    p = pathlib.Path(arg)
    paths += sorted(p.rglob("test_*.py")) if p.is_dir() else [p]
also = os.environ.get("RUNNER_ALSO")
if also:
    paths.append(pathlib.Path(also))
log = pathlib.Path(os.environ["RUNNER_LOG"])
log.write_text(log.read_text() + " ".join(str(p) for p in paths) + "\\n" if log.exists() else
               " ".join(str(p) for p in paths) + "\\n")
lines = []
for p in paths:
    text = p.read_text().splitlines()
    for n, line in enumerate(text, 1):
        m = re.match(r"def (test_\\w+)", line)
        if not m:
            continue
        body = text[n] if n < len(text) else ""
        if "SILENT" in body:
            continue
        if also and p.as_posix() == also and any(also in l for l in lines):
            continue
        lines.append(json.dumps({"target": "unit", "file": p.as_posix(), "line": n,
                                 "name": m.group(1),
                                 "outcome": "failed" if "FAIL" in body else "passed"}))
if os.environ.get("RUNNER_EXTRA_FAIL"):
    lines.append(json.dumps({"target": "unit", "file": "tests/test_b.py",
                             "name": "tearDownAll", "outcome": "failed"}))
if not os.environ.get("RUNNER_NO_RESULTS"):
    (out / "results.jsonl").write_text("".join(l + "\\n" for l in lines))
if os.environ.get("RUNNER_COVERAGE"):
    executed = [int(n) for n in os.environ.get("RUNNER_COVERAGE_LINES", "1").split(",")]
    entry = {"executed_lines": executed, "missing_lines": []}
    if os.environ.get("RUNNER_CONTEXT"):
        entry["contexts"] = {str(n): [os.environ["RUNNER_CONTEXT"]] for n in executed}
    (out / "coverage.json").write_text(json.dumps({"files": {"src/lib.py": entry}}))
sys.exit(1 if any('"failed"' in l for l in lines) or os.environ.get("RUNNER_EXIT") else 0)
"""


def _test_file(name: str, body: str = "assert True") -> str:
    return f"# Verifies: REQ-d00001-A\ndef test_{name}():\n    {body}\n"


def _project(tmp_path: Path, **units) -> tuple[Path, dict]:
    root = tmp_path / "repo"
    (root / "spec").mkdir(parents=True)
    (root / "spec" / "dev.md").write_text(_SPEC, encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "test_a.py").write_text(_test_file("a"), encoding="utf-8")
    (root / "tests" / "test_b.py").write_text(_test_file("b"), encoding="utf-8")
    (root / "src").mkdir()
    (root / "src" / "lib.py").write_text("x = 1\n", encoding="utf-8")
    runner = tmp_path / "runner.py"
    runner.write_text(textwrap.dedent(_RUNNER), encoding="utf-8")
    target = {
        "name": "unit",
        "reporter": "evidence-snapshot",
        "results": "results.jsonl",
        "command": f"{sys.executable} {runner} {{selection}}",
        "units": {"dependencies": {"source": "declared"}, "full_selection": "tests", **units},
        "environment_probes": [
            {"name": "tool", "command": "printenv TOOL_VERSION", "affects_retention": False}
        ],
    }
    config = {
        "version": 5,
        "project": {"name": "units", "namespace": "REQ"},
        "scanning": {
            "skip": ["__pycache__"],
            "spec": {"directories": ["spec"]},
            "code": {"directories": ["src"]},
            "test": {
                "enabled": True,
                "directories": ["tests"],
                "file_patterns": ["test_*.py"],
                "targets": [target],
            },
        },
    }
    _write_config(root, config)
    return root, config


def _write_config(root: Path, config: dict) -> None:
    import tomlkit

    (root / ".elspais.toml").write_text(tomlkit.dumps(config), encoding="utf-8")


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNNER_LOG", str(tmp_path / "runner.log"))
    monkeypatch.setenv("TOOL_VERSION", "1")
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    forget_probes()
    yield
    forget_probes()


def _run(root: Path, config: dict, *, stale_only: bool = True, full: bool = False):
    forget_probes()
    _write_config(root, config)
    typed = validate_config(config)
    results = run_configured_targets(typed, root, stale_only=stale_only, full=full)
    failures = settle_units(typed, root, config, results)
    return results[0], failures


def _executed(tmp_path: Path) -> list[str]:
    log = tmp_path / "runner.log"
    return log.read_text().splitlines() if log.exists() else []


def _area(root: Path, config: dict) -> Path:
    return target_folder(root, validate_config(config), "unit")


# Verifies: REQ-d00333-B, REQ-d00249-O, REQ-d00315-B
def test_a_stale_only_run_executes_only_the_test_files_whose_evidence_changed(tmp_path):
    root, config = _project(tmp_path)
    first, _ = _run(root, config)
    assert first.plan.whole
    (root / "tests" / "test_a.py").write_text(_test_file("a", "assert 1"), encoding="utf-8")

    second, failures = _run(root, config)

    assert failures == []
    assert second.succeeded
    assert sorted(second.plan.selected) == ["tests/test_a.py"]
    assert sorted(second.plan.retained) == ["tests/test_b.py"]
    assert _executed(tmp_path)[-1] == "tests/test_a.py"
    area = _area(root, config)
    assert (area / SELECTION_NAME).read_text() == "tests/test_a.py\n"
    retained = [
        json.loads(line) for line in (area / RETAINED_RESULTS_NAME).read_text().splitlines()
    ]
    assert [r["file"] for r in retained] == ["tests/test_b.py"]
    assert retained[0]["executed_in"]["started_at"]


# Verifies: REQ-d00333-A, REQ-d00323-L+M+O
def test_retained_results_are_read_as_carried_results_naming_the_run_that_executed_them(
    tmp_path,
):
    root, config = _project(tmp_path)
    _run(root, config)
    (root / "tests" / "test_a.py").write_text(_test_file("a", "assert 1"), encoding="utf-8")
    _run(root, config)

    graph = build_graph(config=config, repo_root=root, scan_code=False)
    results = {
        n.get_field("source_file"): n for n in graph.nodes_by_kind(NodeKind.RESULT, namespace="REQ")
    }
    assert results["tests/test_a.py"].get_field("retained_from") is None
    retained = results["tests/test_b.py"]
    assert retained.get_field("carried") is True
    assert retained.get_field("retained_from").startswith("the run of ")
    from elspais.graph.aggregation import retained_result_tally

    assert retained_result_tally(graph) == [
        {"namespace": "REQ", "target": "unit", "executed": 1, "retained": 1}
    ]


# Verifies: REQ-d00315-G, REQ-d00333-K
def test_a_stale_target_whose_tests_are_all_retained_runs_no_command(tmp_path, monkeypatch):
    root, config = _project(tmp_path)
    _run(root, config)
    monkeypatch.setenv("TOOL_VERSION", "2")
    before = len(_executed(tmp_path))

    result, _ = _run(root, config)

    assert result.succeeded
    assert result.plan.selected == {}
    assert len(_executed(tmp_path)) == before
    assert read_ledger(_area(root, config)) is not None


# Verifies: REQ-d00333-I
def test_a_run_asking_for_every_test_retains_none(tmp_path):
    root, config = _project(tmp_path)
    _run(root, config)
    (root / "tests" / "test_a.py").write_text(_test_file("a", "assert 1"), encoding="utf-8")

    result, _ = _run(root, config, full=True)

    assert result.plan.whole
    assert "--full" in result.plan.whole_reason
    assert _executed(tmp_path)[-1] == "tests/test_a.py tests/test_b.py"
    assert not (_area(root, config) / RETAINED_RESULTS_NAME).exists()


# Verifies: REQ-d00333-I
def test_a_run_that_is_not_stale_only_executes_every_test(tmp_path):
    root, config = _project(tmp_path)
    _run(root, config)
    (root / "tests" / "test_a.py").write_text(_test_file("a", "assert 1"), encoding="utf-8")

    result, _ = _run(root, config, stale_only=False)

    assert result.plan.whole


# Verifies: REQ-d00333-G
def test_a_failed_test_file_executes_again_on_the_next_run(tmp_path):
    root, config = _project(tmp_path)
    (root / "tests" / "test_b.py").write_text(_test_file("b", "FAIL = 1"), encoding="utf-8")
    first, _ = _run(root, config)
    assert not first.succeeded
    (root / "tests" / "test_a.py").write_text(_test_file("a", "assert 1"), encoding="utf-8")

    second, _ = _run(root, config)

    assert sorted(second.plan.selected) == ["tests/test_a.py", "tests/test_b.py"] or (
        second.plan.whole
    )
    assert "tests/test_b.py" not in second.plan.retained


# Verifies: REQ-d00333-H
def test_a_test_of_a_selected_file_with_no_result_fails_the_run(tmp_path):
    root, config = _project(tmp_path)
    _run(root, config)
    (root / "tests" / "test_a.py").write_text(_test_file("a", "SILENT = 1"), encoding="utf-8")

    result, failures = _run(root, config)

    assert failures == ["unit"]
    assert not result.succeeded
    ledger = read_ledger(_area(root, config))
    assert ledger.units["tests/test_a.py"].outcome == "no-result"


# Verifies: REQ-d00333-E
def test_a_run_after_an_unfinished_run_executes_every_test(tmp_path):
    root, config = _project(tmp_path)
    _run(root, config)
    from elspais.utilities.fingerprint import start_run

    start_run(root, config, "unit")

    result, _ = _run(root, config)

    assert result.plan.whole
    assert "in progress" in result.plan.whole_reason


# Verifies: REQ-d00333-C
def test_a_dependency_source_that_fails_executes_every_test_and_says_why(tmp_path):
    root, config = _project(tmp_path)
    target = config["scanning"]["test"]["targets"][0]
    target["units"] = {
        "dependencies": {"source": "command", "command": "exit 4"},
        "observes": {"directories": ["tests"]},
        "full_selection": "tests",
    }
    _run(root, config)

    result, _ = _run(root, config)

    assert result.plan.whole
    assert "exited 4" in result.plan.whole_reason
    assert read_ledger(_area(root, config)).source_failed


# Verifies: REQ-d00333-D
def test_a_dependency_outside_the_inputs_is_recorded_and_reported(tmp_path):
    root, config = _project(tmp_path)
    deps = tmp_path / "deps.py"
    deps.write_text(
        "import json,sys\n"
        "print(json.dumps([{'unit': u, 'files': [u, 'docs/notes.md']}"
        " for u in sys.stdin.read().split()]))\n",
        encoding="utf-8",
    )
    target = config["scanning"]["test"]["targets"][0]
    target["inputs"] = {"skip_dirs": ["docs"]}
    target["units"] = {
        "dependencies": {"source": "command", "command": f"{sys.executable} {deps}"},
        "observes": {"directories": ["tests"]},
        "full_selection": "tests",
    }
    (root / "docs").mkdir()
    (root / "docs" / "notes.md").write_text("notes\n", encoding="utf-8")
    _run(root, config)

    from elspais.commands.health import check_dependency_outside_inputs

    graph = build_graph(config=config, repo_root=root, scan_code=False)
    check = check_dependency_outside_inputs(graph, config)
    assert not check.passed
    assert [f.file_path for f in check.findings] == ["docs/notes.md"]


# Verifies: REQ-d00323-P
def test_a_target_holding_retained_results_is_reported_with_each_one(tmp_path):
    root, config = _project(tmp_path)
    _run(root, config)
    (root / "tests" / "test_a.py").write_text(_test_file("a", "assert 1"), encoding="utf-8")
    _run(root, config)

    from elspais.commands.health import check_retained_results

    graph = build_graph(config=config, repo_root=root, scan_code=False)
    check = check_retained_results(graph, config)
    assert not check.passed
    assert check.severity == "info"
    (finding,) = check.findings
    assert "target unit: 1 result(s)" in finding.message
    assert finding.related[0].startswith("tests/test_b.py:2 test_b (passed): retained from ")


# Verifies: REQ-d00322-B
def test_an_evidence_snapshot_refuses_retained_results(tmp_path):
    root, config = _project(tmp_path)
    _run(root, config)
    (root / "tests" / "test_a.py").write_text(_test_file("a", "assert 1"), encoding="utf-8")
    _run(root, config)
    graph = build_graph(config=config, repo_root=root, scan_code=False)

    with pytest.raises(SnapshotRefused) as caught:
        derive_snapshot(graph, root, validate_config(config), ["unit"], (), "")
    assert "1 Retained Result(s)" in str(caught.value)


def _coverage_project(tmp_path: Path, monkeypatch) -> tuple[Path, dict]:
    monkeypatch.setenv("RUNNER_COVERAGE", "1")
    root, config = _project(tmp_path)
    config["scanning"]["test"]["targets"][0]["coverage"] = "coverage.json"
    return root, config


def _lib(root: Path, config: dict):
    graph = build_graph(config=config, repo_root=root)
    return graph.find_by_id("file:REQ:src/lib.py")


# Verifies: REQ-d00333-J+L, REQ-d00323-N
def test_line_coverage_of_an_unchanged_file_is_retained_naming_the_run_that_measured_it(
    tmp_path, monkeypatch
):
    root, config = _coverage_project(tmp_path, monkeypatch)
    _run(root, config)
    assert _lib(root, config).get_field("line_coverage_stale_reason") == ""
    monkeypatch.setenv("TOOL_VERSION", "2")

    result, _ = _run(root, config)

    assert result.plan.selected == {}
    lib = _lib(root, config)
    assert lib.get_field("line_coverage") == {1: 1}
    assert lib.get_field("line_coverage_stale_reason").startswith(
        "line coverage retained from the run of "
    )


# Verifies: REQ-d00333-J
def test_line_coverage_of_a_changed_file_is_not_retained(tmp_path, monkeypatch):
    root, config = _coverage_project(tmp_path, monkeypatch)
    _run(root, config)
    from elspais.utilities.fingerprint import compute_manifest, read_fingerprint
    from elspais.utilities.retention import retained_coverage

    typed = validate_config(config)
    target = typed.scanning.test.targets[0]
    last = read_fingerprint(_area(root, config))
    current = compute_manifest(root, typed, target)
    kept = retained_coverage(root, typed, target, last, current)
    assert set(kept) == {"src/lib.py"}
    assert kept["src/lib.py"]["provenance"]["measured_in"][0]["started_at"] == last["started_at"]

    (root / "src" / "lib.py").write_text("x = 2\n", encoding="utf-8")
    current = compute_manifest(root, typed, target)
    assert retained_coverage(root, typed, target, last, current) is None


# Verifies: REQ-d00333-J
def test_retained_coverage_reads_back_through_the_coverage_reader():
    from elspais.graph.parsers.results.coverage_json import (
        CoverageJsonParser,
        render_coverage_json,
    )

    readings = {
        "src/lib.py": {
            "line_coverage": {1: 1, 2: 0},
            "executable_lines": 2,
            "covered_lines": 1,
            "contexts": {1: ["tests/test_a.py::test_a|run"]},
            "provenance": {"digest": "d", "measured_in": [{"commit": "c"}]},
        }
    }
    assert CoverageJsonParser().parse(render_coverage_json(readings), "x") == readings


# Verifies: REQ-d00323-O
@pytest.mark.parametrize("fmt", ["text", "markdown", "csv"])
def test_the_summary_states_what_each_target_executed_and_retained(tmp_path, fmt):
    from elspais.commands.summary import render_summary

    data = {
        "levels": [],
        "carried_result_targets": 1,
        "total_result_targets": 1,
        "retained_results": {
            "count": 3,
            "targets": [{"namespace": "REQ", "target": "unit", "executed": 2, "retained": 3}],
        },
    }
    rendered = render_summary(data, fmt)
    if fmt == "csv":
        assert "REQ,unit,2,3" in rendered
    else:
        assert "unit (REQ): 2 result(s) executed, 3 retained from earlier runs" in rendered


# Verifies: REQ-d00323-M
def test_the_mcp_result_entry_names_the_run_that_executed_a_retained_result(tmp_path):
    from elspais.mcp.server import _serialize_result_entry

    root, config = _project(tmp_path)
    _run(root, config)
    (root / "tests" / "test_a.py").write_text(_test_file("a", "assert 1"), encoding="utf-8")
    _run(root, config)
    graph = build_graph(config=config, repo_root=root, scan_code=False)
    retained = next(
        n
        for n in graph.nodes_by_kind(NodeKind.RESULT, namespace="REQ")
        if n.get_field("retained_from")
    )

    entry = _serialize_result_entry(retained, graph)

    assert entry["retained_from"].startswith("the run of ")
    assert entry["retained_reason"] == "no input of its evidence changed since it executed"


def _verdict(root: Path, config: dict):
    from elspais.utilities.fingerprint import judge

    forget_probes()
    return judge(root, validate_config(config), "unit")


# Verifies: REQ-d00333-H
def test_a_run_that_left_a_test_without_a_result_stays_failed_for_every_later_reader(tmp_path):
    root, config = _project(tmp_path)
    _run(root, config)
    (root / "tests" / "test_a.py").write_text(_test_file("a", "SILENT = 1"), encoding="utf-8")
    _, failures = _run(root, config)
    assert failures == ["unit"]

    verdict = _verdict(root, config)
    assert verdict.state == "stale"
    assert verdict.reason == "run-faults"
    assert any("tests/test_a.py:2 " in fault for fault in verdict.changed)

    again, failures = _run(root, config)
    assert failures == ["unit"]
    assert "tests/test_a.py" in again.plan.selected

    (root / "tests" / "test_a.py").write_text(_test_file("a", "assert 2"), encoding="utf-8")
    recovered, failures = _run(root, config)
    assert failures == []
    assert recovered.succeeded
    assert _verdict(root, config).state == "fresh"


# Verifies: REQ-d00333-H
def test_a_run_that_cannot_be_settled_fails(tmp_path, monkeypatch):
    root, config = _project(tmp_path)

    def broken(*args, **kwargs):
        raise RuntimeError("the build broke")

    monkeypatch.setattr("elspais.utilities.retention.settle", broken)
    result, failures = _run(root, config)

    assert failures == ["unit"]
    assert not result.succeeded
    verdict = _verdict(root, config)
    assert verdict.reason == "run-faults"
    assert "the build broke" in verdict.changed[0]


# Verifies: REQ-d00333-M
def test_a_units_target_whose_scan_holds_no_test_is_refused_before_its_area_is_touched(
    tmp_path,
):
    root, config = _project(tmp_path)
    config["scanning"]["test"]["targets"][0]["cwd"] = "src"
    area = _area(root, config)

    for stale_only in (False, True):
        result, failures = _run(root, config, stale_only=stale_only)
        assert not result.started
        assert not result.succeeded
        assert "selects no test file under its working directory 'src'" in result.error
        assert failures == []
        assert not area.exists()
        assert _executed(tmp_path) == []


# Verifies: REQ-d00333-G
def test_a_failure_that_binds_to_no_single_test_keeps_its_file_from_being_retained(
    tmp_path, monkeypatch
):
    root, config = _project(tmp_path)
    monkeypatch.setenv("RUNNER_EXTRA_FAIL", "1")
    _run(root, config)
    ledger = read_ledger(_area(root, config))
    assert ledger.units["tests/test_b.py"].outcome == "failed"

    monkeypatch.delenv("RUNNER_EXTRA_FAIL")
    (root / "tests" / "test_a.py").write_text(_test_file("a", "assert 1"), encoding="utf-8")
    second, _ = _run(root, config)
    assert "tests/test_b.py" not in second.plan.retained


# Verifies: REQ-d00333-H
def test_a_retained_file_the_command_executes_in_part_fails_the_run_for_its_other_tests(
    tmp_path, monkeypatch, capsys
):
    root, config = _project(tmp_path)
    two = _test_file("b") + "\n\ndef test_b2():\n    assert True\n"
    (root / "tests" / "test_b.py").write_text(two, encoding="utf-8")
    _run(root, config)
    (root / "tests" / "test_a.py").write_text(_test_file("a", "assert 1"), encoding="utf-8")
    monkeypatch.setenv("RUNNER_ALSO", "tests/test_b.py")

    result, failures = _run(root, config)

    assert "tests/test_b.py" in result.plan.retained
    assert failures == ["unit"]
    err = capsys.readouterr().err
    assert "the command also executed retained test files" in err
    assert "tests/test_b.py:6 " in err
    assert not (_area(root, config) / RETAINED_RESULTS_NAME).exists()


# Verifies: REQ-d00333-B
def test_a_unit_its_dependency_source_leaves_out_executes_on_every_run(tmp_path, monkeypatch):
    from elspais.utilities.retention import NO_EVIDENCE_REASON

    root, config = _project(tmp_path)
    deps = tmp_path / "deps.py"
    deps.write_text(
        "import json,sys\n"
        "print(json.dumps([{'unit': u, 'files': [u]} for u in sys.stdin.read().split()"
        " if u.endswith('test_a.py')]))\n",
        encoding="utf-8",
    )
    target = config["scanning"]["test"]["targets"][0]
    target["units"] = {
        "dependencies": {"source": "command", "command": f"{sys.executable} {deps}"},
        "observes": {"directories": ["tests"]},
        "full_selection": "tests",
    }
    _run(root, config)
    assert read_ledger(_area(root, config)).units["tests/test_b.py"].observed == {}
    # The target is stale through a probe that leaves retention unaffected,
    # so the evidence alone decides each unit.
    monkeypatch.setenv("TOOL_VERSION", "2")

    second, _ = _run(root, config)

    assert second.plan.selected == {"tests/test_b.py": NO_EVIDENCE_REASON}
    assert sorted(second.plan.retained) == ["tests/test_a.py"]


# Verifies: REQ-d00333-A, REQ-d00322-C
def test_retained_results_are_held_in_the_one_byte_form_of_a_result_line(tmp_path):
    from elspais.utilities.evidence import read_result_line, result_line_text

    root, config = _project(tmp_path)
    _run(root, config)
    (root / "tests" / "test_a.py").write_text(_test_file("a", "assert 1"), encoding="utf-8")
    _run(root, config)

    text = (_area(root, config) / RETAINED_RESULTS_NAME).read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    assert lines
    for raw in lines:
        line = read_result_line(json.loads(raw))
        assert line.executed_in is not None
        assert result_line_text(line) == raw


# Verifies: REQ-d00333-L, REQ-d00323-J
def test_a_file_measured_by_this_run_and_an_earlier_one_names_the_earlier_run(
    tmp_path, monkeypatch
):
    from elspais.graph.annotators import _coverage_carried

    root, config = _coverage_project(tmp_path, monkeypatch)
    monkeypatch.setenv("RUNNER_COVERAGE_LINES", "2")
    _run(root, config)
    monkeypatch.setenv("RUNNER_COVERAGE_LINES", "1")
    (root / "tests" / "test_a.py").write_text(_test_file("a", "assert 1"), encoding="utf-8")

    result, _ = _run(root, config)

    assert sorted(result.plan.selected) == ["tests/test_a.py"]
    lib = _lib(root, config)
    assert lib.get_field("line_coverage") == {1: 1, 2: 1}
    assert lib.get_field("line_coverage_stale_reason").startswith(
        "line coverage retained from the run of "
    )
    assert not _coverage_carried(lib)


# Verifies: REQ-d00283-V
def test_a_partial_run_that_left_no_coverage_records_its_coverage_absent(tmp_path, monkeypatch):
    root, config = _coverage_project(tmp_path, monkeypatch)
    _run(root, config)
    monkeypatch.delenv("RUNNER_COVERAGE")
    (root / "tests" / "test_a.py").write_text(_test_file("a", "assert 1"), encoding="utf-8")
    _run(root, config)

    graph = build_graph(config=config, repo_root=root)
    absent = [u for u in graph.unread_artifacts() if u.artifact == "coverage"]
    assert [u.reason for u in absent] == ["absent"]


# Verifies: REQ-d00283-R
def test_a_partial_run_that_left_no_results_records_its_results_absent(tmp_path, monkeypatch):
    root, config = _project(tmp_path)
    _run(root, config)
    monkeypatch.setenv("RUNNER_NO_RESULTS", "1")
    (root / "tests" / "test_a.py").write_text(_test_file("a", "assert 1"), encoding="utf-8")
    _run(root, config)

    graph = build_graph(config=config, repo_root=root, scan_code=False)
    absent = [u for u in graph.unread_artifacts() if u.artifact == "results"]
    assert [u.reason for u in absent] == ["absent"]


# Verifies: REQ-d00327-H
def test_retained_coverage_holds_its_test_names_repo_relative(tmp_path):
    from elspais.utilities.fingerprint import read_fingerprint
    from elspais.utilities.retention import retained_coverage

    root, config = _project(tmp_path)
    target = config["scanning"]["test"]["targets"][0]
    target.update(
        {
            "cwd": "tests",
            "coverage": "coverage.json",
            "results_origin": "working-directory",
            "coverage_origin": "repository-root",
        }
    )
    typed = validate_config(config)
    area = _area(root, config)
    area.mkdir(parents=True)
    entry = {"executed_lines": [1], "missing_lines": [], "contexts": {"1": ["test_a.py::t|run"]}}
    (area / "coverage.json").write_text(json.dumps({"files": {"src/lib.py": entry}}))
    last = {"commit": "c", "root": str(root), "started_at": "s", "manifest": {"src/lib.py": "D"}}

    kept = retained_coverage(root, typed, typed.scanning.test.targets[0], last, {"src/lib.py": "D"})

    assert kept["src/lib.py"]["contexts"] == {1: ["tests/test_a.py::t|run"]}
    assert read_fingerprint(area) is None


# Verifies: REQ-d00333-G
def test_a_command_that_failed_with_no_failing_result_leaves_nothing_retainable(
    tmp_path, monkeypatch
):
    root, config = _project(tmp_path)
    monkeypatch.setenv("RUNNER_EXIT", "1")
    first, _ = _run(root, config)
    assert not first.succeeded
    ledger = read_ledger(_area(root, config))
    assert {e.outcome for e in ledger.units.values()} == {"command-failed"}

    monkeypatch.delenv("RUNNER_EXIT")
    (root / "tests" / "test_a.py").write_text(_test_file("a", "assert 1"), encoding="utf-8")
    second, _ = _run(root, config)
    assert second.plan.retained == {}


# A stand-in Dart test runner: each `test('name', ...)` line of each Dart test
# file it is handed (or finds under a directory it is handed) passes.
# RUNNER_PUB_GET names a package configuration it brings into agreement with
# the pubspec first, listing package util, as `flutter test` resolves packages
# before it tests.
_DART_RUNNER = """
import json, os, pathlib, re, sys
out = pathlib.Path(os.environ["ELSPAIS_TARGET_OUTPUT"])
if os.environ.get("RUNNER_PUB_GET"):
    config = pathlib.Path(os.environ["RUNNER_PUB_GET"])
    data = json.loads(config.read_text())
    data["packages"].append({"name": "util", "rootUri": "../../util/"})
    config.write_text(json.dumps(data))
paths = []
for arg in sys.argv[1:]:
    p = pathlib.Path(arg)
    paths += sorted(p.rglob("*_test.dart")) if p.is_dir() else [p]
log = pathlib.Path(os.environ["RUNNER_LOG"])
log.write_text((log.read_text() if log.exists() else "") + " ".join(map(str, paths)) + "\\n")
lines = []
for p in paths:
    for n, line in enumerate(p.read_text().splitlines(), 1):
        m = re.match(r"\\s*test\\('(\\w+)'", line)
        if m:
            lines.append(json.dumps({"target": "unit", "file": p.as_posix(), "line": n,
                                     "name": m.group(1), "outcome": "passed"}))
(out / "results.jsonl").write_text("".join(l + "\\n" for l in lines))
"""


def _dart_test(lib: str) -> str:
    return (
        f"import '../lib/{lib}';\n\n"
        "void main() {\n"
        "  // Verifies: REQ-d00001-A\n"
        f"  test('{lib.removesuffix('.dart')}', () {{}});\n"
        "}\n"
    )


def _dart_project(tmp_path: Path) -> tuple[Path, dict]:
    """A Dart package whose two test files each import their own library file.

    The package depends on the repository package util by path.
    """
    root = tmp_path / "repo"
    files = {
        "spec/dev.md": _SPEC,
        "app/pubspec.yaml": "name: app\ndependencies:\n  util:\n    path: ../util\n",
        "app/pubspec.lock": "packages: {}\n",
        "util/pubspec.yaml": "name: util\n",
        "app/lib/a.dart": "int a = 1;\n",
        "app/lib/b.dart": "int b = 1;\n",
        "app/test/a_test.dart": _dart_test("a.dart"),
        "app/test/b_test.dart": _dart_test("b.dart"),
        "assets/data.txt": "one\n",
        "app/.dart_tool/package_config.json": json.dumps(
            {
                "configVersion": 2,
                "packages": [
                    {"name": "app", "rootUri": "../"},
                    {"name": "util", "rootUri": "../../util/"},
                ],
            }
        ),
    }
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    runner = tmp_path / "dart_runner.py"
    runner.write_text(textwrap.dedent(_DART_RUNNER), encoding="utf-8")
    target = {
        "name": "unit",
        "reporter": "evidence-snapshot",
        "results": "results.jsonl",
        "command": f"{sys.executable} {runner} {{selection}}",
        "inputs": {"skip_dirs": ["**/.dart_tool"]},
        "units": {"dependencies": {"source": "imports:dart"}, "full_selection": "app/test"},
        "environment_probes": [
            {"name": "sdk", "command": "echo 3"},
            {"name": "tool", "command": "printenv TOOL_VERSION", "affects_retention": False},
        ],
    }
    config = {
        "version": 5,
        "project": {"name": "dart", "namespace": "REQ"},
        "scanning": {
            "spec": {"directories": ["spec"]},
            "code": {"directories": ["app/lib"]},
            "test": {
                "enabled": True,
                "directories": ["app/test"],
                "file_patterns": ["*_test.dart"],
                "targets": [target],
            },
        },
    }
    _write_config(root, config)
    return root, config


# Verifies: REQ-d00333-B+C
def test_a_dart_library_edit_executes_only_the_test_files_importing_it(tmp_path):
    root, config = _dart_project(tmp_path)
    first, failures = _run(root, config)
    assert failures == []
    assert first.plan.whole
    assert first.plan.evidence.files["app/test/a_test.dart"] == {
        "app/test/a_test.dart",
        "app/lib/a.dart",
    }
    (root / "app/lib/a.dart").write_text("int a = 2;\n", encoding="utf-8")

    second, failures = _run(root, config)

    assert failures == []
    assert sorted(second.plan.selected) == ["app/test/a_test.dart"]
    assert "app/lib/a.dart changed" in second.plan.selected["app/test/a_test.dart"]
    assert sorted(second.plan.retained) == ["app/test/b_test.dart"]
    assert _executed(tmp_path)[-1] == "app/test/a_test.dart"


# Verifies: REQ-d00333-B+C
def test_an_input_the_dart_source_does_not_observe_executes_every_test_file(tmp_path):
    root, config = _dart_project(tmp_path)
    _run(root, config)
    (root / "assets/data.txt").write_text("two\n", encoding="utf-8")

    second, _ = _run(root, config)

    assert sorted(second.plan.selected) == ["app/test/a_test.dart", "app/test/b_test.dart"]
    assert second.plan.whole
    assert _executed(tmp_path)[-1] == "app/test/a_test.dart app/test/b_test.dart"


# Verifies: REQ-d00311-E, REQ-d00333-B
@pytest.mark.parametrize("pub_get", [True, False])
def test_a_run_whose_source_holds_no_evidence_states_why_and_asks_again_once_it_ends(
    tmp_path, monkeypatch, capsys, pub_get
):
    root, config = _dart_project(tmp_path)
    resolved = root / "app/.dart_tool/package_config.json"
    resolved.write_text(
        json.dumps({"configVersion": 2, "packages": [{"name": "app", "rootUri": "../"}]}),
        encoding="utf-8",
    )
    if pub_get:
        monkeypatch.setenv("RUNNER_PUB_GET", str(resolved))
    why = (
        "app/pubspec.yaml declares util at util, which app/.dart_tool/package_config.json "
        "does not list; run `dart pub get` or `flutter pub get` in app"
    )

    first, failures = _run(root, config)

    assert failures == []
    assert first.plan.whole
    assert first.plan.whole_reason == (
        f"the dependency source gave no evidence for any test file: {why}"
    )
    err = capsys.readouterr().err
    assert f"units: unit: no dependency evidence for 2 test files: {why}\n" in err
    ledger = read_ledger(_area(root, config))
    # The source answered, so the ledger records no failure of it.
    assert first.plan.source_failed == ""
    assert ledger.source_failed == ""
    observed = ledger.units["app/test/a_test.dart"].observed
    if pub_get:
        # Asked again after the run, the source answers: the digests are
        # those of the tree the run started from.
        assert set(observed) == {"app/test/a_test.dart", "app/lib/a.dart"}
    else:
        assert observed == {}
    # Stale through a probe that leaves retention unaffected.
    monkeypatch.setenv("TOOL_VERSION", "2")
    monkeypatch.delenv("RUNNER_PUB_GET", raising=False)

    second, _ = _run(root, config)

    if pub_get:
        assert sorted(second.plan.retained) == ["app/test/a_test.dart", "app/test/b_test.dart"]
    else:
        assert second.plan.whole
        assert second.plan.whole_reason.endswith(why)


# Verifies: REQ-d00333-B
def test_one_cause_selecting_every_test_file_is_named_as_the_reason_for_the_whole_run(
    tmp_path,
):
    root, config = _dart_project(tmp_path)
    _run(root, config)
    (root / "assets/data.txt").write_text("two\n", encoding="utf-8")

    second, _ = _run(root, config)

    assert second.plan.whole
    assert second.plan.whole_reason == "assets/data.txt changed"
    assert second.plan.selected == {
        "app/test/a_test.dart": "assets/data.txt changed",
        "app/test/b_test.dart": "assets/data.txt changed",
    }
    assert second.plan.retained == {}


# Verifies: REQ-d00333-B
def test_different_causes_selecting_every_test_file_are_summarised_for_the_whole_run(
    tmp_path,
):
    root, config = _dart_project(tmp_path)
    _run(root, config)
    (root / "app/lib/a.dart").write_text("int a = 2;\n", encoding="utf-8")
    (root / "app/lib/b.dart").write_text("int b = 2;\n", encoding="utf-8")

    second, _ = _run(root, config)

    assert second.plan.whole
    assert second.plan.whole_reason == "the evidence of every test file changed"
    assert sorted(second.plan.selected) == ["app/test/a_test.dart", "app/test/b_test.dart"]
    assert second.plan.retained == {}


def _foreign_test_project(tmp_path: Path, **units) -> tuple[Path, dict]:
    """A project whose scan below the target's directory holds a test file its command never runs.

    The stand-in runner executes only ``test_*.py`` files; the scan also reads
    ``*_spec.py``, the way an application's scan holds test files another
    target runs.
    """
    root, config = _project(tmp_path, **units)
    (root / "tests" / "c_spec.py").write_text(_test_file("c"), encoding="utf-8")
    config["scanning"]["test"]["file_patterns"] = ["test_*.py", "*_spec.py"]
    return root, config


# Verifies: REQ-d00333-H
def test_a_scanned_test_file_the_command_never_runs_fails_a_run_that_selects_it(tmp_path):
    from elspais.utilities.retention import unit_inventory

    root, config = _foreign_test_project(tmp_path)
    typed = validate_config(config)
    target = typed.scanning.test.targets[0]
    assert "tests/c_spec.py" in unit_inventory(root, typed, target)

    result, failures = _run(root, config)

    assert failures == ["unit"]
    assert not result.succeeded
    assert read_ledger(_area(root, config)).units["tests/c_spec.py"].outcome == "no-result"


# Verifies: REQ-d00333-H
def test_a_units_target_selecting_its_test_files_leaves_others_out_of_its_units(tmp_path):
    from elspais.utilities.retention import unit_inventory

    root, config = _foreign_test_project(
        tmp_path, tests={"directories": ["tests"], "file_patterns": ["test_*.py"]}
    )
    typed = validate_config(config)
    target = typed.scanning.test.targets[0]
    assert unit_inventory(root, typed, target) == ("tests/test_a.py", "tests/test_b.py")

    result, failures = _run(root, config)

    assert failures == []
    assert result.succeeded
    assert sorted(read_ledger(_area(root, config)).units) == [
        "tests/test_a.py",
        "tests/test_b.py",
    ]
