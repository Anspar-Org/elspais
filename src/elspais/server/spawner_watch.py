# Implements: REQ-o00074
"""Spawner liveness watchdog for the background daemon.

A daemon spawned implicitly to serve a CLI/session records the spawner's
PID (passed via the ``_ELSPAIS_SPAWNER_PID`` env var, since
``start_new_session=True`` reparents the daemon to PID 1). This module
watches that PID at a low frequency and shuts the daemon down once the
spawner is gone, so orphaned daemons cannot accumulate and keep serving
answers no session is watching.

Daemons started without spawner identity (manual ``elspais mcp serve``,
the viewer, ``elspais daemon restart``) never get a watchdog and keep
their TTL-only lifetime.

Shutdown decision matrix (``shutdown_decision``):

    spawner identity absent            -> KEEP (TTL-only behavior)
    spawner alive                      -> KEEP
    spawner dead, no unsaved mutations -> EXIT_CLEAN
    spawner dead, unsaved, in grace    -> WAIT_GRACE (warn, extend)
    spawner dead, unsaved, grace over  -> EXIT_DISCARD (warn loudly, exit)

A daemon outlives its spawner precisely so a later session can adopt it,
and the adopting writer's mutations are indistinguishable from the dead
session's. ``check_once`` therefore reads an activity token — the
mutation-log tip — ahead of the matrix: a tip that moved since the last
check is proof a writer is present, so the daemon keeps serving and the
grace clock restarts. Reads move nothing, so a polling client still
cannot hold an orphan open.

Unsaved mutations are never silently persisted: the daemon logs the true
pending count and the bounded grace deadline, then exits without writing
anything. Persisting is a caller's act; a lifetime rule that edited the
caller's spec files unattended would be a worse failure than the loss it
prevents. The loss risk is visible in daemon.log.
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
DEFAULT_GRACE_SECONDS = 300.0

# Sentinel for "no activity token observed yet" — distinct from a real
# token of None, which is what an empty mutation log reports.
_UNOBSERVED = object()


# Implements: REQ-o00074-G, REQ-o00074-H
def pending_snapshot(graph: Any) -> tuple[int, object]:
    """Return (pending mutation count, activity token) from one snapshot.

    The count is the number of pending unsaved mutations, so a warning
    about losing them states the real figure; a windowed query would cap
    the answer at the window size.

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
    """Outcome of one spawner-liveness evaluation."""

    KEEP = "keep"
    EXIT_CLEAN = "exit-clean"
    WAIT_GRACE = "wait-grace"
    EXIT_DISCARD = "exit-discard"


def shutdown_decision(
    spawner_pid: int | None,
    spawner_alive: bool,
    mutation_count: int | None,
    grace_expired: bool,
) -> Decision:
    """Pure decision function for the spawner watchdog.

    Args:
        spawner_pid: Recorded spawner identity, or None if the daemon was
            started without one (explicit/manual start).
        spawner_alive: Whether the spawner process currently exists.
            Ignored when spawner_pid is None.
        mutation_count: Unsaved in-memory mutations. None means unknown,
            which is treated as dirty (conservative: never discard work
            we cannot prove is saved).
        grace_expired: Whether the bounded dirty-daemon grace period has
            elapsed since the spawner was first seen dead.
    """
    if spawner_pid is None:
        return Decision.KEEP
    if spawner_alive:
        return Decision.KEEP
    dirty = mutation_count is None or mutation_count > 0
    if not dirty:
        return Decision.EXIT_CLEAN
    if grace_expired:
        return Decision.EXIT_DISCARD
    return Decision.WAIT_GRACE


def _default_exit() -> None:
    # Same mechanism as TTLMiddleware._exit: sys.exit() from a non-main
    # thread does not terminate the process; SIGTERM lets uvicorn shut
    # down gracefully.
    os.kill(os.getpid(), signal.SIGTERM)


class SpawnerWatchdog:
    """Low-frequency background check that the spawner is still alive.

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
    ) -> None:
        self._spawner_pid = spawner_pid
        self._pending_fn = pending_fn
        self._lock = lock if lock is not None else nullcontext()
        self._interval = interval_seconds
        self._grace = grace_seconds
        self._alive_fn = alive_fn
        self._exit_fn = exit_fn
        self._clock = clock
        self._dead_since: float | None = None
        self._warned_grace = False
        self._last_token: object = _UNOBSERVED
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _pending(self) -> tuple[int | None, object]:
        """Read pending count and activity token; unknown reads as dirty."""
        try:
            return self._pending_fn()
        except Exception:
            return None, self._last_token

    def check_once(self) -> Decision:
        """Evaluate the decision matrix once and act on the outcome.

        Implements: REQ-o00074-G

        The decision to terminate is taken while holding the writers'
        lock, and the pending state is re-read inside it. Deciding from
        a snapshot taken outside the lock let a mutation be accepted --
        and acknowledged to its writer -- between the read and the exit,
        which terminated the daemon holding work it had just reported as
        absent.
        """
        alive = self._alive_fn(self._spawner_pid)

        count, token = self._pending()

        if alive:
            self._dead_since = None
            self._warned_grace = False
            self._last_token = token
            return Decision.KEEP

        now = self._clock()

        # Implements: REQ-o00074-H
        # A token that moved since the previous check is a writer that
        # adopted this daemon after its spawner died. Keep serving and
        # restart the countdown; the first token seen is a baseline, not
        # activity. Reads never move it, so polling cannot reach here.
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
                spawner_pid=self._spawner_pid,
                spawner_alive=False,
                mutation_count=count,
                grace_expired=grace_expired,
            )
            return self._act(decision, count)

    def _act(self, decision: Decision, count: int | None) -> Decision:
        """Emit the disclosure the decision requires and exit if it says so."""
        # Implements: REQ-o00074-E, REQ-o00074-G, REQ-o00074-I
        if decision is Decision.EXIT_CLEAN:
            print(
                f"Spawner (pid {self._spawner_pid}) is gone and no unsaved "
                "mutations are pending — shutting down.",
                file=sys.stderr,
                flush=True,
            )
            self._exit_fn()
        elif decision is Decision.WAIT_GRACE:
            if not self._warned_grace:
                self._warned_grace = True
                print(
                    f"WARNING: spawner (pid {self._spawner_pid}) is gone but "
                    f"{count if count is not None else 'an unknown number of'} "
                    "unsaved in-memory mutation(s) are pending. Extending for a "
                    f"grace period of {self._grace:.0f}s; save via "
                    "'elspais daemon restart --persist' or the mutations will "
                    "be DISCARDED when the daemon exits.",
                    file=sys.stderr,
                    flush=True,
                )
        elif decision is Decision.EXIT_DISCARD:
            print(
                f"WARNING: spawner (pid {self._spawner_pid}) is gone and the "
                f"grace period expired — exiting WITHOUT saving "
                f"{count if count is not None else 'an unknown number of'} "
                "in-memory mutation(s). They are discarded.",
                file=sys.stderr,
                flush=True,
            )
            self._exit_fn()
        return decision

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
                        f"WARNING: spawner watchdog check failed ({exc!r}); "
                        "retrying at the next interval. If this repeats, the "
                        "daemon may outlive its session.",
                        file=sys.stderr,
                        flush=True,
                    )
                    continue
                if decision in (Decision.EXIT_CLEAN, Decision.EXIT_DISCARD):
                    return

        self._thread = threading.Thread(target=_loop, name="elspais-spawner-watchdog", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the watchdog thread (used by tests)."""
        self._stop.set()
