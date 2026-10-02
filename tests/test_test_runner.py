# Verifies: REQ-d00249-A, REQ-d00249-B, REQ-d00249-C
"""Unit tests for the test-target dispatcher."""

from __future__ import annotations

import contextlib
import os
import sys
import threading
import time
from pathlib import Path

import pytest

from elspais.commands.test_runner import run_configured_targets
from elspais.config.schema import (
    ElspaisConfig,
    ScanningConfig,
    TestScanningConfig,
    TestTargetConfig,
)


def _cfg_with_targets(targets: list[TestTargetConfig]) -> ElspaisConfig:
    return ElspaisConfig(scanning=ScanningConfig(test=TestScanningConfig(targets=targets)))


@contextlib.contextmanager
def _terminal_tee(path: Path):
    """Capture everything this process sends to its terminal into `path`.

    Both the Python-level streams and the underlying file descriptors are
    redirected, so a child that inherits fd 1/2 and an echo written through
    `sys.stdout`/`sys.stderr` land in the same place -- which is what "the
    invoking terminal" means to the developer running the command.
    """
    with open(path, "w", buffering=1) as sink:
        saved_out_fd = os.dup(1)
        saved_err_fd = os.dup(2)
        saved_out, saved_err = sys.stdout, sys.stderr
        try:
            sys.stdout.flush()
            sys.stderr.flush()
            os.dup2(sink.fileno(), 1)
            os.dup2(sink.fileno(), 2)
            sys.stdout = sink
            sys.stderr = sink
            yield
        finally:
            sys.stdout, sys.stderr = saved_out, saved_err
            os.dup2(saved_out_fd, 1)
            os.dup2(saved_err_fd, 2)
            os.close(saved_out_fd)
            os.close(saved_err_fd)


def test_no_targets_returns_empty(tmp_path: Path):
    cfg = _cfg_with_targets([])
    results, captured = run_configured_targets(cfg, tmp_path)
    assert results == []
    assert captured == {}


def test_single_target_success(tmp_path: Path):
    cfg = _cfg_with_targets([TestTargetConfig(name="ok", command="true", reporter="junit")])
    results, captured = run_configured_targets(cfg, tmp_path)
    assert len(results) == 1
    r = results[0]
    assert r.name == "ok"
    assert r.command == "true"
    assert r.returncode == 0
    assert r.error == ""
    assert r.duration_seconds >= 0.0
    assert r.cwd == tmp_path


def test_target_failure_records_nonzero(tmp_path: Path):
    cfg = _cfg_with_targets([TestTargetConfig(name="bad", command="false", reporter="junit")])
    results, _captured = run_configured_targets(cfg, tmp_path)
    assert results[0].returncode != 0


def test_targets_run_in_declaration_order(tmp_path: Path):
    marker = tmp_path / "log.txt"
    cfg = _cfg_with_targets(
        [
            TestTargetConfig(name="first", command=f"echo first >> {marker}", reporter="junit"),
            TestTargetConfig(name="second", command=f"echo second >> {marker}", reporter="junit"),
        ]
    )
    results, _captured = run_configured_targets(cfg, tmp_path)
    assert [r.name for r in results] == ["first", "second"]
    assert marker.read_text().splitlines() == ["first", "second"]


def test_fail_fast_stops_after_first_failure(tmp_path: Path):
    marker = tmp_path / "marker.txt"
    cfg = _cfg_with_targets(
        [
            TestTargetConfig(name="bad", command="false", reporter="junit"),
            TestTargetConfig(name="never", command=f"touch {marker}", reporter="junit"),
        ]
    )
    results, _captured = run_configured_targets(cfg, tmp_path, fail_fast=True)
    assert len(results) == 1
    assert results[0].name == "bad"
    assert not marker.exists()


def test_cwd_resolves_relative_to_repo_root(tmp_path: Path):
    subdir = tmp_path / "subproj"
    subdir.mkdir()
    cfg = _cfg_with_targets(
        [TestTargetConfig(name="pwd", command="pwd > out.txt", cwd="subproj", reporter="junit")]
    )
    results, _captured = run_configured_targets(cfg, tmp_path)
    assert results[0].returncode == 0
    assert results[0].cwd == subdir.resolve()
    assert (subdir / "out.txt").read_text().strip() == str(subdir.resolve())


def test_empty_cwd_uses_repo_root(tmp_path: Path):
    cfg = _cfg_with_targets(
        [TestTargetConfig(name="here", command="pwd > out.txt", reporter="junit")]
    )
    results, _captured = run_configured_targets(cfg, tmp_path)
    assert results[0].cwd == tmp_path
    assert (tmp_path / "out.txt").read_text().strip() == str(tmp_path.resolve())


def test_default_does_not_fail_fast(tmp_path: Path):
    marker = tmp_path / "marker.txt"
    cfg = _cfg_with_targets(
        [
            TestTargetConfig(name="bad", command="false", reporter="junit"),
            TestTargetConfig(name="after", command=f"touch {marker}", reporter="junit"),
        ]
    )
    results, _captured = run_configured_targets(cfg, tmp_path)
    assert len(results) == 2
    assert results[0].returncode != 0
    assert results[1].returncode == 0
    assert marker.exists()


def test_absolute_cwd_outside_repo_is_rejected(tmp_path: Path):
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    repo = tmp_path / "repo"
    repo.mkdir()
    cfg = _cfg_with_targets(
        [TestTargetConfig(name="escape", command="true", cwd=str(outside), reporter="junit")]
    )
    results, _captured = run_configured_targets(cfg, repo)
    assert len(results) == 1
    r = results[0]
    assert r.returncode == -1
    assert "outside the repo root" in r.error


def test_parent_traversal_cwd_is_rejected(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    cfg = _cfg_with_targets(
        [TestTargetConfig(name="dotdot", command="true", cwd="../elsewhere", reporter="junit")]
    )
    results, _captured = run_configured_targets(cfg, repo)
    assert results[0].returncode == -1
    assert "outside the repo root" in results[0].error


def test_relative_subdir_cwd_is_accepted(tmp_path: Path):
    sub = tmp_path / "sub"
    sub.mkdir()
    cfg = _cfg_with_targets(
        [TestTargetConfig(name="ok", command="true", cwd="sub", reporter="junit")]
    )
    results, _captured = run_configured_targets(cfg, tmp_path)
    assert results[0].returncode == 0
    assert results[0].cwd == sub.resolve()


def test_target_without_command_is_skipped(tmp_path: Path):
    """Targets with empty command are skipped (CI mode — tests already ran)."""
    cfg = _cfg_with_targets([TestTargetConfig(name="no-cmd", reporter="junit")])
    results, _captured = run_configured_targets(cfg, tmp_path)
    assert results == []


# Verifies: REQ-d00254-H
def test_only_runs_named_targets(tmp_path: Path):
    """`only` restricts execution to the named subset, in declaration order."""
    marker = tmp_path / "log.txt"
    cfg = _cfg_with_targets(
        [
            TestTargetConfig(name="a", command=f"echo a >> {marker}", reporter="junit"),
            TestTargetConfig(name="b", command=f"echo b >> {marker}", reporter="junit"),
        ]
    )
    results, _captured = run_configured_targets(cfg, tmp_path, only={"a"})
    assert [r.name for r in results] == ["a"]
    assert marker.read_text().splitlines() == ["a"]


# Verifies: REQ-d00254-H
def test_only_none_runs_all_targets(tmp_path: Path):
    """`only=None` (the default) preserves existing run-everything behavior."""
    cfg = _cfg_with_targets(
        [
            TestTargetConfig(name="a", command="true", reporter="junit"),
            TestTargetConfig(name="b", command="true", reporter="junit"),
        ]
    )
    results, _captured = run_configured_targets(cfg, tmp_path, only=None)
    assert [r.name for r in results] == ["a", "b"]


# Verifies: REQ-d00249-B
@pytest.mark.parametrize(
    ("reporter", "stdout_is_captured"),
    [("junit", False), ("flutter-machine", True)],
)
def test_REQ_d00249_B_both_streams_reach_terminal(
    tmp_path: Path, reporter: str, stdout_is_captured: bool
):
    """A runner's stdout AND stderr reach the invoking terminal, whatever its reporter.

    A stdout-channel reporter additionally needs that stdout captured for its
    parser (REQ-d00254-F); capturing it must not cost the developer sight of it.
    """
    # The sentinels live in files the command reads, never in the command text
    # itself -- the runner banner echoes the command, and a sentinel spelled
    # there would be found on the terminal whether or not the runner's own
    # output ever arrived.
    (tmp_path / "out.txt").write_text("OUTLINE\n")
    (tmp_path / "err.txt").write_text("ERRLINE\n")
    cfg = _cfg_with_targets(
        [
            TestTargetConfig(
                name="t",
                command="cat out.txt; cat err.txt >&2; exit 3",
                reporter=reporter,
            )
        ]
    )
    log = tmp_path / "terminal.log"
    with _terminal_tee(log):
        results, captured = run_configured_targets(cfg, tmp_path)
    terminal = log.read_text()

    assert results[0].returncode == 3
    assert "OUTLINE" in terminal, f"runner stdout never reached the terminal: {terminal!r}"
    assert "ERRLINE" in terminal, f"runner stderr never reached the terminal: {terminal!r}"
    if stdout_is_captured:
        assert "OUTLINE" in captured["t"]
    else:
        assert "t" not in captured


# Verifies: REQ-d00249-B
def test_REQ_d00249_B_stdout_channel_streams_live_not_at_exit(tmp_path: Path):
    """Output appears on the terminal while the runner is still going, not after it ends."""
    # Sentinels come from files, not the command text (see above).
    (tmp_path / "early.txt").write_text("EARLY\n")
    (tmp_path / "late.txt").write_text("LATE\n")
    cfg = _cfg_with_targets(
        [
            TestTargetConfig(
                name="slow",
                command="cat early.txt; sleep 1.5; cat late.txt",
                reporter="flutter-machine",
            )
        ]
    )
    log = tmp_path / "terminal.log"
    log.write_text("")
    seen_early_at: list[float] = []
    stop = threading.Event()
    start = time.monotonic()

    def watch() -> None:
        while not stop.is_set():
            if "EARLY" in log.read_text():
                seen_early_at.append(time.monotonic() - start)
                return
            time.sleep(0.02)

    watcher = threading.Thread(target=watch, daemon=True)
    watcher.start()
    try:
        with _terminal_tee(log):
            results, captured = run_configured_targets(cfg, tmp_path)
    finally:
        stop.set()
        watcher.join(timeout=2.0)
    total = time.monotonic() - start

    assert results[0].returncode == 0
    assert "LATE" in captured["slow"]
    assert total >= 1.4, "the runner did not actually take the time the probe relies on"
    assert seen_early_at, "no runner output reached the terminal before the runner exited"
    assert seen_early_at[0] < 1.0, (
        f"output was withheld until the runner finished (EARLY seen at {seen_early_at[0]:.2f}s "
        f"of a {total:.2f}s run)"
    )


# ---------------------------------------------------------------------------
# `elspais test`: execute targets and record their results, evaluating no check
# ---------------------------------------------------------------------------

# The command writes a junit artifact into the target's output area.
_WRITES_RESULTS = (
    'python3 -c "import os,pathlib; '
    "pathlib.Path(os.environ['ELSPAIS_TARGET_OUTPUT'], 'junit.xml')"
    ".write_text('<testsuite/>')\""
)

_SPEC_OK = """\
# Requirements

---

### REQ-d00001: Thing

**Level**: dev | **Status**: Active

## Assertions

A. The system SHALL do the thing.

*End* *Thing*
---
"""

# REQ-d00001 implements a requirement nothing declares.
_SPEC_BROKEN = _SPEC_OK.replace(
    "**Level**: dev | **Status**: Active\n",
    "**Level**: dev | **Status**: Active\n\n**Implements**: REQ-d09999\n",
)


def _target_toml(
    name: str,
    command: str,
    reporter: str = "junit",
    results: str | None = "junit.xml",
    groups: list[str] | None = None,
) -> str:
    lines = [
        "[[scanning.test.targets]]",
        f'name = "{name}"',
        f'reporter = "{reporter}"',
        f'command = """{command}"""',
    ]
    if results is not None:
        lines.append(f'results = "{results}"')
    if groups:
        lines.append("groups = [" + ", ".join(f'"{g}"' for g in groups) + "]")
    return "\n".join(lines) + "\n"


def _cli_project(tmp_path: Path, monkeypatch, *targets: str, spec: str = _SPEC_OK) -> Path:
    """A git repository declaring *targets*, made the working directory."""
    import subprocess

    root = tmp_path / "repo"
    (root / "spec").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    (root / "spec" / "requirements.md").write_text(spec, encoding="utf-8")
    (root / ".elspais.toml").write_text(
        'version = 5\n\n[project]\nname = "runs"\nnamespace = "REQ"\n\n'
        '[scanning.spec]\ndirectories = ["spec"]\n\n'
        "[changelog]\nhash_current = false\n\n"
        "[scanning.test]\nenabled = true\n\n"
        '[scanning.test.groups]\nslow = "runs for over a minute"\n\n' + "\n".join(targets),
        encoding="utf-8",
    )
    monkeypatch.chdir(root)
    return root


# Verifies: REQ-d00249-H, REQ-d00249-J
def test_a_run_of_passing_targets_records_their_results_and_exits_zero(
    tmp_path, monkeypatch, capsys
):
    from elspais.cli import main
    from elspais.utilities.fingerprint import RECORD_NAME, judge

    root = _cli_project(tmp_path, monkeypatch, _target_toml("unit", _WRITES_RESULTS))

    assert main(["test", "--targets", "unit"]) == 0

    out = capsys.readouterr().out
    assert "1 target(s) passed" in out
    folder = root / ".results" / "unit"
    assert sorted(p.name for p in folder.iterdir()) == sorted([RECORD_NAME, "junit.xml"])
    from elspais.config import load_config

    assert judge(root, load_config(root / ".elspais.toml"), "unit").state == "fresh"


# Verifies: REQ-d00249-J
def test_a_run_with_a_failing_target_exits_one_naming_it(tmp_path, monkeypatch, capsys):
    from elspais.cli import main

    _cli_project(
        tmp_path,
        monkeypatch,
        _target_toml("unit", _WRITES_RESULTS),
        _target_toml("broken", "false"),
    )

    assert main(["test"]) == 1

    out = capsys.readouterr().out
    assert "1 of 2 target(s) failed: broken" in out


# Verifies: REQ-d00249-I
def test_a_group_name_selects_the_targets_claiming_it(tmp_path, monkeypatch, capsys):
    from elspais.cli import main

    fast = tmp_path / "fast.txt"
    slow_one = tmp_path / "slow1.txt"
    slow_two = tmp_path / "slow2.txt"
    _cli_project(
        tmp_path,
        monkeypatch,
        _target_toml("fast", f"touch {fast}"),
        _target_toml("slow1", f"touch {slow_one}", groups=["slow"]),
        _target_toml("slow2", f"touch {slow_two}", groups=["slow"]),
    )

    assert main(["test", "--targets", "slow"]) == 0

    assert "2 target(s) passed" in capsys.readouterr().out
    assert slow_one.exists() and slow_two.exists()
    assert not fast.exists()


# Verifies: REQ-d00249-I
@pytest.mark.parametrize(
    "named,wording",
    [
        (["nope"], "unknown --targets: nope"),
        (["none"], "--targets none selects no test target"),
    ],
    ids=["unknown-name", "none"],
)
def test_a_selection_no_run_executes_is_refused(tmp_path, monkeypatch, capsys, named, wording):
    from elspais.cli import main

    marker = tmp_path / "ran.txt"
    root = _cli_project(tmp_path, monkeypatch, _target_toml("unit", f"touch {marker}"))

    assert main(["test", "--targets", *named]) == 2

    assert wording in capsys.readouterr().err
    assert not marker.exists()
    assert not (root / ".results").exists()


# Verifies: REQ-d00249-I
def test_both_runs_refuse_an_unknown_name_with_one_text(tmp_path, monkeypatch, capsys):
    from elspais.cli import main

    _cli_project(tmp_path, monkeypatch, _target_toml("unit", "true"))

    assert main(["checks", "--run-tests", "--targets", "nope"]) == 2
    checks_err = capsys.readouterr().err
    assert main(["test", "--targets", "nope"]) == 2
    test_err = capsys.readouterr().err

    assert test_err == checks_err
    assert "unknown --targets: nope" in test_err


# Verifies: REQ-d00249-K
def test_a_target_whose_results_would_not_be_recorded_refuses_the_run(
    tmp_path, monkeypatch, capsys
):
    """The flutter target reads its command's output and declares no artifact.
    The whole selection is refused before the other target runs."""
    from elspais.cli import main

    marker = tmp_path / "ran.txt"
    _cli_project(
        tmp_path,
        monkeypatch,
        _target_toml("unit", f"touch {marker}"),
        _target_toml("widgets", "true", reporter="flutter-machine", results=None),
    )

    assert main(["test"]) == 2

    err = capsys.readouterr().err
    assert "widgets" in err
    assert "results" in err
    assert not marker.exists()


# Verifies: REQ-d00249-K
def test_a_stdout_target_declaring_its_results_is_executed(tmp_path, monkeypatch, capsys):
    """The negative: the same reporter with a results pattern is not refused."""
    from elspais.cli import main

    marker = tmp_path / "ran.txt"
    _cli_project(
        tmp_path,
        monkeypatch,
        _target_toml("widgets", f"touch {marker}", reporter="flutter-machine", results="m.jsonl"),
    )

    assert main(["test"]) == 0
    assert marker.exists()


# Verifies: REQ-d00249-H
def test_fail_fast_stops_at_the_first_failing_target(tmp_path, monkeypatch, capsys):
    from elspais.cli import main

    marker = tmp_path / "after.txt"
    _cli_project(
        tmp_path,
        monkeypatch,
        _target_toml("broken", "false"),
        _target_toml("after", f"touch {marker}"),
    )

    assert main(["test", "--fail-fast"]) == 1

    assert "1 of 1 target(s) failed: broken" in capsys.readouterr().out
    assert not marker.exists()


# Verifies: REQ-d00249-H, REQ-d00249-J
@pytest.mark.parametrize(
    "spec,checks_exit",
    [(_SPEC_OK, 0), (_SPEC_BROKEN, 1)],
    ids=["sound-spec", "broken-reference"],
)
def test_a_specification_error_does_not_change_the_outcome(
    tmp_path, monkeypatch, capsys, spec, checks_exit
):
    """The same passing target: `checks --run-tests` fails over the broken
    spec alone, and `test`, which evaluates no check, passes over both."""
    from elspais.cli import main

    _cli_project(tmp_path, monkeypatch, _target_toml("unit", _WRITES_RESULTS), spec=spec)

    assert main(["checks", "--lenient", "--run-tests", "--targets", "unit"]) == checks_exit
    capsys.readouterr()

    assert main(["test", "--targets", "unit"]) == 0
    assert "1 target(s) passed" in capsys.readouterr().out
