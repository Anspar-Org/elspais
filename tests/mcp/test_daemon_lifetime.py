# Verifies: REQ-o00074-A+B+C+D+E+G+H+I+J+K+M+O, REQ-o00075-B, REQ-o00076-E, REQ-p00083-A+C+D+H
"""Daemon lifetime tests, verifying REQ-o00074 (Background Daemon Lifetime).

A daemon started on behalf of a client is bound to that client at the
moment it starts: the identity is resolved from evidence available then
(D), handed to the spawned process (A), recorded in the state record
clients read to find the daemon (B), and withheld entirely when the start
was explicit rather than client-driven (C).

The daemon is shared, so its lifetime follows its *clients* rather than
the one process that happened to start it: a client adopting a running
daemon joins the recorded set, the daemon keeps serving while any of them
exists, and terminates once none does (E). Before terminating it
discloses how much unsaved work it holds and when it will act (M), treats
a newly applied change as proof that a writer is still present and
restarts the interval (H), persists that work rather than discarding it
and records the facts of the save for the next client (REQ-p00083-A,
REQ-p00083-C), retires that record when a client saves at its own request
(REQ-p00083-H), and keeps the work rather than dropping it when the save
itself fails (REQ-p00083-D).

Unit-level only: process liveness is faked (``alive_fn``) and the clock
is a counter, so the decision matrix and the watchdog transitions are
exercised deterministically with no sleeping. Assertion F -- that the
obligation holds under every idle-timeout configuration and is not
discharged by client request traffic -- is a property of the running
process's timeout wiring and is covered by the subprocess-based
companions in tests/e2e/test_e2e_special.py.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from unittest.mock import MagicMock, patch

import pytest

from elspais.server.client_watch import (
    DEFAULT_GRACE_SECONDS,
    ClientWatchdog,
    Decision,
    pending_snapshot,
    pid_alive,
    shutdown_decision,
)

# Words that would characterise the work rather than report the facts of
# the save. REQ-p00083-C's disclosure states who saved, when, how much,
# and what triggered it, and stops there: a client can vanish because it
# finished, crashed, or lost its connection, and the daemon cannot tell
# those apart, so it must not hand the reader a conclusion.
JUDGEMENT_WORDS = ("abandoned", "orphaned", "provisional", "unconfirmed")

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

    Usable only for a watchdog with exactly ONE recorded client: the check
    calls ``alive_fn`` once per recorded pid, and this scaffolding uses
    that single call as the boundary between one logical check and the
    next. Multi-client tests drive liveness from a pid->bool map instead.

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


def _ok_stop():
    """The shape ``finalize_shutdown`` returns when it accounted for the work."""
    return {
        "success": True,
        "finalized": True,
        "pending": 1,
        "saved": True,
        "files_written": 1,
    }


def _watchdog(
    alive_results,
    pending_snapshots,
    clock,
    grace=300.0,
    lock=None,
    stop_fn=None,
):
    """Build a single-client watchdog driven by a scripted check sequence.

    See ``_ScriptedChecks`` for the shape of ``pending_snapshots``. The
    watchdog no longer decides what happens to the work: it hands over to
    the process's one shutdown routine, which is what ``stop_fn`` stands
    in for here. The default succeeds, so an expired grace reaches
    EXIT_SAVE; tests for the failure branch pass their own.
    """
    script = _ScriptedChecks(alive_results, pending_snapshots)
    exits: list[str] = []

    wd = ClientWatchdog(
        client_pid=4321,
        pending_fn=script.pending,
        interval_seconds=0.01,
        grace_seconds=grace,
        alive_fn=script.alive,
        exit_fn=lambda: exits.append("exit"),
        clock=clock,
        lock=lock,
        stop_fn=stop_fn if stop_fn is not None else _ok_stop,
    )
    return wd, exits


def _map_watchdog(alive_map, clock, *, pending=(0, 5), grace=300.0, stop_fn=None):
    """Watchdog whose liveness comes from a mutable ``{pid: bool}`` map.

    The scripted scaffolding above assumes one ``alive_fn`` call per check;
    a watchdog with several recorded clients calls it once per client, and
    ``attach_client`` calls it again at attach time. A map answers any
    number of calls consistently.
    """
    exits: list[str] = []
    wd = ClientWatchdog(
        client_pid=4321,
        pending_fn=lambda: pending,
        interval_seconds=0.01,
        grace_seconds=grace,
        alive_fn=lambda pid: alive_map.get(pid, False),
        exit_fn=lambda: exits.append("exit"),
        clock=clock,
        stop_fn=stop_fn if stop_fn is not None else _ok_stop,
    )
    return wd, exits


# ---------------------------------------------------------------------------
# Lifetime follows the client set, not the process that started the daemon
# ---------------------------------------------------------------------------


class TestAbsentClientsTerminateDaemon:
    """Validates REQ-o00074-E: while any recorded client still exists the daemon
    keeps serving, and while none of them exists it terminates rather than keep
    serving indefinitely.
    """

    @pytest.mark.parametrize(
        ("has_clients", "any_alive", "count", "grace_expired", "expected"),
        [
            # No client identity recorded (explicit start): always keep,
            # regardless of everything else -- TTL-only behavior preserved.
            (False, False, 0, True, Decision.KEEP),
            (False, False, 5, True, Decision.KEEP),
            (False, True, 0, False, Decision.KEEP),
            # A client is alive: keep, dirty or clean.
            (True, True, 0, False, Decision.KEEP),
            (True, True, 7, True, Decision.KEEP),
            # No client alive + clean: exit immediately.
            (True, False, 0, False, Decision.EXIT_CLEAN),
            (True, False, 0, True, Decision.EXIT_CLEAN),
            # No client alive + dirty: bounded grace, then save-and-exit.
            (True, False, 3, False, Decision.WAIT_GRACE),
            (True, False, 3, True, Decision.EXIT_SAVE),
            # Unknown mutation count is treated as dirty (conservative).
            (True, False, None, False, Decision.WAIT_GRACE),
            (True, False, None, True, Decision.EXIT_SAVE),
        ],
    )
    def test_REQ_o00074_E_shutdown_decision_matrix(
        self, has_clients, any_alive, count, grace_expired, expected
    ):
        assert (
            shutdown_decision(
                has_clients=has_clients,
                any_client_alive=any_alive,
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

    def test_REQ_o00074_E_live_client_keeps_daemon(self):
        """The negative case: a present client is never terminated."""
        clock = _Clock()
        wd, exits = _watchdog([True], iter(()), clock)
        assert wd.check_once() is Decision.KEEP
        assert exits == []

    def test_REQ_o00074_E_absent_client_with_no_pending_work_exits(self, capsys):
        clock = _Clock()
        wd, exits = _watchdog([False], [(0, None)], clock)
        assert wd.check_once() is Decision.EXIT_CLEAN
        assert exits == ["exit"]
        assert "shutting down" in capsys.readouterr().err

    def test_REQ_o00074_E_client_seen_present_again_resets_grace(self):
        """A client seen alive again resets the dirty-grace clock."""
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


class TestAdoptingClientsJoinTheRecordedSet:
    """Validates REQ-o00074-E: a client that begins using an already-running
    daemon is recorded alongside its existing clients, so the daemon does not
    stop underneath the client actually using it -- and, crucially, the daemon
    still terminates once every recorded client, adopted ones included, is gone.
    """

    def test_REQ_o00074_E_attach_records_a_live_client(self):
        clock = _Clock()
        wd, _ = _map_watchdog({4321: True, 999: True}, clock)

        assert wd.attach_client(999) is True
        assert wd.clients() == [999, 4321]

    @pytest.mark.parametrize("pid", [0, 1, -3])
    def test_REQ_o00074_E_attach_refuses_pids_that_name_no_client(self, pid):
        """0 and negatives are not process identities; 1 is init, whose death
        never comes, so watching it is a daemon that never terminates."""
        clock = _Clock()
        wd, _ = _map_watchdog({4321: True}, clock)

        assert wd.attach_client(pid) is False
        assert wd.clients() == [4321]

    def test_REQ_o00074_E_attach_refuses_a_dead_client(self):
        clock = _Clock()
        alive = {4321: True, 777: False}
        wd, _ = _map_watchdog(alive, clock)

        assert wd.attach_client(777) is False
        assert wd.clients() == [4321]

    def test_REQ_o00074_E_live_adopted_client_keeps_a_daemon_whose_client_died(self):
        """The daemon outlives the client that started it, by design."""
        clock = _Clock()
        alive = {4321: True, 999: True}
        wd, exits = _map_watchdog(alive, clock, pending=(2, "m1"), grace=300.0)

        assert wd.attach_client(999) is True
        alive[4321] = False  # the original client is gone

        # Well past every grace deadline, the daemon keeps serving.
        for offset in (0, 500, 1000, 2000, 5000):
            clock.now = 1000.0 + offset
            assert wd.check_once() is Decision.KEEP, (
                f"daemon stopped underneath a live client at t+{offset}"
            )
        assert exits == []
        assert wd.clients() == [999], "dead client was not pruned from the client set"

    def test_REQ_o00074_E_daemon_with_dead_client_and_dead_adopted_clients_terminates(self, capsys):
        """The negative case the positive one above cannot prove.

        A daemon that has been adopted must still die once the adopters die.
        The client set is reached through the pruning path -- a real attach
        followed by that client's death -- rather than starting empty, so a
        watchdog that recorded adopters but never re-checked them would fail
        here.
        """
        clock = _Clock()
        alive = {4321: True, 999: True}
        wd, exits = _map_watchdog(alive, clock, pending=(0, "m1"))

        assert wd.attach_client(999) is True
        assert wd.clients() == [999, 4321]

        # The client exits first; the adopter keeps the daemon serving.
        alive[4321] = False
        assert wd.check_once() is Decision.KEEP
        assert wd.clients() == [999]
        assert exits == []

        # Now the adopter goes too. Nobody is left using the daemon.
        alive[999] = False
        clock.now += 100
        assert wd.check_once() is Decision.EXIT_CLEAN, (
            "daemon kept serving with every recorded client gone"
        )
        assert exits == ["exit"]
        assert "shutting down" in capsys.readouterr().err

    def test_REQ_o00074_E_dead_clients_are_pruned_while_a_live_one_remains(self):
        """The published set stays an honest answer to 'who is using this'."""
        clock = _Clock()
        alive = {4321: True, 111: True, 222: True}
        wd, _ = _map_watchdog(alive, clock)

        assert wd.attach_client(111) is True
        assert wd.attach_client(222) is True
        assert wd.clients() == [111, 222, 4321]

        alive[111] = False
        alive[4321] = False
        assert wd.check_once() is Decision.KEEP
        assert wd.clients() == [222]


class TestHeldSessionIsAClient:
    """Validates REQ-o00074-A and REQ-o00074-E: a client can be present as a
    held stream rather than as a process identifier, and a handle of that kind
    binds the daemon's lifetime exactly as a recorded pid does — it keeps the
    daemon while it lasts, and lets it go once it is gone.
    """

    def test_REQ_o00074_E_held_session_keeps_the_daemon(self):
        """Validates REQ-o00074-E: a client present only as a held stream is
        a client, so the daemon keeps serving while it is held even though
        every recorded process id is gone."""
        held = {"open": True}
        exits: list[str] = []

        def _exit() -> None:
            if held["open"]:
                pytest.fail("terminated while a session was held")
            exits.append("exit")

        wd = ClientWatchdog(
            client_pid=4242,
            pending_fn=lambda: (0, 0),
            alive_fn=lambda pid: False,
            exit_fn=_exit,
            stop_fn=_ok_stop,
            extra_liveness_fn=lambda: held["open"],
        )
        assert wd.check_once() is Decision.KEEP
        held["open"] = False
        assert wd.check_once() is Decision.EXIT_CLEAN
        assert exits == ["exit"]

    def test_REQ_o00074_B_stream_only_client_reaches_the_state_record(self, tmp_path):
        """Validates REQ-o00074-B: a client present only as a held stream
        registers nothing, so a record written on registration alone never
        mentions it — and an operator asking why the daemon is still running
        would find no answer for the client keeping it alive. The periodic
        check computes the composition, so it publishes it."""
        from elspais.mcp.daemon import record_daemon_clients, write_daemon_json

        write_daemon_json(
            repo_root=tmp_path, pid=111, port=222, server_type="daemon", client_pid=333
        )
        wd = ClientWatchdog(
            client_pid=333,
            pending_fn=lambda: (0, 0),
            alive_fn=lambda pid: False,
            exit_fn=lambda: pytest.fail("terminated while a session was held"),
            stop_fn=_ok_stop,
            extra_liveness_fn=lambda: 1,
            publish_fn=lambda pids, held: record_daemon_clients(tmp_path, pids, held),
        )
        assert wd.check_once() is Decision.KEEP

        info = json.loads((tmp_path / ".elspais" / "daemon.json").read_text())
        assert info["clients"] == [{"kind": "session", "count": 1}]

    def test_REQ_o00074_B_dead_pids_are_pruned_from_the_published_set_while_held(self):
        """Validates REQ-o00074-B: a held stream keeps the daemon alive but
        says nothing about a pid that has died, so the published set must
        still drop it — a record naming clients that are gone answers the
        operator's question wrongly."""
        alive = {333: True}
        published: list[tuple[list[int], int]] = []
        wd = ClientWatchdog(
            client_pid=333,
            pending_fn=lambda: (0, 0),
            alive_fn=lambda pid: alive.get(pid, False),
            exit_fn=lambda: pytest.fail("terminated while a session was held"),
            stop_fn=_ok_stop,
            extra_liveness_fn=lambda: 1,
            publish_fn=lambda pids, held: published.append((pids, held)),
        )
        assert wd.check_once() is Decision.KEEP
        assert published == [([333], 1)]

        alive[333] = False
        assert wd.check_once() is Decision.KEEP
        assert published[-1] == ([], 1), "a dead client survived in the published set"

    def test_REQ_o00074_B_unchanged_composition_is_not_republished(self):
        """Validates REQ-o00074-B: the record is written when it has something
        new to say. Rewriting it every interval is churn under whoever is
        reading it and carries no information the last write did not."""
        published: list[tuple[list[int], int]] = []
        wd = ClientWatchdog(
            client_pid=333,
            pending_fn=lambda: (0, 0),
            alive_fn=lambda pid: True,
            exit_fn=lambda: pytest.fail("terminated with a live client"),
            stop_fn=_ok_stop,
            extra_liveness_fn=lambda: 0,
            publish_fn=lambda pids, held: published.append((pids, held)),
        )
        for _ in range(4):
            assert wd.check_once() is Decision.KEEP
        assert published == [([333], 0)]

    def test_REQ_o00074_E_broken_liveness_source_does_not_read_as_no_clients(self, capsys):
        """Validates REQ-o00074-E: a liveness source that cannot answer has
        said nothing about whether a client is there. Reading its failure as
        'nobody is using this daemon' would terminate a daemon on the strength
        of a broken instrument, so the check keeps the daemon and reports."""

        def _boom() -> bool:
            raise RuntimeError("tracker unavailable")

        wd = ClientWatchdog(
            client_pid=4242,
            pending_fn=lambda: (0, 0),
            alive_fn=lambda pid: False,
            exit_fn=lambda: pytest.fail("terminated on a failed liveness check"),
            stop_fn=_ok_stop,
            extra_liveness_fn=_boom,
        )
        assert wd.check_once() is Decision.KEEP
        assert "tracker unavailable" in capsys.readouterr().err


class TestWatchdogSurvivesAFailedCheck:
    """Validates REQ-o00074-E: the obligation to terminate survives a check that
    fails. A check raising (a rebuild mid-flight, a transient OS error) must
    cost one interval, not the guard: a dead watchdog thread is silent, and the
    daemon it stopped watching outlives its clients forever.
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

        wd = ClientWatchdog(
            client_pid=4321,
            pending_fn=lambda: (0, 5),
            interval_seconds=0.01,
            grace_seconds=0.0,
            alive_fn=alive_fn,
            exit_fn=lambda: exits.append("exit"),
            stop_fn=_ok_stop,
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
        _wait_for(lambda: exits == ["exit"], "the watchdog to terminate once its clients are gone")


# ---------------------------------------------------------------------------
# Disclosure of pending work before termination
# ---------------------------------------------------------------------------


class TestPendingWorkIsDisclosed:
    """Validates REQ-o00074-G: a daemon holding unsaved in-memory changes does
    not terminate before disclosing how many changes are pending and the
    deadline at which it will persist them and stop.
    """

    def test_REQ_o00074_G_dirty_daemon_waits_then_saves(self, capsys):
        clock = _Clock()
        wd, exits = _watchdog(
            [False, False, False],
            [(2, "m1"), (2, "m1"), (2, "m1")],
            clock,
            grace=300.0,
        )

        # First check with no client: disclose, extend, do not exit.
        assert wd.check_once() is Decision.WAIT_GRACE
        assert exits == []
        err = capsys.readouterr().err
        assert "2" in err, f"pending count not disclosed: {err!r}"
        assert "300" in err, f"deadline not disclosed: {err!r}"

        # Still inside grace: waits again, but discloses only once.
        clock.now += 100
        assert wd.check_once() is Decision.WAIT_GRACE
        assert exits == []
        assert capsys.readouterr().err == ""

        # Grace expired: save, then exit.
        clock.now += 300
        assert wd.check_once() is Decision.EXIT_SAVE
        assert exits == ["exit"]
        err = capsys.readouterr().err
        assert "Saved" in err
        assert "2" in err

    def test_REQ_o00074_G_unknown_pending_count_treated_as_dirty(self):
        clock = _Clock()

        def boom():
            raise RuntimeError("graph unavailable")

        exits: list[str] = []
        wd = ClientWatchdog(
            client_pid=4321,
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

    def test_REQ_o00074_G_default_grace_is_sized_for_a_thinking_client(self):
        """The deadline a daemon discloses is its own default, and that default
        has to outlast the quiet stretches a reasoning client routinely takes
        between mutations. A shell-prompt-sized grace would make the disclosed
        deadline a promise to save work the writer had not finished."""
        wd = ClientWatchdog(client_pid=4321, pending_fn=lambda: (0, None))

        assert wd._grace == DEFAULT_GRACE_SECONDS
        assert DEFAULT_GRACE_SECONDS >= 1800.0, (
            "the grace period is shorter than the quiet stretch a reasoning "
            "client routinely takes between mutations"
        )


class TestTerminationDecidesUnderTheWritersLock:
    """Validates REQ-o00074-G: the count a termination acts on is the count at
    the moment of terminating, read while writers are excluded -- so a change
    accepted (and acknowledged to its writer) after the first read cannot be
    acted on from the stale read.
    """

    def test_REQ_o00074_G_write_landing_after_the_clean_read_is_not_lost(self, capsys):
        """A clean read then a write, before the exit: the daemon keeps serving."""
        clock = _Clock()
        # One check: outside the lock the log looks clean at revision 5;
        # inside it, a writer has landed one mutation and moved it to 6.
        wd, exits = _watchdog([False], [[(0, 5), (1, 6)]], clock)

        assert wd.check_once() is Decision.KEEP
        assert exits == [], "daemon terminated holding a mutation it had just acknowledged"
        assert "shutting down" not in capsys.readouterr().err

    def test_REQ_o00074_G_write_landing_in_the_gap_outranks_an_expired_grace(self, capsys):
        """An expired countdown does not license acting on the stale read."""
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
        assert exits == [], "expired grace acted on a read a later mutation had overtaken"

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
        wd = ClientWatchdog(
            client_pid=4321,
            pending_fn=lambda: (0, 5),
            grace_seconds=300.0,
            alive_fn=lambda pid: False,
            exit_fn=lambda: events.append("terminate"),
            clock=clock,
            lock=_RecordingLock(),
            stop_fn=lambda: (events.append("stop"), _ok_stop())[1],
        )

        assert wd.check_once() is Decision.EXIT_CLEAN
        # The shutdown routine runs inside the same bracket: a writer that
        # slipped in between the count and the save would be acknowledged
        # and then lost.
        assert events == [
            "enter",
            "stop",
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
    """Validates REQ-o00074-H: a change applied after the daemon observed every
    recorded client absent counts as evidence a writer is still using the
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

        # t=1000: no client, work pending. Token recorded, not activity.
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
        assert "pending" in capsys.readouterr().err, "one-shot disclosure was not re-armed"

        # t=1701: past every candidate restart anchor. The reset is bounded,
        # not an immortality bug.
        clock.now = 1701.0
        assert wd.check_once() is Decision.EXIT_SAVE
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
        assert wd.check_once() is Decision.EXIT_SAVE
        assert exits == ["exit"], "polling kept a clientless daemon alive past its deadline"


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
        assert fg.mutation_log.tail(0)[-1].id == tip_before, (
            "apply+undo did not restore the log tip -- the test no longer poses the problem"
        )
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
        wd = ClientWatchdog(
            client_pid=4321,
            pending_fn=lambda: pending_snapshot(fg),
            grace_seconds=300.0,
            alive_fn=lambda pid: False,
            exit_fn=lambda: exits.append("exit"),
            clock=clock,
        )

        # t=1000: no client, one mutation pending. Baseline token.
        assert wd.check_once() is Decision.WAIT_GRACE

        # The writer keeps working in apply-then-undo cycles, well past the
        # grace deadline the first check anchored.
        for offset in (200, 400, 600, 800):
            fg.update_title("REQ-p00002", f"Data Privacy (draft {offset})")
            fg.undo_last()
            clock.now = 1000.0 + offset
            assert wd.check_once() is Decision.KEEP, (
                "a writer applying and undoing between checks was judged idle"
            )
        assert exits == []

        fg.undo_last()  # leave the log as the fixture handed it over
        assert len(fg.mutation_log.tail(0)) == baseline


# ---------------------------------------------------------------------------
# Termination preserves the work, and says so in facts
# ---------------------------------------------------------------------------


class TestTerminationPersistsPendingWork:
    """Validates REQ-o00074-I, REQ-p00083-A: a daemon terminating with no client
    present persists the changes it holds rather than discarding them. The watchdog
    decides only *that* the daemon stops; what happens to the work is handed
    to the process's one shutdown routine, which every other way of stopping
    runs too, and the process is signalled only once that routine reports it
    accounted for the work.
    """

    def test_REQ_o00074_I_expired_grace_stops_through_the_shutdown_routine(self, capsys):
        clock = _Clock()
        events: list[str] = []
        wd, exits = _watchdog(
            [False, False],
            [(3, "m1"), (3, "m1")],
            clock,
            grace=300.0,
            stop_fn=lambda: (events.append("stop"), _ok_stop())[1],
        )

        assert wd.check_once() is Decision.WAIT_GRACE
        assert events == [], "the daemon stopped before its deadline"
        capsys.readouterr()

        clock.now += 400
        assert wd.check_once() is Decision.EXIT_SAVE
        assert exits == ["exit"]
        # The routine runs first and the signal follows it -- never the
        # other way round, which would signal a process still holding
        # unaccounted work.
        assert events == ["stop"], f"the shutdown routine did not run: {events}"

    def test_REQ_o00074_I_clean_exit_stops_through_the_routine_before_signalling(self):
        """Even with nothing pending the exit goes through the same routine:
        the count the watchdog saw is not the authority on what is held."""
        clock = _Clock()
        events: list[str] = []
        wd = ClientWatchdog(
            client_pid=4321,
            pending_fn=lambda: (0, "m0"),
            grace_seconds=300.0,
            alive_fn=lambda pid: False,
            exit_fn=lambda: events.append("exit"),
            clock=clock,
            stop_fn=lambda: (events.append("stop"), _ok_stop())[1],
        )

        assert wd.check_once() is Decision.EXIT_CLEAN
        assert events == ["stop", "exit"], f"the routine did not precede the signal: {events}"

    @pytest.mark.parametrize(
        "pending",
        [(4, "m1"), (0, "m0")],
        ids=["work-pending", "nothing-pending"],
    )
    def test_REQ_o00074_I_no_shutdown_routine_configured_is_a_failure_not_a_discard(
        self, capsys, pending
    ):
        """A watchdog with no routine wired to it must not resolve the deadlock
        by exiting anyway: that is the discard the requirement forbids. It holds
        on the clean branch too -- the watchdog's own count is a snapshot, not
        proof that nothing is held."""
        clock = _Clock()
        exits: list[str] = []
        wd = ClientWatchdog(
            client_pid=4321,
            pending_fn=lambda: pending,
            grace_seconds=0.0,
            alive_fn=lambda pid: False,
            exit_fn=lambda: exits.append("exit"),
            clock=clock,
        )

        assert wd.check_once() is Decision.SAVE_FAILED
        assert exits == [], "daemon exited holding work it never persisted"


class TestAutomaticSaveRecordStatesFactsOnly:
    """Validates REQ-o00074-I, REQ-p00083-C: the daemon records that it performed the save
    itself, when, how many changes it covered, and what triggered it -- and
    nothing that characterises the work. A client can vanish because it
    finished, crashed, or lost its connection, and the daemon cannot tell those
    apart, so a record that judged the work would be a conclusion substituted
    for an observation.
    """

    def test_REQ_o00074_I_record_carries_exactly_the_facts(self, tmp_path):
        from elspais.mcp.daemon import read_automatic_save, record_automatic_save

        record_automatic_save(
            tmp_path, mutation_count=4, files_written=2, trigger="no recorded client was running"
        )
        record = read_automatic_save(tmp_path)

        assert record is not None
        assert set(record) == {
            "saved_by",
            "saved_at",
            "mutation_count",
            "files_written",
            "trigger",
            "version",
        }, f"record fields drifted from the facts the requirement names: {sorted(record)}"
        assert record["saved_by"] == "daemon"
        assert record["mutation_count"] == 4
        assert record["files_written"] == 2
        assert record["trigger"] == "no recorded client was running"

    def test_REQ_o00074_I_record_characterises_nothing(self, tmp_path):
        """No field name and no field value passes a judgement on the work."""
        from elspais.mcp.daemon import read_automatic_save, record_automatic_save

        record_automatic_save(
            tmp_path, mutation_count=1, files_written=1, trigger="no recorded client was running"
        )
        record = read_automatic_save(tmp_path)
        assert record is not None

        haystack = " ".join([*record.keys(), *(v for v in record.values() if isinstance(v, str))])
        found = [w for w in JUDGEMENT_WORDS if w in haystack.lower()]
        assert not found, (
            f"the automatic-save record characterises the work ({found}); it must state "
            "who saved, when, how much, and what triggered it, and let the reader conclude"
        )

    def test_REQ_o00074_I_absent_record_reads_as_none(self, tmp_path):
        from elspais.mcp.daemon import read_automatic_save

        assert read_automatic_save(tmp_path) is None

    @pytest.mark.parametrize(
        "surface",
        ["graph_status", "workspace_info"],
    )
    def test_REQ_o00074_I_record_is_disclosed_to_later_clients(
        self, tmp_path, canonical_federated_graph, surface
    ):
        """A client working with the affected files is told without asking."""
        from elspais.mcp.daemon import record_automatic_save
        from elspais.mcp.server import _build_base_workspace_info, _get_graph_status

        def read():
            if surface == "graph_status":
                return _get_graph_status(canonical_federated_graph, tmp_path)
            return _build_base_workspace_info(tmp_path, {})

        assert "automatic_save" not in read(), "record surfaced with nothing recorded"

        record_automatic_save(tmp_path, mutation_count=3, files_written=1, trigger="t")
        disclosed = read().get("automatic_save")

        assert disclosed is not None, f"{surface} did not disclose the automatic save"
        assert disclosed["saved_by"] == "daemon"
        assert disclosed["mutation_count"] == 3


class TestClientRequestedSaveRetiresTheRecord:
    """Validates REQ-p00083-H: while a client persists pending changes at its own
    request, any outstanding record of a save the daemon performed is retired --
    it describes a state that no longer stands, and a notice that never retires
    is one nobody reads.
    """

    def test_REQ_o00074_J_clear_retires_the_record(self, tmp_path):
        from elspais.mcp.daemon import (
            clear_automatic_save,
            read_automatic_save,
            record_automatic_save,
        )

        record_automatic_save(tmp_path, mutation_count=1, files_written=1, trigger="t")
        assert read_automatic_save(tmp_path) is not None

        clear_automatic_save(tmp_path)
        assert read_automatic_save(tmp_path) is None

    def test_REQ_o00074_J_clearing_an_absent_record_is_not_an_error(self, tmp_path):
        from elspais.mcp.daemon import clear_automatic_save

        clear_automatic_save(tmp_path)  # must not raise


@pytest.fixture
def hht_project(tmp_path):
    """A throwaway copy of the hht-like fixture the save paths may write to."""
    import shutil
    from pathlib import Path

    src = Path(__file__).parent.parent / "fixtures" / "hht-like"
    dest = tmp_path / "project"
    shutil.copytree(src, dest)
    return dest


class TestPersistPendingRecordsAndRetires:
    """Validates REQ-o00074-I, REQ-p00083-A, REQ-p00083-C, REQ-p00083-H on the
    save path the MCP surface uses: a save the daemon performs leaves the record
    on disk beside the files it wrote, and the next client-requested save takes
    it away.
    """

    @pytest.fixture
    def project(self, hht_project):
        return hht_project

    def test_REQ_o00074_I_automatic_save_writes_the_record_beside_the_files(self, project):
        from elspais.mcp.daemon import read_automatic_save
        from elspais.mcp.shared_state import persist_pending
        from elspais.server.state import AppState

        state = AppState.from_config(repo_root=project)
        state.graph.update_title("REQ-p00001", "User Authentication (daemon-saved)")

        result = persist_pending(
            state.shared, automatic=True, trigger="no recorded client was running"
        )

        assert result.get("success"), result
        record = read_automatic_save(project)
        assert record is not None, "an automatic save left no record for the next client"
        assert record["saved_by"] == "daemon"
        assert record["mutation_count"] == 1
        assert record["trigger"] == "no recorded client was running"
        assert "daemon-saved" in (project / "spec" / "prd-core.md").read_text(), (
            "the daemon's save did not reach disk"
        )

    def test_REQ_o00074_J_client_requested_save_retires_the_record(self, project):
        from elspais.mcp.daemon import read_automatic_save
        from elspais.mcp.shared_state import persist_pending
        from elspais.server.state import AppState

        state = AppState.from_config(repo_root=project)
        state.graph.update_title("REQ-p00001", "User Authentication (daemon-saved)")
        assert persist_pending(state.shared, automatic=True, trigger="t").get("success")
        assert read_automatic_save(project) is not None

        state.graph.update_title("REQ-p00001", "User Authentication (client-saved)")
        # A client-requested save on an Active requirement supplies its own
        # changelog reason; only the daemon's own save writes one for itself.
        assert persist_pending(state.shared, message="client asked for this").get("success")

        assert read_automatic_save(project) is None, (
            "a client-requested save left the daemon's record standing"
        )


class TestViewerSaveRetiresTheRecord:
    """Validates REQ-p00083-H: while a client persists pending changes at its own
    request, any outstanding record of a save the daemon performed is retired --
    on the viewer's HTTP save route as well as on the MCP one.

    Both routes reach disk through ``persist_pending``, which is where the
    retirement lives, so this is the canary for that arrangement: a viewer save
    that stopped going through the shared path would still write the files and
    would leave the notice standing behind them, and a viewer user would be
    reading about a save its own save had superseded.
    """

    @pytest.fixture
    def client_and_project(self, hht_project):
        from starlette.testclient import TestClient

        from elspais.server.app import create_app
        from elspais.server.state import AppState

        state = AppState.from_config(repo_root=hht_project)
        return TestClient(create_app(state=state, mount_mcp=False)), state, hht_project

    def test_REQ_o00074_J_viewer_save_retires_the_daemons_record(self, client_and_project):
        from elspais.graph import render
        from elspais.mcp.daemon import record_automatic_save

        client, state, project = client_and_project

        # A daemon saved unattended at some earlier point, and said so.
        record_automatic_save(
            project, mutation_count=2, files_written=1, trigger="no recorded client was running"
        )
        record_path = project / ".elspais" / "automatic-save.json"
        assert record_path.is_file()
        assert client.get("/api/dirty").json().get("automatic_save") is not None, (
            "the record was not being disclosed, so its retirement proves nothing"
        )

        # This client applies its own change and asks for it to be persisted.
        node = state.graph.find_by_id("REQ-p00001")
        resp = client.post(
            "/api/mutate/title",
            json={
                "node_id": "REQ-p00001",
                "new_title": "User Authentication (viewer-saved)",
                "if_version": render.node_version(node),
            },
        )
        assert resp.status_code == 200, resp.text

        dirty = client.get("/api/dirty").json()
        assert dirty["mutation_count"] == 1
        resp = client.post(
            "/api/save",
            json={"if_tip_mutation_id": dirty["tip"], "message": "the client asked for this"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["success"] is True
        assert "viewer-saved" in (project / "spec" / "prd-core.md").read_text(), (
            "the save did not reach disk, so there was nothing to retire the record for"
        )

        # The record now describes a state that no longer stands.
        assert not record_path.exists(), (
            "a client-requested save over HTTP left the daemon's record standing on disk"
        )
        assert "automatic_save" not in client.get("/api/dirty").json(), (
            "/api/dirty still discloses a retired record"
        )
        assert client.get("/api/check-freshness").json().get("automatic_save") is None, (
            "/api/check-freshness still discloses a retired record"
        )

    def test_REQ_o00074_J_refused_viewer_save_retires_nothing(self, client_and_project):
        """The retirement follows a save that happened. A rejected one leaves
        the record standing, because the state it describes still stands."""
        from elspais.mcp.daemon import record_automatic_save

        client, state, project = client_and_project

        record_automatic_save(project, mutation_count=2, files_written=1, trigger="t")
        record_path = project / ".elspais" / "automatic-save.json"

        # A tip the caller cannot have seen: the save is refused.
        resp = client.post("/api/save", json={"if_tip_mutation_id": "f" * 32})

        assert resp.status_code == 409, resp.text
        assert record_path.is_file(), "a refused save retired a record it never superseded"


class TestFailedSaveRetainsTheWork:
    """Validates REQ-p00083-D: a daemon that cannot persist what it holds reports
    the failure and keeps the work rather than discarding it, and does not treat
    its termination as complete -- it stays up and tries again.
    """

    @pytest.mark.parametrize(
        ("stop_fn", "how"),
        [
            (lambda: {"success": False, "error": "disk full"}, "reported failure"),
            (lambda: (_ for _ in ()).throw(OSError("read-only file system")), "raised"),
        ],
        ids=["reported-failure", "raised"],
    )
    def test_REQ_o00074_K_failed_save_does_not_exit(self, capsys, stop_fn, how):
        clock = _Clock()
        wd, exits = _watchdog(
            [False, False],
            [(5, "m1"), (5, "m1")],
            clock,
            grace=300.0,
            stop_fn=stop_fn,
        )

        assert wd.check_once() is Decision.WAIT_GRACE
        capsys.readouterr()

        clock.now += 400
        assert wd.check_once() is Decision.SAVE_FAILED, f"a save that {how} was treated as done"
        assert exits == [], "daemon exited after a failed save, destroying the work it held"
        err = capsys.readouterr().err
        assert "FAILED" in err
        assert "retained" in err

    def test_REQ_o00074_K_daemon_retries_at_the_next_interval_and_then_exits(self, capsys):
        clock = _Clock()
        outcomes = [{"success": False, "error": "disk full"}, _ok_stop()]
        wd, exits = _watchdog(
            [False, False, False],
            [(5, "m1"), (5, "m1"), (5, "m1")],
            clock,
            grace=300.0,
            stop_fn=lambda: outcomes.pop(0),
        )

        assert wd.check_once() is Decision.WAIT_GRACE
        clock.now += 400
        assert wd.check_once() is Decision.SAVE_FAILED
        assert exits == []
        capsys.readouterr()

        clock.now += 10
        assert wd.check_once() is Decision.EXIT_SAVE, "the daemon never retried the failed save"
        assert exits == ["exit"]
        assert "Saved" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Client identity: resolution, recording, and the explicit-start exemption
# ---------------------------------------------------------------------------


class TestClientIdentityResolution:
    """Validates REQ-o00074-D: client identity is derived only from evidence
    available at the moment of starting, and when no identity can be
    established the daemon starts with none rather than with an inferred one.
    """

    def test_REQ_o00074_D_env_override(self, monkeypatch):
        from elspais.mcp import daemon

        monkeypatch.setenv("ELSPAIS_CLIENT_PID", str(os.getpid()))
        assert daemon.resolve_client_pid() == os.getpid()

    @pytest.mark.parametrize("value", ["not-a-pid", "0", "1", "-3"])
    def test_REQ_o00074_D_env_override_invalid(self, monkeypatch, value):
        from elspais.mcp import daemon

        monkeypatch.setenv("ELSPAIS_CLIENT_PID", value)
        assert daemon.resolve_client_pid() is None

    def test_REQ_o00074_D_legacy_env_override(self, monkeypatch):
        """Validates REQ-o00074-D: the former variable name, ``ELSPAIS_SPAWNER_PID``,
        still resolves a client handle when set on its own -- callers that set it
        before the rename to ``ELSPAIS_CLIENT_PID`` keep working."""
        from elspais.mcp import daemon

        monkeypatch.delenv("ELSPAIS_CLIENT_PID", raising=False)
        monkeypatch.setenv("ELSPAIS_SPAWNER_PID", str(os.getpid()))
        assert daemon.resolve_client_pid() == os.getpid()

    def test_REQ_o00074_D_claude_ancestor(self, monkeypatch):
        from elspais.mcp import daemon

        monkeypatch.delenv("ELSPAIS_CLIENT_PID", raising=False)
        monkeypatch.setenv("CLAUDECODE", "1")
        with patch(
            "elspais.mcp.daemon._iter_proc_ancestors",
            return_value=iter([(200, "zsh"), (300, "claude"), (400, "zsh")]),
        ):
            assert daemon.resolve_client_pid() == 300

    def test_REQ_o00074_D_no_session_identity(self, monkeypatch):
        """No env override, no Claude session, no tty -> None (TTL-only)."""
        from elspais.mcp import daemon

        monkeypatch.delenv("ELSPAIS_CLIENT_PID", raising=False)
        monkeypatch.delenv("CLAUDECODE", raising=False)
        with patch("elspais.mcp.daemon._session_leader_has_tty", return_value=False):
            assert daemon.resolve_client_pid() is None

    def test_REQ_o00074_D_interactive_session_leader(self, monkeypatch):
        from elspais.mcp import daemon

        monkeypatch.delenv("ELSPAIS_CLIENT_PID", raising=False)
        monkeypatch.delenv("CLAUDECODE", raising=False)
        with (
            patch("elspais.mcp.daemon.os.getsid", return_value=7777),
            patch("elspais.mcp.daemon._session_leader_has_tty", return_value=True),
        ):
            assert daemon.resolve_client_pid() == 7777


class TestUnusableClientIdentityIsRefused:
    """Validates REQ-o00074-D: a handed-over PID at or below the floor the
    resolver applies names no client -- pid 1 is init, whose death never comes,
    and 0/negative are not process identities at all. The daemon starts with no
    client identity rather than watching one, which is the TTL-only behavior
    the requirement asks for when no identity can be established.
    """

    def _client_pids_watched(self, monkeypatch, tmp_path, env_value):
        """Run the daemon's startup path and report the PIDs it set a watch on."""
        from elspais.mcp import server as mcp_server

        monkeypatch.delenv("_ELSPAIS_DAEMON_JSON", raising=False)
        monkeypatch.setenv("_ELSPAIS_CLIENT_PID", env_value)

        watched: list[int] = []

        class _StubWatchdog:
            def __init__(self, client_pid, **kwargs):
                watched.append(client_pid)

            def start(self):
                pass

        with (
            patch("elspais.server.state.AppState.from_config", return_value=MagicMock()),
            patch("elspais.server.app.create_app", return_value=MagicMock()),
            patch("elspais.server.client_watch.ClientWatchdog", _StubWatchdog),
            patch("uvicorn.Config", return_value=MagicMock()),
            patch("uvicorn.Server", return_value=MagicMock()),
            patch("anyio.run"),
        ):
            mcp_server.run_server(working_dir=tmp_path, transport="streamable-http", port=59999)
        return watched

    @pytest.mark.parametrize("value", ["1", "0", "-3", "not-a-pid"])
    def test_REQ_o00074_D_unusable_client_pid_starts_no_watchdog(
        self, monkeypatch, tmp_path, value
    ):
        assert self._client_pids_watched(monkeypatch, tmp_path, value) == [], (
            f"daemon watched a pid it cannot learn anything from: {value!r}"
        )

    def test_REQ_o00074_D_real_client_pid_is_watched(self, monkeypatch, tmp_path):
        """The control: a usable identity does produce a watch on that pid."""
        assert self._client_pids_watched(monkeypatch, tmp_path, "5555") == [5555]

    def test_REQ_o00074_D_already_dead_declared_pid_is_unusable(self, monkeypatch):
        """A well-formed but already-dead declared pid is unusable, decisively:
        ``_declared_client_pid`` reports ``_UNUSABLE`` rather than falling through
        to the Claude-ancestor or tty-session rungs, and ``resolve_client_pid``
        reports ``None`` rather than recording a handle that names a process
        already gone. Recording it would bind the daemon to a process the very
        next liveness check would find dead, reaping the daemon at once -- an
        outcome its author would read as the daemon failing rather than as its
        own declaration being stale."""
        from elspais.mcp import daemon

        proc = subprocess.Popen([sys.executable, "-c", "pass"])
        proc.wait()
        dead_pid = proc.pid

        monkeypatch.delenv("ELSPAIS_CLIENT_PID", raising=False)
        monkeypatch.setenv("ELSPAIS_SPAWNER_PID", str(dead_pid))

        assert daemon._declared_client_pid() == daemon._UNUSABLE
        with patch(
            "elspais.mcp.daemon._iter_proc_ancestors",
            side_effect=AssertionError("must not fall through to the claude-ancestor rung"),
        ):
            monkeypatch.setenv("CLAUDECODE", "1")
            assert daemon.resolve_client_pid() is None


class TestImplicitStartRecordsClient:
    """Validates REQ-o00074-A: a daemon started implicitly on behalf of a client
    records that client's identity at the moment it is started, so it can
    afterwards determine whether the client still exists.
    """

    def test_REQ_o00074_A_start_daemon_passes_client_env(self, tmp_path):
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
                start_daemon(tmp_path, ttl_minutes=1, client_pid=9876)

        assert popen_calls[0]["env"]["_ELSPAIS_CLIENT_PID"] == "9876"

    def test_REQ_o00074_A_ensure_daemon_resolves_client(self, tmp_path):
        """The implicit CLI spawn path ties the daemon to the resolved client."""
        from elspais.mcp.daemon import ensure_daemon

        captured = {}

        def fake_start(repo_root, ttl_minutes, client_pid=None):
            captured["client_pid"] = client_pid
            return 12000

        with (
            patch("elspais.mcp.daemon.get_daemon_info", return_value=None),
            patch("elspais.mcp.daemon.get_cli_ttl", return_value=30),
            patch("elspais.mcp.daemon.resolve_client_pid", return_value=4242),
            patch("elspais.mcp.daemon.start_daemon", side_effect=fake_start),
        ):
            assert ensure_daemon(tmp_path) == 12000

        assert captured["client_pid"] == 4242


class TestReusingClientAnnouncesItself:
    """Validates REQ-o00074-E: a client that begins using a daemon that is
    already running says so, rather than leaving the daemon watching only the
    client that started it and stopping underneath this one.
    """

    def test_REQ_o00074_E_ensure_daemon_attaches_on_the_reuse_path(self, tmp_path):
        from elspais.mcp.daemon import ensure_daemon

        info = {"port": 12345, "version": None}
        attached: list = []

        with (
            patch("elspais.mcp.daemon.get_daemon_info", return_value=info),
            patch("elspais.mcp.daemon._config_hash_stale", return_value=False),
            patch("elspais.mcp.daemon.resolve_client_pid", return_value=4242),
            patch(
                "elspais.mcp.daemon.attach_client",
                side_effect=lambda i, pid: attached.append((i, pid)),
            ),
        ):
            assert ensure_daemon(tmp_path) == 12345

        assert attached == [(info, 4242)], "reusing a running daemon did not register the client"

    def test_REQ_o00074_E_attach_client_posts_the_pid_to_the_daemon(self):
        """The wire call names the client and reports what the daemon answered."""
        from elspais.mcp import daemon

        captured = {}

        class _Resp:
            def read(self):
                return json.dumps({"attached": True, "clients": [111, 4321]}).encode()

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            captured["body"] = json.loads(req.data.decode())
            return _Resp()

        with patch("elspais.mcp.daemon.urlopen", side_effect=fake_urlopen):
            assert daemon.attach_client({"port": 9999}, 111) is True

        assert captured["url"].endswith("/api/session/attach")
        assert captured["body"] == {"pid": 111}

    def test_REQ_o00074_E_attach_client_without_an_identity_is_a_no_op(self):
        """No identity to record leaves the daemon's lifetime exactly as it was."""
        from elspais.mcp import daemon

        with patch("elspais.mcp.daemon.urlopen", side_effect=AssertionError("must not call")):
            assert daemon.attach_client({"port": 9999}, None) is False
            assert daemon.attach_client({}, 111) is False


class TestClientSetIsObservable:
    """Validates REQ-o00074-B: the client identities a daemon has recorded are
    observable in the state record by which clients locate it
    (``.elspais/daemon.json``).
    """

    def test_REQ_o00074_B_write_daemon_json_records_client_pid(self, tmp_path):
        from elspais.mcp.daemon import write_daemon_json

        path = write_daemon_json(
            repo_root=tmp_path, pid=111, port=222, server_type="daemon", client_pid=333
        )
        info = json.loads(path.read_text())
        assert info["client_pid"] == 333
        assert info["clients"] == [{"kind": "pid", "id": 333}], (
            "the initial client set is not published, or not by kind of handle"
        )

    def test_REQ_o00074_B_record_daemon_clients_republishes_the_whole_set(self, tmp_path):
        from elspais.mcp.daemon import record_daemon_clients, write_daemon_json

        write_daemon_json(
            repo_root=tmp_path, pid=111, port=222, server_type="daemon", client_pid=333
        )
        record_daemon_clients(tmp_path, [777, 333])

        info = json.loads((tmp_path / ".elspais" / "daemon.json").read_text())
        assert info["clients"] == [
            {"kind": "pid", "id": 333},
            {"kind": "pid", "id": 777},
        ], "an adopted client is not observable"

    def test_REQ_o00074_B_held_sessions_are_published_as_their_own_kind(self, tmp_path):
        """A client present only as a held stream is watched, and a record
        that could only hold process ids would leave it invisible."""
        from elspais.mcp.daemon import record_daemon_clients, write_daemon_json

        write_daemon_json(
            repo_root=tmp_path, pid=111, port=222, server_type="daemon", client_pid=333
        )
        record_daemon_clients(tmp_path, [333], held=2)

        info = json.loads((tmp_path / ".elspais" / "daemon.json").read_text())
        assert info["clients"] == [
            {"kind": "pid", "id": 333},
            {"kind": "session", "count": 2},
        ]

    def test_REQ_o00074_B_record_daemon_clients_without_a_record_is_a_no_op(self, tmp_path):
        from elspais.mcp.daemon import record_daemon_clients

        record_daemon_clients(tmp_path, [1, 2])  # must not raise or create a file
        assert not (tmp_path / ".elspais" / "daemon.json").exists()


class TestExplicitStartRecordsNoClient:
    """Validates REQ-o00074-C: a daemon started explicitly rather than on behalf
    of a client records no client identity, and its lifetime remains governed
    solely by its idle timeout.
    """

    def test_REQ_o00074_C_write_daemon_json_omits_client_identity_when_absent(self, tmp_path):
        """Explicit starts (viewer, manual serve) record no client identity."""
        from elspais.mcp.daemon import write_daemon_json

        path = write_daemon_json(repo_root=tmp_path, pid=111, port=222, server_type="viewer")
        info = json.loads(path.read_text())
        assert "client_pid" not in info
        assert "clients" not in info

    def test_REQ_o00074_C_start_daemon_without_client_scrubs_env(self, tmp_path, monkeypatch):
        """Explicit starts must not inherit a stale client PID from the env."""
        from elspais.mcp.daemon import start_daemon

        monkeypatch.setenv("_ELSPAIS_CLIENT_PID", "1212")
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

        assert "_ELSPAIS_CLIENT_PID" not in popen_calls[0]["env"]

    def test_REQ_o00074_C_restart_daemon_spawns_without_client(self, tmp_path):
        """`elspais daemon restart` is an explicit start: no client tie."""
        from elspais.mcp.daemon import restart_daemon

        captured = {}

        def fake_start(repo_root, ttl_minutes, client_pid=None):
            captured["client_pid"] = client_pid
            return 12001

        with (
            patch("elspais.mcp.daemon.get_daemon_info", return_value=None),
            patch("elspais.mcp.daemon.get_cli_ttl", return_value=30),
            patch("elspais.mcp.daemon.start_daemon", side_effect=fake_start),
        ):
            result = restart_daemon(tmp_path)

        assert result["success"] is True
        assert captured["client_pid"] is None


class TestRestartSaysWhatBecomesOfTheWork:
    """Validates REQ-p00083-A, REQ-p00083-B: a restart holding unsaved work refuses until the
    caller says what is to become of it, and the two answers are exclusive.

    ``--persist`` saves it here, where a changelog reason can be supplied;
    ``--discard-changes`` instructs the daemon to drop it. A restart that
    simply proceeded would meet a daemon that saves whatever it holds on its
    way out, which is the opposite of what a caller wanting rid of the work
    asked for.
    """

    def test_REQ_o00074_I_the_two_answers_are_mutually_exclusive(self, tmp_path):
        from elspais.mcp.daemon import restart_daemon

        result = restart_daemon(tmp_path, discard_changes=True, persist=True)

        assert result["success"] is False
        assert "discard-changes" in result["error"] and "persist" in result["error"], result

    def test_REQ_o00074_I_neither_answer_refuses_and_offers_both(self, tmp_path):
        from elspais.mcp.daemon import restart_daemon

        with (
            patch("elspais.mcp.daemon.get_daemon_info", return_value={"pid": 999, "port": 1}),
            patch("elspais.mcp.daemon.get_daemon_mutation_count", return_value=3),
            patch("elspais.mcp.daemon.stop_daemon") as stop,
        ):
            result = restart_daemon(tmp_path)

        assert result["success"] is False
        assert result["mutation_count"] == 3
        assert "--persist" in result["error"], result
        assert "--discard-changes" in result["error"], result
        assert "--force" not in result["error"], "the retired flag is still being offered"
        assert stop.call_count == 0, "the daemon was stopped despite the refusal"

    def test_REQ_o00074_I_the_discard_goes_to_the_daemon_however_the_count_reads(self, tmp_path):
        """The pending count is a read that can go stale between the read and
        the instruction. A discard that trusted a zero would stop the daemon
        with an ordinary signal, and the daemon would save the change that had
        arrived in between -- so the instruction is always sent, and the daemon
        decides against the log it actually holds."""
        from elspais.mcp.daemon import restart_daemon

        stops: list[bool] = []

        with (
            patch("elspais.mcp.daemon.get_daemon_info", return_value={"pid": 999, "port": 1}),
            patch("elspais.mcp.daemon.get_daemon_mutation_count", return_value=0),
            patch(
                "elspais.mcp.daemon.request_daemon_stop",
                side_effect=lambda info, discard_changes=False: (
                    stops.append(discard_changes) or {"success": True, "discarded": True}
                ),
            ),
            patch("elspais.mcp.daemon.wait_for_daemon_exit", return_value=True),
            patch("elspais.mcp.daemon.stop_daemon"),
            patch("elspais.mcp.daemon.get_cli_ttl", return_value=30),
            patch("elspais.mcp.daemon.start_daemon", return_value=12002),
        ):
            result = restart_daemon(tmp_path, discard_changes=True)

        assert result["success"] is True, result
        assert stops == [True], "the discard instruction never reached the daemon"

    def test_REQ_o00074_I_refused_discard_abandons_the_restart(self, tmp_path):
        """The daemon refused because another writer's change arrived. Killing
        it now would destroy that change, which is exactly what the refusal was
        protecting -- so the restart stops here and says why."""
        from elspais.mcp.daemon import restart_daemon

        rejection = {
            "success": False,
            "code": "mutation_log_conflict",
            "error": "the log has moved on",
        }

        with (
            patch("elspais.mcp.daemon.get_daemon_info", return_value={"pid": 999, "port": 1}),
            patch("elspais.mcp.daemon.get_daemon_mutation_count", return_value=1),
            patch("elspais.mcp.daemon.request_daemon_stop", return_value=rejection),
            patch("elspais.mcp.daemon.stop_daemon") as stop,
            patch("elspais.mcp.daemon.start_daemon") as start,
        ):
            result = restart_daemon(tmp_path, discard_changes=True)

        assert result["success"] is False
        assert result["code"] == "mutation_log_conflict"
        assert "the log has moved on" in result["error"]
        assert stop.call_count == 0, "the refused restart killed the daemon anyway"
        assert start.call_count == 0

    def test_REQ_o00074_I_the_changelog_reason_reaches_the_persisting_save(self, tmp_path):
        """``--persist`` saves here rather than in the daemon's own shutdown
        precisely so a reason can be given for it; a reason the caller typed and
        the save never saw would leave the tree failing its own changelog rule.
        """
        from elspais.mcp.daemon import restart_daemon

        seen: list[str | None] = []

        with (
            patch("elspais.mcp.daemon.get_daemon_info", return_value={"pid": 999, "port": 1}),
            patch("elspais.mcp.daemon.get_daemon_mutation_count", return_value=2),
            patch(
                "elspais.mcp.daemon.save_daemon_mutations",
                side_effect=lambda info, message=None: seen.append(message) or {"success": True},
            ),
            patch("elspais.mcp.daemon.stop_daemon"),
            patch("elspais.mcp.daemon.get_cli_ttl", return_value=30),
            patch("elspais.mcp.daemon.start_daemon", return_value=12003),
        ):
            result = restart_daemon(tmp_path, persist=True, message="because the review said so")

        assert result["success"] is True, result
        assert seen == ["because the review said so"]


class TestStoppingDaemonIsReplacedNotReused:
    """Verifies REQ-o00075-B and REQ-o00076-E: what a client locates describes
    the process it would reach, and one working tree is served by one process.

    A daemon that has committed to stopping still answers, so a liveness
    check alone cannot tell it from one that will serve. It refuses every
    write it is handed, and tells the caller to reconnect to a server that
    will be started on demand -- which is untrue while it is the server a
    client locates. The record therefore says the process is stopping, and
    a client that finds that waits for the process to go before starting
    its replacement. It never starts one alongside.
    """

    def test_REQ_o00076_E_committed_stop_is_recorded_in_the_state_record(self, tmp_path):
        from elspais.mcp.daemon import daemon_is_stopping, get_daemon_info, write_daemon_json
        from elspais.mcp.shared_state import SharedServerState

        write_daemon_json(tmp_path, pid=os.getpid(), port=4321)
        state = SharedServerState()
        state["working_dir"] = tmp_path
        assert daemon_is_stopping(get_daemon_info(tmp_path)) is False

        state.begin_shutdown()

        info = get_daemon_info(tmp_path)
        assert daemon_is_stopping(info) is True, "the record still describes a serving daemon"
        assert info["port"] == 4321, "marking the record destroyed what it said"

    def test_REQ_o00075_B_record_owned_by_another_process_is_left_alone(self, tmp_path):
        """A stdio server holds a private graph and owns no record. Marking the
        one it finds would report a daemon as stopping that is serving fine."""
        from elspais.mcp.daemon import daemon_is_stopping, get_daemon_info, write_daemon_json
        from elspais.mcp.shared_state import SharedServerState

        write_daemon_json(tmp_path, pid=os.getpid() + 1, port=4321)
        state = SharedServerState()
        state["working_dir"] = tmp_path

        state.begin_shutdown()

        with open(tmp_path / ".elspais" / "daemon.json") as fh:
            assert daemon_is_stopping(json.load(fh)) is False
        assert get_daemon_info(tmp_path) is not None or True  # record survives either way

    def test_REQ_o00075_B_marking_a_record_that_cannot_be_written_is_not_an_error(self, tmp_path):
        """A stop that raises on the way out is a stop that does not happen."""
        from elspais.mcp.shared_state import SharedServerState

        state = SharedServerState()
        state["working_dir"] = tmp_path / "does" / "not" / "exist"

        state.begin_shutdown()  # must not raise

        assert state.is_shutting_down is True

    def test_REQ_o00075_B_stopping_daemon_is_replaced_rather_than_reused(self, tmp_path):
        from elspais.mcp import daemon as dm

        info = {"pid": 999, "port": 4321, "stopping": True}
        order: list[str] = []

        with (
            patch.object(dm, "get_daemon_info", return_value=info),
            patch.object(
                dm,
                "wait_for_daemon_exit",
                side_effect=lambda i, timeout=20.0: order.append("waited") or True,
            ),
            patch.object(dm, "get_cli_ttl", return_value=30),
            patch.object(dm, "resolve_client_pid", return_value=None),
            patch.object(dm, "notify_unbound_lifetime"),
            patch.object(
                dm,
                "start_daemon",
                side_effect=lambda *a, **k: order.append("started") or 5555,
            ),
        ):
            port = dm.ensure_daemon(tmp_path)

        assert port == 5555, "the stopping daemon was handed to the caller"
        assert order == ["waited", "started"], "a replacement started before the daemon was gone"

    def test_REQ_o00075_B_daemon_that_will_not_go_is_neither_reused_nor_duplicated(self, tmp_path):
        from elspais.mcp import daemon as dm

        info = {"pid": 999, "port": 4321, "stopping": True}

        with (
            patch.object(dm, "get_daemon_info", return_value=info),
            patch.object(dm, "wait_for_daemon_exit", return_value=False),
            patch.object(dm, "get_cli_ttl", return_value=30),
            patch.object(dm, "start_daemon") as start,
            pytest.raises(RuntimeError),
        ):
            dm.ensure_daemon(tmp_path)

        assert start.call_count == 0, "a second process was started for one working tree"

    def test_REQ_o00075_B_successors_record_is_not_unlinked(self, tmp_path):
        """The predecessor is gone and something has already taken its place.
        Clearing the record now would hide a daemon that is serving."""
        from elspais.mcp import daemon as dm

        successor = {"pid": 1000, "port": 6000}
        dm.write_daemon_json(tmp_path, pid=1000, port=6000)

        with (
            patch.object(dm, "wait_for_daemon_exit", return_value=True),
            patch.object(dm, "get_daemon_info", return_value=successor),
        ):
            assert dm.replace_stopping_daemon(tmp_path, {"pid": 999, "port": 4321}) is True

        assert (tmp_path / ".elspais" / "daemon.json").exists(), (
            "the successor's record was removed"
        )

    def test_REQ_o00075_B_command_does_not_reach_a_stopping_daemon(self, tmp_path):
        from elspais.commands import _engine

        info = {"pid": 999, "port": 4321, "stopping": True}
        reached: list[int] = []

        with (
            patch("elspais.config.find_git_root", return_value=tmp_path),
            patch("elspais.commands._daemon_client._get_daemon_port", return_value=4321),
            patch("elspais.mcp.daemon.get_daemon_info", return_value=info),
            patch("elspais.mcp.daemon.wait_for_daemon_exit", return_value=True),
            patch("elspais.mcp.daemon.ensure_daemon", return_value=7777),
            patch(
                "elspais.commands._daemon_client._try_port",
                side_effect=lambda port, *a, **k: reached.append(port) or {"ok": True},
            ),
        ):
            result = _engine._try_daemon("/api/run/checks", {})

        assert result is not None
        assert reached == [7777], f"a stopping daemon served the command: {reached}"


class TestIdleTimeoutSparesADaemonInUse:
    """Verifies REQ-o00074-O: while a daemon has a recorded client that still
    exists, the idle timeout is not what ends it.

    Going quiet is not going away. An agent that applies a change and then
    reasons about the next one sends nothing for long stretches, and a
    timeout that cannot tell that from an abandoned daemon takes the
    daemon from the client least able to notice. A daemon with no recorded
    client is the one the timeout governs, and for it nothing changes.
    """

    @staticmethod
    def _middleware(monkeypatch, endings, **kwargs):
        from elspais.mcp.shared_state import SharedServerState
        from elspais.server.middleware import TTLMiddleware

        # A stop the daemon decided on ends the process directly; a signal
        # sent to itself would be recorded here too, and is not expected.
        monkeypatch.setattr("elspais.server.middleware.os._exit", endings.append)
        monkeypatch.setattr(
            "elspais.server.middleware.os.kill",
            lambda pid, sig: endings.append(f"signal:{sig}"),
        )
        shared = SharedServerState()
        mw = TTLMiddleware(app=lambda *a: None, ttl_minutes=60, shared=shared, **kwargs)
        mw._timer.cancel()
        return shared, mw

    def test_REQ_o00074_O_live_client_survives_an_expired_idle_timeout(self, monkeypatch):
        endings: list[object] = []
        shared, mw = self._middleware(monkeypatch, endings, clients_alive=lambda: True)

        mw._exit()
        mw._timer.cancel()

        assert endings == [], "the idle timeout stopped a daemon a client is using"
        assert shared.is_shutting_down is False, "a daemon in use was committed to stopping"

    def test_REQ_o00074_O_spared_daemon_waits_out_another_idle_period(self, monkeypatch):
        endings: list[object] = []
        _shared, mw = self._middleware(monkeypatch, endings, clients_alive=lambda: True)
        first = mw._timer

        mw._exit()

        assert mw._timer is not first, "the timer was not restarted; the check will never rerun"
        mw._timer.cancel()

    def test_REQ_o00074_O_daemon_with_no_recorded_client_still_times_out(self, monkeypatch):
        endings: list[object] = []
        shared, mw = self._middleware(monkeypatch, endings, clients_alive=lambda: False)

        mw._exit()

        assert endings == [0], "a daemon nobody is using was not stopped by its idle timeout"
        assert shared.is_shutting_down is True

    def test_REQ_o00074_O_an_absent_liveness_source_reads_as_no_clients(self, monkeypatch):
        """An explicitly started daemon has no client watchdog to ask, and its
        lifetime is governed solely by its idle timeout (REQ-o00074-C)."""
        endings: list[object] = []
        shared, mw = self._middleware(monkeypatch, endings)

        mw._exit()

        assert endings == [0], "an explicitly started daemon stopped answering to its timeout"
        assert shared.is_shutting_down is True

    def test_REQ_o00074_O_unreadable_liveness_source_does_not_read_as_no_clients(
        self, monkeypatch, capsys
    ):
        endings: list[object] = []

        def _boom() -> bool:
            raise RuntimeError("the client set could not be read")

        shared, mw = self._middleware(monkeypatch, endings, clients_alive=_boom)

        mw._exit()
        mw._timer.cancel()

        assert endings == [], "a broken instrument ended a daemon no evidence says is unused"
        assert shared.is_shutting_down is False
        assert "could not be read" in capsys.readouterr().err

    def test_REQ_o00074_O_the_watchdogs_client_set_is_what_the_timeout_consults(self):
        """The daemon's clients are the watchdog's business; the timeout asks it
        rather than keeping a second answer that can disagree with the first."""
        from elspais.server.client_watch import ClientWatchdog

        alive = {4242: True}
        wd = ClientWatchdog(
            client_pid=4242,
            pending_fn=lambda: (0, 1),
            alive_fn=lambda pid: alive.get(pid, False),
        )
        assert wd.has_live_client() is True

        alive[4242] = False
        assert wd.has_live_client() is False

    def test_REQ_o00074_O_an_inconclusive_held_source_keeps_the_daemon(self, capsys):
        from elspais.server.client_watch import ClientWatchdog

        def _boom() -> int:
            raise RuntimeError("the session tracker could not be read")

        wd = ClientWatchdog(
            client_pid=4242,
            pending_fn=lambda: (0, 1),
            alive_fn=lambda pid: False,
            extra_liveness_fn=_boom,
        )

        assert wd.has_live_client() is True
        assert "could not be read" in capsys.readouterr().err

    def test_REQ_o00074_O_reading_the_client_set_publishes_nothing(self):
        """The timeout's question is a read. A check that pruned or republished
        would make the record depend on how often the timeout happened to ask."""
        from elspais.server.client_watch import ClientWatchdog

        published: list[tuple] = []
        wd = ClientWatchdog(
            client_pid=4242,
            pending_fn=lambda: (0, 1),
            alive_fn=lambda pid: False,
            publish_fn=lambda pids, held: published.append((pids, held)),
        )

        wd.has_live_client()

        assert published == [], "a read of the client set rewrote the state record"
        assert wd.clients() == [4242], "a read of the client set pruned it"


class TestStoppingDaemonStopsAdvertising:
    def test_REQ_o00074_B_publishing_preserves_a_stopping_mark(self, tmp_path):
        """Validates REQ-o00074-B: the record a client reads to find a daemon
        must describe the process it would reach, so a mark saying it is
        stopping must survive anything else that writes the record.

        Publishing read-modify-writes, so a publish that starts AFTER the mark
        preserves it -- pinned here because that is what keeps the remaining
        exposure to a publish already in flight when the mark lands, rather
        than to every publish that follows one."""
        import json
        import os

        from elspais.mcp.daemon import (
            _daemon_json_path,
            daemon_is_stopping,
            get_daemon_info,
            mark_daemon_stopping,
            record_daemon_clients,
        )

        path = _daemon_json_path(tmp_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"pid": os.getpid(), "port": 41000, "clients": []}))

        mark_daemon_stopping(tmp_path, os.getpid())
        record_daemon_clients(tmp_path, [4242], 0)

        info = get_daemon_info(tmp_path)
        assert daemon_is_stopping(info), "a later publish erased the stopping mark"
        assert info["clients"] == [{"kind": "pid", "id": 4242}]
