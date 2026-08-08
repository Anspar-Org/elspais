# Implements: REQ-d00010-A
"""Starlette middleware for the elspais server."""
from __future__ import annotations

import json
import logging
import os
import signal
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

    def __init__(self, app, shared, ttl_minutes: float = 30) -> None:
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
        self._start_timer()

    def _start_timer(self) -> None:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self._ttl_seconds, self._exit)
            self._timer.daemon = True
            self._timer.start()

    # Implements: REQ-o00062-O, REQ-o00074-I, REQ-o00074-K
    def _exit(self) -> None:
        from elspais.mcp.shared_state import finalize_shutdown, report_shutdown_outcome

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
        # sys.exit() only raises SystemExit in the calling thread — it does
        # NOT terminate the process when called from a non-main thread.
        # Use SIGTERM so uvicorn shuts down gracefully.
        os.kill(os.getpid(), signal.SIGTERM)

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
