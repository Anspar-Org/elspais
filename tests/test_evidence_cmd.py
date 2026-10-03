# Verifies: REQ-d00322-A+B+D+E+F+H+I
"""``elspais evidence write`` and ``elspais evidence verify``, through the CLI.

Each test builds a git repository holding a project whose ``flutter`` target
runs a stub. The stub writes a ``flutter-machine`` stream into the target's
output area: one run of a shared scenario, passing or failing as the
``STUB_OUTCOME`` environment variable says.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from elspais.cli import main
from tests.core.test_target_ingestion import (
    _RUNNER_A,
    _RUNNER_A_DART,
    _SHARED_CONFIG,
    _SHARED_DART,
    _SHARED_FILE,
    _SHARED_SPEC,
    _machine_run,
)

_EVIDENCE = "test-evidence"
_COMPARED = ("results.jsonl", "snapshot.json", "TRACEABILITY.md")
_GIT = [
    "git",
    "-c",
    "user.name=x",
    "-c",
    "user.email=x@x",
    "-c",
    "commit.gpgsign=false",
    "-c",
    "init.defaultBranch=main",
]

# The stream of one run, with the repository root and the outcome left open.
_STREAM = _machine_run(Path("@ROOT@"), _RUNNER_A, _SHARED_FILE, "@OUTCOME@", 1)

_STUB = f"""\
import os
import pathlib
import sys

root = pathlib.Path.cwd()
outcome = os.environ.get("STUB_OUTCOME", "success")
if os.environ.get("STUB_TOUCH"):
    # An input of the target changes while the run is going.
    (root / "test" / "touched.dart").write_text("// touched\\n")
stream = {_STREAM!r}.replace("@ROOT@", str(root)).replace("@OUTCOME@", outcome)
out = pathlib.Path(os.environ["ELSPAIS_TARGET_OUTPUT"])
(out / "machine.jsonl").write_text(stream + "\\n")
sys.exit(0 if outcome == "success" else 1)
"""

_TARGET = """
[[scanning.test.targets]]
name = "flutter"
reporter = "flutter-machine"
results = "machine.jsonl"
match = "source"
"""

_RUN_TARGET = (
    _TARGET
    + f"""command = '"{sys.executable}" tools/stub.py'

[scanning.test.targets.inputs]
directories = ["test"]
"""
)

# A target with no command: another job runs it and leaves its results.
_COPIED_TARGET = """
[[scanning.test.targets]]
name = "copied"
reporter = "flutter-machine"
results = "machine.jsonl"
match = "source"

[scanning.test.targets.inputs]
directories = ["test"]
"""


def _git(root: Path, *args: str) -> None:
    subprocess.run([*_GIT, *args], cwd=root, check=True, capture_output=True)


def _project(root: Path, monkeypatch, *, evidence: bool = True, extra_targets: str = "") -> Path:
    config = _SHARED_CONFIG.replace(_TARGET, _RUN_TARGET + extra_targets)
    assert config != _SHARED_CONFIG
    if evidence:
        config = config.replace(
            'file_patterns = ["*.dart"]\n',
            f'file_patterns = ["*.dart"]\nevidence = "{_EVIDENCE}"\n',
        )
    files = {
        ".elspais.toml": config,
        ".gitignore": ".results/\n",
        "README.md": "# Project\n",
        "spec/requirements.md": _SHARED_SPEC,
        "tools/stub.py": _STUB,
        _SHARED_FILE: _SHARED_DART,
        _RUNNER_A: _RUNNER_A_DART,
    }
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    monkeypatch.chdir(root)
    monkeypatch.delenv("STUB_OUTCOME", raising=False)
    monkeypatch.delenv("STUB_TOUCH", raising=False)
    return root


def _snapshot_bytes(root: Path) -> dict[str, bytes]:
    return {name: (root / _EVIDENCE / name).read_bytes() for name in _COMPARED}


def _commit(root: Path) -> None:
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "evidence")


# Verifies: REQ-d00322-A
def test_a_project_naming_no_snapshot_directory_is_refused(tmp_path, monkeypatch, capsys):
    _project(tmp_path, monkeypatch, evidence=False)

    assert main(["evidence", "write"]) == 2

    assert "scanning.test.evidence" in capsys.readouterr().err


# Verifies: REQ-d00322-B
def test_a_target_with_no_results_is_refused_by_name(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path, monkeypatch)

    assert main(["evidence", "write"]) == 2

    err = capsys.readouterr().err
    assert "target flutter results are absent" in err
    assert not (root / _EVIDENCE).exists()


# Verifies: REQ-d00322-B
def test_a_target_whose_input_changed_during_its_run_is_refused_as_stale(
    tmp_path, monkeypatch, capsys
):
    root = _project(tmp_path, monkeypatch)
    monkeypatch.setenv("STUB_TOUCH", "1")
    assert main(["test"]) == 0
    capsys.readouterr()

    assert main(["evidence", "write"]) == 2

    err = capsys.readouterr().err
    assert "target flutter results are stale" in err
    assert "test/touched.dart" in err
    assert not (root / _EVIDENCE).exists()


# Verifies: REQ-d00322-A, REQ-d00322-E, REQ-d00322-F
def test_a_snapshot_is_written_and_a_second_write_is_byte_identical(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path, monkeypatch)
    assert main(["test"]) == 0

    assert main(["evidence", "write", "--fact", "backends=vm"]) == 0

    first = _snapshot_bytes(root)
    assert (root / _EVIDENCE / "timings.jsonl").is_file()
    report = first["TRACEABILITY.md"].decode("utf-8")
    assert "<details><summary>Evidence</summary>" in report
    assert f"{_SHARED_FILE}:3" in report
    assert str(root) not in report
    assert b'"backends"' in first["snapshot.json"]
    # The snapshot directory is not an input of the target, so the results
    # stay fresh after it is written, and the next write reads the same tree.
    assert main(["evidence", "write", "--fact", "backends=vm"]) == 0
    assert _snapshot_bytes(root) == first


# Verifies: REQ-d00322-F
def test_the_written_report_presents_the_snapshots_run_as_its_own(tmp_path, monkeypatch, capsys):
    """The snapshot's results are the run the report describes, not a baseline."""
    root = _project(tmp_path, monkeypatch)
    assert main(["test"]) == 0

    assert main(["evidence", "write"]) == 0

    report = (root / _EVIDENCE / "TRACEABILITY.md").read_text(encoding="utf-8")
    assert "(baseline)" not in report
    assert "carried from a prior run" not in report
    assert "> Legend:" not in report


# Verifies: REQ-d00322-F, REQ-d00322-G
def test_the_written_report_keeps_its_table_whole(tmp_path, monkeypatch, capsys):
    """Every row sits in one table, and the evidence follows it."""
    root = _project(tmp_path, monkeypatch)
    assert main(["test"]) == 0

    assert main(["evidence", "write"]) == 0

    lines = (root / _EVIDENCE / "TRACEABILITY.md").read_text(encoding="utf-8").splitlines()
    table = [i for i, line in enumerate(lines) if line.startswith("|")]
    assert table == list(range(table[0], table[-1] + 1))
    assert lines.index("## Evidence") > table[-1]


# Verifies: REQ-d00322-D
def test_writing_over_uncommitted_work_names_it_and_still_writes(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path, monkeypatch)
    assert main(["test"]) == 0
    (root / "notes.txt").write_text("draft\n", encoding="utf-8")
    capsys.readouterr()

    assert main(["evidence", "write"]) == 0

    err = capsys.readouterr().err
    assert "notes.txt" in err
    assert (root / _EVIDENCE / "results.jsonl").is_file()


# Verifies: REQ-d00322-H, REQ-d00322-I
def test_verify_agrees_with_the_snapshot_it_was_written_from(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path, monkeypatch)
    assert main(["test"]) == 0
    assert main(["evidence", "write", "--fact", "backends=vm"]) == 0
    _commit(root)
    capsys.readouterr()

    assert main(["evidence", "verify", "--fact", "backends=vm"]) == 0

    assert "matches the current results" in capsys.readouterr().out


# Verifies: REQ-d00322-H, REQ-d00322-I
def test_verify_with_run_reports_an_outcome_that_changed(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path, monkeypatch)
    assert main(["test"]) == 0
    assert main(["evidence", "write", "--fact", "backends=vm"]) == 0
    _commit(root)
    monkeypatch.setenv("STUB_OUTCOME", "failure")
    capsys.readouterr()

    assert main(["evidence", "verify", "--run", "--fact", "backends=vm"]) == 1

    out = capsys.readouterr().out
    assert f"outcome: target flutter: {_SHARED_FILE}:3" in out
    assert "passed -> failed" in out
    # The report the new results render differs as well.
    assert "report:" in out


# Verifies: REQ-d00322-H, REQ-d00322-I
def test_verify_reports_a_declared_fact_that_differs(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path, monkeypatch)
    assert main(["test"]) == 0
    assert main(["evidence", "write", "--fact", "backends=vm"]) == 0
    _commit(root)
    capsys.readouterr()

    assert main(["evidence", "verify", "--fact", "backends=other"]) == 1

    out = capsys.readouterr().out
    assert "fact: backends: 'vm' -> 'other'" in out
    assert "outcome:" not in out


# Verifies: REQ-d00322-H, REQ-d00322-I
def test_verify_reports_a_tree_that_moved_on(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path, monkeypatch)
    assert main(["test"]) == 0
    assert main(["evidence", "write"]) == 0
    _commit(root)
    # Not an input of the target, so its results stay fresh; but it is part
    # of the tree the snapshot describes.
    (root / "README.md").write_text("# Project, edited\n", encoding="utf-8")
    capsys.readouterr()

    assert main(["evidence", "verify"]) == 1

    out = capsys.readouterr().out
    assert "tree: the snapshot describes tree" in out


# Verifies: REQ-d00322-A
def test_a_target_another_job_ran_is_written_but_not_executed(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path, monkeypatch, extra_targets=_COPIED_TARGET)
    assert main(["fingerprint", "start", "copied"]) == 0
    folder = Path(capsys.readouterr().out.strip())
    stream = _machine_run(root, _RUNNER_A, _SHARED_FILE, "success", 1)
    (folder / "machine.jsonl").write_text(stream + "\n", encoding="utf-8")
    assert main(["fingerprint", "finish", "copied"]) == 0

    assert main(["evidence", "write", "--targets", "copied"]) == 0
    results = (root / _EVIDENCE / "results.jsonl").read_text(encoding="utf-8")
    assert '"target":"copied"' in results

    capsys.readouterr()
    assert main(["evidence", "verify", "--run", "--targets", "copied"]) == 2
    assert "command" in capsys.readouterr().err


# Verifies: REQ-d00322-H
@pytest.mark.parametrize("missing", ["results.jsonl", "snapshot.json"])
def test_verify_refuses_a_snapshot_missing_a_compared_file(tmp_path, monkeypatch, capsys, missing):
    root = _project(tmp_path, monkeypatch)
    assert main(["test"]) == 0
    assert main(["evidence", "write"]) == 0
    (root / _EVIDENCE / missing).unlink()
    capsys.readouterr()

    assert main(["evidence", "verify"]) == 2

    assert missing in capsys.readouterr().err


# Verifies: REQ-d00322-E, REQ-d00322-H+I
def test_a_clone_verifies_a_snapshot_written_beside_an_ignored_input(tmp_path, monkeypatch, capsys):
    """A file git ignores is an input of the run that wrote, and absent from a clone."""
    root = _project(tmp_path / "work", monkeypatch)
    (root / ".gitignore").write_text(".results/\ntest/scratch.txt\n", encoding="utf-8")
    _commit(root)
    (root / "test" / "scratch.txt").write_text("local only\n", encoding="utf-8")
    assert main(["test"]) == 0
    assert main(["evidence", "write"]) == 0
    _commit(root)

    clone = tmp_path / "clone"
    subprocess.run([*_GIT, "clone", "-q", str(root), str(clone)], check=True, capture_output=True)
    assert not (clone / "test" / "scratch.txt").exists()
    monkeypatch.chdir(clone)
    assert main(["test"]) == 0
    capsys.readouterr()

    assert main(["evidence", "verify"]) == 0

    assert "matches the current results" in capsys.readouterr().out


# A target whose reporter no parser reads.
_UNKNOWN_REPORTER_TARGET = """
[[scanning.test.targets]]
name = "copied"
reporter = "junit-xmll"
results = "machine.jsonl"

[scanning.test.targets.inputs]
directories = ["test"]
"""


def _copied_run(root: Path, capsys, text: str) -> None:
    """Record a finished run of the `copied` target leaving *text* as its results."""
    assert main(["fingerprint", "start", "copied"]) == 0
    folder = Path(capsys.readouterr().out.strip())
    (folder / "machine.jsonl").write_text(text, encoding="utf-8")
    assert main(["fingerprint", "finish", "copied"]) == 0
    capsys.readouterr()


# The stream of one run, cut off after its test started and before it ended.
def _truncated_stream(root: Path) -> str:
    events = [
        json.loads(line)
        for line in _machine_run(root, _RUNNER_A, _SHARED_FILE, "success", 1).splitlines()
    ]
    cut = next(
        i for i, e in enumerate(events) if e.get("type") == "testDone" and not e.get("hidden")
    )
    return "\n".join(json.dumps(e) for e in events[:cut]) + "\n"


# Verifies: REQ-d00322-B
@pytest.mark.parametrize(
    ("target", "results", "cause"),
    [
        (_UNKNOWN_REPORTER_TARGET, lambda root: "<testsuite/>\n", "junit-xmll"),
        (_COPIED_TARGET, lambda root: "{not json\n", "no JSON events"),
        (_COPIED_TARGET, _truncated_stream, "started and reported no result"),
    ],
    ids=["unknown-reporter", "unparseable", "truncated-stream"],
)
def test_results_the_build_could_not_read_are_refused_by_name(
    tmp_path, monkeypatch, capsys, target, results, cause
):
    root = _project(tmp_path, monkeypatch, extra_targets=target)
    _copied_run(root, capsys, results(root))

    assert main(["evidence", "write", "--targets", "copied"]) == 2

    err = capsys.readouterr().err
    assert "error: target copied results are" in err
    assert cause in err
    assert not (root / _EVIDENCE).exists()
