# Verifies: REQ-d00254-H
"""Unit tests for `elspais checks --run-tests` target selection/validation.

Covers both selectors: `--targets`, which names targets outright, and
`--groups`, which names them through the group model of REQ-d00283.

`health.run()` imports `get_config`/`find_git_root` (from `elspais.config`)
and `run_configured_targets` (from `elspais.commands.test_runner`) locally
inside the function body, so patching attributes on the `health` module
does not intercept them. These tests patch the real import sources
(`elspais.config.get_config`, `elspais.config.find_git_root`) instead, and
patch `health._validate_config`/`health._run_local_checks` directly since
those are module-level references resolved on the `health` module itself.
`run_configured_targets` runs for real (no mocking) against real shell
commands so the selected subset is exercised end to end.
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


def _cfg_with_targets(
    targets: list[TestTargetConfig], groups: dict[str, str] | None = None
) -> ElspaisConfig:
    return ElspaisConfig(
        scanning=ScanningConfig(test=TestScanningConfig(groups=dict(groups or {}), targets=targets))
    )


def _base_args(targets: list[str] | None, groups: list[str] | None = None) -> argparse.Namespace:
    return argparse.Namespace(
        run_tests=True,
        fail_fast=False,
        targets=targets,
        groups=groups,
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


def _two_commandful_targets(tmp_path, groups_for_b=()):
    return [
        TestTargetConfig(name="a", command=f"touch {tmp_path / 'a.txt'}", reporter="junit"),
        TestTargetConfig(
            name="b",
            command=f"touch {tmp_path / 'b.txt'}",
            reporter="junit",
            groups=list(groups_for_b),
        ),
    ]


def _capture_local_checks(monkeypatch) -> list[argparse.Namespace]:
    captured_args: list[argparse.Namespace] = []

    def _fake_local_checks(args, params):
        captured_args.append(args)
        return {"healthy": True, "checks": []}

    monkeypatch.setattr(health, "_run_local_checks", _fake_local_checks)
    return captured_args


# Verifies: REQ-d00254-I, REQ-d00283-I
def test_run_stashes_fresh_targets_on_args(monkeypatch, tmp_path):
    """A selective run stashes the executed subset as args._fresh_targets."""
    cfg = _cfg_with_targets(_two_commandful_targets(tmp_path))
    monkeypatch.setattr("elspais.config.get_config", lambda *a, **k: {})
    monkeypatch.setattr("elspais.config.find_git_root", lambda *a, **k: tmp_path)
    monkeypatch.setattr(health, "_validate_config", lambda d: cfg)
    captured_args = _capture_local_checks(monkeypatch)

    args = _base_args(["a"])
    rc = health.run(args)

    assert rc == 0
    assert captured_args, "_run_local_checks should have been called"
    assert captured_args[0]._fresh_targets == {"a"}


# Verifies: REQ-d00254-J
def test_run_naming_every_configured_target_is_a_full_run(monkeypatch, tmp_path):
    """Whether a run is selective follows from the targets it executed, not
    from how the selection was expressed -- so naming them all is a full run."""
    cfg = _cfg_with_targets(_two_commandful_targets(tmp_path))
    monkeypatch.setattr("elspais.config.get_config", lambda *a, **k: {})
    monkeypatch.setattr("elspais.config.find_git_root", lambda *a, **k: tmp_path)
    monkeypatch.setattr(health, "_validate_config", lambda d: cfg)
    captured_args = _capture_local_checks(monkeypatch)

    args = _base_args(["a", "b"])
    rc = health.run(args)

    assert rc == 0
    assert captured_args, "_run_local_checks should have been called"
    assert captured_args[0]._fresh_targets is None, (
        "a run that executed every configured target is full, however it was asked for"
    )


# Verifies: REQ-d00283-E
def test_groups_flag_executes_only_that_groups_targets(monkeypatch, tmp_path):
    marker_a = tmp_path / "a.txt"
    marker_b = tmp_path / "b.txt"
    cfg = _cfg_with_targets(
        _two_commandful_targets(tmp_path, groups_for_b=["uat"]),
        groups={"uat": "needs a live backend"},
    )
    monkeypatch.setattr("elspais.config.get_config", lambda *a, **k: {})
    monkeypatch.setattr("elspais.config.find_git_root", lambda *a, **k: tmp_path)
    monkeypatch.setattr(health, "_validate_config", lambda d: cfg)
    captured_args = _capture_local_checks(monkeypatch)

    rc = health.run(_base_args(None, groups=["uat"]))

    assert rc == 0
    assert marker_b.exists(), "the selected group's target must run"
    assert not marker_a.exists(), "a target outside the selected group must not run"
    assert captured_args[0]._fresh_targets == {"b"}


# Verifies: REQ-d00283-D
def test_no_selection_runs_the_default_group(monkeypatch, tmp_path):
    """With a group declared and claimed, a bare run executes `default` only."""
    marker_a = tmp_path / "a.txt"
    marker_b = tmp_path / "b.txt"
    cfg = _cfg_with_targets(
        _two_commandful_targets(tmp_path, groups_for_b=["uat"]),
        groups={"uat": "needs a live backend"},
    )
    monkeypatch.setattr("elspais.config.get_config", lambda *a, **k: {})
    monkeypatch.setattr("elspais.config.find_git_root", lambda *a, **k: tmp_path)
    monkeypatch.setattr(health, "_validate_config", lambda d: cfg)
    captured_args = _capture_local_checks(monkeypatch)

    rc = health.run(_base_args(None))

    assert rc == 0
    assert marker_a.exists(), "the default group's target must run"
    assert not marker_b.exists(), "a target that claimed a group is out of `default`"
    assert captured_args[0]._fresh_targets == {"a"}


# Verifies: REQ-d00283-H
def test_unknown_group_name_errors(capsys, monkeypatch, tmp_path):
    cfg = _cfg_with_targets(
        _two_commandful_targets(tmp_path, groups_for_b=["uat"]),
        groups={"uat": "needs a live backend"},
    )
    monkeypatch.setattr("elspais.config.get_config", lambda *a, **k: {})
    monkeypatch.setattr("elspais.config.find_git_root", lambda *a, **k: tmp_path)
    monkeypatch.setattr(health, "_validate_config", lambda d: cfg)
    monkeypatch.setattr(
        health, "_run_local_checks", lambda args, params: {"healthy": True, "checks": []}
    )

    rc = health.run(_base_args(None, groups=["uta"]))

    err = capsys.readouterr().err
    assert rc == 2
    assert "uta" in err, "the refusal must name the group it could not resolve"
    assert not (tmp_path / "a.txt").exists(), "a refused selection must execute nothing"
    assert not (tmp_path / "b.txt").exists()


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
version = 5

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
