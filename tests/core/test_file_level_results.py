"""Tests for crediting a test file from the exit status of its target's command.

A target that declares ``file_results`` takes the exit status of its command as
the result of each test file it scans. A citation in such a file that binds to
no test binds to the file, and the file's result decides it. A per-test result,
where the target also has one, decides the citations of the test it names.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from elspais.config.schema import ElspaisConfig, TestTargetConfig
from elspais.graph import NodeKind, make_file_result_id
from elspais.graph.metrics import tested_and_passing, tested_partition

_CONFIG = """\
version = 5

[project]
name = "filelevel"
namespace = "REQ"

[levels.dev]
rank = 1
letter = "d"
implements = ["dev"]

[id-patterns]
canonical = "{{namespace}}-{{level.letter}}{{component}}"

[id-patterns.component]
style = "numeric"
digits = 5
leading_zeros = true

[scanning.spec]
directories = ["spec"]

[scanning.test]
enabled = true
directories = ["tests"]
file_patterns = ["*.py"]

[[scanning.test.targets]]
name = "scripts"
cwd = "tests/scripts"
command = '"{python}" check_layout.py'
file_results = true
{extra}
[rules.format]
require_hash = false
require_assertions = false
require_status = false
"""

_SPEC = """\
# Requirements

---

### REQ-d00001: Layout

**Level**: dev | **Status**: Active

## Assertions

A. The system SHALL keep the layout file.
B. The system SHALL name the layout.
C. The system SHALL keep the names file.

*End* *Layout*
---

### REQ-d00002: Other

**Level**: dev | **Status**: Active

## Assertions

A. The system SHALL do the other thing.

*End* *Other*
---
"""

# A module of top-level assertions: a bare interpreter exits non-zero at the
# first one that fails. Its first citation is above no test, so it binds to
# the file; its second is inside a test.
_LAYOUT = "tests/scripts/check_layout.py"
_LAYOUT_PY = """\
# Verifies: REQ-d00001-A
import pathlib

assert pathlib.Path("expected.txt").read_text() == "ok"


def test_b():
    # Verifies: REQ-d00001-B
    assert True


test_b()
"""

_NAMES = "tests/scripts/check_names.py"
_NAMES_PY = """\
# Verifies: REQ-d00001-C
import os

assert os.sep
"""

# Outside the target's working directory, so no file-level result reaches it.
_OTHER = "tests/unit/check_other.py"
_OTHER_PY = """\
# Verifies: REQ-d00002-A
import os

assert os.sep
"""

# A target that also reads per-test results names test_b in a pytest-json report.
_MIXED_EXTRA = """\
reporter = "pytest-json"
results = "*.json"
"""


def _write_project(root: Path, *, layout_ok: bool, extra: str = "") -> None:
    files = {
        ".elspais.toml": _CONFIG.format(python=sys.executable, extra=extra),
        "spec/requirements.md": _SPEC,
        _LAYOUT: _LAYOUT_PY,
        _NAMES: _NAMES_PY,
        _OTHER: _OTHER_PY,
        "tests/scripts/expected.txt": "ok" if layout_ok else "broken",
    }
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _typed_config(root: Path) -> ElspaisConfig:
    from elspais.config import load_config

    return ElspaisConfig.model_validate(load_config(root / ".elspais.toml"))


def _build(root: Path):
    from elspais.config import load_config
    from elspais.graph.factory import build_graph

    return build_graph(repo_root=root), load_config(root / ".elspais.toml")


def _rollup(graph, req_id: str):
    return graph.find_by_id(req_id).get_metric("rollup_metrics")


def _file_results(graph) -> dict[str, str]:
    return {
        r.id: r.get_field("status")
        for r in graph.iter_by_kind(NodeKind.RESULT)
        if r.get_field("match") == "file"
    }


def _verdicts(graph, req_id: str) -> dict[str, str]:
    """Each tested label of *req_id* mapped to passed, failed or awaiting."""
    rollup = _rollup(graph, req_id)
    passing = tested_and_passing(rollup)
    failing = set(passing.failing_labels)
    verdicts = {}
    for label, credit in rollup.tested.total_by_label.items():
        if credit <= 0:
            continue
        if label in failing:
            verdicts[label] = "failed"
        elif passing.total_by_label.get(label, 0.0) > 0:
            verdicts[label] = "passed"
        else:
            verdicts[label] = "awaiting"
    return verdicts


# ---------------------------------------------------------------------------
# The setting
# ---------------------------------------------------------------------------


# Verifies: REQ-d00329-A
@pytest.mark.parametrize(
    "fields",
    [
        {"command": "python check.py"},
        {"command": "python check.py", "results": "*.json", "file_results": True},
    ],
    ids=["command-without-file-results", "results-pattern-without-reporter"],
)
def test_a_target_without_a_reporter_is_refused_unless_its_status_is_its_result(fields):
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="reporter is required"):
        TestTargetConfig(name="scripts", **fields)
    # The same command is admitted once its exit status is its files' result.
    TestTargetConfig(name="scripts", command=fields["command"], file_results=True)


# ---------------------------------------------------------------------------
# Recording the exit status
# ---------------------------------------------------------------------------


# Verifies: REQ-d00329-B
@pytest.mark.parametrize("status", [0, 3])
def test_a_finished_run_records_the_exit_status_it_is_given(tmp_path: Path, status: int):
    from elspais.utilities.fingerprint import (
        finish_run,
        read_fingerprint,
        recorded_exit_status,
        results_present,
        start_run,
    )

    _write_project(tmp_path, layout_ok=True)
    config = _typed_config(tmp_path)
    folder = start_run(tmp_path, config, "scripts")

    assert recorded_exit_status(folder) is None
    assert results_present(tmp_path, config, config.scanning.test.targets[0]) is False

    finish_run(tmp_path, config, "scripts", exit_status=status)

    assert read_fingerprint(folder)["exit_status"] == status
    assert recorded_exit_status(folder) == status
    assert results_present(tmp_path, config, config.scanning.test.targets[0]) is True


# Verifies: REQ-d00329-B+I
def test_a_run_finished_without_a_status_records_none(tmp_path: Path):
    from elspais.utilities.fingerprint import (
        finish_run,
        read_fingerprint,
        recorded_exit_status,
        start_run,
    )

    _write_project(tmp_path, layout_ok=True)
    config = _typed_config(tmp_path)
    folder = start_run(tmp_path, config, "scripts")
    finish_run(tmp_path, config, "scripts")

    assert "exit_status" not in read_fingerprint(folder)
    assert recorded_exit_status(folder) is None


# Verifies: REQ-d00329-B+I
def test_a_command_that_could_not_start_records_no_exit_status(tmp_path: Path):
    """A working directory that does not exist stops the command spawning at all."""
    from elspais.commands.test_runner import run_configured_targets
    from elspais.utilities.fingerprint import read_fingerprint, target_folder

    _write_project(tmp_path, layout_ok=True)
    config = _typed_config(tmp_path)
    target = config.scanning.test.targets[0].model_copy(update={"cwd": "tests/absent"})
    test_cfg = config.scanning.test.model_copy(update={"targets": [target]})
    config = config.model_copy(
        update={"scanning": config.scanning.model_copy(update={"test": test_cfg})}
    )

    (result,) = run_configured_targets(config, tmp_path)[0]

    assert result.error
    fingerprint = read_fingerprint(target_folder(tmp_path, config, "scripts"))
    assert fingerprint["finished_at"]
    assert "exit_status" not in fingerprint


# Verifies: REQ-d00329-B
def test_fingerprint_finish_passes_its_exit_status_through(tmp_path: Path, monkeypatch):
    import argparse

    from elspais.commands import fingerprint_cmd
    from elspais.utilities.fingerprint import recorded_exit_status, start_run, target_folder

    _write_project(tmp_path, layout_ok=True)
    config = _typed_config(tmp_path)
    start_run(tmp_path, config, "scripts")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(fingerprint_cmd, "find_git_root", lambda: tmp_path)

    rc = fingerprint_cmd.run(
        argparse.Namespace(
            fingerprint_action="finish", target="scripts", exit_status=2, config=None
        )
    )

    assert rc == 0
    assert recorded_exit_status(target_folder(tmp_path, config, "scripts")) == 2


# ---------------------------------------------------------------------------
# A passing and a failing file, through the configured command
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module", params=[True, False], ids=["command-passed", "command-failed"])
def ran_project(request, tmp_path_factory):
    """A project whose file-level target ran its command, which passed or failed."""
    from elspais.commands.test_runner import run_configured_targets

    root = tmp_path_factory.mktemp("filelevel") / "proj"
    _write_project(root, layout_ok=request.param)
    (result,) = run_configured_targets(_typed_config(root), root)[0]
    graph, config = _build(root)
    return request.param, result, graph, config, root


# Verifies: REQ-d00329-B+C+D
def test_the_command_runs_and_its_status_is_recorded(ran_project):
    from elspais.utilities.fingerprint import read_fingerprint

    passed, result, _graph, _config, root = ran_project

    assert (result.returncode == 0) is passed
    fingerprint = read_fingerprint(root / ".results" / "scripts")
    assert fingerprint["exit_status"] == result.returncode


# Verifies: REQ-d00329-C+D+E
def test_each_scanned_file_holds_one_file_level_result_named_by_target_and_file(ran_project):
    passed, _result, graph, _config, _root = ran_project

    expected_status = "passed" if passed else "failed"
    assert _file_results(graph) == {
        make_file_result_id("REQ", "scripts", _LAYOUT): expected_status,
        make_file_result_id("REQ", "scripts", _NAMES): expected_status,
    }


# Verifies: REQ-d00329-C+D+F+G+J
def test_every_citation_in_the_files_takes_the_command_verdict(ran_project):
    """The file-bound citations (A, C) and the one inside a test (B) alike."""
    passed, _result, graph, _config, _root = ran_project

    expected = "passed" if passed else "failed"
    assert _verdicts(graph, "REQ-d00001") == {"A": expected, "B": expected, "C": expected}
    partition = tested_partition(_rollup(graph, "REQ-d00001"))
    assert partition.awaiting == 0
    if passed:
        assert tested_and_passing(_rollup(graph, "REQ-d00001")).covered == 3
    else:
        assert partition.passed == 0
        assert partition.failed == 3
        assert tested_and_passing(_rollup(graph, "REQ-d00001")).has_failures is True


# Verifies: REQ-d00329-D
def test_a_failing_command_is_reported_as_failed_results(ran_project):
    from elspais.commands.health import check_test_results

    passed, _result, graph, config, _root = ran_project
    check = check_test_results(graph, config)

    assert check.passed is passed


# Verifies: REQ-d00329-F, REQ-d00274-G+H
def test_a_file_bound_citation_is_not_reported_and_one_outside_the_target_is(ran_project):
    from elspais.commands.health import check_unbound_citations

    _passed, _result, graph, config, _root = ran_project
    check = check_unbound_citations(graph, config)
    paths = {f.file_path for f in check.findings}

    assert paths == {_OTHER}
    assert _verdicts(graph, "REQ-d00002") == {}
    assert _rollup(graph, "REQ-d00002").tested.covered == 0


# Verifies: REQ-d00329-G, REQ-d00274-I
def test_file_level_results_are_not_reported_as_unmatched_or_file_bound(ran_project):
    from elspais.commands.health import (
        check_file_bound_results,
        check_ingestion_faults,
        check_unmatched_results,
    )

    _passed, _result, graph, config, _root = ran_project

    assert check_unmatched_results(graph, config).passed is True
    assert check_file_bound_results(graph, config).passed is True
    # A target with no reporter whose run recorded its exit status owes no
    # results file, so nothing is reported as unread.
    assert check_ingestion_faults(graph, config, expected_targets=("REQ:scripts",)).passed


# ---------------------------------------------------------------------------
# No recorded exit status
# ---------------------------------------------------------------------------


# Verifies: REQ-d00329-I
@pytest.mark.parametrize("recorded", ["never-run", "finished-without-status"])
def test_without_a_recorded_status_each_citation_awaits_a_result(tmp_path: Path, recorded):
    from elspais.commands.health import check_ingestion_faults
    from elspais.utilities.fingerprint import finish_run, start_run

    _write_project(tmp_path, layout_ok=True)
    if recorded == "finished-without-status":
        config = _typed_config(tmp_path)
        start_run(tmp_path, config, "scripts")
        finish_run(tmp_path, config, "scripts")

    graph, config = _build(tmp_path)

    assert _file_results(graph) == {}
    assert _verdicts(graph, "REQ-d00001") == {"A": "awaiting", "B": "awaiting", "C": "awaiting"}
    check = check_ingestion_faults(graph, config, expected_targets=("REQ:scripts",))
    assert check.passed is False
    assert any("exit status" in f.message for f in check.findings)


# ---------------------------------------------------------------------------
# A target scanning no test file
# ---------------------------------------------------------------------------

_EMPTY_CWD = "tests/empty"


def _point_target_at_empty_folder(root: Path) -> None:
    """Move the target's working directory to a folder holding no scanned test file.

    The folder exists and holds a file, but not one the target scans.
    """
    (root / _EMPTY_CWD).mkdir(parents=True, exist_ok=True)
    (root / _EMPTY_CWD / "notes.txt").write_text("not a test\n", encoding="utf-8")
    config_path = root / ".elspais.toml"
    text = config_path.read_text(encoding="utf-8")
    assert 'cwd = "tests/scripts"' in text
    config_path.write_text(
        text.replace('cwd = "tests/scripts"', f'cwd = "{_EMPTY_CWD}"', 1), encoding="utf-8"
    )


def _target_faults(graph, target: str) -> list:
    return [f for f in graph.ingestion_faults() if f.target == target]


# Verifies: REQ-d00329-K
@pytest.mark.parametrize("recorded", ["exit-status-recorded", "never-run"])
def test_a_target_scanning_no_test_file_is_reported_with_its_working_directory(
    tmp_path: Path, recorded: str
):
    from elspais.commands.health import check_ingestion_faults
    from elspais.utilities.fingerprint import finish_run, start_run

    _write_project(tmp_path, layout_ok=True)
    _point_target_at_empty_folder(tmp_path)
    if recorded == "exit-status-recorded":
        config = _typed_config(tmp_path)
        start_run(tmp_path, config, "scripts")
        finish_run(tmp_path, config, "scripts", exit_status=0)

    graph, config = _build(tmp_path)

    (fault,) = _target_faults(graph, "scripts")
    assert fault.path == _EMPTY_CWD
    assert _EMPTY_CWD in fault.cause
    assert _file_results(graph) == {}

    check = check_ingestion_faults(graph, config)
    assert check.passed is False
    (finding,) = [f for f in check.findings if "target scripts" in f.message]
    assert finding.file_path == _EMPTY_CWD
    assert _EMPTY_CWD in finding.message


# Verifies: REQ-d00329-K
def test_a_target_whose_working_directory_holds_a_scanned_test_file_is_not_reported(
    tmp_path: Path,
):
    from elspais.commands.health import check_ingestion_faults
    from elspais.utilities.fingerprint import finish_run, start_run

    _write_project(tmp_path, layout_ok=True)
    config = _typed_config(tmp_path)
    start_run(tmp_path, config, "scripts")
    finish_run(tmp_path, config, "scripts", exit_status=0)

    graph, config = _build(tmp_path)

    assert _target_faults(graph, "scripts") == []
    assert _verdicts(graph, "REQ-d00001") == {"A": "passed", "B": "passed", "C": "passed"}
    assert check_ingestion_faults(graph, config, expected_targets=("REQ:scripts",)).passed


# ---------------------------------------------------------------------------
# A target mixing per-test and file-level results
# ---------------------------------------------------------------------------


def _record_mixed_run(root: Path, *, per_test: str, exit_status: int) -> None:
    from elspais.utilities.fingerprint import finish_run, start_run

    config = _typed_config(root)
    folder = start_run(root, config, "scripts")
    report = {
        "created_at": "test",
        "summary": {"total": 1},
        "tests": [
            {
                "nodeid": "tests/scripts/check_layout.py::test_b",
                "outcome": per_test,
                "duration": 0.001,
            }
        ],
    }
    (folder / "report.json").write_text(json.dumps(report), encoding="utf-8")
    finish_run(root, config, "scripts", exit_status=exit_status)


# Verifies: REQ-d00329-G+H, REQ-d00274-I
@pytest.mark.parametrize(
    ("per_test", "exit_status"),
    [("failed", 0), ("passed", 1), ("passed", 0)],
    ids=["test-failed-command-passed", "test-passed-command-failed", "both-passed"],
)
def test_a_per_test_result_decides_its_test_and_the_file_result_decides_the_rest(
    tmp_path: Path, per_test: str, exit_status: int
):
    from elspais.commands.health import (
        check_file_bound_results,
        check_unbound_citations,
        check_unmatched_results,
    )

    _write_project(tmp_path, layout_ok=True, extra=_MIXED_EXTRA)
    _record_mixed_run(tmp_path, per_test=per_test, exit_status=exit_status)
    graph, config = _build(tmp_path)

    file_verdict = "passed" if exit_status == 0 else "failed"
    assert _verdicts(graph, "REQ-d00001") == {"A": file_verdict, "B": per_test, "C": file_verdict}
    (test_b,) = [t for t in graph.iter_by_kind(NodeKind.TEST) if "test_b" in t.id]
    yielded = [c for c in test_b.iter_children() if c.kind is NodeKind.RESULT]
    assert yielded
    assert all(r.get_field("match") != "file" for r in yielded)
    assert check_unmatched_results(graph, config).passed is True
    assert check_file_bound_results(graph, config).passed is True
    assert {f.file_path for f in check_unbound_citations(graph, config).findings} == {_OTHER}


# ---------------------------------------------------------------------------
# Evidence Snapshot
# ---------------------------------------------------------------------------


# Verifies: REQ-d00329-E
def test_an_evidence_snapshot_refuses_a_file_level_result(tmp_path: Path):
    import subprocess

    from elspais.config import get_config, validate_config
    from elspais.utilities.evidence import SnapshotRefused, derive_snapshot
    from elspais.utilities.fingerprint import finish_run, start_run

    _write_project(tmp_path, layout_ok=True)
    (tmp_path / ".gitignore").write_text(".results/\n", encoding="utf-8")
    git = ["git", "-c", "user.name=x", "-c", "user.email=x@x", "-c", "commit.gpgsign=false"]
    for args in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "init"]):
        subprocess.run([*git, *args], cwd=tmp_path, check=True, capture_output=True)
    config = validate_config(
        get_config(tmp_path / ".elspais.toml", start_path=tmp_path, quiet=True)
    )
    start_run(tmp_path, config, "scripts")
    finish_run(tmp_path, config, "scripts", exit_status=0)
    graph, _raw = _build(tmp_path)

    with pytest.raises(SnapshotRefused) as refused:
        derive_snapshot(graph, tmp_path, config, ["scripts"], (), "")

    assert any(
        "file-level result" in reason and _LAYOUT in reason for reason in refused.value.reasons
    )


# Verifies: REQ-d00329-E
def test_evidence_write_names_a_file_level_target_rather_than_leaving_it_out(
    tmp_path: Path, monkeypatch, capsys
):
    import subprocess

    from elspais.cli import main

    _write_project(tmp_path, layout_ok=True)
    config_path = tmp_path / ".elspais.toml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            'file_patterns = ["*.py"]\n',
            'file_patterns = ["*.py"]\nevidence = "test-evidence"\n',
            1,
        ),
        encoding="utf-8",
    )
    (tmp_path / ".gitignore").write_text(".results/\n", encoding="utf-8")
    git = ["git", "-c", "user.name=x", "-c", "user.email=x@x", "-c", "commit.gpgsign=false"]
    for args in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "init"]):
        subprocess.run([*git, *args], cwd=tmp_path, check=True, capture_output=True)
    monkeypatch.chdir(tmp_path)

    assert main(["test", "--targets", "scripts"]) == 0
    capsys.readouterr()

    assert main(["evidence", "write", "--targets", "scripts"]) == 2
    err = capsys.readouterr().err
    assert "file-level result" in err and _LAYOUT in err
    assert not (tmp_path / "test-evidence").exists()
