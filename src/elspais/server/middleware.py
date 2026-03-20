# Implements: REQ-d00010-A
"""Starlette middleware for the elspais server."""
from __future__ import annotations

import sys
import threading

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class NoCacheMiddleware(BaseHTTPMiddleware):
    """Set Cache-Control headers to prevent browser caching (dev server)."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response


class AutoRefreshMiddleware(BaseHTTPMiddleware):
    """Call state.ensure_fresh() on every request (throttled internally)."""

    async def dispatch(self, request: Request, call_next) -> Response:
        app_state = getattr(request.app.state, "app_state", None)
        if app_state is not None:
            app_state.ensure_fresh()
        return await call_next(request)


class TTLMiddleware(BaseHTTPMiddleware):
    """Auto-exit after inactivity (daemon mode).

    Starts a daemon watchdog thread that calls sys.exit(0) after
    ``ttl_minutes`` of inactivity. Each incoming request resets the timer.
    """

    def __init__(self, app, ttl_minutes: float = 30) -> None:
        super().__init__(app)
        self._ttl_seconds = ttl_minutes * 60
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()
        self._start_timer()

    def _start_timer(self) -> None:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self._ttl_seconds, self._exit)
            self._timer.daemon = True
            self._timer.start()

    @staticmethod
    def _exit() -> None:
        print("\nTTL expired — shutting down.", file=sys.stderr)
        sys.exit(0)

    async def dispatch(self, request: Request, call_next) -> Response:
        self._start_timer()
        return await call_next(request)
