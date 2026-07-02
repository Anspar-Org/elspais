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


# Verifies: REQ-d00254-I
def test_run_stashes_fresh_targets_on_args(monkeypatch, tmp_path):
    """health.run() with --run-tests --targets a stashes {'a'} as args._fresh_targets."""
    marker_a = tmp_path / "a.txt"
    cfg = _cfg_with_targets(
        [TestTargetConfig(name="a", command=f"touch {marker_a}", reporter="junit")]
    )
    monkeypatch.setattr("elspais.config.get_config", lambda *a, **k: {})
    monkeypatch.setattr("elspais.config.find_git_root", lambda *a, **k: tmp_path)
    monkeypatch.setattr(health, "_validate_config", lambda d: cfg)

    captured_args: list[argparse.Namespace] = []

    def _fake_local_checks(args, params):
        captured_args.append(args)
        return {"healthy": True, "checks": []}

    monkeypatch.setattr(health, "_run_local_checks", _fake_local_checks)

    args = _base_args(["a"])
    rc = health.run(args)

    assert rc == 0
    assert captured_args, "_run_local_checks should have been called"
    assert captured_args[0]._fresh_targets == {"a"}


# Verifies: REQ-d00254-I
def test_run_local_checks_threads_fresh_targets_into_build_graph(monkeypatch, tmp_path):
    """_run_local_checks() passes args._fresh_targets through to build_graph()."""
    import elspais.graph.factory as factory_mod

    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()
    (spec_dir / "reqs.md").write_text(
        """\
### REQ-p00001: Test Req

**Level**: PRD | **Status**: Active

The system SHALL do something testable.

*End* *Test Req* | **Hash**: ________
""",
        encoding="utf-8",
    )
    config_path = tmp_path / ".elspais.toml"
    config_path.write_text(
        """\
version = 3

[project]
name = "fresh-targets"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]
""",
        encoding="utf-8",
    )

    captured: dict = {}
    original_build_graph = factory_mod.build_graph

    def spy(*a, **k):
        captured["fresh_targets"] = k.get("fresh_targets")
        return original_build_graph(*a, **k)

    monkeypatch.setattr(factory_mod, "build_graph", spy)

    args = argparse.Namespace(
        spec_dir=None,
        config=str(config_path),
        _captured_results=None,
        _fresh_targets={"a"},
    )
    result = health._run_local_checks(args, {})

    assert "healthy" in result
    assert captured["fresh_targets"] == {"a"}
