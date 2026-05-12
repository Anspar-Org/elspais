# Verifies: REQ-d00249-A, REQ-d00249-B, REQ-d00249-C
"""Unit tests for the test-runner dispatcher."""
from __future__ import annotations

from pathlib import Path

from elspais.commands.test_runner import run_configured_runners
from elspais.config.schema import (
    ElspaisConfig,
    ScanningConfig,
    TestRunnerConfig,
    TestScanningConfig,
)


def _cfg_with_runners(runners: list[TestRunnerConfig]) -> ElspaisConfig:
    return ElspaisConfig(scanning=ScanningConfig(test=TestScanningConfig(runners=runners)))


def test_no_runners_returns_empty_list(tmp_path: Path):
    cfg = _cfg_with_runners([])
    results = run_configured_runners(cfg, tmp_path)
    assert results == []


def test_single_runner_success(tmp_path: Path):
    cfg = _cfg_with_runners([TestRunnerConfig(name="ok", command="true")])
    results = run_configured_runners(cfg, tmp_path)
    assert len(results) == 1
    r = results[0]
    assert r.name == "ok"
    assert r.command == "true"
    assert r.returncode == 0
    assert r.error == ""
    assert r.duration_seconds >= 0.0
    assert r.cwd == tmp_path


def test_runner_failure_records_nonzero(tmp_path: Path):
    cfg = _cfg_with_runners([TestRunnerConfig(name="bad", command="false")])
    results = run_configured_runners(cfg, tmp_path)
    assert results[0].returncode != 0


def test_runners_run_in_declaration_order(tmp_path: Path):
    marker = tmp_path / "log.txt"
    cfg = _cfg_with_runners(
        [
            TestRunnerConfig(name="first", command=f"echo first >> {marker}"),
            TestRunnerConfig(name="second", command=f"echo second >> {marker}"),
        ]
    )
    results = run_configured_runners(cfg, tmp_path)
    assert [r.name for r in results] == ["first", "second"]
    assert marker.read_text().splitlines() == ["first", "second"]


def test_fail_fast_stops_after_first_failure(tmp_path: Path):
    marker = tmp_path / "marker.txt"
    cfg = _cfg_with_runners(
        [
            TestRunnerConfig(name="bad", command="false"),
            TestRunnerConfig(name="never", command=f"touch {marker}"),
        ]
    )
    results = run_configured_runners(cfg, tmp_path, fail_fast=True)
    assert len(results) == 1
    assert results[0].name == "bad"
    assert not marker.exists()


def test_cwd_resolves_relative_to_repo_root(tmp_path: Path):
    subdir = tmp_path / "subproj"
    subdir.mkdir()
    cfg = _cfg_with_runners([TestRunnerConfig(name="pwd", command="pwd > out.txt", cwd="subproj")])
    results = run_configured_runners(cfg, tmp_path)
    assert results[0].returncode == 0
    assert results[0].cwd == subdir.resolve()
    assert (subdir / "out.txt").read_text().strip() == str(subdir.resolve())


def test_empty_cwd_uses_repo_root(tmp_path: Path):
    cfg = _cfg_with_runners([TestRunnerConfig(name="here", command="pwd > out.txt")])
    results = run_configured_runners(cfg, tmp_path)
    assert results[0].cwd == tmp_path
    assert (tmp_path / "out.txt").read_text().strip() == str(tmp_path.resolve())


def test_default_does_not_fail_fast(tmp_path: Path):
    marker = tmp_path / "marker.txt"
    cfg = _cfg_with_runners(
        [
            TestRunnerConfig(name="bad", command="false"),
            TestRunnerConfig(name="after", command=f"touch {marker}"),
        ]
    )
    results = run_configured_runners(cfg, tmp_path)
    assert len(results) == 2
    assert results[0].returncode != 0
    assert results[1].returncode == 0
    assert marker.exists()
