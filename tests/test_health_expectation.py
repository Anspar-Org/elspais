# Verifies: REQ-d00283-P+Q+R+S+T+U+V, REQ-d00311-N+O
"""A target with no results is judged by what the run executed and expected.

The build records each artifact it did not read as a fact. These tests hold
the health checks to dividing those facts by the question the run asked: a
target the run executed or expected that left nothing is missing results
(`tests.ingestion_fault`); a target nobody ran or asked for is not run
(`tests.not_run`); a target whose run has not recorded its end is in
progress (`tests.run_in_progress`) and is judged in no other way.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from elspais.commands import health
from elspais.commands.health import (
    check_ingestion_faults,
    check_runs_in_progress,
    check_targets_not_run,
    check_test_results_stale,
    run_test_checks,
)
from elspais.graph.builder import TraceGraph, UnreadArtifact
from elspais.graph.federated import FederatedGraph, RepoEntry

# ─────────────────────────────────────────────────────────────────────────────
# In-memory federations: the division alone, over recorded facts
# ─────────────────────────────────────────────────────────────────────────────


def _member(name: str, namespace: str, targets: list[dict]) -> dict:
    return {
        "project": {"name": name, "namespace": namespace},
        "scanning": {"test": {"enabled": True, "targets": targets}},
    }


def _absent(target: str, artifact: str = "results", path: str | None = None) -> UnreadArtifact:
    if path is None:
        path = f".results/{target}/junit.xml" if artifact == "results" else ""
    return UnreadArtifact(target=target, artifact=artifact, path=path, reason="absent")


def _federation(*members: tuple[str, dict, list[UnreadArtifact]]) -> FederatedGraph:
    """A federation whose first member is the root, each graph holding *artifacts*."""
    entries = []
    for name, config, artifacts in members:
        graph = TraceGraph()
        for artifact in artifacts:
            graph.record_unread_artifact(artifact)
        entries.append(
            RepoEntry(name=name, graph=graph, config=config, repo_root=Path("/repo") / name)
        )
    return FederatedGraph(entries)


_FILE_TARGET = {"name": "unit", "reporter": "junit", "results": "junit.xml"}
_OUTPUT_TARGET = {"name": "unit", "reporter": "flutter-machine"}

# The same fact, a target with no results, delivered through each channel.
_CHANNELS = pytest.mark.parametrize(
    "target,artifact",
    [
        (_FILE_TARGET, _absent("unit")),
        (_OUTPUT_TARGET, _absent("unit", path="")),
    ],
    ids=["file", "runner-output"],
)


def _single(target: dict, *artifacts: UnreadArtifact) -> FederatedGraph:
    return _federation(("solo", _member("solo", "REQ", [target]), list(artifacts)))


# Verifies: REQ-d00283-S+T
@_CHANNELS
def test_a_target_neither_executed_nor_expected_is_not_run(target, artifact):
    graph = _single(target, artifact)

    not_run = check_targets_not_run(graph, {})
    faults = check_ingestion_faults(graph, {})

    assert not_run.passed is False
    assert not_run.severity == "info"
    (finding,) = not_run.findings
    assert "target unit" in finding.message
    assert "not run" in finding.message
    assert finding.repo == "solo"
    assert faults.passed is True
    assert faults.findings == []


# Verifies: REQ-d00283-R+T
@_CHANNELS
def test_a_target_the_run_expected_with_no_results_is_missing_results(target, artifact):
    graph = _single(target, artifact)

    faults = check_ingestion_faults(graph, {}, ("unit",))
    not_run = check_targets_not_run(graph, {}, ("unit",))

    assert faults.passed is False
    assert faults.severity == "warning"
    (finding,) = faults.findings
    assert "unit" in finding.message
    assert "executed or expected" in finding.message
    assert finding.file_path == (artifact.path or None)
    assert not_run.passed is True
    assert not_run.findings == []


# Verifies: REQ-d00283-R+S
def test_expecting_one_target_leaves_the_others_not_run():
    other = {"name": "e2e", "reporter": "junit", "results": "junit.xml"}
    graph = _federation(
        ("solo", _member("solo", "REQ", [_FILE_TARGET, other]), [_absent("unit"), _absent("e2e")])
    )

    (missing,) = check_ingestion_faults(graph, {}, ("unit",)).findings
    (not_run,) = check_targets_not_run(graph, {}, ("unit",)).findings

    assert "unit" in missing.message
    assert "target e2e" in not_run.message


# Verifies: REQ-d00283-V
def test_coverage_absent_beside_results_present_is_missing_whatever_was_expected():
    """Results are there, so the target ran; coverage it declares and did not
    leave is missing even though the run neither executed nor expected it."""
    target = {**_FILE_TARGET, "coverage": "coverage.json"}
    graph = _single(target, _absent("unit", "coverage", ".results/unit/coverage.json"))

    faults = check_ingestion_faults(graph, {})
    not_run = check_targets_not_run(graph, {})

    (finding,) = faults.findings
    assert finding.file_path == ".results/unit/coverage.json"
    assert "coverage" in finding.message
    assert not_run.passed is True


# Verifies: REQ-d00283-S+V
def test_coverage_only_target_absent_and_unexpected_is_not_run():
    """A target that reads only coverage has no results to show it ran."""
    target = {"name": "cover", "reporter": "lcov", "coverage": "lcov.info"}
    graph = _single(target, _absent("cover", "coverage", ".results/cover/lcov.info"))

    assert check_ingestion_faults(graph, {}).passed is True
    (finding,) = check_targets_not_run(graph, {}).findings
    assert "target cover" in finding.message

    (expected,) = check_ingestion_faults(graph, {}, ("cover",)).findings
    assert expected.file_path == ".results/cover/lcov.info"


# Verifies: REQ-d00283-R+S+V
def test_a_target_leaving_neither_results_nor_coverage_is_reported_once_per_question():
    target = {**_FILE_TARGET, "coverage": "coverage.json"}
    artifacts = (_absent("unit"), _absent("unit", "coverage", ".results/unit/coverage.json"))

    graph = _single(target, *artifacts)
    assert len(check_targets_not_run(graph, {}).findings) == 1
    assert check_ingestion_faults(graph, {}).passed is True

    expected = check_ingestion_faults(graph, {}, ("unit",))
    assert {f.file_path for f in expected.findings} == {
        ".results/unit/junit.xml",
        ".results/unit/coverage.json",
    }
    assert check_targets_not_run(graph, {}, ("unit",)).passed is True


# Verifies: REQ-d00283-U
def test_an_associate_target_sharing_an_expected_root_targets_name_is_not_run():
    """The run expects the root's `unit`. The associate's `unit` is another
    repository's target, which this run never named."""
    graph = _federation(
        ("core", _member("core", "REQ", [_FILE_TARGET]), []),
        ("lib", _member("lib", "LIB", [_FILE_TARGET]), [_absent("unit")]),
    )

    faults = check_ingestion_faults(graph, {}, ("unit",))
    (finding,) = check_targets_not_run(graph, {}, ("unit",)).findings

    assert faults.passed is True
    assert finding.repo == "lib"


# Verifies: REQ-d00283-U
def test_an_associate_whose_name_is_the_roots_display_name_is_still_not_expected():
    """A member is the root by its namespace, not by what it is called. An
    associate declared under the key `app`, in a federation whose root
    project is also called `app`, is still another repository."""
    graph = _federation(
        ("app", _member("app", "REQ", [_FILE_TARGET]), []),
        ("app", _member("app-lib", "LIB", [_FILE_TARGET]), [_absent("unit")]),
    )

    assert check_ingestion_faults(graph, {}, ("unit",)).passed is True
    assert len(check_targets_not_run(graph, {}, ("unit",)).findings) == 1


# Verifies: REQ-d00285-E+G
@pytest.mark.parametrize("check_name", ["tests.not_run", "tests.run_in_progress"])
def test_the_severity_of_each_new_check_is_the_one_the_project_configures(check_name):
    from elspais.utilities.findings import REGISTRY

    running = UnreadArtifact(
        target="unit",
        artifact="results",
        path="",
        reason="running",
        started_at="2026-10-01T09:00:00+00:00",
    )
    graph = _single(_FILE_TARGET, _absent("unit") if check_name == "tests.not_run" else running)
    check = check_targets_not_run if check_name == "tests.not_run" else check_runs_in_progress

    assert REGISTRY[check_name].default == "info"
    assert check(graph, {}).severity == "info"

    raised = check(graph, {"rules": {"severity": {check_name: "warning"}}})
    assert raised.severity == "warning"
    assert raised.findings

    silenced = check(graph, {"rules": {"severity": {check_name: "off"}}})
    assert silenced.details.get("skipped") is True
    assert silenced.findings == []


# Verifies: REQ-d00283-P+R
def test_the_test_checks_hand_the_expectation_to_the_checks_that_judge_it():
    graph = _single(_FILE_TARGET, _absent("unit"))

    def by_name(expected):
        return {c.name: c for c in run_test_checks(graph, config={}, expected_targets=expected)}

    unexpected = by_name(())
    expected = by_name(("unit",))

    assert unexpected["tests.ingestion_fault"].passed is True
    assert unexpected["tests.not_run"].passed is False
    assert expected["tests.ingestion_fault"].passed is False
    assert expected["tests.not_run"].passed is True
    assert "tests.run_in_progress" in expected


# ─────────────────────────────────────────────────────────────────────────────
# On-disk projects: the build and the checks together
# ─────────────────────────────────────────────────────────────────────────────

_SPEC = """\
### REQ-p00001: Test Req

**Level**: PRD | **Status**: Active

The system SHALL do something testable.

*End* *Test Req* | **Hash**: ________
"""

_JUNIT = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="tests" tests="1" failures="0">
    <testcase classname="tests.test_thing" name="test_a" time="0.01"/>
  </testsuite>
</testsuites>
"""

_CONFIG = """\
version = 5

[project]
name = "expect"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[scanning.test]
enabled = true

[scanning.test.groups]
uat = "needs a live backend"
device = "needs the device farm"

[[scanning.test.targets]]
name = "unit"
reporter = "junit"
results = "junit.xml"

[[scanning.test.targets]]
name = "journeys"
reporter = "junit"
results = "junit.xml"
coverage = "coverage.json"
groups = ["uat"]
"""


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    (root / "spec").mkdir(parents=True)
    (root / "spec" / "reqs.md").write_text(_SPEC, encoding="utf-8")
    (root / ".elspais.toml").write_text(_CONFIG, encoding="utf-8")
    return root


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _build(root: Path):
    from elspais.graph.factory import build_graph

    return build_graph(config_path=root / ".elspais.toml", repo_root=root, scan_code=False)


def _config(root: Path) -> dict:
    from elspais.config import load_config

    return load_config(root / ".elspais.toml")


# Verifies: REQ-d00283-E+P+R
def test_a_group_named_as_expected_expects_each_of_its_targets(tmp_path):
    from elspais.commands._targets import resolve_expected_targets

    root = _project(tmp_path)
    _write(root, ".results/unit/junit.xml", _JUNIT)
    expected = tuple(sorted(resolve_expected_targets(_config(root), ["uat"])))

    graph = _build(root)
    findings = check_ingestion_faults(graph, {}, expected).findings

    assert expected == ("journeys",)
    assert {f.file_path for f in findings} == {
        ".results/journeys/junit.xml",
        ".results/journeys/coverage.json",
    }


# Verifies: REQ-d00283-R
def test_an_expected_target_whose_results_are_present_reports_nothing(tmp_path):
    root = _project(tmp_path)
    _write(root, ".results/unit/junit.xml", _JUNIT)

    graph = _build(root)
    faults = check_ingestion_faults(graph, {}, ("unit",))
    not_run = check_targets_not_run(graph, {}, ("unit",))

    assert faults.passed is True
    assert [f.message.split(":")[0] for f in not_run.findings] == ["target journeys"]


# Verifies: REQ-d00283-V
def test_results_present_with_coverage_absent_is_missing_coverage_unexpected(tmp_path):
    root = _project(tmp_path)
    _write(root, ".results/journeys/junit.xml", _JUNIT)

    (finding,) = check_ingestion_faults(_build(root), {}).findings

    assert finding.file_path == ".results/journeys/coverage.json"


# Verifies: REQ-d00311-N+O
def test_a_run_in_progress_is_reported_with_its_start_and_judged_no_other_way(tmp_path):
    from elspais.utilities.fingerprint import read_record, start_run

    root = _project(tmp_path)
    config = _config(root)
    folder = start_run(root, config, "unit")
    (folder / "junit.xml").write_text(_JUNIT, encoding="utf-8")
    started_at = read_record(folder)["started_at"]

    graph = _build(root)
    running = check_runs_in_progress(graph, {})
    stale = check_test_results_stale(graph, config)
    faults = check_ingestion_faults(graph, {}, ("unit",))
    not_run = check_targets_not_run(graph, {}, ("unit",))

    assert running.passed is False
    assert running.severity == "info"
    (finding,) = running.findings
    assert "target unit" in finding.message
    assert started_at in finding.message
    assert stale.passed is True
    assert stale.findings == []
    assert faults.passed is True
    assert all("target unit" not in f.message for f in not_run.findings)


# Verifies: REQ-d00311-N
def test_no_run_in_progress_reports_nothing(tmp_path):
    root = _project(tmp_path)
    _write(root, ".results/unit/junit.xml", _JUNIT)

    check = check_runs_in_progress(_build(root), {})

    assert check.passed is True
    assert check.findings == []


# ─────────────────────────────────────────────────────────────────────────────
# Resolving the names a run expects
# ─────────────────────────────────────────────────────────────────────────────


# Verifies: REQ-d00283-E+P
@pytest.mark.parametrize(
    "named,expected",
    [
        (["unit"], {"unit"}),
        (["uat"], {"journeys"}),
        (["unit", "uat"], {"unit", "journeys"}),
        (["all"], {"unit", "journeys"}),
        (["default"], {"unit"}),
        (["none"], set()),
        ([], set()),
    ],
)
def test_expected_names_resolve_as_target_selections_do(tmp_path, named, expected):
    from elspais.commands._targets import resolve_expected_targets

    assert resolve_expected_targets(_config(_project(tmp_path)), named) == expected


# Verifies: REQ-d00283-H+P
def test_an_unknown_expected_name_is_refused_naming_the_option_and_the_vocabulary(tmp_path):
    from elspais.commands._targets import resolve_expected_targets

    with pytest.raises(ValueError) as caught:
        resolve_expected_targets(_config(_project(tmp_path)), ["unit", "bogus"])

    message = str(caught.value)
    assert message.startswith("unknown --expect: bogus.")
    assert "Configured targets: journeys, unit." in message
    assert "Known groups: all, default, device, none, uat." in message


# Verifies: REQ-d00283-H+P
def test_an_expected_selection_standing_for_no_target_is_refused(tmp_path):
    """`device` is a declared group no target claims. Expecting it would
    expect nothing, and a run expecting nothing reports nothing missing."""
    from elspais.commands._targets import resolve_expected_targets

    with pytest.raises(ValueError) as caught:
        resolve_expected_targets(_config(_project(tmp_path)), ["device"])

    assert "--expect device stands for no configured target" in str(caught.value)
    assert "`none`" in str(caught.value)


# ─────────────────────────────────────────────────────────────────────────────
# The command: --expect, and what --run-tests adds to the expectation
# ─────────────────────────────────────────────────────────────────────────────


# Verifies: REQ-d00283-H+P
def test_the_command_refuses_an_unknown_expected_name(tmp_path, monkeypatch, capsys):
    from elspais.cli import main

    root = _project(tmp_path)
    monkeypatch.chdir(root)

    assert main(["checks", "--expect", "bogus"]) == 2
    err = capsys.readouterr().err
    assert "unknown --expect: bogus" in err
    assert "Known groups: all, default, device, none, uat." in err


def _args(**overrides) -> argparse.Namespace:
    base = {
        "run_tests": False,
        "fail_fast": False,
        "targets": None,
        "expect": None,
        "config": None,
        "format": "text",
        "lenient": True,
        "quiet": False,
        "verbose": False,
        "include_passing_details": False,
        "spec_only": False,
        "code_only": False,
        "tests_only": False,
        "terms_only": False,
        "spec_dir": None,
        "status": None,
    }
    base.update(overrides)
    return argparse.Namespace(**base)


def _capture_requests(monkeypatch) -> list:
    """Record the ChecksRequest the command builds, on either compute path."""
    from elspais.commands import _engine

    requests: list = []

    def _local(args, request):
        requests.append(request)
        return {"healthy": True, "checks": []}

    def _call(endpoint, request, compute, **_kw):
        requests.append(request)
        return {"healthy": True, "checks": []}

    monkeypatch.setattr(health, "_run_local_checks", _local)
    monkeypatch.setattr(_engine, "call", _call)
    return requests


# Verifies: REQ-d00283-P
def test_expected_names_reach_the_request_resolved(tmp_path, monkeypatch):
    root = _project(tmp_path)
    monkeypatch.chdir(root)
    requests = _capture_requests(monkeypatch)

    assert health.run(_args(expect=[["uat"], ["unit"]])) == 0

    (request,) = requests
    assert request.expected_targets == ("journeys", "unit")


# Verifies: REQ-d00283-Q
@pytest.mark.parametrize(
    "expect,expected",
    [(None, ("a",)), ([["b"]], ("a", "b"))],
    ids=["executed-only", "executed-and-expected"],
)
def test_a_run_expects_every_target_it_executes(tmp_path, monkeypatch, expect, expected):
    from elspais.config.schema import (
        ElspaisConfig,
        ScanningConfig,
        TestScanningConfig,
        TestTargetConfig,
    )

    cfg = ElspaisConfig(
        scanning=ScanningConfig(
            test=TestScanningConfig(
                targets=[
                    TestTargetConfig(name=name, command="true", reporter="junit")
                    for name in ("a", "b")
                ]
            )
        )
    )
    monkeypatch.setattr("elspais.config.get_config", lambda *a, **k: {})
    monkeypatch.setattr("elspais.config.validate_config", lambda d: cfg)
    monkeypatch.setattr("elspais.config.find_git_root", lambda *a, **k: tmp_path)
    monkeypatch.setattr(health, "_validate_config", lambda d: cfg)
    requests = _capture_requests(monkeypatch)

    assert health.run(_args(run_tests=True, targets=[["a"]], expect=expect)) == 0

    (request,) = requests
    assert request.expected_targets == expected
