# Verifies: REQ-o00074-A+E
"""A held session as a client handle, verifying REQ-o00074.

REQ-o00074-A asks for a handle whose disappearance the daemon can observe
without the client's cooperation. A held stream is one: the transport
reports the close, including when the client is killed, and the daemon
binds the loopback interface only, so a dead client's socket closes at
once. REQ-o00074-E therefore obliges a client holding one to be recorded.

The distinction that matters is against REQ-o00074-F: a completed request
is traffic and must not count, while a stream still open is presence.
"""

from __future__ import annotations

import anyio
import pytest

from elspais.server.session_track import HeldSessionTracker


class _App:
    """Minimal ASGI app: GET holds until cancelled, POST returns at once."""

    def __init__(self, gate: anyio.Event) -> None:
        self.gate = gate

    async def __call__(self, scope, receive, send):
        if scope["method"] == "GET":
            await self.gate.wait()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})


@pytest.mark.anyio
async def test_REQ_o00074_A_held_stream_counts_as_a_client():
    """Validates REQ-o00074-A: a stream still open is a handle the daemon
    can observe, so it counts while it is held."""
    gate = anyio.Event()
    tracker = HeldSessionTracker()
    app = tracker.asgi(_App(gate))
    assert tracker.held() == 0

    async with anyio.create_task_group() as tg:
        tg.start_soon(app, {"type": "http", "method": "GET"}, _noop_receive, _noop_send)
        await _until(lambda: tracker.held() == 1)
        gate.set()
    assert tracker.held() == 0


@pytest.mark.anyio
async def test_REQ_o00074_F_completed_request_is_not_presence():
    """Validates REQ-o00074-F: request traffic does not discharge the
    liveness obligation, so a POST that has finished leaves no client."""
    tracker = HeldSessionTracker()
    app = tracker.asgi(_App(anyio.Event()))
    await app({"type": "http", "method": "POST"}, _noop_receive, _noop_send)
    assert tracker.held() == 0


@pytest.mark.anyio
async def test_REQ_o00074_A_stream_that_errors_releases_its_handle():
    """Validates REQ-o00074-A: the handle disappears when the connection
    does, without the client saying anything — including when it fails."""
    tracker = HeldSessionTracker()

    async def _boom(scope, receive, send):
        raise RuntimeError("connection dropped")

    app = tracker.asgi(_boom)
    with pytest.raises(RuntimeError):
        await app({"type": "http", "method": "GET"}, _noop_receive, _noop_send)
    assert tracker.held() == 0


@pytest.mark.anyio
async def test_REQ_o00074_A_cancelled_stream_releases_its_handle():
    """Validates REQ-o00074-A: a client killed mid-stream cooperates in
    nothing — the server task is simply cancelled — and the handle must
    still go, or a dead client would hold the daemon open forever."""
    gate = anyio.Event()
    tracker = HeldSessionTracker()
    app = tracker.asgi(_App(gate))

    async with anyio.create_task_group() as tg:
        tg.start_soon(app, {"type": "http", "method": "GET"}, _noop_receive, _noop_send)
        await _until(lambda: tracker.held() == 1)
        tg.cancel_scope.cancel()
    assert tracker.held() == 0


@pytest.mark.anyio
async def test_REQ_o00074_A_non_http_scopes_pass_through_untouched():
    """Validates REQ-o00074-A: the tracker sits on the daemon's request
    path, so a scope it does not count — a lifespan message — must still
    reach the app it wraps."""
    seen: list[str] = []

    async def _app(scope, receive, send):
        seen.append(scope["type"])

    tracker = HeldSessionTracker()
    app = tracker.asgi(_app)
    await app({"type": "lifespan"}, _noop_receive, _noop_send)
    assert seen == ["lifespan"]
    assert tracker.held() == 0


async def _noop_receive():
    return {"type": "http.request", "body": b"", "more_body": False}


async def _noop_send(message):
    return None


async def _until(predicate, timeout: float = 2.0):
    with anyio.fail_after(timeout):
        while not predicate():
            await anyio.sleep(0.01)
