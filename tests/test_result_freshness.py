"""Tests for the freshness of results by fingerprint, and for target output areas.

Each test creates a small project on disk and records a run of a target. The
test then changes the project. Then the test reads the freshness verdict.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from elspais.commands.health import check_test_results_stale
from elspais.config import validate_config
from elspais.graph.builder import TraceGraph
from elspais.graph.federated import FederatedGraph
from elspais.utilities.fingerprint import (
    RECORD_NAME,
    RunNotStarted,
    finish_run,
    input_files,
    judge,
    read_record,
    start_run,
    target_folder,
)

_JUNIT = '<?xml version="1.0"?><testsuite name="s" tests="0"></testsuite>\n'


def _config(targets: list[dict], **scanning) -> dict:
    return {
        "project": {"name": "fresh", "namespace": "REQ"},
        "scanning": {"test": {"enabled": True, "targets": targets}, **scanning},
    }


def _target(name: str = "unit", **extra) -> dict:
    return {"name": name, "reporter": "junit", "results": "junit.xml", **extra}


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (root / "docs").mkdir()
    (root / "docs" / "guide.md").write_text("# Guide\n", encoding="utf-8")
    return root


def _run(root: Path, config: dict, name: str = "unit") -> Path:
    """Record one complete run of target *name*. The run writes its results."""
    folder = start_run(root, config, name)
    (folder / "junit.xml").write_text(_JUNIT, encoding="utf-8")
    finish_run(root, config, name)
    return folder


def _check(root: Path, config: dict):
    graph = FederatedGraph.from_single(TraceGraph(), config=config, repo_root=root)
    return check_test_results_stale(graph, config)


# Verifies: REQ-d00311-B, REQ-d00311-G
def test_results_whose_inputs_are_unchanged_produce_no_finding(tmp_path):
    root = _project(tmp_path)
    config = _config([_target()])
    _run(root, config)

    check = _check(root, config)

    assert check.passed is True
    assert check.findings == []


# Verifies: REQ-d00311-B, REQ-d00311-G
def test_reused_results_are_fresh_whatever_the_timestamps_say(tmp_path):
    """A rewrite of an input with identical content keeps the results fresh."""
    root = _project(tmp_path)
    config = _config([_target()])
    folder = _run(root, config)
    old = time.time() - 3600
    os.utime(folder / "junit.xml", (old, old))
    source = root / "src" / "a.py"
    source.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    assert _check(root, config).passed is True


# Verifies: REQ-d00311-C, REQ-d00311-E, REQ-d00311-F
def test_a_changed_input_makes_results_stale_and_is_named(tmp_path):
    root = _project(tmp_path)
    config = _config([_target()])
    _run(root, config)
    (root / "src" / "a.py").write_text("x = 2\n", encoding="utf-8")

    check = _check(root, config)

    assert check.passed is False
    assert check.severity == "warning"
    (finding,) = check.findings
    assert "unit" in finding.message
    assert "inputs changed since it ran" in finding.message
    assert "src/a.py" in finding.message
    assert finding.related == ["src/a.py"]


# Verifies: REQ-d00311-C, REQ-d00311-F
def test_an_input_changed_while_the_run_was_going_makes_results_stale(tmp_path):
    root = _project(tmp_path)
    config = _config([_target()])
    folder = start_run(root, config, "unit")
    (folder / "junit.xml").write_text(_JUNIT, encoding="utf-8")
    (root / "src" / "a.py").write_text("x = 2\n", encoding="utf-8")
    finish_run(root, config, "unit")

    (finding,) = _check(root, config).findings

    assert "while it ran" in finding.message
    assert "src/a.py" in finding.message


# Verifies: REQ-d00311-D, REQ-d00311-E
def test_results_with_no_recorded_run_are_stale_and_say_why(tmp_path):
    root = _project(tmp_path)
    config = _config([_target()])
    folder = root / ".results" / "unit"
    folder.mkdir(parents=True)
    (folder / "junit.xml").write_text(_JUNIT, encoding="utf-8")

    (finding,) = _check(root, config).findings

    assert "no fingerprint was recorded" in finding.message


# Verifies: REQ-d00311-A
def test_each_target_is_judged_on_its_own(tmp_path):
    root = _project(tmp_path)
    config = _config([_target("unit"), _target("e2e", inputs={"directories": ["docs"]})])
    _run(root, config, "unit")
    _run(root, config, "e2e")
    (root / "src" / "a.py").write_text("x = 2\n", encoding="utf-8")

    check = _check(root, config)

    assert [f.message.split(":")[0] for f in check.findings] == ["target unit"]


# Verifies: REQ-d00311-A
def test_a_target_with_no_results_on_disk_is_not_judged(tmp_path):
    root = _project(tmp_path)
    config = _config([_target()])

    assert judge(root, config, "unit").state == "absent"
    assert _check(root, config).passed is True


# Verifies: REQ-d00311-H, REQ-d00311-I, REQ-d00312-D
def test_a_run_recorded_from_outside_is_judged_as_one_the_tool_recorded(tmp_path, monkeypatch):
    from elspais.cli import main

    root = _project(tmp_path)
    config = _config([_target()])
    (root / ".elspais.toml").write_text(
        'version = 5\n\n[project]\nname = "fresh"\nnamespace = "REQ"\n\n'
        "[scanning.test]\nenabled = true\n\n"
        '[[scanning.test.targets]]\nname = "unit"\nreporter = "junit"\n'
        'results = "junit.xml"\n',
        encoding="utf-8",
    )
    tool = start_run(root, config, "unit")
    tool_digest = read_record(tool)["digest"]

    (tool / "leftover.xml").write_text(_JUNIT, encoding="utf-8")

    monkeypatch.chdir(root)
    assert main(["fingerprint", "start", "unit"]) == 0
    assert sorted(p.name for p in tool.iterdir()) == [RECORD_NAME]
    (tool / "junit.xml").write_text(_JUNIT, encoding="utf-8")
    assert main(["fingerprint", "finish", "unit"]) == 0

    assert read_record(tool)["digest"] == tool_digest
    assert judge(root, config, "unit").state == "fresh"


# Verifies: REQ-d00312-D, REQ-d00311-D
@pytest.mark.parametrize(
    "finished_before", [False, True], ids=["never-started", "already-finished"]
)
def test_finishing_a_run_no_start_began_is_refused(tmp_path, finished_before):
    """Without a start, results from an earlier run would carry this run's fingerprint."""
    root = _project(tmp_path)
    config = _config([_target()])
    if finished_before:
        _run(root, config)
    else:
        folder = root / ".results" / "unit"
        folder.mkdir(parents=True)
        (folder / "junit.xml").write_text(_JUNIT, encoding="utf-8")

    with pytest.raises(RunNotStarted, match="fingerprint start unit"):
        finish_run(root, config, "unit")


# Verifies: REQ-d00312-D
def test_the_command_refuses_a_finish_no_start_began(tmp_path, monkeypatch, capsys):
    from elspais.cli import main

    root = _project(tmp_path)
    (root / ".elspais.toml").write_text(
        'version = 5\n\n[project]\nname = "fresh"\nnamespace = "REQ"\n\n'
        "[scanning.test]\nenabled = true\n\n"
        '[[scanning.test.targets]]\nname = "unit"\nreporter = "junit"\n'
        'results = "junit.xml"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(root)

    assert main(["fingerprint", "finish", "unit"]) == 1
    assert "fingerprint start unit" in capsys.readouterr().err


# Verifies: REQ-d00311-H
def test_recording_an_unknown_target_is_refused(tmp_path, monkeypatch, capsys):
    from elspais.cli import main

    root = _project(tmp_path)
    (root / ".elspais.toml").write_text(
        'version = 5\n\n[project]\nname = "fresh"\nnamespace = "REQ"\n', encoding="utf-8"
    )
    monkeypatch.chdir(root)

    assert main(["fingerprint", "start", "nope"]) == 2
    assert "no test target named 'nope'" in capsys.readouterr().err


# Verifies: REQ-d00311-J
def test_every_file_is_an_input_by_default(tmp_path):
    root = _project(tmp_path)
    config = _config([_target()])
    _run(root, config)
    (root / "notes.txt").write_text("a file nobody tracks\n", encoding="utf-8")

    verdict = judge(root, config, "unit")

    assert verdict.state == "stale"
    assert verdict.changed == ("notes.txt",)


# Verifies: REQ-d00311-K
def test_an_include_set_limits_the_inputs(tmp_path):
    root = _project(tmp_path)
    config = _config([_target(inputs={"directories": ["src"]})])
    _run(root, config)

    (root / "docs" / "guide.md").write_text("# Changed\n", encoding="utf-8")
    assert judge(root, config, "unit").state == "fresh"

    (root / "src" / "a.py").write_text("x = 2\n", encoding="utf-8")
    assert judge(root, config, "unit").state == "stale"


# Verifies: REQ-d00311-L
@pytest.mark.parametrize(
    "inputs",
    [
        {"skip_dirs": ["docs"]},
        {"skip_files": ["*.md"]},
        {"directories": ["docs"], "skip_files": ["*.md"]},
    ],
    ids=["skip-dir", "skip-file", "exclude-wins-over-include"],
)
def test_an_exclude_set_removes_inputs(tmp_path, inputs):
    root = _project(tmp_path)
    config = _config([_target(inputs=inputs)])
    _run(root, config)

    (root / "docs" / "guide.md").write_text("# Changed\n", encoding="utf-8")

    assert judge(root, config, "unit").state == "fresh"


# Verifies: REQ-d00311-M
def test_the_output_root_and_the_global_skip_list_are_never_inputs(tmp_path):
    root = _project(tmp_path)
    config = _config([_target(), _target("other")], skip=[".cache"])
    _run(root, config)

    other = root / ".results" / "other"
    other.mkdir(parents=True)
    (other / "junit.xml").write_text(_JUNIT, encoding="utf-8")
    (root / ".cache").mkdir()
    (root / ".cache" / "state").write_text("changes every run\n", encoding="utf-8")

    assert judge(root, config, "unit").state == "fresh"


# Verifies: REQ-d00311-M
def test_a_scanning_kind_skip_is_not_an_exclusion_of_inputs(tmp_path):
    """Only the global skip list removes inputs.

    The skip lists of a scanning kind control only what a scan reads.
    """
    root = _project(tmp_path)
    config = _config([_target()], spec={"skip_dirs": ["docs"]})
    before = {p.relative_to(root).as_posix() for p in input_files(root, config, _unit(config))}

    assert "docs/guide.md" in before


def _unit(config: dict):
    return validate_config(config).scanning.test.targets[0]


# Verifies: REQ-d00312-A, REQ-d00312-B
def test_each_target_has_a_folder_under_the_configured_root(tmp_path):
    config = _config(
        [
            {"name": "unit", "reporter": "junit", "results": "out/unit/j.xml"},
            {"name": "e2e", "reporter": "junit", "results": "out/e2e/j.xml"},
        ]
    )
    config["scanning"]["test"]["output_root"] = "out"

    assert target_folder(tmp_path, config, "unit") == (tmp_path / "out" / "unit").resolve()
    assert target_folder(tmp_path, config, "e2e") == (tmp_path / "out" / "e2e").resolve()


# Verifies: REQ-d00312-C
@pytest.mark.parametrize(
    "target",
    [
        {"name": "unit", "reporter": "junit", "results": "../junit.xml"},
        {"name": "unit", "reporter": "junit", "results": "../e2e/junit.xml"},
        {"name": "unit", "coverage": "nested/../../lcov.info"},
        {"name": "unit", "reporter": "junit", "results": "/abs/.results/unit/junit.xml"},
        {"name": "app", "cwd": "app", "coverage": ".."},
    ],
    ids=["above-folder", "another-targets-folder", "climbs-after-descending", "absolute", "cwd"],
)
def test_a_location_outside_the_targets_area_is_refused_naming_the_area(target):
    with pytest.raises(Exception) as caught:
        validate_config(_config([target]))

    assert f'".results/{target["name"]}"' in str(caught.value)


# Verifies: REQ-d00312-A, REQ-d00312-C
def test_paths_name_files_in_the_targets_area_whatever_its_cwd(tmp_path):
    """The results path of a target with a cwd stays relative to its output area."""
    from elspais.graph.factory import build_graph

    root = _project(tmp_path)
    (root / "app").mkdir()
    folder = root / ".results" / "app"
    folder.mkdir(parents=True)
    (folder / "junit.xml").write_text(
        '<?xml version="1.0"?><testsuite name="s" tests="1">'
        '<testcase classname="tests.t" name="test_a" time="0.1"/></testsuite>\n',
        encoding="utf-8",
    )
    config = _config([_target("app", cwd="app", results="junit.xml")])

    graph = build_graph(config=config, repo_root=root, scan_code=False)

    from elspais.graph.GraphNode import NodeKind

    (result,) = graph.iter_by_kind(NodeKind.RESULT)
    assert result.get_field("result_file") == ".results/app/junit.xml"


# Verifies: REQ-d00312-D
def test_a_run_starts_with_an_empty_output_area(tmp_path):
    root = _project(tmp_path)
    config = _config([_target(results="*.xml")])
    folder = _run(root, config)
    (folder / "leftover.xml").write_text(_JUNIT, encoding="utf-8")

    start_run(root, config, "unit")

    assert sorted(p.name for p in folder.iterdir()) == [RECORD_NAME]


# Verifies: REQ-d00312-D, REQ-d00311-B
def test_the_runner_hands_the_command_its_folder_and_records_the_run(tmp_path):
    from elspais.commands.test_runner import run_configured_targets

    root = _project(tmp_path)
    config = _config(
        [
            _target(
                command=(
                    'python3 -c "import os,pathlib; '
                    "pathlib.Path(os.environ['ELSPAIS_TARGET_OUTPUT'], 'junit.xml')"
                    ".write_text('<testsuite/>')\""
                )
            )
        ]
    )
    stale = root / ".results" / "unit"
    stale.mkdir(parents=True)
    (stale / "old.xml").write_text(_JUNIT, encoding="utf-8")

    results, _ = run_configured_targets(validate_config(config), root)

    assert results[0].returncode == 0
    assert sorted(p.name for p in stale.iterdir()) == sorted([RECORD_NAME, "junit.xml"])
    assert judge(root, config, "unit").state == "fresh"
