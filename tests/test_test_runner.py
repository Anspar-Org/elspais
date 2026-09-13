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
