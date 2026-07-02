# Verifies: REQ-d00254-H
"""Unit tests for `elspais checks --run-tests --targets` selection/validation.

`health.run()` imports `get_config`/`find_git_root` (from `elspais.config`)
and `run_configured_targets` (from `elspais.commands.test_runner`) locally
inside the function body, so patching attributes on the `health` module
does not intercept them. These tests patch the real import sources
(`elspais.config.get_config`, `elspais.config.find_git_root`) instead, and
patch `health._validate_config`/`health._run_local_checks` directly since
those are module-level references resolved on the `health` module itself.
`run_configured_targets` runs for real (no mocking) against real shell
commands so the `--targets` subset selection is exercised end to end.
"""
from __future__ import annotations

import argparse

from elspais.commands import health
from elspais.config.schema import (
    ElspaisConfig,
    ScanningConfig,
    TestScanningConfig,
    TestTargetConfig,
)


def _cfg_with_targets(targets: list[TestTargetConfig]) -> ElspaisConfig:
    return ElspaisConfig(scanning=ScanningConfig(test=TestScanningConfig(targets=targets)))


def _base_args(targets: list[str] | None) -> argparse.Namespace:
    return argparse.Namespace(
        run_tests=True,
        fail_fast=False,
        targets=targets,
        config=None,
        format="text",
        lenient=True,
        quiet=False,
        verbose=False,
        include_passing_details=False,
        spec_only=False,
        code_only=False,
        tests_only=False,
        terms_only=False,
        spec_dir=None,
        status=None,
    )


# Verifies: REQ-d00254-H
def test_unknown_target_name_errors(capsys, monkeypatch, tmp_path):
    cfg = _cfg_with_targets([TestTargetConfig(name="a", command="true", reporter="junit")])
    monkeypatch.setattr("elspais.config.get_config", lambda *a, **k: {})
    monkeypatch.setattr(health, "_validate_config", lambda d: cfg)

    args = _base_args(["nope"])
    rc = health.run(args)

    err = capsys.readouterr().err
    assert rc == 2
    assert "unknown --targets: nope" in err
    assert "Configured targets: a" in err


# Verifies: REQ-d00254-H
def test_targets_flag_executes_only_named_subset(monkeypatch, tmp_path):
    marker_a = tmp_path / "a.txt"
    marker_b = tmp_path / "b.txt"
    cfg = _cfg_with_targets(
        [
            TestTargetConfig(name="a", command=f"touch {marker_a}", reporter="junit"),
            TestTargetConfig(name="b", command=f"touch {marker_b}", reporter="junit"),
        ]
    )
    monkeypatch.setattr("elspais.config.get_config", lambda *a, **k: {})
    monkeypatch.setattr("elspais.config.find_git_root", lambda *a, **k: tmp_path)
    monkeypatch.setattr(health, "_validate_config", lambda d: cfg)
    monkeypatch.setattr(
        health, "_run_local_checks", lambda args, params: {"healthy": True, "checks": []}
    )

    args = _base_args(["a"])
    rc = health.run(args)

    assert rc == 0
    assert marker_a.exists()
    assert not marker_b.exists()


# Verifies: REQ-d00254-H
def test_absent_targets_flag_runs_all(monkeypatch, tmp_path):
    marker_a = tmp_path / "a.txt"
    marker_b = tmp_path / "b.txt"
    cfg = _cfg_with_targets(
        [
            TestTargetConfig(name="a", command=f"touch {marker_a}", reporter="junit"),
            TestTargetConfig(name="b", command=f"touch {marker_b}", reporter="junit"),
        ]
    )
    monkeypatch.setattr("elspais.config.get_config", lambda *a, **k: {})
    monkeypatch.setattr("elspais.config.find_git_root", lambda *a, **k: tmp_path)
    monkeypatch.setattr(health, "_validate_config", lambda d: cfg)
    monkeypatch.setattr(
        health, "_run_local_checks", lambda args, params: {"healthy": True, "checks": []}
    )

    args = _base_args(None)
    rc = health.run(args)

    assert rc == 0
    assert marker_a.exists()
    assert marker_b.exists()
