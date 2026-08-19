# Implements: REQ-d00010-A
"""Starlette middleware for the elspais server."""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import traceback

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_log = logging.getLogger(__name__)


class NoCacheMiddleware(BaseHTTPMiddleware):
    """Set Cache-Control headers to prevent browser caching (dev server)."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response


class AutoRefreshMiddleware(BaseHTTPMiddleware):
    """Call state.ensure_fresh() on every request (throttled internally).

    CLI daemon clients send ``X-Force-Fresh: 1`` to bypass the throttle,
    ensuring the graph reflects any file changes made since the last request
    (e.g., after ``elspais fix`` writes spec files).
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        app_state = getattr(request.app.state, "app_state", None)
        if app_state is not None:
            if request.headers.get("x-force-fresh"):
                app_state._last_stale_check = 0  # bypass throttle
            app_state.ensure_fresh()
        return await call_next(request)


class TTLMiddleware(BaseHTTPMiddleware):
    """Stop the process after a period with no requests (daemon mode).

    A timer fires ``ttl_minutes`` after the last request and signals the
    process to stop; each incoming request restarts it.

    Going idle is not the same as having nothing to lose. An agent that
    applies a change and then reasons for half an hour sends no requests
    the whole time, so this is the *common* way a daemon holding unsaved
    work stops, not an exotic one. The timer therefore hands over to the
    process's one shutdown routine before it signals anything, exactly as
    the client-liveness watchdog does.
    """

    def __init__(self, app, shared, ttl_minutes: float = 30, clients_alive=None) -> None:
        super().__init__(app)
        self._ttl_seconds = ttl_minutes * 60
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()
        # Required, and supplied at construction rather than captured
        # from the first request. A timer that fires before any request
        # has arrived, or one wired up without a holder, would otherwise
        # stop the process without reaching the shutdown routine — which
        # is the behaviour this class exists to stop having.
        self._shared = shared
        # Supplied the same way, and absent means "no recorded client":
        # a daemon somebody started deliberately has no client to answer
        # to, and its lifetime stays exactly what it was.
        self._clients_alive = clients_alive
        self._start_timer()

    def _start_timer(self) -> None:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self._ttl_seconds, self._exit)
            self._timer.daemon = True
            self._timer.start()

    # Implements: REQ-o00074-O
    def _has_live_client(self) -> bool:
        """Whether a recorded client of this daemon still exists.

        Asked before anything else a stop would do. A source that cannot
        answer has said nothing about whether a client is there, so its
        failure keeps the daemon: ending one on the strength of a broken
        instrument is the outcome this check exists to prevent.
        """
        if self._clients_alive is None:
            return False
        try:
            return bool(self._clients_alive())
        except Exception as exc:
            print(
                f"WARNING: a client-liveness source could not be read ({exc!r}); "
                "treating the idle timeout as inconclusive and keeping the daemon.",
                file=sys.stderr,
                flush=True,
            )
            return True

    # Implements: REQ-o00062-O, REQ-o00074-O, REQ-p00083-A, REQ-p00083-D
    def _exit(self) -> None:
        from elspais.mcp.shared_state import finalize_shutdown, report_shutdown_outcome

        # Asked first, and before the shutdown routine, because that
        # routine commits the process to stopping: a daemon spared here
        # after being committed there would refuse every write and never
        # go, which is worse than either outcome on its own.
        if self._has_live_client():
            # Quiet is not gone. The timeout governs a daemon nobody is
            # using; this one has a client, so it waits out another idle
            # period and asks again rather than spinning.
            self._start_timer()
            return

        trigger = "the idle timeout expired"
        outcome = finalize_shutdown(self._shared, trigger=trigger)
        report_shutdown_outcome(outcome, trigger)
        if not outcome.get("success"):
            # The work is still held and is still reachable — the refusal
            # flag stays down — so stopping now would destroy it. Wait out
            # another idle period and try again instead.
            self._start_timer()
            return
        print("\nTTL expired — shutting down.", file=sys.stderr)
        # Nobody asked for this stop, so nobody is waiting on it: the
        # daemon decided, and it ends. Signalling itself would only put a
        # drain in the way, and a client holding a request open can stall
        # that drain for as long as it likes — with the work already
        # written and every write already refused, waiting there protects
        # nothing and risks a process that never goes. Dropping in-flight
        # reads is the cost, and a reader sees a reset it can act on.
        #
        # os._exit, not sys.exit: this runs on a timer thread, where
        # SystemExit unwinds that thread and leaves the process serving.
        os._exit(0)

    async def dispatch(self, request: Request, call_next) -> Response:
        self._start_timer()
        return await call_next(request)


class APIErrorMiddleware(BaseHTTPMiddleware):
    """Catch unhandled exceptions on /api/ routes and return JSON errors.

    Without this, unhandled exceptions produce an HTML 500 page which
    the frontend can't parse, resulting in 'Unknown error' messages.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        if not request.url.path.startswith("/api/"):
            return await call_next(request)
        try:
            return await call_next(request)
        except Exception:
            _log.exception("Unhandled error in %s %s", request.method, request.url.path)
            body = json.dumps(
                {
                    "success": False,
                    "error": f"Internal server error in {request.url.path}",
                    "detail": traceback.format_exc(),
                }
            ).encode()
            return Response(
                content=body,
                status_code=500,
                media_type="application/json",
            )
