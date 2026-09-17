# Verifies: REQ-d00254-H
"""Unit tests for `elspais checks --run-tests` target selection/validation.

Covers `--targets`, the ONE selector: it names test targets, some of them by
the name of a group they claim, a group being an alias for the set of targets
in it (REQ-d00283-E+I). There is no second selector.

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


def _base_args(targets: list[str] | list[list[str]] | None) -> argparse.Namespace:
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
    # Both vocabularies, because `--targets` reads from both: a reader who
    # mistyped a group name learns the group names, not only the target ones.
    assert "Configured targets: a" in err
    assert "Known groups: all, default" in err


# Verifies: REQ-d00283-H
def test_unknown_name_error_names_the_declared_groups_too(capsys, monkeypatch, tmp_path):
    """A project that declares a group has that group in the vocabulary the
    refusal publishes -- otherwise the message names a smaller set of legal
    spellings than the flag actually admits."""
    cfg = _cfg_with_targets(
        [TestTargetConfig(name="a", command="true", reporter="junit")],
        groups={"uat": "needs a live backend", "slow": "runs for over a minute"},
    )
    monkeypatch.setattr("elspais.config.get_config", lambda *a, **k: {})
    monkeypatch.setattr(health, "_validate_config", lambda d: cfg)

    rc = health.run(_base_args(["uta"]))

    err = capsys.readouterr().err
    assert rc == 2
    assert "Known groups: all, default, slow, uat" in err


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
def test_a_group_name_executes_only_that_groups_targets(monkeypatch, tmp_path):
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

    rc = health.run(_base_args(["uat"]))

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
def test_unknown_name_errors(capsys, monkeypatch, tmp_path):
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

    rc = health.run(_base_args(["uta"]))

    err = capsys.readouterr().err
    assert rc == 2
    assert "uta" in err, "the refusal must name the group it could not resolve"
    assert not (tmp_path / "a.txt").exists(), "a refused selection must execute nothing"
    assert not (tmp_path / "b.txt").exists()


def _three_commandful_targets(tmp_path):
    """`a` in `default`, `b` in `uat`, `c` in `slow` -- so a target name and a
    group name can each reach a target the other does not."""
    return [
        TestTargetConfig(name="a", command=f"touch {tmp_path / 'a.txt'}", reporter="junit"),
        TestTargetConfig(
            name="b", command=f"touch {tmp_path / 'b.txt'}", reporter="junit", groups=["uat"]
        ),
        TestTargetConfig(
            name="c", command=f"touch {tmp_path / 'c.txt'}", reporter="junit", groups=["slow"]
        ),
    ]


_THREE_GROUPS = {"uat": "needs a live backend", "slow": "runs for over a minute"}


def _grouped_run(monkeypatch, tmp_path, named):
    cfg = _cfg_with_targets(_three_commandful_targets(tmp_path), groups=_THREE_GROUPS)
    monkeypatch.setattr("elspais.config.get_config", lambda *a, **k: {})
    monkeypatch.setattr("elspais.config.find_git_root", lambda *a, **k: tmp_path)
    monkeypatch.setattr(health, "_validate_config", lambda d: cfg)
    captured = _capture_local_checks(monkeypatch)

    rc = health.run(_base_args(named))

    ran = {n for n in "abc" if (tmp_path / f"{n}.txt").exists()}
    return rc, ran, captured


# Verifies: REQ-d00283-E+I
def test_a_target_name_beside_a_group_name_runs_both(monkeypatch, tmp_path):
    """A group is an alias, so naming one alongside a target WIDENS the run.
    The retired reading -- each selector narrowing the other -- would have run
    nothing here, `a` belonging to no group named."""
    rc, ran, captured = _grouped_run(monkeypatch, tmp_path, ["a", "uat"])

    assert rc == 0
    assert ran == {"a", "b"}, "a run executes every target it named"
    assert captured[0]._fresh_targets == {"a", "b"}


# Verifies: REQ-d00283-E+I
def test_two_group_names_run_the_union_of_their_targets(monkeypatch, tmp_path):
    rc, ran, captured = _grouped_run(monkeypatch, tmp_path, ["uat", "slow"])

    assert rc == 0
    assert ran == {"b", "c"}
    assert captured[0]._fresh_targets == {"b", "c"}


# Verifies: REQ-d00283-E
def test_targets_accumulate_across_repeated_flags(monkeypatch, tmp_path):
    """The selection a repeated flag builds reaches target resolution whole.

    The nested shape here is what the CLI parser actually produces for
    `--targets a --targets uat`; letting the last occurrence stand for the
    whole would have run `uat`'s targets alone.
    """
    import tyro

    from elspais.commands.args import ChecksArgs

    parsed = tyro.cli(ChecksArgs, args=["--run-tests", "--targets", "a", "--targets", "uat"])
    assert parsed.targets == [["a"], ["uat"]], "the parser keeps each occurrence apart"

    rc, ran, captured = _grouped_run(monkeypatch, tmp_path, parsed.targets)

    assert rc == 0
    assert ran == {"a", "b"}
    assert captured[0]._fresh_targets == {"a", "b"}


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
    from elspais.commands._requests import ChecksRequest

    result = health._run_local_checks(args, ChecksRequest())

    assert "healthy" in result
    assert captured["fresh_targets"] == {"a"}
