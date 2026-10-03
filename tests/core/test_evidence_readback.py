# Verifies: REQ-d00322-J
"""A build reads a target's results back from the project's Evidence Snapshot.

Each test builds a project whose scenario is declared once in a shared file
and executed by two runner files, with a `flutter-machine` target and a
committed snapshot directory.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from elspais.graph.GraphNode import NodeKind
from elspais.utilities.evidence import ResultLine, Snapshot, render_files
from tests.core.test_target_ingestion import (
    _RUNNER_A,
    _RUNNER_A_DART,
    _RUNNER_B,
    _RUNNER_B_DART,
    _SHARED_CONFIG,
    _SHARED_DART,
    _SHARED_FILE,
    _SHARED_LINE,
    _SHARED_SPEC,
    _machine_run,
)

_EVIDENCE = "test-evidence"
_SCENARIO = "boot two stores share one identity"


def _scenario_run(runner: str, outcome: str = "passed") -> ResultLine:
    return ResultLine(
        target="flutter",
        file=_SHARED_FILE,
        line=_SHARED_LINE,
        name=_SCENARIO,
        runner=runner,
        outcome=outcome,
    )


def _snapshot(*results: ResultLine, targets=(("flutter", "d" * 64),)) -> dict[str, str]:
    return render_files(
        Snapshot(
            results=tuple(results),
            tree="t" * 64,
            targets=tuple(targets),
            facts=(),
            elspais="0.0.0",
            timings=(),
            report="# Traceability\n",
        )
    )


def _project(root: Path, snapshot: dict[str, str] | None, *, own_results: bool) -> Path:
    config = _SHARED_CONFIG.replace(
        'file_patterns = ["*.dart"]\n',
        f'file_patterns = ["*.dart"]\nevidence = "{_EVIDENCE}"\n',
    )
    assert config != _SHARED_CONFIG
    files = {
        ".elspais.toml": config,
        "spec/requirements.md": _SHARED_SPEC,
        _SHARED_FILE: _SHARED_DART,
        _RUNNER_A: _RUNNER_A_DART,
        _RUNNER_B: _RUNNER_B_DART,
    }
    for name, text in (snapshot or {}).items():
        files[f"{_EVIDENCE}/{name}"] = text
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    if own_results:
        out = root / ".results" / "flutter"
        out.mkdir(parents=True)
        (out / "machine.jsonl").write_text(
            _machine_run(root, _RUNNER_A, _SHARED_FILE, "success", 1) + "\n",
            encoding="utf-8",
        )
    return root


def _build(root: Path, **kwargs):
    from elspais.graph.factory import build_graph

    return build_graph(repo_root=root, **kwargs)


def _results(graph) -> list:
    return sorted(graph.iter_by_kind(NodeKind.RESULT), key=lambda r: r.id)


def _unread(graph, target: str = "flutter") -> list:
    return [a for a in graph.unread_artifacts() if a.target == target]


# Verifies: REQ-d00322-J
def test_a_target_with_no_results_of_its_own_reads_the_snapshot(tmp_path):
    from elspais.graph.metrics import tested_and_passing

    root = _project(
        tmp_path, _snapshot(_scenario_run(_RUNNER_A), _scenario_run(_RUNNER_B)), own_results=False
    )
    graph = _build(root)
    results = _results(graph)

    assert len(results) == 2
    for result in results:
        assert result.get_field("carried") is True
        assert result.get_field("match_scope") == "test"
        assert result.get_field("source_file") == _SHARED_FILE
        assert result.get_field("result_file") == f"{_EVIDENCE}/results.jsonl"
    assert sorted(r.get_field("result_line") for r in results) == [1, 2]
    assert sorted(r.get_field("runner_file") for r in results) == [_RUNNER_A, _RUNNER_B]
    # The snapshot supplied the target, so its results are not missing.
    assert _unread(graph) == []

    rollup = graph.find_by_id("REQ-d00001").get_metric("rollup_metrics")
    assert tested_and_passing(rollup).covered == 1.0


# Verifies: REQ-d00322-J
def test_a_failed_outcome_in_the_snapshot_reads_as_failed(tmp_path):
    from elspais.graph.metrics import tested_and_passing

    root = _project(
        tmp_path,
        _snapshot(_scenario_run(_RUNNER_A), _scenario_run(_RUNNER_B, "failed")),
        own_results=False,
    )
    graph = _build(root)

    rollup = graph.find_by_id("REQ-d00001").get_metric("rollup_metrics")
    passing = tested_and_passing(rollup)
    assert passing.covered == 0
    assert passing.has_failures is True


# Verifies: REQ-d00322-J
def test_two_identical_lines_read_back_as_two_results(tmp_path):
    root = _project(
        tmp_path, _snapshot(_scenario_run(_RUNNER_A), _scenario_run(_RUNNER_A)), own_results=False
    )
    results = _results(_build(root))

    assert len(results) == 2
    assert len({r.id for r in results}) == 2


# Verifies: REQ-d00322-J
def test_a_target_the_snapshot_selected_with_no_results_reads_as_none(tmp_path):
    """A selected target whose run produced no result is supplied, not missing."""
    root = _project(tmp_path, _snapshot(), own_results=False)
    graph = _build(root)

    assert _results(graph) == []
    assert _unread(graph) == []


# Verifies: REQ-d00322-J
def test_a_target_the_snapshot_does_not_hold_reads_as_missing(tmp_path):
    root = _project(tmp_path, _snapshot(targets=()), own_results=False)
    graph = _build(root)

    assert _results(graph) == []
    assert [a.reason for a in _unread(graph)] == ["absent"]


# Verifies: REQ-d00322-J
def test_a_target_with_results_of_its_own_reads_nothing_from_the_snapshot(tmp_path):
    root = _project(
        tmp_path,
        _snapshot(_scenario_run(_RUNNER_A), _scenario_run(_RUNNER_B), _scenario_run(_RUNNER_B)),
        own_results=True,
    )
    results = _results(_build(root))

    assert len(results) == 1
    (result,) = results
    assert result.get_field("carried") is False
    assert result.get_field("result_file") == ".results/flutter/machine.jsonl"


# Verifies: REQ-d00322-J
def test_a_build_reading_only_the_snapshot_ignores_the_targets_own_results(tmp_path):
    root = _project(
        tmp_path,
        _snapshot(_scenario_run(_RUNNER_A), _scenario_run(_RUNNER_B), _scenario_run(_RUNNER_B)),
        own_results=True,
    )
    results = _results(_build(root, evidence_only=True))

    assert len(results) == 3
    assert {r.get_field("result_file") for r in results} == {f"{_EVIDENCE}/results.jsonl"}
    assert all(r.get_field("carried") is True for r in results)


# Verifies: REQ-d00322-J
def test_a_build_reading_only_the_snapshot_reads_it_before_its_report_exists(tmp_path):
    files = _snapshot(_scenario_run(_RUNNER_A))
    del files["TRACEABILITY.md"]
    root = _project(tmp_path, files, own_results=False)
    graph = _build(root, evidence_only=True)

    assert len(_results(graph)) == 1
    assert graph.ingestion_faults() == []


def _faults(graph) -> list[tuple[str, int | None, str]]:
    return [(f.path, f.line, f.cause) for f in graph.ingestion_faults()]


# Verifies: REQ-d00322-J
@pytest.mark.parametrize(
    "file,text,line",
    [
        ("results.jsonl", '{"target": "flutter"\n', 2),
        ("results.jsonl", '{"file":"x","name":"n","outcome":"lost","target":"flutter"}\n', 2),
        ("snapshot.json", "not json\n", None),
        ("TRACEABILITY.md", None, None),
    ],
    ids=["malformed-result-line", "unknown-outcome", "malformed-snapshot-json", "missing-report"],
)
def test_an_unreadable_snapshot_is_a_fault_naming_its_file_and_line(tmp_path, file, text, line):
    """An unreadable snapshot is reported, never read as an empty one."""
    from elspais.commands.health import check_ingestion_faults

    files = _snapshot(_scenario_run(_RUNNER_A))
    if text is None:
        del files[file]
    elif file == "results.jsonl":
        files[file] += text
    else:
        files[file] = text
    root = _project(tmp_path, files, own_results=False)
    graph = _build(root)

    assert _results(graph) == []
    ((path, fault_line, cause),) = _faults(graph)
    assert path == f"{_EVIDENCE}/{file}"
    assert fault_line == line
    assert "Evidence Snapshot" in cause
    # Nothing was read for the target, so it reads as missing results.
    assert [a.reason for a in _unread(graph)] == ["absent"]

    (entry,) = list(graph.iter_repos())
    check = check_ingestion_faults(graph, entry.config)
    assert check.passed is False
    assert any(f"{_EVIDENCE}/{file}" in f.message for f in check.findings)


# Verifies: REQ-d00322-J
def test_a_snapshot_directory_that_does_not_exist_supplies_nothing(tmp_path):
    root = _project(tmp_path, None, own_results=False)
    graph = _build(root)

    assert _results(graph) == []
    assert graph.ingestion_faults() == []
    assert [a.reason for a in _unread(graph)] == ["absent"]


# Verifies: REQ-d00322-J
@pytest.mark.parametrize("value", ["../x", "/abs/evidence", "..", "."])
def test_an_evidence_directory_outside_the_repository_is_refused(value):
    from pydantic import ValidationError

    from elspais.config.schema import TestScanningConfig

    with pytest.raises(ValidationError, match="scanning.test.evidence .* must name a directory"):
        TestScanningConfig(evidence=value)


# Verifies: REQ-d00322-J
@pytest.mark.parametrize(
    "value,normalized", [("", ""), ("test-evidence/", "test-evidence"), ("a/./b", "a/b")]
)
def test_an_evidence_directory_inside_the_repository_is_kept_normalized(value, normalized):
    from elspais.config.schema import TestScanningConfig

    assert TestScanningConfig(evidence=value).evidence == normalized


# Verifies: REQ-d00322-J
def test_the_parser_places_a_line_read_without_its_number_by_position():
    from elspais.graph.parsers.results.evidence_snapshot import EvidenceSnapshotParser

    text = (
        '{"file":"a.dart","line":4,"name":"n","outcome":"skipped",'
        '"skip_reason":"needs postgres","target":"t"}\n'
        '{"_line":7,"file":"b.dart","name":"m","outcome":"passed","runner":"r.dart","target":"t"}'
    )
    first, second = EvidenceSnapshotParser().parse(text, "ev/results.jsonl")

    assert (first["ordinal"], first["result_line"]) == (1, 1)
    assert (first["status"], first["message"], first["line"]) == ("skipped", "needs postgres", 4)
    assert (second["ordinal"], second["result_line"]) == (7, 7)
    assert (second["source_path"], second["runner_path"]) == ("b.dart", "r.dart")
    assert second["line"] is None


# Verifies: REQ-d00322-J
@pytest.mark.parametrize(
    "text,cause",
    [("{not json", "not valid JSON"), ("[1]", "not a JSON object"), ('{"file":"a"}', "missing")],
)
def test_the_parser_records_a_line_it_cannot_read(text, cause):
    from elspais.graph.parsers.results.evidence_snapshot import EvidenceSnapshotParser

    parser = EvidenceSnapshotParser()
    assert parser.parse(text, "ev/results.jsonl") == []
    (diagnostic,) = list(parser.iter_diagnostics())
    assert diagnostic.path == "ev/results.jsonl"
    assert diagnostic.line == 1
    assert cause in diagnostic.cause


# Verifies: REQ-d00283-Z, REQ-d00311-N
def test_an_expected_target_whose_run_is_in_progress_is_not_supplied_by_the_snapshot(tmp_path):
    """A run in progress is missing results, even where the snapshot holds the target."""
    from elspais.commands.health import check_ingestion_faults
    from elspais.config import load_config
    from elspais.utilities.fingerprint import start_run

    root = _project(tmp_path, _snapshot(_scenario_run(_RUNNER_A)), own_results=False)
    start_run(root, load_config(root / ".elspais.toml"), "flutter")
    graph = _build(root)

    assert _results(graph) == []
    assert [a.reason for a in _unread(graph)] == ["running"]
    faults = check_ingestion_faults(graph, {}, ("REQ:flutter",))
    assert faults.passed is False
    assert any(
        "target flutter" in f.message and "run is in progress" in f.message for f in faults.findings
    )


# Verifies: REQ-d00322-J
def test_the_parser_numbers_lines_by_line_feeds_alone():
    """A value holding a Unicode line separator does not shift later lines."""
    from elspais.graph.parsers.results.evidence_snapshot import EvidenceSnapshotParser

    text = (
        '{"file":"a.dart","name":"x\u2028y","outcome":"passed","target":"t"}\n'
        '{"file":"b.dart","name":"m","outcome":"passed","target":"t"}\n'
    )
    parser = EvidenceSnapshotParser()
    first, second = parser.parse(text, "ev/results.jsonl")

    assert list(parser.iter_diagnostics()) == []
    assert (first["name"], first["result_line"]) == ("x\u2028y", 1)
    assert (second["name"], second["result_line"]) == ("m", 2)


# Verifies: REQ-d00322-J, REQ-d00254-O, REQ-d00294-C
@pytest.mark.parametrize(
    "setting",
    ["line_base = 0", 'environment = "suite-hostname"', 'environment = "results-path"'],
)
def test_the_targets_own_reporter_settings_do_not_apply_to_the_snapshot(tmp_path, setting):
    """The snapshot's lines are in the tool's own numbering and carry no environment."""
    from elspais.commands.health import check_ingestion_faults

    root = _project(tmp_path, _snapshot(_scenario_run(_RUNNER_A)), own_results=False)
    config_path = root / ".elspais.toml"
    text = config_path.read_text(encoding="utf-8")
    patched = text.replace('match = "source"\n', f'match = "source"\n{setting}\n')
    assert patched != text
    config_path.write_text(patched, encoding="utf-8")

    graph = _build(root)
    (result,) = _results(graph)

    assert result.get_field("match_scope") == "test"
    assert result.get_field("line") == _SHARED_LINE
    assert graph.ingestion_faults() == []
    (entry,) = list(graph.iter_repos())
    assert check_ingestion_faults(graph, entry.config).passed is True


def _finished_empty_run(root: Path) -> None:
    from elspais.config import load_config
    from elspais.utilities.fingerprint import finish_run, start_run

    config = load_config(root / ".elspais.toml")
    start_run(root, config, "flutter")
    finish_run(root, config, "flutter")


# Verifies: REQ-d00322-J, REQ-d00283-R
@pytest.mark.parametrize("fresh", [None, {"flutter"}], ids=["plain-build", "executed"])
def test_a_target_that_ran_here_and_left_nothing_is_not_supplied_by_the_snapshot(tmp_path, fresh):
    """A finished run with no results owns that answer: an expected target fails the gate."""
    from elspais.commands.health import check_ingestion_faults

    root = _project(
        tmp_path, _snapshot(_scenario_run(_RUNNER_A), _scenario_run(_RUNNER_B)), own_results=False
    )
    _finished_empty_run(root)
    graph = _build(root, fresh_targets=fresh)

    assert _results(graph) == []
    assert [a.reason for a in _unread(graph)] == ["absent"]
    faults = check_ingestion_faults(graph, {}, ("REQ:flutter",))
    assert faults.passed is False


# Verifies: REQ-d00322-J, REQ-d00254-I
def test_a_target_this_run_executes_is_not_supplied_by_the_snapshot(tmp_path):
    """No fingerprint is needed: a target the run executes reads no carried results."""
    root = _project(tmp_path, _snapshot(_scenario_run(_RUNNER_A)), own_results=False)
    graph = _build(root, fresh_targets={"flutter"})

    assert _results(graph) == []
    assert [a.reason for a in _unread(graph)] == ["absent"]


# Verifies: REQ-d00322-J
def test_a_build_reading_only_the_snapshot_reads_it_after_a_finished_empty_run(tmp_path):
    root = _project(tmp_path, _snapshot(_scenario_run(_RUNNER_A)), own_results=False)
    _finished_empty_run(root)
    graph = _build(root, evidence_only=True, fresh_targets={"flutter"})

    (result,) = _results(graph)
    assert result.get_field("carried") is True
    assert _unread(graph) == []
