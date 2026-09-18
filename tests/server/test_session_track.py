# Verifies: REQ-o00074-A+E, REQ-o00079-A+B+C
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

import json

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


# Verifies: REQ-o00074-A
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


# Verifies: REQ-o00074-F
@pytest.mark.anyio
async def test_REQ_o00074_F_completed_request_is_not_presence():
    """Validates REQ-o00074-F: request traffic does not discharge the
    liveness obligation, so a POST that has finished leaves no client."""
    tracker = HeldSessionTracker()
    app = tracker.asgi(_App(anyio.Event()))
    await app({"type": "http", "method": "POST"}, _noop_receive, _noop_send)
    assert tracker.held() == 0


# Verifies: REQ-o00074-A
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


# Verifies: REQ-o00074-A
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


# Verifies: REQ-o00074-A
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


# ---------------------------------------------------------------------------
# The page's change stream as a held handle (REQ-o00079)
# ---------------------------------------------------------------------------


def _events_app(canonical_federated_graph):
    """The real viewer app, so the route and its tracker are the ones served."""
    from elspais.server.app import create_app
    from elspais.server.state import AppState

    fg = canonical_federated_graph
    config = fg._repos[fg._root_repo].config
    repo_root = fg._repos[fg._root_repo].repo_root
    state = AppState(graph=fg, repo_root=repo_root, config=config)
    return create_app(state, mount_mcp=False), state


class _Client:
    """One HTTP request driven at the ASGI level, closed when the test says.

    ``disconnect`` is what a browser tab closing looks like to the server:
    the transport delivers ``http.disconnect`` and the response task is
    cancelled. The events the server wrote before that are kept for
    inspection.
    """

    def __init__(self, path: str) -> None:
        self.scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "root_path": "",
            "headers": [(b"host", b"testserver")],
            "client": ("127.0.0.1", 1),
            "server": ("127.0.0.1", 80),
        }
        self._closed = anyio.Event()
        self._sent_body = False
        self.status: int | None = None
        self.chunks: list[bytes] = []
        self.finished = anyio.Event()

    async def receive(self) -> dict:
        if not self._sent_body:
            self._sent_body = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await self._closed.wait()
        return {"type": "http.disconnect"}

    async def send(self, message: dict) -> None:
        if message["type"] == "http.response.start":
            self.status = message["status"]
        elif message["type"] == "http.response.body":
            if message.get("body"):
                self.chunks.append(message["body"])
            if not message.get("more_body", False):
                self.finished.set()

    def disconnect(self) -> None:
        self._closed.set()

    def events(self) -> list[tuple[str, dict]]:
        out: list[tuple[str, dict]] = []
        for block in b"".join(self.chunks).decode().split("\n\n"):
            name, data = None, None
            for line in block.splitlines():
                if line.startswith("event: "):
                    name = line[len("event: ") :]
                elif line.startswith("data: "):
                    data = json.loads(line[len("data: ") :])
            if name is not None and data is not None:
                out.append((name, data))
        return out


async def _run(app, client: _Client) -> None:
    await app(client.scope, client.receive, client.send)


# Verifies: REQ-o00079-A
@pytest.mark.anyio
async def test_REQ_o00079_A_open_change_stream_is_a_held_handle(canonical_federated_graph):
    """Validates REQ-o00079-A: a page holding the change stream is counted
    as a client for as long as the stream is open, through the same tracker
    that counts an agent's MCP session."""
    app, state = _events_app(canonical_federated_graph)
    tracker = state.shared["session_tracker"]
    page = _Client("/api/events")

    async with anyio.create_task_group() as tg:
        tg.start_soon(_run, app, page)
        await _until(lambda: tracker.held() == 1)
        assert page.status == 200
        page.disconnect()
        await _until(lambda: tracker.held() == 0)
    assert tracker.held() == 0


# Verifies: REQ-o00079-A
@pytest.mark.anyio
async def test_REQ_o00079_A_a_completed_request_on_the_page_is_not_a_handle(
    canonical_federated_graph,
):
    """Validates REQ-o00079-A: only the stream the page holds open counts.
    A GET the page makes and that completes — the count probe — is traffic
    (REQ-o00074-F) and leaves nothing held."""
    app, state = _events_app(canonical_federated_graph)
    tracker = state.shared["session_tracker"]
    probe = _Client("/api/dirty")

    await _run(app, probe)
    assert probe.status == 200
    assert tracker.held() == 0


# Verifies: REQ-o00079-C
@pytest.mark.anyio
async def test_REQ_o00079_C_stream_opens_with_the_current_tip_and_its_interval(
    canonical_federated_graph, monkeypatch
):
    """Validates REQ-o00079-C: the first thing the page hears is where the
    graph stands and how often the server undertakes to speak, so the page
    can tell a quiet server from a gone one without a number of its own."""
    monkeypatch.setenv("_ELSPAIS_EVENTS_HEARTBEAT", "0.2")
    app, state = _events_app(canonical_federated_graph)
    page = _Client("/api/events")

    async with anyio.create_task_group() as tg:
        tg.start_soon(_run, app, page)
        await _until(lambda: len(page.events()) >= 1)
        page.disconnect()

    name, data = page.events()[0]
    assert name == "hello"
    assert data["mutation_tip"] == ""
    assert data["heartbeat_seconds"] == 0.2
    assert data["stale"] is False


# Verifies: REQ-o00079-C
@pytest.mark.anyio
async def test_REQ_o00079_C_a_change_is_announced_without_being_asked_for(
    canonical_federated_graph, monkeypatch
):
    """Validates REQ-o00079-C: a mutation applied to the graph reaches the
    page as an announcement carrying the moved tip, and is undone the same
    way — the page is told, it never asks."""
    monkeypatch.setenv("_ELSPAIS_EVENTS_HEARTBEAT", "30")
    app, state = _events_app(canonical_federated_graph)
    page = _Client("/api/events")
    fg = canonical_federated_graph

    async with anyio.create_task_group() as tg:
        tg.start_soon(_run, app, page)
        await _until(lambda: len(page.events()) >= 1)
        entry = fg.update_title("REQ-p00001", "Announced Title")
        try:
            await _until(lambda: len(page.events()) >= 2, timeout=5.0)
            name, data = page.events()[1]
            assert name == "change"
            assert data["mutation_tip"] == entry.id
            assert data["has_pending_mutations"] is True
        finally:
            fg.undo_last()
        await _until(lambda: len(page.events()) >= 3, timeout=5.0)
        page.disconnect()

    name, data = page.events()[2]
    assert name == "change", "an undo changes what the page shows and must be announced too"
    assert data["mutation_tip"] == ""


# Verifies: REQ-o00079-C
@pytest.mark.anyio
async def test_REQ_o00079_C_server_announces_itself_when_nothing_changed(
    canonical_federated_graph, monkeypatch
):
    """Validates REQ-o00079-C: with nothing to report the server still
    speaks at its interval, which is what lets the page treat silence past
    that interval as a server that has stopped answering (REQ-o00079-E)."""
    monkeypatch.setenv("_ELSPAIS_EVENTS_HEARTBEAT", "0.2")
    app, state = _events_app(canonical_federated_graph)
    page = _Client("/api/events")

    async with anyio.create_task_group() as tg:
        tg.start_soon(_run, app, page)
        await _until(lambda: len(page.events()) >= 3, timeout=5.0)
        page.disconnect()

    names = [name for name, _ in page.events()]
    assert names[0] == "hello"
    assert names[1:3] == ["heartbeat", "heartbeat"]


# Verifies: REQ-o00079-B
@pytest.mark.anyio
async def test_REQ_o00079_B_stream_ends_once_the_process_commits_to_stopping(
    canonical_federated_graph, monkeypatch
):
    """Validates REQ-o00079-B: a process that has committed to stopping
    stops announcing, so a page holding the stream does not stall the
    drain a stop waits on, and the ending is executed rather than held
    open by the very client it is serving."""
    monkeypatch.setenv("_ELSPAIS_EVENTS_HEARTBEAT", "0.2")
    app, state = _events_app(canonical_federated_graph)
    tracker = state.shared["session_tracker"]
    page = _Client("/api/events")

    async with anyio.create_task_group() as tg:
        tg.start_soon(_run, app, page)
        await _until(lambda: len(page.events()) >= 1)
        state.shared.begin_shutdown()
        with anyio.fail_after(5.0):
            await page.finished.wait()
        page.disconnect()
    assert tracker.held() == 0
