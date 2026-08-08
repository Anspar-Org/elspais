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
from typing import Any

DEFAULT_CHECK_INTERVAL_SECONDS = 60.0
DEFAULT_GRACE_SECONDS = 300.0

# Sentinel for "no activity token observed yet" — distinct from a real
# token of None, which is what an empty mutation log reports.
_UNOBSERVED = object()


# Implements: REQ-o00074-G, REQ-o00074-H
def pending_snapshot(graph: Any) -> tuple[int, str | None]:
    """Return (pending mutation count, activity token) from one snapshot.

    The count is the number of pending unsaved mutations, so a warning
    about losing them states the real figure; a windowed query would cap
    the answer at the window size. The token is the mutation-log tip,
    which moves only when a change is applied or reversed — the same
    identity the history-level guards use.

    ``tail(0)`` snapshots the whole log; never iterate the live list
    while other writers may be appending to it.
    """
    entries = graph.mutation_log.tail(0)
    return len(entries), (entries[-1].id if entries else None)


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
        pending_fn: Callable[[], tuple[int, str | None]],
        interval_seconds: float = DEFAULT_CHECK_INTERVAL_SECONDS,
        grace_seconds: float = DEFAULT_GRACE_SECONDS,
        alive_fn: Callable[[int], bool] = pid_alive,
        exit_fn: Callable[[], None] = _default_exit,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._spawner_pid = spawner_pid
        self._pending_fn = pending_fn
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

    def check_once(self) -> Decision:
        """Evaluate the decision matrix once and act on the outcome."""
        alive = self._alive_fn(self._spawner_pid)

        count: int | None
        token: object
        try:
            count, token = self._pending_fn()
        except Exception:
            # Unknown -> treated as dirty, and no claim about activity.
            count, token = None, self._last_token

        if alive:
            self._dead_since = None
            self._warned_grace = False
            self._last_token = token
            return Decision.KEEP

        now = self._clock()

        # Implements: REQ-o00074-H
        # A tip that moved since the previous check is a writer that
        # adopted this daemon after its spawner died. Keep serving and
        # restart the countdown; the first token seen is a baseline, not
        # activity. Reads never move the tip, so polling cannot reach here.
        moved = self._last_token is not _UNOBSERVED and token != self._last_token
        self._last_token = token
        if moved:
            self._dead_since = now
            self._warned_grace = False
            return Decision.KEEP

        if self._dead_since is None:
            self._dead_since = now

        grace_expired = (now - self._dead_since) >= self._grace
        decision = shutdown_decision(
            spawner_pid=self._spawner_pid,
            spawner_alive=False,
            mutation_count=count,
            grace_expired=grace_expired,
        )

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
                decision = self.check_once()
                if decision in (Decision.EXIT_CLEAN, Decision.EXIT_DISCARD):
                    return

        self._thread = threading.Thread(target=_loop, name="elspais-spawner-watchdog", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the watchdog thread (used by tests)."""
        self._stop.set()
