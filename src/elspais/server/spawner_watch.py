# Implements: REQ-p00015-E
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

Unsaved mutations are never silently persisted: the daemon logs the
mutation count and the bounded grace deadline, then exits without
writing anything. The loss risk is visible in daemon.log.
"""

from __future__ import annotations

import enum
import os
import signal
import sys
import threading
import time
from collections.abc import Callable

DEFAULT_CHECK_INTERVAL_SECONDS = 60.0
DEFAULT_GRACE_SECONDS = 300.0


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
        mutation_count_fn: Callable[[], int | None],
        interval_seconds: float = DEFAULT_CHECK_INTERVAL_SECONDS,
        grace_seconds: float = DEFAULT_GRACE_SECONDS,
        alive_fn: Callable[[int], bool] = pid_alive,
        exit_fn: Callable[[], None] = _default_exit,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._spawner_pid = spawner_pid
        self._mutation_count_fn = mutation_count_fn
        self._interval = interval_seconds
        self._grace = grace_seconds
        self._alive_fn = alive_fn
        self._exit_fn = exit_fn
        self._clock = clock
        self._dead_since: float | None = None
        self._warned_grace = False
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def check_once(self) -> Decision:
        """Evaluate the decision matrix once and act on the outcome."""
        alive = self._alive_fn(self._spawner_pid)
        if alive:
            self._dead_since = None
            self._warned_grace = False
            return Decision.KEEP

        now = self._clock()
        if self._dead_since is None:
            self._dead_since = now

        count: int | None
        try:
            count = self._mutation_count_fn()
        except Exception:
            count = None  # unknown -> treated as dirty

        grace_expired = (now - self._dead_since) >= self._grace
        decision = shutdown_decision(
            spawner_pid=self._spawner_pid,
            spawner_alive=False,
            mutation_count=count,
            grace_expired=grace_expired,
        )

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
