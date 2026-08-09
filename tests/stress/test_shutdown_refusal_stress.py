# Verifies: REQ-p00083-G, REQ-o00062-O
"""A writer racing the daemon's decision to stop.

Between the decision to stop and the end of the drain, the HTTP stack and
the MCP worker threads keep accepting requests. A mutation accepted in
that window is guarded, applied, acknowledged to its writer -- and then
dies with the process. The whole point of persisting rather than
discarding pending work (REQ-p00083-A) is undone if the daemon goes on
swallowing writes it will never keep.

The invariant this battery asserts is not a timing window but the
irreversibility of the decision: once a writer has been told
``server_shutting_down``, nothing it sends afterwards may be
acknowledged as applied. Every response must be one of a small closed
set, and a refusal must carry the same body the MCP surface returns.

The daemon here is its own process, not the session-scoped ``stress_daemon``
every other test in this tier shares: the test kills it.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from tests.e2e.conftest import load_fixture
from tests.stress.conftest import _await_daemon_port, _await_viewer_ready

pytestmark = [pytest.mark.stress]

SCALE = float(os.environ.get("ELSPAIS_STRESS_SCALE", "1.0"))

NODES = ["REQ-p00001", "REQ-p00002", "REQ-p00003"]

# The exact keys the shutdown guard puts on a rejection, on either surface.
REFUSAL_KEYS = {"success", "code", "error", "hint"}


@pytest.fixture
def dying_daemon(tmp_path_factory):
    """A daemon this test is allowed to kill; yields (root, port, proc)."""
    pytest.importorskip("mcp")
    pytest.importorskip("httpx")
    root = tmp_path_factory.mktemp("shutdown_race")
    load_fixture("e2e-standard", root)

    state_dir = root / ".elspais"
    state_dir.mkdir(exist_ok=True)
    daemon_json = state_dir / "daemon.json"
    log_path = state_dir / "daemon.log"

    cmd = [
        sys.executable,
        "-m",
        "elspais",
        "mcp",
        "serve",
        "--transport",
        "streamable-http",
        "--port",
        "0",
        "--ttl",
        "30",
    ]
    with open(log_path, "w") as log_file:
        proc = subprocess.Popen(
            cmd,
            cwd=root,
            stdout=log_file,
            stderr=log_file,
            stdin=subprocess.DEVNULL,
            env={**os.environ, "_ELSPAIS_DAEMON_JSON": str(daemon_json)},
        )
    try:
        port = _await_daemon_port(daemon_json, proc, log_path)
        _await_viewer_ready(port, proc, log_path)
        yield root, port, proc
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


class TestWritesRacingTheShutdownDecision:
    """Verifies REQ-p00083-G: a write that arrives after the daemon has decided
    to stop is refused, never acknowledged and then lost with the process; and
    REQ-o00062-O: the refusal a writer receives has the shape callers already
    handle.
    """

    def test_no_write_is_acknowledged_after_that_writer_was_refused(self, dying_daemon):
        import httpx

        root, port, proc = dying_daemon
        base = f"http://127.0.0.1:{port}"
        writers = 6
        refusals: list[dict] = []
        refusals_lock = threading.Lock()
        # Per writer: everything that happened, in order, so an
        # acknowledgement landing after a refusal is visible as an order
        # violation rather than only as a count.
        timelines: list[list[str]] = [[] for _ in range(writers)]
        stop = threading.Event()

        def worker(i: int) -> None:
            client = httpx.Client(base_url=base, timeout=10.0)
            node = NODES[i % len(NODES)]
            n = 0
            while not stop.is_set():
                n += 1
                try:
                    r = client.get(f"/api/node/{node}")
                    if r.status_code != 200:
                        timelines[i].append("read-refused")
                        continue
                    version = r.json()["version"]
                    r = client.post(
                        "/api/mutate/title",
                        json={
                            "node_id": node,
                            "new_title": f"race-{i}-{n}",
                            "if_version": version,
                        },
                    )
                    body = r.json()
                except (httpx.HTTPError, ValueError):
                    # The socket died with the process. Nothing was
                    # acknowledged, which is a safe outcome.
                    timelines[i].append("gone")
                    continue
                if body.get("success"):
                    timelines[i].append("applied")
                elif body.get("code") == "server_shutting_down":
                    assert r.status_code == 409, f"refusal status {r.status_code}: {body}"
                    with refusals_lock:
                        refusals.append(body)
                    timelines[i].append("refused")
                elif body.get("code") == "version_conflict":
                    timelines[i].append("conflict")
                else:
                    timelines[i].append(f"UNCLASSIFIED:{body}")
            client.close()

        with ThreadPoolExecutor(max_workers=writers) as ex:
            futures = [ex.submit(worker, i) for i in range(writers)]
            # Let the writers get going, then take the decision out from
            # under them.
            time.sleep(1.0 * SCALE)
            proc.send_signal(signal.SIGTERM)
            proc.wait(timeout=30)
            time.sleep(0.5)
            stop.set()
            for f in futures:
                f.result()

        log_tail = (root / ".elspais" / "daemon.log").read_text()[-1500:]

        for i, timeline in enumerate(timelines):
            bad = [e for e in timeline if e.startswith("UNCLASSIFIED")]
            assert not bad, f"writer {i} got an unclassifiable response: {bad[0]}"
            assert timeline, f"writer {i} never completed a single attempt: {log_tail}"
            if "refused" in timeline:
                after = timeline[timeline.index("refused") + 1 :]
                assert "applied" not in after, (
                    f"writer {i} had a write acknowledged after it was told the "
                    f"server was shutting down: {timeline}"
                )

        assert proc.returncode is not None, "the daemon never stopped"
        # A run in which nobody was ever refused proves nothing: the drain
        # window is real (writers are hammering across it), so a daemon that
        # accepted everything until the socket closed is the accepted-then-
        # lost outcome, wearing a clean result.
        assert refusals, (
            "no writer was refused across the drain: writes were accepted right "
            f"up to the socket closing. daemon log tail: {log_tail}"
        )
        for body in refusals:
            assert set(body) == REFUSAL_KEYS, f"refusal body drifted: {sorted(body)}"
            assert body["success"] is False

    def test_refusal_body_matches_the_guard_the_mcp_surface_uses(self, dying_daemon):
        """The wire body a racing writer receives is the guard's own dict, not
        a hand-rolled lookalike -- so one handler covers both surfaces."""
        import httpx

        from elspais.mcp.server import _guard_shutdown

        class _Stopping:
            is_shutting_down = True

        expected = _guard_shutdown(_Stopping())
        assert expected is not None

        root, port, proc = dying_daemon
        client = httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=10.0)
        node = NODES[0]
        version = client.get(f"/api/node/{node}").json()["version"]

        proc.send_signal(signal.SIGTERM)
        # Race the drain: keep trying until either a refusal comes back or
        # the process is gone. A run in which the socket closes first proves
        # nothing about the body, so it is reported rather than passed.
        refusal = None
        deadline = time.time() + 15
        while time.time() < deadline and refusal is None:
            try:
                r = client.post(
                    "/api/mutate/title",
                    json={"node_id": node, "new_title": "late", "if_version": version},
                )
                body = r.json()
            except (httpx.HTTPError, ValueError):
                break
            if body.get("code") == "server_shutting_down":
                refusal = body
        client.close()
        proc.wait(timeout=30)

        if refusal is None:
            pytest.skip("the drain closed the socket before a refusal could be observed")
        assert refusal == expected, f"the wire refusal differs from the guard's: {refusal}"

    def test_daemon_json_and_process_agree_after_the_stop(self, dying_daemon):
        """A stopped daemon leaves no live process behind for the next client
        to be routed to."""
        root, port, proc = dying_daemon

        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=30)

        daemon_json = root / ".elspais" / "daemon.json"
        if daemon_json.is_file():
            recorded = json.loads(daemon_json.read_text()).get("pid")
            if recorded is not None:
                with pytest.raises(ProcessLookupError):
                    os.kill(recorded, 0)
