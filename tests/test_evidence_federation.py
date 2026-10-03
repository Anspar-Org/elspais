# Verifies: REQ-d00249-L, REQ-d00322-K+L
"""Federation members: running their targets, and reading their snapshots.

Each test builds two git repositories side by side: ``root``, which declares
``lib`` as an associate under the namespace ``LIB``, and ``lib``. Both hold
a ``flutter`` target whose command runs a stub writing a ``flutter-machine``
stream into the target's output area, and both name an *Evidence Snapshot*
directory.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from elspais.cli import main
from elspais.commands.health import check_test_results_stale
from elspais.config import get_config
from elspais.graph import NodeKind
from elspais.graph.factory import build_graph
from tests.core.test_target_ingestion import (
    _RUNNER_A,
    _RUNNER_A_DART,
    _SHARED_CONFIG,
    _SHARED_DART,
    _SHARED_FILE,
    _SHARED_SPEC,
)
from tests.test_evidence_cmd import _EVIDENCE, _GIT, _RUN_TARGET, _STUB, _TARGET

_ASSOCIATE = '\n[associates.lib]\npath = "../lib"\nnamespace = "LIB"\n'


def _git(root: Path, *args: str) -> None:
    subprocess.run([*_GIT, *args], cwd=root, check=True, capture_output=True)


def _repo(root: Path, *, name: str, namespace: str, extra: str = "") -> Path:
    config = (
        _SHARED_CONFIG.replace(_TARGET, _RUN_TARGET)
        .replace('name = "shared"', f'name = "{name}"')
        .replace('namespace = "REQ"', f'namespace = "{namespace}"')
        .replace(
            'file_patterns = ["*.dart"]\n',
            f'file_patterns = ["*.dart"]\nevidence = "{_EVIDENCE}"\n',
        )
    ) + extra
    files = {
        ".elspais.toml": config,
        ".gitignore": ".results/\n",
        "README.md": f"# {name}\n",
        "spec/requirements.md": _SHARED_SPEC.replace("REQ-", f"{namespace}-"),
        "tools/stub.py": _STUB,
        _SHARED_FILE: _SHARED_DART.replace("REQ-", f"{namespace}-"),
        _RUNNER_A: _RUNNER_A_DART,
    }
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    return root


def _federation(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    lib = _repo(tmp_path / "lib", name="lib", namespace="LIB")
    root = _repo(tmp_path / "root", name="root", namespace="REQ", extra=_ASSOCIATE)
    monkeypatch.delenv("STUB_OUTCOME", raising=False)
    monkeypatch.delenv("STUB_TOUCH", raising=False)
    monkeypatch.chdir(root)
    return root, lib


def _area(repo: Path) -> Path:
    return repo / ".results" / "flutter"


def _lib_snapshot_without_results(tmp_path: Path, monkeypatch, lib: Path) -> None:
    """Write and commit lib's snapshot, then move its own results away."""
    monkeypatch.chdir(lib)
    assert main(["test"]) == 0
    assert main(["evidence", "write"]) == 0
    _git(lib, "add", "-A")
    _git(lib, "commit", "-q", "-m", "evidence")
    (lib / ".results").rename(tmp_path / "lib-results-moved-aside")


def _lib_results(graph) -> list:
    return list(graph.nodes_by_kind(NodeKind.RESULT, namespace="LIB"))


# Verifies: REQ-d00249-L
def test_a_member_target_named_by_namespace_runs_in_the_member(tmp_path, monkeypatch, capsys):
    root, lib = _federation(tmp_path, monkeypatch)

    assert main(["test", "--targets", "LIB:flutter"]) == 0

    assert (_area(lib) / "machine.jsonl").is_file()
    # The stub writes the paths of the directory it ran in.
    assert str(lib) in (_area(lib) / "machine.jsonl").read_text(encoding="utf-8")
    assert not (root / ".results").exists()


# Verifies: REQ-d00249-L
def test_a_bare_run_never_reaches_a_member(tmp_path, monkeypatch):
    root, lib = _federation(tmp_path, monkeypatch)

    assert main(["test"]) == 0

    assert (_area(root) / "machine.jsonl").is_file()
    assert not (lib / ".results").exists()


# Verifies: REQ-d00249-L
def test_a_selection_naming_root_and_member_runs_each_in_its_own_repository(tmp_path, monkeypatch):
    root, lib = _federation(tmp_path, monkeypatch)

    assert main(["test", "--targets", "flutter", "--targets", "LIB:flutter"]) == 0

    assert str(root) in (_area(root) / "machine.jsonl").read_text(encoding="utf-8")
    assert str(lib) in (_area(lib) / "machine.jsonl").read_text(encoding="utf-8")


# Verifies: REQ-d00249-L
def test_checks_run_tests_runs_a_named_member_target_in_the_member(tmp_path, monkeypatch, capsys):
    root, lib = _federation(tmp_path, monkeypatch)

    capsys.readouterr()

    # The exit code also reflects checks this fixture does not satisfy.
    main(["checks", "--run-tests", "--targets", "LIB:flutter", "--format", "json"])

    assert (_area(lib) / "machine.jsonl").is_file()
    assert not (root / ".results").exists()
    checks = {c["name"]: c for c in json.loads(capsys.readouterr().out)["checks"]}
    # The member's results were read: the run expected them and none is missing.
    assert checks["tests.ingestion_fault"]["passed"]
    assert {f["repo"] for f in checks["tests.not_run"]["findings"]} == {"root"}


# Verifies: REQ-d00249-L
def test_an_unknown_namespace_is_refused(tmp_path, monkeypatch, capsys):
    root, lib = _federation(tmp_path, monkeypatch)

    assert main(["test", "--targets", "NOPE:flutter"]) == 2

    err = capsys.readouterr().err
    assert "unknown --targets namespace: NOPE" in err
    assert "LIB" in err
    assert not (lib / ".results").exists()
    assert not (root / ".results").exists()


# Verifies: REQ-d00249-L
def test_a_target_the_member_does_not_declare_is_refused_naming_the_member(
    tmp_path, monkeypatch, capsys
):
    root, lib = _federation(tmp_path, monkeypatch)

    assert main(["test", "--targets", "LIB:nope"]) == 2

    assert "unknown --targets (member LIB): nope" in capsys.readouterr().err
    assert not (lib / ".results").exists()


# Verifies: REQ-d00322-L
def test_a_member_without_results_reads_its_snapshot_carried(tmp_path, monkeypatch):
    root, lib = _federation(tmp_path, monkeypatch)
    _lib_snapshot_without_results(tmp_path, monkeypatch, lib)
    monkeypatch.chdir(root)

    graph = build_graph(repo_root=root)

    results = _lib_results(graph)
    assert results
    assert all(r.get_field("carried") for r in results)
    assert all(r.get_field("result_file") == f"{_EVIDENCE}/results.jsonl" for r in results)
    assert {r.get_field("status") for r in results} == {"passed"}


# Verifies: REQ-d00322-L
def test_a_member_with_results_of_its_own_does_not_read_its_snapshot(tmp_path, monkeypatch):
    root, lib = _federation(tmp_path, monkeypatch)
    monkeypatch.chdir(lib)
    assert main(["test"]) == 0
    assert main(["evidence", "write"]) == 0
    monkeypatch.chdir(root)

    graph = build_graph(repo_root=root)

    results = _lib_results(graph)
    assert len(results) == 1
    assert not results[0].get_field("result_file", "").startswith(_EVIDENCE)


# Verifies: REQ-d00322-K
def test_a_member_snapshot_of_its_current_tree_reads_as_fresh(tmp_path, monkeypatch):
    root, lib = _federation(tmp_path, monkeypatch)
    _lib_snapshot_without_results(tmp_path, monkeypatch, lib)
    monkeypatch.chdir(root)

    check = check_test_results_stale(build_graph(repo_root=root), get_config(None, root))

    assert check.passed
    assert check.message == "Test results are fresh"


# Verifies: REQ-d00322-K
def test_a_member_snapshot_of_another_tree_is_reported_stale(tmp_path, monkeypatch):
    root, lib = _federation(tmp_path, monkeypatch)
    _lib_snapshot_without_results(tmp_path, monkeypatch, lib)
    # The member's tree moves on after its snapshot was written.
    (lib / "README.md").write_text("# lib, edited\n", encoding="utf-8")
    monkeypatch.chdir(root)

    check = check_test_results_stale(build_graph(repo_root=root), get_config(None, root))

    assert not check.passed
    (finding,) = check.findings
    assert finding.repo == "lib"
    assert finding.file_path == f"{_EVIDENCE}/snapshot.json"
    assert f"Evidence Snapshot {_EVIDENCE} describes another tree" in finding.message
    # A bare write from the root reaches only the root, so the remedy names
    # the member's targets by namespace.
    assert "`elspais evidence write --targets LIB:flutter`" in finding.message


# Verifies: REQ-d00322-K
def test_a_root_snapshot_of_another_tree_names_the_bare_write(tmp_path, monkeypatch):
    root, lib = _federation(tmp_path, monkeypatch)
    assert main(["test"]) == 0
    assert main(["evidence", "write"]) == 0
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "evidence")
    (root / ".results").rename(tmp_path / "root-results-moved-aside")
    (root / "README.md").write_text("# root, edited\n", encoding="utf-8")

    check = check_test_results_stale(build_graph(repo_root=root), get_config(None, root))

    (finding,) = check.findings
    assert finding.repo == "root"
    assert "`elspais evidence write`" in finding.message


# Verifies: REQ-d00322-K+L
def test_a_member_snapshot_holding_no_result_is_still_judged(tmp_path, monkeypatch, capsys):
    """A snapshot whose selected target produced no result is still its source."""
    root, lib = _federation(tmp_path, monkeypatch)
    monkeypatch.chdir(lib)
    assert main(["fingerprint", "start", "flutter"]) == 0
    folder = Path(capsys.readouterr().out.strip())
    (folder / "machine.jsonl").write_text("", encoding="utf-8")
    assert main(["fingerprint", "finish", "flutter"]) == 0
    assert main(["evidence", "write"]) == 0
    assert (lib / _EVIDENCE / "results.jsonl").read_text(encoding="utf-8") == ""
    _git(lib, "add", "-A")
    _git(lib, "commit", "-q", "-m", "evidence")
    (lib / ".results").rename(tmp_path / "lib-results-moved-aside")
    (lib / "README.md").write_text("# lib, edited\n", encoding="utf-8")
    monkeypatch.chdir(root)

    check = check_test_results_stale(build_graph(repo_root=root), get_config(None, root))

    assert not check.passed
    (finding,) = check.findings
    assert finding.repo == "lib"
    assert f"Evidence Snapshot {_EVIDENCE} describes another tree" in finding.message


# Verifies: REQ-d00322-B, REQ-d00249-L
def test_a_member_target_is_refused_by_the_name_that_selected_it(tmp_path, monkeypatch, capsys):
    root, lib = _federation(tmp_path, monkeypatch)

    assert main(["evidence", "write", "--targets", "LIB:flutter"]) == 2

    assert "error: target LIB:flutter results are absent" in capsys.readouterr().err
    assert not (lib / _EVIDENCE).exists()


# Verifies: REQ-d00322-H, REQ-d00249-L
def test_a_member_difference_names_the_target_by_namespace(tmp_path, monkeypatch, capsys):
    root, lib = _federation(tmp_path, monkeypatch)
    assert main(["test", "--targets", "LIB:flutter"]) == 0
    assert main(["evidence", "write", "--targets", "LIB:flutter"]) == 0
    _git(lib, "add", "-A")
    _git(lib, "commit", "-q", "-m", "evidence")
    monkeypatch.setenv("STUB_OUTCOME", "failure")
    capsys.readouterr()

    assert main(["evidence", "verify", "--run", "--targets", "LIB:flutter"]) == 1

    out = capsys.readouterr().out
    assert "outcome: target LIB:flutter:" in out


# Verifies: REQ-d00322-L, REQ-d00249-L
def test_a_member_snapshot_is_written_and_verified_from_the_root(tmp_path, monkeypatch, capsys):
    root, lib = _federation(tmp_path, monkeypatch)
    assert main(["test", "--targets", "LIB:flutter"]) == 0

    assert main(["evidence", "write", "--targets", "LIB:flutter"]) == 0

    assert (lib / _EVIDENCE / "results.jsonl").is_file()
    assert not (root / _EVIDENCE).exists()
    _git(lib, "add", "-A")
    _git(lib, "commit", "-q", "-m", "evidence")
    capsys.readouterr()
    assert main(["evidence", "verify", "--run", "--targets", "LIB:flutter"]) == 0
    assert "matches the current results" in capsys.readouterr().out


# Verifies: REQ-d00322-L
def test_a_snapshot_selection_spanning_two_repositories_is_refused(tmp_path, monkeypatch, capsys):
    root, lib = _federation(tmp_path, monkeypatch)

    assert main(["evidence", "write", "--targets", "flutter", "--targets", "LIB:flutter"]) == 2

    assert "describes one repository" in capsys.readouterr().err
    assert not (root / _EVIDENCE).exists()
    assert not (lib / _EVIDENCE).exists()


# Verifies: REQ-d00322-E+F
@pytest.mark.parametrize("lib_snapshot", [False, True])
def test_the_root_snapshot_of_a_federation_is_byte_stable(tmp_path, monkeypatch, lib_snapshot):
    root, lib = _federation(tmp_path, monkeypatch)
    if lib_snapshot:
        _lib_snapshot_without_results(tmp_path, monkeypatch, lib)
        monkeypatch.chdir(root)
    assert main(["test"]) == 0

    assert main(["evidence", "write"]) == 0
    compared = ("results.jsonl", "snapshot.json", "TRACEABILITY.md")
    first = {name: (root / _EVIDENCE / name).read_bytes() for name in compared}
    assert main(["evidence", "write"]) == 0

    assert {name: (root / _EVIDENCE / name).read_bytes() for name in compared} == first
    report = first["TRACEABILITY.md"].decode("utf-8")
    assert str(tmp_path) not in report
