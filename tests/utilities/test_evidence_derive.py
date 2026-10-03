# Verifies: REQ-d00322-A, REQ-d00322-C, REQ-d00322-D, REQ-d00322-E, REQ-d00322-M
"""An *Evidence Snapshot* is derived from the RESULT nodes of a built graph.

Each test builds a git repository holding a project, writes a target's own
results into its output area, builds the graph, and derives the snapshot.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from elspais.config import get_config, validate_config
from elspais.utilities.evidence import (
    SnapshotRefused,
    derive_snapshot,
    load_snapshot,
    render_files,
    tree_digest,
)
from elspais.utilities.fingerprint import compute_manifest, manifest_digest
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

# A second target that selects the same tests and never produces a result.
_EMPTY_TARGET = """
[[scanning.test.targets]]
name = "empty"
reporter = "flutter-machine"
results = "machine.jsonl"
match = "source"
"""


def _git(root: Path, *args: str) -> None:
    subprocess.run([*_GIT, *args], cwd=root, check=True, capture_output=True)


def _write(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _project(root: Path, *, extra_config: str = "") -> Path:
    config = _SHARED_CONFIG.replace(
        'file_patterns = ["*.dart"]\n',
        f'file_patterns = ["*.dart"]\nevidence = "{_EVIDENCE}"\n',
    )
    assert config != _SHARED_CONFIG
    _write(
        root,
        {
            ".elspais.toml": config + extra_config,
            ".gitignore": ".results/\n",
            "spec/requirements.md": _SHARED_SPEC,
            _SHARED_FILE: _SHARED_DART,
            _RUNNER_A: _RUNNER_A_DART,
            _RUNNER_B: _RUNNER_B_DART,
        },
    )
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    return root


def _own_results(root: Path, *runs: str, target: str = "flutter") -> None:
    out = root / ".results" / target
    out.mkdir(parents=True, exist_ok=True)
    (out / "machine.jsonl").write_text("\n".join(runs) + "\n", encoding="utf-8")


def _derive(root: Path, targets: list[str], facts=(), **kwargs):
    from elspais.graph.factory import build_graph

    config = validate_config(get_config(root / ".elspais.toml", start_path=root, quiet=True))
    graph = build_graph(repo_root=root)
    return derive_snapshot(graph, root, config, targets, tuple(facts), "", **kwargs), config


# Verifies: REQ-d00322-A, REQ-d00322-C
def test_each_result_of_a_selected_target_becomes_one_line(tmp_path):
    root = _project(tmp_path)
    _own_results(
        root,
        _machine_run(root, _RUNNER_A, _SHARED_FILE, "success", 1),
        _machine_run(root, _RUNNER_B, _SHARED_FILE, "failure", 3),
    )

    snapshot, _config = _derive(root, ["flutter"])

    assert [(r.file, r.line, r.name, r.runner, r.outcome) for r in snapshot.results] == [
        (_SHARED_FILE, _SHARED_LINE, _SCENARIO, _RUNNER_A, "passed"),
        (_SHARED_FILE, _SHARED_LINE, _SCENARIO, _RUNNER_B, "failed"),
    ]
    assert {r.target for r in snapshot.results} == {"flutter"}
    # No failure message, duration or absolute path reaches the compared file.
    text = render_files(snapshot)["results.jsonl"]
    assert str(tmp_path) not in text
    assert "duration" not in text


# Verifies: REQ-d00322-C
def test_a_runner_is_held_only_where_it_differs_from_the_declaring_file(tmp_path):
    root = _project(tmp_path)
    _own_results(root, _machine_run(root, _SHARED_FILE, _SHARED_FILE, "success", 1))

    snapshot, _config = _derive(root, ["flutter"])

    assert [r.runner for r in snapshot.results] == [None]


# Verifies: REQ-d00322-C
@pytest.mark.parametrize(
    "result, outcome",
    [("success", "passed"), ("failure", "failed"), ("error", "failed")],
    ids=["passed", "failed", "error-reads-failed"],
)
def test_an_outcome_is_passed_failed_or_skipped(tmp_path, result, outcome):
    root = _project(tmp_path)
    _own_results(root, _machine_run(root, _RUNNER_A, _SHARED_FILE, result, 1))

    snapshot, _config = _derive(root, ["flutter"])

    assert [r.outcome for r in snapshot.results] == [outcome]
    assert [r.skip_reason for r in snapshot.results] == [None]


_JUNIT_CONFIG = """\
version = 5

[project]
name = "py"
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
directories = ["tests"]
file_patterns = ["test_*.py"]
evidence = "test-evidence"

[[scanning.test.targets]]
name = "unit"
reporter = "junit"
results = "junit.xml"

[rules.format]
require_hash = false
require_assertions = false
require_status = false
"""

_PY_TEST = """\
# Verifies: REQ-d00001-A
def test_pays():
    assert True


# Verifies: REQ-d00001-A
def test_refunds():
    assert True
"""

_JUNIT = """\
<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="pays" tests="2">
  <testcase classname="tests.test_pays" name="test_pays" time="0.5">
    <failure message="assert False">Traceback at /home/someone/x.py</failure>
  </testcase>
  <testcase classname="tests.test_pays" name="test_refunds" time="0.1">
    <skipped message="needs postgres"/>
  </testcase>
</testsuite>
"""


def _junit_project(root: Path) -> Path:
    _write(
        root,
        {
            ".elspais.toml": _JUNIT_CONFIG,
            ".gitignore": ".results/\n",
            "spec/requirements.md": _SHARED_SPEC,
            "tests/test_pays.py": _PY_TEST,
        },
    )
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    out = root / ".results" / "unit"
    out.mkdir(parents=True)
    (out / "junit.xml").write_text(_JUNIT, encoding="utf-8")
    return root


# Verifies: REQ-d00322-C
def test_a_result_bound_by_its_test_id_is_placed_at_its_test(tmp_path):
    """A junit result names its test by id; its line is the test's own."""
    root = _junit_project(tmp_path)

    snapshot, _config = _derive(root, ["unit"])

    assert [(r.file, r.line, r.name, r.outcome) for r in snapshot.results] == [
        ("tests/test_pays.py", 2, "test_pays", "failed"),
        ("tests/test_pays.py", 7, "test_refunds", "skipped"),
    ]
    # A failure message varies between runs; it is never held.
    assert "assert False" not in render_files(snapshot)["results.jsonl"]


# Verifies: REQ-d00322-C
def test_a_skipped_result_keeps_its_reason(tmp_path):
    root = _junit_project(tmp_path)

    snapshot, _config = _derive(root, ["unit"])

    assert [r.skip_reason for r in snapshot.results] == [None, "needs postgres"]


# Verifies: REQ-d00322-D
def test_a_selected_target_with_no_results_is_still_held(tmp_path):
    """Review Focus 1: a target whose run produced nothing is held, with no lines."""
    root = _project(tmp_path, extra_config=_EMPTY_TARGET)
    _own_results(root, _machine_run(root, _RUNNER_A, _SHARED_FILE, "success", 1))
    _own_results(root, "", target="empty")

    snapshot, config = _derive(root, ["empty", "flutter"])

    by_name = {t.name: t for t in config.scanning.test.targets}
    tracked = tree_digest(root, exclude=_EVIDENCE).paths
    assert snapshot.targets == tuple(
        (
            name,
            manifest_digest(
                {
                    path: digest
                    for path, digest in compute_manifest(root, config, by_name[name]).items()
                    if path in tracked
                }
            ),
        )
        for name in ("empty", "flutter")
    )
    assert {r.target for r in snapshot.results} == {"flutter"}


# Verifies: REQ-d00322-D+E
def test_a_target_digest_covers_only_the_files_the_tree_digest_covers(tmp_path):
    """A file git does not track is absent from a checkout of the commit.

    It is an input of the target on the machine that ran it, and nowhere
    else, so it never reaches the snapshot's digest of the target's inputs.
    """
    root = _project(tmp_path)
    (root / ".gitignore").write_text(".results/\nscratch/\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "ignore scratch")
    _own_results(root, _machine_run(root, _RUNNER_A, _SHARED_FILE, "success", 1))
    before, _config = _derive(root, ["flutter"])

    (root / "scratch").mkdir()
    (root / "scratch" / "cache.txt").write_text("local\n", encoding="utf-8")
    (root / "untracked.txt").write_text("loose\n", encoding="utf-8")
    after, _config = _derive(root, ["flutter"])

    assert after.targets == before.targets
    # A tracked input still moves the digest.
    (root / _RUNNER_A).write_text(_RUNNER_A_DART + "// edited\n", encoding="utf-8")
    edited, _config = _derive(root, ["flutter"])
    assert edited.targets != before.targets


# Verifies: REQ-d00322-A
def test_a_target_not_selected_contributes_nothing(tmp_path):
    root = _project(tmp_path, extra_config=_EMPTY_TARGET)
    _own_results(root, _machine_run(root, _RUNNER_A, _SHARED_FILE, "success", 1))

    snapshot, _config = _derive(root, ["empty"])

    assert snapshot.results == ()
    assert [name for name, _digest in snapshot.targets] == ["empty"]


# Verifies: REQ-d00322-D
def test_the_snapshot_names_its_tree_and_the_facts_declared(tmp_path):
    root = _project(tmp_path)
    _own_results(root, _machine_run(root, _RUNNER_A, _SHARED_FILE, "success", 1))

    snapshot, _config = _derive(root, ["flutter"], facts=[("flutter", "3.44.7"), ("b", "vm")])

    assert snapshot.tree == tree_digest(root, exclude=_EVIDENCE).digest
    assert snapshot.facts == (("b", "vm"), ("flutter", "3.44.7"))


# Verifies: REQ-d00322-D
def test_a_snapshot_written_over_uncommitted_work_names_another_tree(tmp_path):
    """Review Focus 3: the digest covers the working content, not the commit."""
    root = _project(tmp_path)
    _own_results(root, _machine_run(root, _RUNNER_A, _SHARED_FILE, "success", 1))
    committed, _config = _derive(root, ["flutter"])

    (root / _RUNNER_A).write_text(_RUNNER_A_DART + "// edited\n", encoding="utf-8")
    edited = tree_digest(root, exclude=_EVIDENCE)
    current, _config = _derive(root, ["flutter"], tree=edited)

    assert edited.uncommitted == (_RUNNER_A,)
    assert current.tree == edited.digest != committed.tree


# Verifies: REQ-d00322-E
def test_two_runs_of_one_tree_with_the_same_outcomes_derive_identical_bytes(tmp_path):
    root = _project(tmp_path)
    runs = (
        _machine_run(root, _RUNNER_A, _SHARED_FILE, "success", 1),
        _machine_run(root, _RUNNER_B, _SHARED_FILE, "success", 3),
    )
    _own_results(root, *runs)
    first, _config = _derive(root, ["flutter"])
    # The second run reports in another order, with other times.
    _own_results(root, *reversed(runs))
    second, _config = _derive(root, ["flutter"])

    a, b = render_files(first), render_files(second)
    assert {k: v for k, v in a.items() if k != "timings.jsonl"} == {
        k: v for k, v in b.items() if k != "timings.jsonl"
    }


# Verifies: REQ-d00322-M
def test_each_result_keeps_its_duration_and_output_beside_the_snapshot(tmp_path):
    root = _project(tmp_path)
    run = _machine_run(root, _RUNNER_A, _SHARED_FILE, "success", 1).split("\n")
    start, done = json.loads(run[1]), json.loads(run[2])
    start["time"], done["time"] = 100, 1600
    run[1], run[2] = json.dumps(start), json.dumps(done)
    run.insert(2, json.dumps({"type": "print", "testID": 2, "message": "ratio 0.9x"}))
    _own_results(root, "\n".join(run))

    snapshot, _config = _derive(root, ["flutter"])

    assert [(t.duration, t.output) for t in snapshot.timings] == [(1.5, "ratio 0.9x")]
    assert "ratio" not in render_files(snapshot)["results.jsonl"]


# Verifies: REQ-d00322-C
def test_a_derived_snapshot_reads_back_and_rebinds_its_results(tmp_path):
    """The place a line holds is the bound test's own, so a read-back binds it."""
    from elspais.graph.factory import build_graph
    from elspais.graph.GraphNode import NodeKind

    root = _project(tmp_path)
    _own_results(
        root,
        _machine_run(root, _RUNNER_A, _SHARED_FILE, "success", 1),
        _machine_run(root, _RUNNER_B, _SHARED_FILE, "failure", 3),
    )
    snapshot, _config = _derive(root, ["flutter"])
    _write(root, {f"{_EVIDENCE}/{name}": text for name, text in render_files(snapshot).items()})

    graph = build_graph(repo_root=root, evidence_only=True)
    results = list(graph.iter_by_kind(NodeKind.RESULT))
    assert len(results) == 2
    assert {r.get_field("match_scope") for r in results} == {"test"}
    assert load_snapshot(root / _EVIDENCE).results == snapshot.results


# Verifies: REQ-d00322-C, REQ-d00322-E
def test_a_result_that_binds_to_no_test_is_refused(tmp_path):
    root = _project(tmp_path)
    run = _machine_run(root, _RUNNER_A, _SHARED_FILE, "success", 1).split("\n")
    start = json.loads(run[1])
    start["test"]["line"], start["test"]["root_line"] = 7, 9
    run[1] = json.dumps(start)
    _own_results(root, "\n".join(run))

    with pytest.raises(SnapshotRefused) as refused:
        _derive(root, ["flutter"])

    (reason,) = refused.value.reasons
    assert "target flutter" in reason
    assert f"{_SHARED_FILE}:7" in reason
    assert "binds to no single test" in reason


# Verifies: REQ-d00322-C, REQ-d00322-E
def test_a_runner_outside_the_repository_is_refused(tmp_path):
    """The test binds, but the file that executed it holds a path from one machine."""
    root = _project(tmp_path / "repo")
    elsewhere = tmp_path / "elsewhere" / _RUNNER_A
    run = _machine_run(root, _RUNNER_A, _SHARED_FILE, "success", 1).split("\n")
    suite = json.loads(run[0])
    suite["suite"]["path"] = str(elsewhere)
    run[0] = json.dumps(suite)
    _own_results(root, "\n".join(run))

    with pytest.raises(SnapshotRefused) as refused:
        _derive(root, ["flutter"])

    (reason,) = refused.value.reasons
    assert f"target flutter: {_SHARED_FILE}:{_SHARED_LINE}" in reason
    assert "lies outside the repository" in reason


def _read_back(root: Path, snapshot) -> list:
    from elspais.graph.factory import build_graph
    from elspais.graph.GraphNode import NodeKind

    _write(root, {f"{_EVIDENCE}/{name}": text for name, text in render_files(snapshot).items()})
    return list(build_graph(repo_root=root, evidence_only=True).iter_by_kind(NodeKind.RESULT))


# Verifies: REQ-d00322-C
def test_a_result_bound_by_its_test_id_rebinds_from_the_snapshot(tmp_path):
    """A junit result names its test by id; read back, it binds by the test's place."""
    root = _junit_project(tmp_path)
    snapshot, _config = _derive(root, ["unit"])

    results = _read_back(root, snapshot)

    assert len(results) == 2
    assert {r.get_field("match_scope") for r in results} == {"test"}
    assert {p.id for r in results for p in r.iter_parents()} == {
        "test:tests/test_pays.py::test_pays",
        "test:tests/test_pays.py::test_refunds",
    }


# Verifies: REQ-d00322-C
def test_a_result_bound_by_its_root_line_is_placed_at_its_test(tmp_path):
    """A `testWidgets` result names a framework line; the snapshot holds the test's."""
    root = _project(tmp_path)
    run = _machine_run(root, _RUNNER_B, _SHARED_FILE, "success", 1).split("\n")
    start = json.loads(run[1])
    # The runner's own test, reported at a framework line, with its call site.
    del start["test"]["url"]
    start["test"].update(name="decoy", line=99, root_line=3)
    start["test"]["root_url"] = f"file://{root / _RUNNER_B}"
    run[1] = json.dumps(start)
    _own_results(root, "\n".join(run))

    snapshot, _config = _derive(root, ["flutter"])
    assert [(r.file, r.line, r.runner) for r in snapshot.results] == [(_RUNNER_B, 3, None)]

    results = _read_back(root, snapshot)
    assert [r.get_field("match_scope") for r in results] == ["test"]


# Verifies: REQ-d00322-A
def test_an_unknown_target_is_refused(tmp_path):
    root = _project(tmp_path)

    with pytest.raises(SnapshotRefused, match="'nope'"):
        _derive(root, ["nope"])
