# Verifies: REQ-o00074-A+B+C+D
"""Daemon session-identity tests, verifying REQ-o00074 (Background Daemon Lifetime).

A daemon started on behalf of a session is bound to that session at the
moment it starts: the identity is resolved from evidence available then
(D), handed to the spawned process (A), recorded in the state record
clients read to find the daemon (B), and withheld entirely when the start
was explicit rather than session-driven (C).

Unit-level only: process liveness is faked (``alive_fn``) so the
decision matrix and watchdog transitions are exercised deterministically.
A subprocess-based e2e companion lives in tests/e2e/test_e2e_special.py.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from unittest.mock import patch

import pytest

from elspais.server.spawner_watch import (
    Decision,
    SpawnerWatchdog,
    pid_alive,
    shutdown_decision,
)

# ---------------------------------------------------------------------------
# shutdown_decision: full matrix (spawner identity x alive x dirty x grace)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("spawner_pid", "alive", "count", "grace_expired", "expected"),
    [
        # No spawner identity (manual/explicit start): always keep,
        # regardless of everything else — TTL-only behavior preserved.
        (None, False, 0, True, Decision.KEEP),
        (None, False, 5, True, Decision.KEEP),
        (None, True, 0, False, Decision.KEEP),
        # Spawner alive: keep, dirty or clean.
        (1234, True, 0, False, Decision.KEEP),
        (1234, True, 7, True, Decision.KEEP),
        # Spawner dead + clean: exit immediately.
        (1234, False, 0, False, Decision.EXIT_CLEAN),
        (1234, False, 0, True, Decision.EXIT_CLEAN),
        # Spawner dead + dirty: bounded grace, then discard-exit.
        (1234, False, 3, False, Decision.WAIT_GRACE),
        (1234, False, 3, True, Decision.EXIT_DISCARD),
        # Unknown mutation count is treated as dirty (conservative).
        (1234, False, None, False, Decision.WAIT_GRACE),
        (1234, False, None, True, Decision.EXIT_DISCARD),
    ],
)
def test_shutdown_decision_matrix(spawner_pid, alive, count, grace_expired, expected):
    assert (
        shutdown_decision(
            spawner_pid=spawner_pid,
            spawner_alive=alive,
            mutation_count=count,
            grace_expired=grace_expired,
        )
        is expected
    )


# ---------------------------------------------------------------------------
# pid_alive
# ---------------------------------------------------------------------------


def test_pid_alive_own_process():
    assert pid_alive(os.getpid()) is True


def test_pid_alive_exited_process():
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    assert pid_alive(proc.pid) is False


def test_pid_alive_invalid_pids():
    assert pid_alive(0) is False
    assert pid_alive(-1) is False


# ---------------------------------------------------------------------------
# SpawnerWatchdog.check_once transitions
# ---------------------------------------------------------------------------


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _watchdog(alive_results, counts, clock, grace=300.0):
    """Build a watchdog with scripted liveness/count sequences."""
    alive_iter = iter(alive_results)
    count_iter = iter(counts)
    exits: list[str] = []

    wd = SpawnerWatchdog(
        spawner_pid=4321,
        mutation_count_fn=lambda: next(count_iter),
        interval_seconds=0.01,
        grace_seconds=grace,
        alive_fn=lambda pid: next(alive_iter),
        exit_fn=lambda: exits.append("exit"),
        clock=clock,
    )
    return wd, exits


def test_watchdog_alive_keeps(capsys):
    clock = _Clock()
    wd, exits = _watchdog([True], iter(()), clock)
    assert wd.check_once() is Decision.KEEP
    assert exits == []


def test_watchdog_dead_clean_exits(capsys):
    clock = _Clock()
    wd, exits = _watchdog([False], [0], clock)
    assert wd.check_once() is Decision.EXIT_CLEAN
    assert exits == ["exit"]
    err = capsys.readouterr().err
    assert "shutting down" in err


def test_watchdog_dead_dirty_waits_then_discards(capsys):
    clock = _Clock()
    wd, exits = _watchdog([False, False, False], [2, 2, 2], clock, grace=300.0)

    # First check after death: warn, extend, do not exit.
    assert wd.check_once() is Decision.WAIT_GRACE
    assert exits == []
    err = capsys.readouterr().err
    assert "WARNING" in err
    assert "2" in err
    assert "DISCARDED" in err  # loss risk visible in the log

    # Still inside grace: waits again, but warns only once.
    clock.now += 100
    assert wd.check_once() is Decision.WAIT_GRACE
    assert exits == []
    assert "WARNING" not in capsys.readouterr().err

    # Grace expired: exit without saving, loudly.
    clock.now += 300
    assert wd.check_once() is Decision.EXIT_DISCARD
    assert exits == ["exit"]
    err = capsys.readouterr().err
    assert "WARNING" in err
    assert "discarded" in err


def test_watchdog_spawner_recovery_resets_grace():
    """A spawner seen alive again resets the dirty-grace clock."""
    clock = _Clock()
    wd, exits = _watchdog([False, True, False, False], [1, 1, 1], clock, grace=300.0)

    assert wd.check_once() is Decision.WAIT_GRACE  # dead at t=1000
    clock.now += 200
    assert wd.check_once() is Decision.KEEP  # alive again -> reset
    clock.now += 200  # t=1400; without reset, grace would have expired
    assert wd.check_once() is Decision.WAIT_GRACE
    assert exits == []


def test_watchdog_mutation_count_error_treated_as_dirty():
    clock = _Clock()

    def boom():
        raise RuntimeError("graph unavailable")

    exits: list[str] = []
    wd = SpawnerWatchdog(
        spawner_pid=4321,
        mutation_count_fn=boom,
        grace_seconds=300.0,
        alive_fn=lambda pid: False,
        exit_fn=lambda: exits.append("exit"),
        clock=clock,
    )
    assert wd.check_once() is Decision.WAIT_GRACE
    assert exits == []


# ---------------------------------------------------------------------------
# Session identity: resolution, recording, and the explicit-start exemption
# ---------------------------------------------------------------------------


class TestSpawnerIdentityResolution:
    """Validates REQ-o00074-D: session identity is derived only from evidence
    available at the moment of starting, and when no session identity can be
    established the daemon starts with none rather than with an inferred one.
    """

    def test_REQ_o00074_D_env_override(self, monkeypatch):
        from elspais.mcp import daemon

        monkeypatch.setenv("ELSPAIS_SPAWNER_PID", "5555")
        assert daemon.resolve_spawner_pid() == 5555

    @pytest.mark.parametrize("value", ["not-a-pid", "0", "1", "-3"])
    def test_REQ_o00074_D_env_override_invalid(self, monkeypatch, value):
        from elspais.mcp import daemon

        monkeypatch.setenv("ELSPAIS_SPAWNER_PID", value)
        assert daemon.resolve_spawner_pid() is None

    def test_REQ_o00074_D_claude_ancestor(self, monkeypatch):
        from elspais.mcp import daemon

        monkeypatch.delenv("ELSPAIS_SPAWNER_PID", raising=False)
        monkeypatch.setenv("CLAUDECODE", "1")
        with patch(
            "elspais.mcp.daemon._iter_proc_ancestors",
            return_value=iter([(200, "zsh"), (300, "claude"), (400, "zsh")]),
        ):
            assert daemon.resolve_spawner_pid() == 300

    def test_REQ_o00074_D_no_session_identity(self, monkeypatch):
        """No env override, no Claude session, no tty -> None (TTL-only)."""
        from elspais.mcp import daemon

        monkeypatch.delenv("ELSPAIS_SPAWNER_PID", raising=False)
        monkeypatch.delenv("CLAUDECODE", raising=False)
        with patch("elspais.mcp.daemon._session_leader_has_tty", return_value=False):
            assert daemon.resolve_spawner_pid() is None

    def test_REQ_o00074_D_interactive_session_leader(self, monkeypatch):
        from elspais.mcp import daemon

        monkeypatch.delenv("ELSPAIS_SPAWNER_PID", raising=False)
        monkeypatch.delenv("CLAUDECODE", raising=False)
        with (
            patch("elspais.mcp.daemon.os.getsid", return_value=7777),
            patch("elspais.mcp.daemon._session_leader_has_tty", return_value=True),
        ):
            assert daemon.resolve_spawner_pid() == 7777


class TestImplicitStartRecordsSession:
    """Validates REQ-o00074-A: a daemon started implicitly on behalf of a
    session records the identity of that session at the moment it is started,
    so it can afterwards determine whether the session still exists.
    """

    def test_REQ_o00074_A_start_daemon_passes_spawner_env(self, tmp_path):
        from elspais.mcp.daemon import start_daemon

        popen_calls = []

        with (
            patch("elspais.mcp.daemon.stop_daemon"),
            patch(
                "elspais.mcp.daemon.subprocess.Popen",
                side_effect=lambda *a, **kw: popen_calls.append(kw),
            ),
            patch("elspais.mcp.daemon.time.time", side_effect=[0, 20, 20]),  # force timeout
        ):
            with pytest.raises(RuntimeError):
                start_daemon(tmp_path, ttl_minutes=1, spawner_pid=9876)

        assert popen_calls[0]["env"]["_ELSPAIS_SPAWNER_PID"] == "9876"

    def test_REQ_o00074_A_ensure_daemon_resolves_spawner(self, tmp_path):
        """The implicit CLI spawn path ties the daemon to the resolved session."""
        from elspais.mcp.daemon import ensure_daemon

        captured = {}

        def fake_start(repo_root, ttl_minutes, spawner_pid=None):
            captured["spawner_pid"] = spawner_pid
            return 12000

        with (
            patch("elspais.mcp.daemon.get_daemon_info", return_value=None),
            patch("elspais.mcp.daemon.get_cli_ttl", return_value=30),
            patch("elspais.mcp.daemon.resolve_spawner_pid", return_value=4242),
            patch("elspais.mcp.daemon.start_daemon", side_effect=fake_start),
        ):
            assert ensure_daemon(tmp_path) == 12000

        assert captured["spawner_pid"] == 4242


class TestSpawnerIdentityIsObservable:
    """Validates REQ-o00074-B: a recorded session identity is observable in the
    state record by which clients locate the daemon (``.elspais/daemon.json``).
    """

    def test_REQ_o00074_B_write_daemon_json_records_spawner_pid(self, tmp_path):
        from elspais.mcp.daemon import write_daemon_json

        path = write_daemon_json(
            repo_root=tmp_path, pid=111, port=222, server_type="daemon", spawner_pid=333
        )
        assert json.loads(path.read_text())["spawner_pid"] == 333


class TestExplicitStartRecordsNoSession:
    """Validates REQ-o00074-C: a daemon started explicitly rather than on behalf
    of a session records no session identity, and its lifetime remains governed
    solely by its idle timeout.
    """

    def test_REQ_o00074_C_write_daemon_json_omits_spawner_pid_when_absent(self, tmp_path):
        """Explicit starts (viewer, manual serve) record no spawner identity."""
        from elspais.mcp.daemon import write_daemon_json

        path = write_daemon_json(repo_root=tmp_path, pid=111, port=222, server_type="viewer")
        assert "spawner_pid" not in json.loads(path.read_text())

    def test_REQ_o00074_C_start_daemon_without_spawner_scrubs_env(self, tmp_path, monkeypatch):
        """Explicit starts must not inherit a stale spawner PID from the env."""
        from elspais.mcp.daemon import start_daemon

        monkeypatch.setenv("_ELSPAIS_SPAWNER_PID", "1212")
        popen_calls = []

        with (
            patch("elspais.mcp.daemon.stop_daemon"),
            patch(
                "elspais.mcp.daemon.subprocess.Popen",
                side_effect=lambda *a, **kw: popen_calls.append(kw),
            ),
            patch("elspais.mcp.daemon.time.time", side_effect=[0, 20, 20]),
        ):
            with pytest.raises(RuntimeError):
                start_daemon(tmp_path, ttl_minutes=1)

        assert "_ELSPAIS_SPAWNER_PID" not in popen_calls[0]["env"]

    def test_REQ_o00074_C_restart_daemon_spawns_without_spawner(self, tmp_path):
        """`elspais daemon restart` is an explicit start: no session tie."""
        from elspais.mcp.daemon import restart_daemon

        captured = {}

        def fake_start(repo_root, ttl_minutes, spawner_pid=None):
            captured["spawner_pid"] = spawner_pid
            return 12001

        with (
            patch("elspais.mcp.daemon.get_daemon_info", return_value=None),
            patch("elspais.mcp.daemon.get_cli_ttl", return_value=30),
            patch("elspais.mcp.daemon.start_daemon", side_effect=fake_start),
        ):
            result = restart_daemon(tmp_path)

        assert result["success"] is True
        assert captured["spawner_pid"] is None
