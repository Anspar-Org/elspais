# Implements: REQ-o00074
"""Client-liveness watchdog for the background daemon.

A daemon spawned implicitly to serve a CLI/session records the spawning
client's PID (passed via the ``_ELSPAIS_CLIENT_PID`` env var, since
``start_new_session=True`` reparents the daemon to PID 1). A client that
later adopts the running daemon registers itself too, so the watchdog
tracks a *set* of client PIDs rather than only the process that happened
to start the daemon. It watches them at a low frequency and shuts the
daemon down once every one of them is gone, so orphaned daemons cannot
accumulate and keep serving answers no client is watching.

Daemons started without client identity (manual ``elspais mcp serve``,
the viewer, ``elspais daemon``) never get a watchdog and keep
their TTL-only lifetime.

Shutdown decision matrix (``shutdown_decision``):

    no client identity recorded        -> KEEP (TTL-only behavior)
    some recorded client alive         -> KEEP
    all clients gone, nothing unsaved  -> EXIT_CLEAN
    all gone, unsaved, in grace        -> WAIT_GRACE (warn, extend)
    all gone, unsaved, grace over      -> EXIT_SAVE (persist, then exit)

``check_once`` also reads an activity token — the mutation log's
monotonic revision — ahead of the matrix: a token that moved since the
last check is proof a writer is present even when its identity was never
resolvable, so the daemon keeps serving and the grace clock restarts.
Reads move nothing, so a polling client still cannot hold an orphan open.

Pending work is never destroyed at the deadline. This module does not
persist it itself: both exiting decisions hand over to the process's one
shutdown routine (``finalize_shutdown`` in ``mcp/shared_state.py``),
which every other way of stopping runs too, so the daemon behaves the
same whether its clients went away, its idle timeout expired, or
somebody signalled it. That routine records who saved, when, how much,
and what triggered it, so a later client can see how the files reached
their current form (REQ-p00083-C). The record states those facts and
nothing else: a client can disappear because it finished, crashed, or
lost its connection, and nothing here can tell those apart, so no
conclusion about the work is drawn on the reader's behalf.

Preservation is the default because the costs are asymmetric — the files
are under revision control, where an unwanted write costs one command to
inspect and revert, while discarded work has to be redone from memory
and sometimes cannot be. If the save itself fails, the work is retained
and retried rather than dropped (REQ-p00083-D).
"""

from __future__ import annotations

import enum
import os
import sys
import threading
import time
from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from typing import Any

DEFAULT_CHECK_INTERVAL_SECONDS = 60.0
# A client that reasons between mutations routinely goes quiet for far
# longer than a few minutes, and going quiet is not the same as going
# away. The grace period is sized for that, not for a shell prompt.
DEFAULT_GRACE_SECONDS = 1800.0

# Sentinel for "no activity token observed yet" — distinct from a real
# token of None, which is what an empty mutation log reports.
_UNOBSERVED = object()


# Implements: REQ-o00074-G, REQ-o00074-H
def pending_snapshot(graph: Any) -> tuple[int, object]:
    """Return (pending mutation count, activity token) from one snapshot.

    The count is the number of pending unsaved mutations, so a warning
    about them states the real figure; a windowed query would cap the
    answer at the window size.

    The token is the log's monotonic revision, not its tip: an append
    followed by an undo restores the previous tip exactly, so a writer
    working steadily in that pattern would read as idle.

    ``tail(0)`` snapshots the whole log; never iterate the live list
    while other writers may be appending to it.
    """
    log = graph.mutation_log
    return len(log.tail(0)), log.revision


def pid_alive(pid: int) -> bool:
    """Return True if a process with this PID exists.

    Uses ``os.kill(pid, 0)``: EPERM means the process exists but belongs
    to another user (treated as alive); ESRCH means it is gone.
    """
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


class Decision(enum.Enum):
    """Outcome of one client-liveness evaluation."""

    KEEP = "keep"
    EXIT_CLEAN = "exit-clean"
    WAIT_GRACE = "wait-grace"
    EXIT_SAVE = "exit-save"
    SAVE_FAILED = "save-failed"


def shutdown_decision(
    has_clients: bool,
    any_client_alive: bool,
    mutation_count: int | None,
    grace_expired: bool,
) -> Decision:
    """Pure decision function for the client-liveness watchdog.

    Args:
        has_clients: Whether any client identity was ever recorded. False
            means the daemon was started explicitly and keeps TTL-only
            lifetime.
        any_client_alive: Whether at least one recorded client still
            exists. Ignored when has_clients is False.
        mutation_count: Unsaved in-memory mutations. None means unknown,
            which is treated as dirty (conservative: never assume work
            we cannot see is absent).
        grace_expired: Whether the bounded dirty-daemon grace period has
            elapsed since the last client was seen gone.
    """
    if not has_clients:
        return Decision.KEEP
    if any_client_alive:
        return Decision.KEEP
    dirty = mutation_count is None or mutation_count > 0
    if not dirty:
        return Decision.EXIT_CLEAN
    if grace_expired:
        return Decision.EXIT_SAVE
    return Decision.WAIT_GRACE


def _default_exit() -> None:
    # Same as TTLMiddleware._exit, and for the same reasons. Nobody asked
    # for this stop, so nobody is waiting on it: the work is written and
    # writes are refused, so a drain a held-open request can stall
    # indefinitely protects nothing. os._exit, not sys.exit: this runs on
    # the watchdog thread, where SystemExit unwinds that thread and leaves
    # the process serving.
    os._exit(0)


class ClientWatchdog:
    """Low-frequency background check that some client is still alive.

    Independent of HTTP traffic (and of TTLMiddleware, which is absent
    when cli_ttl < 0), so polling clients cannot keep an orphaned daemon
    alive indefinitely.
    """

    def __init__(
        self,
        client_pid: int,
        pending_fn: Callable[[], tuple[int, object]],
        interval_seconds: float = DEFAULT_CHECK_INTERVAL_SECONDS,
        grace_seconds: float = DEFAULT_GRACE_SECONDS,
        alive_fn: Callable[[int], bool] = pid_alive,
        exit_fn: Callable[[], None] = _default_exit,
        clock: Callable[[], float] = time.monotonic,
        lock: AbstractContextManager[Any] | None = None,
        stop_fn: Callable[[], dict[str, Any]] | None = None,
        extra_liveness_fn: Callable[[], int] | None = None,
        publish_fn: Callable[[list[int], int], None] | None = None,
    ) -> None:
        self._clients: set[int] = {client_pid}
        self._clients_lock = threading.Lock()
        self._pending_fn = pending_fn
        self._lock = lock if lock is not None else nullcontext()
        self._interval = interval_seconds
        self._grace = grace_seconds
        self._alive_fn = alive_fn
        self._exit_fn = exit_fn
        self._stop_fn = stop_fn
        self._extra_liveness_fn = extra_liveness_fn
        self._publish_fn = publish_fn
        self._published: tuple[tuple[int, ...], int] | None = None
        self._clock = clock
        self._dead_since: float | None = None
        self._warned_grace = False
        self._last_token: object = _UNOBSERVED
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # Implements: REQ-o00074-E
    def attach_client(self, pid: int) -> bool:
        """Record a client that has begun using this already-running daemon.

        A daemon is shared: it serves several clients at once and
        deliberately outlives the one that started it so a later client
        can pick it up. Binding its lifetime to the starter alone would
        shut it down underneath whoever is actually using it.

        Returns False for a PID that cannot name a live client.
        """
        if pid <= 1 or not self._alive_fn(pid):
            return False
        with self._clients_lock:
            self._clients.add(pid)
        return True

    # Implements: REQ-o00074-O
    def has_live_client(self) -> bool:
        """Whether any recorded client still exists. Reads, changes nothing.

        The daemon's client set is this watchdog's business, so anything
        else that needs the answer — the idle timeout, which must not be
        the cause of a daemon's termination while a client is there — asks
        here rather than keeping a second answer that can disagree.

        A read, not a check: it prunes nothing and publishes nothing, so
        the state record does not depend on how often it is asked. A
        handle source that cannot be read is inconclusive, which is
        neither "some" nor "none", and reads as a client being there.
        """
        with self._clients_lock:
            pids = list(self._clients)
        if any(self._alive_fn(pid) for pid in pids):
            return True
        held = self._held_handles()
        return held is None or held > 0

    def clients(self) -> list[int]:
        """Currently recorded client PIDs, for disclosure to callers."""
        with self._clients_lock:
            return sorted(self._clients)

    def _any_client_alive(self) -> bool:
        """True if any recorded client still exists; prunes the dead ones.

        Pruning keeps the recorded set an honest answer to "who is using
        this daemon", which assertion B publishes.

        Pruning runs first and unconditionally. A held stream keeps the
        daemon alive, but it says nothing about a pid that has died, and
        a check that stopped early would republish clients that are gone.

        A held stream counts as a client without being a recorded pid: it
        is a handle of a different kind, not an exception to the rule
        (REQ-o00074-A). A source that cannot answer has said nothing
        about whether a client is there, so its failure is reported and
        the daemon kept — terminating on the strength of a broken
        instrument would end a daemon no evidence says is unused.
        """
        with self._clients_lock:
            live = {pid for pid in self._clients if self._alive_fn(pid)}
            self._clients = live if live else self._clients
            pids_alive = bool(live)
        held = self._held_handles()
        self._publish(sorted(live), held)
        return pids_alive or held is None or held > 0

    def _held_handles(self) -> int | None:
        """How many client handles of another kind are currently held.

        None means the source could not be read: inconclusive, which is
        neither "some" nor "none". It keeps the daemon and publishes
        nothing, because a record written from an unreadable instrument
        would state as fact something nobody observed.
        """
        if self._extra_liveness_fn is None:
            return 0
        try:
            return int(self._extra_liveness_fn() or 0)
        except Exception as exc:
            print(
                f"WARNING: a client-liveness source could not be read ({exc!r}); "
                "treating this check as inconclusive and keeping the daemon.",
                file=sys.stderr,
                flush=True,
            )
            return None

    # Implements: REQ-o00074-B
    def _publish(self, pids: list[int], held: int | None) -> None:
        """Publish the client set this check computed, if it has changed.

        The periodic check is the one place that knows the daemon's true
        client composition: a client present only as a held stream
        registers nothing, so a record written on registration alone
        never mentions it, and the operator asking why the daemon is
        still running finds no answer for the client keeping it alive.

        Only a changed composition is written. Rewriting an unchanged
        record every interval is churn under whoever is reading it, and
        buys no information.
        """
        if self._publish_fn is None or held is None:
            return
        composition = (tuple(pids), held)
        if composition == self._published:
            return
        try:
            self._publish_fn(pids, held)
        except Exception as exc:
            print(
                f"WARNING: could not publish the daemon's client set ({exc!r}); "
                "the daemon's lifetime is unaffected, but its state record "
                "may not describe the clients it is watching.",
                file=sys.stderr,
                flush=True,
            )
            return
        self._published = composition

    def _pending(self) -> tuple[int | None, object]:
        """Read pending count and activity token; unknown reads as dirty."""
        try:
            return self._pending_fn()
        except Exception:
            return None, self._last_token

    def check_once(self) -> Decision:
        """Evaluate the decision matrix once and act on the outcome.

        Implements: REQ-o00074-E, REQ-o00074-G

        The decision to terminate is taken while holding the writers'
        lock, and the pending state is re-read inside it. Deciding from
        a snapshot taken outside the lock let a mutation be accepted --
        and acknowledged to its writer -- between the read and the exit,
        which terminated the daemon holding work it had just reported as
        absent.
        """
        alive = self._any_client_alive()

        count, token = self._pending()

        if alive:
            self._dead_since = None
            self._warned_grace = False
            self._last_token = token
            return Decision.KEEP

        now = self._clock()

        # Implements: REQ-o00074-H
        # A token that moved since the previous check is a writer using
        # this daemon whose identity was never resolvable. Keep serving
        # and restart the countdown; the first token seen is a baseline,
        # not activity. Reads never move it, so polling cannot reach here.
        moved = self._last_token is not _UNOBSERVED and token != self._last_token
        self._last_token = token
        if moved:
            self._dead_since = now
            self._warned_grace = False
            return Decision.KEEP

        if self._dead_since is None:
            self._dead_since = now

        grace_expired = (now - self._dead_since) >= self._grace

        with self._lock:
            # Re-read under the lock: no writer can be mid-mutation now,
            # so this count is the one the exit acts on. A token that
            # moved between the two reads is a writer that got its
            # mutation in during the gap; that is activity, and it
            # outranks an expired countdown.
            recheck_count, recheck_token = self._pending()
            moved_in_gap = recheck_token != token
            count, token = recheck_count, recheck_token
            self._last_token = token
            if moved_in_gap:
                self._dead_since = now
                self._warned_grace = False
                return Decision.KEEP
            decision = shutdown_decision(
                has_clients=True,
                any_client_alive=False,
                mutation_count=count,
                grace_expired=grace_expired,
            )
            return self._act(decision, count)

    def _act(self, decision: Decision, count: int | None) -> Decision:
        """Emit the disclosure the decision requires and exit if it says so.

        Implements: REQ-o00074-E, REQ-o00074-M, REQ-p00083-A, REQ-p00083-D

        Runs under the writers' lock. Neither exiting branch decides for
        itself what happens to the work: both hand over to the process's
        one shutdown routine, which persists whatever is pending, raises
        the refusal flag so a later write cannot be accepted into a drain
        that would drop it, and reports whether it succeeded. Only then
        is the process signalled. A routine that could not persist has
        kept the work, so the daemon stays up and tries again.
        """
        if decision is Decision.EXIT_CLEAN:
            outcome = self._run_stop_routine()
            if not outcome.get("success"):
                self._report_stop_failure(count, outcome)
                return Decision.SAVE_FAILED
            print(
                "No recorded client is running and no unsaved mutations are "
                "pending — shutting down.",
                file=sys.stderr,
                flush=True,
            )
            self._exit_fn()
        elif decision is Decision.WAIT_GRACE:
            if not self._warned_grace:
                self._warned_grace = True
                print(
                    "No recorded client is running. "
                    f"{count if count is not None else 'An unknown number of'} "
                    f"unsaved in-memory mutation(s) are pending. In {self._grace:.0f}s, "
                    "if no client is running and nothing further is applied, the "
                    "daemon will save them to disk and stop, and will record that "
                    "it saved them itself.",
                    file=sys.stderr,
                    flush=True,
                )
        elif decision is Decision.EXIT_SAVE:
            outcome = self._run_stop_routine()
            if not outcome.get("success"):
                # Retaining unsaved work beats destroying it, so the
                # daemon stays up and tries again rather than resolving
                # the deadlock by dropping the mutations.
                self._report_stop_failure(count, outcome)
                self._warned_grace = False
                return Decision.SAVE_FAILED
            print(
                "No recorded client is running and the grace period expired. "
                f"Saved {count if count is not None else 'an unknown number of'} "
                "pending mutation(s) to disk and shutting down. The save was "
                "performed by the daemon, not requested by a client; that is "
                "recorded for the next client to read.",
                file=sys.stderr,
                flush=True,
            )
            self._exit_fn()
        return decision

    def _run_stop_routine(self) -> dict[str, Any]:
        """Hand over to the process's shutdown routine; never raise.

        A watchdog with no routine wired to it refuses to exit rather
        than exiting on its own: the whole point of routing through one
        routine is that nothing terminates without the work being
        accounted for, and a missing wire must fail that way round.
        """
        if self._stop_fn is None:
            return {"success": False, "error": "no shutdown routine configured"}
        try:
            return self._stop_fn()
        except Exception as exc:
            return {"success": False, "error": repr(exc)}

    def _report_stop_failure(self, count: int | None, outcome: dict[str, Any]) -> None:
        """Say what actually happened, not what usually happens.

        A clean stop reached this because the routine could not run at
        all, not because a save of anything failed; naming a grace period
        it never entered, and a count of zero it never tried to write,
        would send the reader looking in the wrong place.
        """
        if count == 0:
            print(
                "No recorded client is running and nothing is pending, but the "
                f"daemon could not stop: {outcome.get('error')}. It stays up and "
                "retries at the next interval.",
                file=sys.stderr,
                flush=True,
            )
            return
        print(
            "No recorded client is running and the grace period expired. Saving "
            f"{count if count is not None else 'an unknown number of'} pending "
            f"mutation(s) FAILED: {outcome.get('error')}. The mutations are "
            "retained; the daemon stays up and retries at the next interval.",
            file=sys.stderr,
            flush=True,
        )

    def start(self) -> None:
        """Start the background watchdog thread."""
        if self._thread is not None:
            return

        def _loop() -> None:
            while not self._stop.wait(self._interval):
                try:
                    decision = self.check_once()
                except Exception as exc:  # never let the guard die silently
                    print(
                        f"WARNING: client watchdog check failed ({exc!r}); "
                        "retrying at the next interval. If this repeats, the "
                        "daemon may outlive every client using it.",
                        file=sys.stderr,
                        flush=True,
                    )
                    continue
                if decision in (Decision.EXIT_CLEAN, Decision.EXIT_SAVE):
                    return

        self._thread = threading.Thread(target=_loop, name="elspais-client-watchdog", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the watchdog thread (used by tests)."""
        self._stop.set()
