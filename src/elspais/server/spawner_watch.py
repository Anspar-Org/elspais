# Implements: REQ-o00074
"""Client-liveness watchdog for the background daemon.

A daemon spawned implicitly to serve a CLI/session records the spawning
client's PID (passed via the ``_ELSPAIS_SPAWNER_PID`` env var, since
``start_new_session=True`` reparents the daemon to PID 1). A client that
later adopts the running daemon registers itself too, so the watchdog
tracks a *set* of client PIDs rather than only the process that happened
to start the daemon. It watches them at a low frequency and shuts the
daemon down once every one of them is gone, so orphaned daemons cannot
accumulate and keep serving answers no client is watching.

Daemons started without client identity (manual ``elspais mcp serve``,
the viewer, ``elspais daemon restart``) never get a watchdog and keep
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

Pending work is never destroyed at the deadline. The daemon persists it
and records who saved, when, how much, and what triggered it, so a later
client can see how the files reached their current form (REQ-o00074-I).
The record states those facts and nothing else: a client can disappear
because it finished, crashed, or lost its connection, and nothing here
can tell those apart, so no conclusion about the work is drawn on the
reader's behalf.

Preservation is the default because the costs are asymmetric — the files
are under revision control, where an unwanted write costs one command to
inspect and revert, while discarded work has to be redone from memory
and sometimes cannot be. If the save itself fails, the work is retained
and retried rather than dropped (REQ-o00074-K).
"""

from __future__ import annotations

import enum
import os
import signal
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
    # Same mechanism as TTLMiddleware._exit: sys.exit() from a non-main
    # thread does not terminate the process; SIGTERM lets uvicorn shut
    # down gracefully.
    os.kill(os.getpid(), signal.SIGTERM)


class SpawnerWatchdog:
    """Low-frequency background check that some client is still alive.

    Independent of HTTP traffic (and of TTLMiddleware, which is absent
    when cli_ttl < 0), so polling clients cannot keep an orphaned daemon
    alive indefinitely.
    """

    def __init__(
        self,
        spawner_pid: int,
        pending_fn: Callable[[], tuple[int, object]],
        interval_seconds: float = DEFAULT_CHECK_INTERVAL_SECONDS,
        grace_seconds: float = DEFAULT_GRACE_SECONDS,
        alive_fn: Callable[[int], bool] = pid_alive,
        exit_fn: Callable[[], None] = _default_exit,
        clock: Callable[[], float] = time.monotonic,
        lock: AbstractContextManager[Any] | None = None,
        save_fn: Callable[[], dict[str, Any]] | None = None,
        shutdown_fn: Callable[[], None] | None = None,
    ) -> None:
        self._clients: set[int] = {spawner_pid}
        self._clients_lock = threading.Lock()
        self._pending_fn = pending_fn
        self._lock = lock if lock is not None else nullcontext()
        self._interval = interval_seconds
        self._grace = grace_seconds
        self._alive_fn = alive_fn
        self._exit_fn = exit_fn
        self._save_fn = save_fn
        self._shutdown_fn = shutdown_fn
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

    def clients(self) -> list[int]:
        """Currently recorded client PIDs, for disclosure to callers."""
        with self._clients_lock:
            return sorted(self._clients)

    def _any_client_alive(self) -> bool:
        """True if any recorded client still exists; prunes the dead ones.

        Pruning keeps the recorded set an honest answer to "who is using
        this daemon", which assertion B publishes.
        """
        with self._clients_lock:
            live = {pid for pid in self._clients if self._alive_fn(pid)}
            self._clients = live if live else self._clients
            return bool(live)

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

        Implements: REQ-o00074-E, REQ-o00074-G, REQ-o00074-I, REQ-o00074-K

        Runs under the writers' lock. Both exiting branches raise the
        shutdown flag before signalling the process, so a write that
        arrives after the decision is refused rather than accepted and
        then dropped by the drain.
        """
        if decision is Decision.EXIT_CLEAN:
            print(
                "No recorded client is running and no unsaved mutations are "
                "pending — shutting down.",
                file=sys.stderr,
                flush=True,
            )
            self._begin_shutdown()
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
            result = self._automatic_save(count)
            if not result.get("success"):
                # Retaining unsaved work beats destroying it, so the
                # daemon stays up and tries again rather than resolving
                # the deadlock by dropping the mutations.
                print(
                    "No recorded client is running and the grace period "
                    f"expired. Saving "
                    f"{count if count is not None else 'an unknown number of'} "
                    f"pending mutation(s) FAILED: {result.get('error')}. The "
                    "mutations are retained; the daemon stays up and retries "
                    "at the next interval.",
                    file=sys.stderr,
                    flush=True,
                )
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
            self._begin_shutdown()
            self._exit_fn()
        return decision

    def _begin_shutdown(self) -> None:
        if self._shutdown_fn is not None:
            self._shutdown_fn()

    def _automatic_save(self, count: int | None) -> dict[str, Any]:
        """Persist pending work, reporting failure rather than raising."""
        if self._save_fn is None:
            return {"success": False, "error": "no save path configured"}
        try:
            return self._save_fn()
        except Exception as exc:
            return {"success": False, "error": repr(exc)}

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

        self._thread = threading.Thread(target=_loop, name="elspais-spawner-watchdog", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the watchdog thread (used by tests)."""
        self._stop.set()
