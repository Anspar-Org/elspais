# Implements: REQ-o00074-A, REQ-o00074-E
"""Held MCP streams as client handles.

A client holding a server-to-client stream open is present in a way a
completed request never is: the transport reports the close, including
when the client is killed, and the daemon binds the loopback interface
only, so a dead client's socket goes at once. That satisfies what a
client handle must be — something whose disappearance the daemon observes
without the client's cooperation — for a client that can supply no
process identifier.

Only long-lived streams count. A request that completed is traffic, and
counting traffic is the loophole that lets a polling client hold an
abandoned daemon open (REQ-o00074-F).
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any


class HeldSessionTracker:
    """Counts streams currently held open through the wrapped app."""

    def __init__(self) -> None:
        self._held = 0
        self._lock = threading.Lock()

    def held(self) -> int:
        with self._lock:
            return self._held

    def asgi(self, app: Callable[..., Any]) -> Callable[..., Any]:
        """Wrap an ASGI app so its held streams are counted."""

        async def _wrapped(scope: dict, receive: Any, send: Any) -> None:
            # Anything that is not an HTTP GET passes straight through:
            # lifespan messages cross this mount too, and a POST that has
            # finished is traffic rather than presence.
            if scope.get("type") != "http" or scope.get("method") != "GET":
                await app(scope, receive, send)
                return
            with self._lock:
                self._held += 1
            try:
                await app(scope, receive, send)
            finally:
                # Runs on a clean close, an error, and a cancellation, which
                # is what makes the handle's disappearance observable
                # without the client having to say anything.
                with self._lock:
                    self._held -= 1

        return _wrapped
