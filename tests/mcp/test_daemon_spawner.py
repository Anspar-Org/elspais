# Verifies: REQ-o00074-A+B+C+D+E+G+H+I
"""Daemon lifetime tests, verifying REQ-o00074 (Background Daemon Lifetime).

A daemon started on behalf of a session is bound to that session at the
moment it starts: the identity is resolved from evidence available then
(D), handed to the spawned process (A), recorded in the state record
clients read to find the daemon (B), and withheld entirely when the start
was explicit rather than session-driven (C).

Once the recorded session is gone the daemon terminates (E), discloses
any pending unsaved work honestly before doing so (G), treats a newly
applied change as proof that a writer adopted it and restarts the
interval (H), and never writes those pending changes to disk on its own
initiative (I).

Unit-level only: process liveness is faked (``alive_fn``) so the
decision matrix and watchdog transitions are exercised deterministically.
A subprocess-based e2e companion, including the idle-timeout independence
of assertion F, lives in tests/e2e/test_e2e_special.py.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from unittest.mock import MagicMock, patch

import pytest

from elspais.server.spawner_watch import (
    Decision,
    SpawnerWatchdog,
    pending_snapshot,
    pid_alive,
    shutdown_decision,
)

# ---------------------------------------------------------------------------
# Shared scaffolding
# ---------------------------------------------------------------------------


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class _ScriptedChecks:
    """Scripted liveness results and pending snapshots, one entry per check.

    One check reads the pending state more than once: outside the writers'
    lock for the activity comparison, and again inside the lock immediately
    before deciding. A scripted entry is therefore either a single
    ``(pending_count, activity_token)`` snapshot -- served to every read in
    that check, so count and token can never disagree -- or a *list* of
    snapshots, handed out in order, which scripts a state that changed
    between two reads of the same check.
    """

    def __init__(self, alive_results, pending_snapshots) -> None:
        self._alive = iter(alive_results)
        self._checks = iter(pending_snapshots)
        self._reads: list = []

    def alive(self, pid: int) -> bool:
        # alive_fn is called exactly once at the top of check_once, so it
        # marks the boundary between one logical check and the next.
        entry = next(self._checks, None)
        if entry is None:
            self._reads = []
        elif isinstance(entry, list):
            self._reads = list(entry)
        else:
            self._reads = [entry]
        return next(self._alive)

    def pending(self):
        if not self._reads:
            raise RuntimeError("no pending snapshot scripted for this check")
        if len(self._reads) > 1:
            return self._reads.pop(0)
        return self._reads[0]


def _watchdog(alive_results, pending_snapshots, clock, grace=300.0, lock=None):
    """Build a watchdog driven by a scripted check sequence.

    See ``_ScriptedChecks`` for the shape of ``pending_snapshots``.
    """
    script = _ScriptedChecks(alive_results, pending_snapshots)
    exits: list[str] = []

    wd = SpawnerWatchdog(
        spawner_pid=4321,
        pending_fn=script.pending,
        interval_seconds=0.01,
        grace_seconds=grace,
        alive_fn=script.alive,
        exit_fn=lambda: exits.append("exit"),
        clock=clock,
        lock=lock,
    )
    return wd, exits


# ---------------------------------------------------------------------------
# Termination while the recorded session is absent
# ---------------------------------------------------------------------------


class TestAbsentSessionTerminatesDaemon:
    """Validates REQ-o00074-E: while the session a daemon recorded is no longer
    present, the daemon terminates rather than keep serving indefinitely -- and,
    symmetrically, keeps serving while that session is still present.
    """

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
    def test_REQ_o00074_E_shutdown_decision_matrix(
        self, spawner_pid, alive, count, grace_expired, expected
    ):
        assert (
            shutdown_decision(
                spawner_pid=spawner_pid,
                spawner_alive=alive,
                mutation_count=count,
                grace_expired=grace_expired,
            )
            is expected
        )

    def test_REQ_o00074_E_pid_alive_own_process(self):
        assert pid_alive(os.getpid()) is True

    def test_REQ_o00074_E_pid_alive_exited_process(self):
        proc = subprocess.Popen([sys.executable, "-c", "pass"])
        proc.wait()
        assert pid_alive(proc.pid) is False

    def test_REQ_o00074_E_pid_alive_invalid_pids(self):
        assert pid_alive(0) is False
        assert pid_alive(-1) is False

    def test_REQ_o00074_E_live_session_keeps_daemon(self):
        """The negative case: a present session is never terminated."""
        clock = _Clock()
        wd, exits = _watchdog([True], iter(()), clock)
        assert wd.check_once() is Decision.KEEP
        assert exits == []

    def test_REQ_o00074_E_absent_session_with_no_pending_work_exits(self, capsys):
        clock = _Clock()
        wd, exits = _watchdog([False], [(0, None)], clock)
        assert wd.check_once() is Decision.EXIT_CLEAN
        assert exits == ["exit"]
        assert "shutting down" in capsys.readouterr().err

    def test_REQ_o00074_E_session_seen_present_again_resets_grace(self):
        """A session seen alive again resets the dirty-grace clock."""
        clock = _Clock()
        wd, exits = _watchdog(
            [False, True, False, False],
            [(1, "m1"), (1, "m1"), (1, "m1")],
            clock,
            grace=300.0,
        )

        assert wd.check_once() is Decision.WAIT_GRACE  # dead at t=1000
        clock.now += 200
        assert wd.check_once() is Decision.KEEP  # alive again -> reset
        clock.now += 200  # t=1400; without reset, grace would have expired
        assert wd.check_once() is Decision.WAIT_GRACE
        assert exits == []


class TestWatchdogSurvivesAFailedCheck:
    """Validates REQ-o00074-E: the obligation to terminate survives a check that
    fails. A check raising (a rebuild mid-flight, a transient OS error) must
    cost one interval, not the guard: a dead watchdog thread is silent, and the
    daemon it stopped watching outlives its session forever.
    """

    def test_REQ_o00074_E_failed_check_costs_one_interval_not_the_watchdog(self, request):
        calls: list[str] = []
        exits: list[str] = []
        state = {"alive": True}

        def alive_fn(pid: int) -> bool:
            calls.append("check")
            if len(calls) == 1:
                raise OSError("transient failure on the first check")
            return state["alive"]

        wd = SpawnerWatchdog(
            spawner_pid=4321,
            pending_fn=lambda: (0, 5),
            interval_seconds=0.01,
            grace_seconds=0.0,
            alive_fn=alive_fn,
            exit_fn=lambda: exits.append("exit"),
        )
        request.addfinalizer(wd.stop)
        wd.start()

        def _wait_for(predicate, what):
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                if predicate():
                    return
                time.sleep(0.005)
            pytest.fail(f"timed out waiting for {what} (checks={len(calls)}, exits={exits})")

        # The thread kept checking after the raise.
        _wait_for(lambda: len(calls) >= 3, "the watchdog to check again after a failed check")
        assert exits == []

        # And a later check still reaches -- and acts on -- a decision.
        state["alive"] = False
        _wait_for(lambda: exits == ["exit"], "the watchdog to terminate once the session is gone")


# ---------------------------------------------------------------------------
# Disclosure of pending work before termination
# ---------------------------------------------------------------------------


class TestPendingWorkIsDisclosed:
    """Validates REQ-o00074-G: a daemon holding unsaved in-memory changes does
    not terminate before disclosing how many changes are pending and the
    deadline after which they are lost.
    """

    def test_REQ_o00074_G_dirty_daemon_waits_then_discards(self, capsys):
        clock = _Clock()
        wd, exits = _watchdog(
            [False, False, False],
            [(2, "m1"), (2, "m1"), (2, "m1")],
            clock,
            grace=300.0,
        )

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

    def test_REQ_o00074_G_unknown_pending_count_treated_as_dirty(self):
        clock = _Clock()

        def boom():
            raise RuntimeError("graph unavailable")

        exits: list[str] = []
        wd = SpawnerWatchdog(
            spawner_pid=4321,
            pending_fn=boom,
            grace_seconds=300.0,
            alive_fn=lambda pid: False,
            exit_fn=lambda: exits.append("exit"),
            clock=clock,
        )
        assert wd.check_once() is Decision.WAIT_GRACE
        assert exits == []

    def test_REQ_o00074_G_warning_states_pending_count_and_deadline(self, capsys):
        """The disclosure names both quantities the requirement asks for."""
        clock = _Clock()
        wd, exits = _watchdog([False], [(7, "m7")], clock, grace=180.0)

        assert wd.check_once() is Decision.WAIT_GRACE
        assert exits == []
        err = capsys.readouterr().err
        assert "7" in err, f"pending count not disclosed: {err!r}"
        assert "180" in err, f"deadline not disclosed: {err!r}"


class TestTerminationDecidesUnderTheWritersLock:
    """Validates REQ-o00074-G: the count a termination acts on is the count at
    the moment of terminating, read while writers are excluded -- so a change
    accepted (and acknowledged to its writer) after the first read cannot be
    destroyed by a decision taken from the stale read.
    """

    def test_REQ_o00074_G_write_landing_after_the_clean_read_is_not_discarded(self, capsys):
        """A clean read then a write, before the exit: the daemon keeps serving."""
        clock = _Clock()
        # One check: outside the lock the log looks clean at revision 5;
        # inside it, a writer has landed one mutation and moved it to 6.
        wd, exits = _watchdog([False], [[(0, 5), (1, 6)]], clock)

        assert wd.check_once() is Decision.KEEP
        assert exits == [], "daemon terminated holding a mutation it had just acknowledged"
        assert "shutting down" not in capsys.readouterr().err

    def test_REQ_o00074_G_write_landing_in_the_gap_outranks_an_expired_grace(self, capsys):
        """An expired countdown does not license discarding a just-landed write."""
        clock = _Clock()
        wd, exits = _watchdog(
            [False, False],
            [(1, 5), [(1, 5), (2, 6)]],
            clock,
            grace=300.0,
        )

        assert wd.check_once() is Decision.WAIT_GRACE  # t=1000, deadline 1300
        capsys.readouterr()

        clock.now = 1400.0  # past the deadline
        assert wd.check_once() is Decision.KEEP
        assert exits == [], "expired grace discarded a mutation that landed after the read"

    def test_REQ_o00074_G_decision_is_taken_while_holding_the_writers_lock(self):
        """The terminate decision is bracketed by the lock the writers take."""
        events: list[str] = []

        class _RecordingLock:
            def __enter__(self):
                events.append("enter")
                return self

            def __exit__(self, *exc):
                events.append("exit")
                return False

        clock = _Clock()
        wd = SpawnerWatchdog(
            spawner_pid=4321,
            pending_fn=lambda: (0, 5),
            grace_seconds=300.0,
            alive_fn=lambda pid: False,
            exit_fn=lambda: events.append("terminate"),
            clock=clock,
            lock=_RecordingLock(),
        )

        assert wd.check_once() is Decision.EXIT_CLEAN
        assert events == [
            "enter",
            "terminate",
            "exit",
        ], f"terminate decision was not taken inside the writers' lock: {events}"


class TestPendingCountIsHonest:
    """Validates REQ-o00074-G: the disclosed count is the number actually
    pending, not a figure capped by how the daemon happens to query its log.
    """

    def test_REQ_o00074_G_snapshot_counts_every_pending_mutation(
        self, mutable_graph, canonical_federated_graph
    ):
        # The daemon's pending-count source is a named helper so both the
        # watchdog and this test read the same answer.
        fg = canonical_federated_graph
        assert fg.mutation_log.tail(0) == [], "fixture must start with no pending mutations"

        before_count, before_token = pending_snapshot(fg)
        assert before_count == 0

        for i in range(5):
            fg.update_title("REQ-p00001", f"User Authentication {i}")

        count, token = pending_snapshot(fg)
        assert count == 5, "disclosed count is not the number actually pending"
        # The token is the log's revision, not its tip: five appends moved
        # it five times, and it is comparable across checks.
        assert token == before_token + 5


# ---------------------------------------------------------------------------
# An applied change proves a writer is still present
# ---------------------------------------------------------------------------


class TestAppliedChangeProvesWriterPresent:
    """Validates REQ-o00074-H: a change applied after the daemon observed its
    recorded session absent counts as evidence a writer is still using the
    daemon and restarts the interval before termination -- while traffic that
    changes nothing does not.
    """

    def test_REQ_o00074_H_applied_change_restarts_the_interval(self, capsys):
        clock = _Clock()
        wd, exits = _watchdog(
            [False, False, False, False],
            [(2, "m1"), (3, "m2"), (3, "m2"), (3, "m2")],
            clock,
            grace=300.0,
        )

        # t=1000: session absent, work pending. Token recorded, not activity.
        assert wd.check_once() is Decision.WAIT_GRACE
        capsys.readouterr()

        # t=1100: a writer adopted the daemon and applied a change.
        clock.now = 1100.0
        assert wd.check_once() is Decision.KEEP
        assert exits == []

        # t=1350: past the original 1000+300 deadline. Still serving.
        clock.now = 1350.0
        assert wd.check_once() is Decision.WAIT_GRACE
        assert exits == [], "adopted writer's daemon was terminated on the stale deadline"
        assert "WARNING" in capsys.readouterr().err, "one-shot warning was not re-armed"

        # t=1701: past every candidate restart anchor. The reset is bounded,
        # not an immortality bug.
        clock.now = 1701.0
        assert wd.check_once() is Decision.EXIT_DISCARD
        assert exits == ["exit"]

    def test_REQ_o00074_H_unchanged_token_does_not_restart_the_interval(self):
        """A pure reader polling the daemon moves nothing and saves nothing."""
        clock = _Clock()
        wd, exits = _watchdog([False] * 4, [(2, "m1")] * 4, clock, grace=300.0)

        assert wd.check_once() is Decision.WAIT_GRACE  # t=1000
        clock.now = 1100.0
        assert wd.check_once() is Decision.WAIT_GRACE
        clock.now = 1200.0
        assert wd.check_once() is Decision.WAIT_GRACE
        assert exits == []

        clock.now = 1300.0
        assert wd.check_once() is Decision.EXIT_DISCARD
        assert exits == ["exit"], "polling kept an orphaned daemon alive past its deadline"


class TestUndoneWorkStillCountsAsActivity:
    """Validates REQ-o00074-H: a writer working in apply-then-undo cycles is
    still a writer. The log's tip returns to exactly where it was after such a
    pair, so an activity token derived from the tip reports that writer as
    absent and terminates a daemon somebody is actively using.
    """

    def test_REQ_o00074_H_apply_then_undo_moves_the_activity_token(
        self, mutable_graph, canonical_federated_graph
    ):
        fg = canonical_federated_graph
        assert fg.mutation_log.tail(0) == [], "fixture must start with no pending mutations"

        fg.update_title("REQ-p00001", "User Authentication (kept)")
        count_before, token_before = pending_snapshot(fg)
        tip_before = fg.mutation_log.tail(0)[-1].id

        fg.update_title("REQ-p00002", "Data Privacy (transient)")
        fg.undo_last()

        count_after, token_after = pending_snapshot(fg)
        assert count_after == count_before, "apply+undo did not restore the pending count"
        assert (
            fg.mutation_log.tail(0)[-1].id == tip_before
        ), "apply+undo did not restore the log tip -- the test no longer poses the problem"
        assert token_after != token_before, (
            "activity token did not move across an apply+undo pair: a writer working "
            "in that pattern reads as idle"
        )

        fg.undo_last()  # leave the log as the fixture handed it over
        assert fg.mutation_log.tail(0) == []

    def test_REQ_o00074_H_writer_undoing_between_checks_is_judged_active(
        self, mutable_graph, canonical_federated_graph
    ):
        """Applying and undoing between every check keeps the daemon serving."""
        fg = canonical_federated_graph
        baseline = len(fg.mutation_log.tail(0))
        fg.update_title("REQ-p00001", "User Authentication (pending)")

        clock = _Clock()
        exits: list[str] = []
        wd = SpawnerWatchdog(
            spawner_pid=4321,
            pending_fn=lambda: pending_snapshot(fg),
            grace_seconds=300.0,
            alive_fn=lambda pid: False,
            exit_fn=lambda: exits.append("exit"),
            clock=clock,
        )

        # t=1000: session absent, one mutation pending. Baseline token.
        assert wd.check_once() is Decision.WAIT_GRACE

        # The writer keeps working in apply-then-undo cycles, well past the
        # grace deadline the first check anchored.
        for offset in (200, 400, 600, 800):
            fg.update_title("REQ-p00002", f"Data Privacy (draft {offset})")
            fg.undo_last()
            clock.now = 1000.0 + offset
            assert (
                wd.check_once() is Decision.KEEP
            ), "a writer applying and undoing between checks was judged idle"
        assert exits == []

        fg.undo_last()  # leave the log as the fixture handed it over
        assert len(fg.mutation_log.tail(0)) == baseline


# ---------------------------------------------------------------------------
# Termination never persists on the daemon's own initiative
# ---------------------------------------------------------------------------


class TestTerminationDoesNotPersist:
    """Validates REQ-o00074-I: a daemon does not persist pending changes on its
    own initiative while terminating; persisting them remains an act a caller
    requests.
    """

    def test_REQ_o00074_I_discard_exit_writes_no_spec_files(
        self, mutable_graph, canonical_federated_graph, hht_like_fixture
    ):
        fg = canonical_federated_graph
        fg.update_title("REQ-p00002", "Data Privacy (unsaved)")

        spec_files = sorted((hht_like_fixture / "spec").rglob("*.md"))
        assert spec_files, "fixture spec tree is empty"
        before = {p: p.stat().st_mtime_ns for p in spec_files}

        clock = _Clock()
        exits: list[str] = []
        wd = SpawnerWatchdog(
            spawner_pid=4321,
            pending_fn=lambda: pending_snapshot(fg),
            grace_seconds=300.0,
            alive_fn=lambda pid: False,
            exit_fn=lambda: exits.append("exit"),
            clock=clock,
        )

        assert wd.check_once() is Decision.WAIT_GRACE
        clock.now += 400
        assert wd.check_once() is Decision.EXIT_DISCARD
        assert exits == ["exit"]

        after = {p: p.stat().st_mtime_ns for p in spec_files}
        assert after == before, "terminating daemon wrote spec files no caller asked it to write"


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


class TestUnusableSpawnerIdentityIsRefused:
    """Validates REQ-o00074-D: a handed-over PID at or below the floor the
    resolver applies names no session -- pid 1 is init, whose death never comes,
    and 0/negative are not process identities at all. The daemon starts with no
    session identity rather than watching one, which is the TTL-only behavior
    the requirement asks for when no identity can be established.
    """

    def _spawner_pids_watched(self, monkeypatch, tmp_path, env_value):
        """Run the daemon's startup path and report the PIDs it set a watch on."""
        from elspais.mcp import server as mcp_server

        monkeypatch.delenv("_ELSPAIS_DAEMON_JSON", raising=False)
        monkeypatch.setenv("_ELSPAIS_SPAWNER_PID", env_value)

        watched: list[int] = []

        class _StubWatchdog:
            def __init__(self, spawner_pid, **kwargs):
                watched.append(spawner_pid)

            def start(self):
                pass

        with (
            patch("elspais.server.state.AppState.from_config", return_value=MagicMock()),
            patch("elspais.server.app.create_app", return_value=MagicMock()),
            patch("elspais.server.spawner_watch.SpawnerWatchdog", _StubWatchdog),
            patch("uvicorn.Config", return_value=MagicMock()),
            patch("uvicorn.Server", return_value=MagicMock()),
            patch("anyio.run"),
        ):
            mcp_server.run_server(working_dir=tmp_path, transport="streamable-http", port=59999)
        return watched

    @pytest.mark.parametrize("value", ["1", "0", "-3", "not-a-pid"])
    def test_REQ_o00074_D_unusable_spawner_pid_starts_no_watchdog(
        self, monkeypatch, tmp_path, value
    ):
        assert (
            self._spawner_pids_watched(monkeypatch, tmp_path, value) == []
        ), f"daemon watched a pid it cannot learn anything from: {value!r}"

    def test_REQ_o00074_D_real_spawner_pid_is_watched(self, monkeypatch, tmp_path):
        """The control: a usable identity does produce a watch on that pid."""
        assert self._spawner_pids_watched(monkeypatch, tmp_path, "5555") == [5555]


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
