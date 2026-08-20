# Verifies: REQ-o00062-I, REQ-o00062-N, REQ-o00062-Q
"""Concurrency stress battery for the optimistic-concurrency guards.

Genuinely concurrent writers (barrier-released threads) race the two live
surfaces of one daemon — MCP tools on FastMCP worker threads, viewer HTTP
routes on the event loop — and every round asserts the guard invariants:

- exactly one writer per version token wins (REQ-o00062-I), losers get a
  well-formed ``version_conflict``;
- exactly one history actor per mutation-log tip wins (REQ-o00062-N);
- the same holds when the racers are split across MCP and HTTP
  (REQ-o00062-Q — the surfaces guard against each other, not only
  against their own transport);
- after a randomized storm the graph is coherent, a tip-guarded save
  persists every accepted write, and the saved state passes checks.

Scale with ``ELSPAIS_STRESS_SCALE`` (float, default 1.0): CI keeps the
default; a manual soak run can use e.g. ``ELSPAIS_STRESS_SCALE=10``.
"""

from __future__ import annotations

import json
import os
import random
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

pytestmark = [pytest.mark.stress]

SCALE = float(os.environ.get("ELSPAIS_STRESS_SCALE", "1.0"))


def _rounds(base: int) -> int:
    return max(1, int(base * SCALE))


# ---------------------------------------------------------------------------
# Clients: viewer HTTP surface + minimal sync MCP streamable-http client
# ---------------------------------------------------------------------------


class McpClient:
    """Minimal synchronous MCP streamable-http client, safe per-thread.

    The real ``mcp`` client is asyncio-only; barrier-released racer threads
    need a sync client each. Speaks just enough of the protocol:
    initialize, initialized notification, tools/call with SSE responses.
    """

    def __init__(self, base: str):
        import httpx

        self.http = httpx.Client(base_url=base, timeout=30.0)
        self.session_id: str | None = None
        self._id = 0
        self._lock = threading.Lock()
        resp = self._post(
            {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "stress", "version": "0"},
                },
            }
        )
        assert resp and "result" in resp, f"MCP initialize failed: {resp}"
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def _next_id(self) -> int:
        with self._lock:
            self._id += 1
            return self._id

    def _post(self, payload: dict) -> dict | None:
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        if self.session_id:
            headers["mcp-session-id"] = self.session_id
        r = self.http.post("/mcp/", json=payload, headers=headers)
        if "mcp-session-id" in r.headers:
            self.session_id = r.headers["mcp-session-id"]
        if r.status_code == 202:
            return None
        if "text/event-stream" in r.headers.get("content-type", ""):
            msg = None
            for line in r.text.splitlines():
                if line.startswith("data:"):
                    msg = json.loads(line[5:].strip())
            return msg
        return r.json() if r.content else None

    def call(self, tool: str, arguments: dict) -> dict:
        resp = self._post(
            {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "tools/call",
                "params": {"name": tool, "arguments": arguments},
            }
        )
        assert resp is not None and "error" not in resp, f"RPC failure: {resp}"
        result = resp["result"]
        if result.get("structuredContent") is not None:
            sc = result["structuredContent"]
            return sc.get("result", sc)
        return json.loads(result["content"][0]["text"])


class Surfaces:
    """Both surfaces of one daemon, plus the shared assertions."""

    def __init__(self, root, port: int, mcp_clients: int):
        import httpx

        self.root = root
        self.base = f"http://127.0.0.1:{port}"
        self.http = httpx.Client(base_url=self.base, timeout=30.0)
        self.mcp = [McpClient(self.base) for _ in range(mcp_clients)]

    def node(self, node_id: str) -> dict:
        r = self.http.get(f"/api/node/{node_id}")
        assert r.status_code == 200, f"read {node_id}: {r.status_code} {r.text[:200]}"
        return r.json()

    def version(self, node_id: str) -> str:
        return self.node(node_id)["version"]

    def title_http(self, node_id: str, title: str, if_version: str) -> dict:
        r = self.http.post(
            "/api/mutate/title",
            json={"node_id": node_id, "new_title": title, "if_version": if_version},
        )
        body = r.json()
        body["_status"] = r.status_code
        return body

    def current_tip(self) -> str:
        return self.mcp[0].call("get_mutation_log", {"limit": 1}).get("current_tip", "")


@pytest.fixture(scope="module")
def surfaces(stress_daemon):
    root, port = stress_daemon
    return Surfaces(root, port, mcp_clients=4)


def barrier_run(n: int, fn) -> list:
    """Release n threads through a barrier simultaneously; collect results."""
    barrier = threading.Barrier(n)
    results: list = [None] * n

    def work(i: int) -> None:
        barrier.wait()
        try:
            results[i] = fn(i)
        except Exception as exc:  # surfaced by the caller's assertions
            results[i] = {"_exception": repr(exc)}

    threads = [threading.Thread(target=work, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


def _wins(results: list) -> list[int]:
    return [i for i, r in enumerate(results) if r.get("success")]


def _non_conflicts(results: list) -> list:
    return [
        (i, r)
        for i, r in enumerate(results)
        if not r.get("success")
        and r.get("code") not in ("version_conflict", "mutation_log_conflict")
    ]


# ---------------------------------------------------------------------------
# Races
# ---------------------------------------------------------------------------


class TestVersionTokenRaces:
    """Verifies REQ-o00062-I: one accept per token, no lost updates."""

    NODE = "REQ-p00001"

    def test_same_token_http_race_has_exactly_one_winner(self, surfaces):
        writers = 8
        for rnd in range(_rounds(10)):
            ver = surfaces.version(self.NODE)
            titles = [f"http-r{rnd}-w{i}" for i in range(writers)]
            results = barrier_run(
                writers,
                lambda i, ts=titles, v=ver: surfaces.title_http(self.NODE, ts[i], v),
            )
            wins = _wins(results)
            assert len(wins) == 1, f"round {rnd}: {len(wins)} winners: {results}"
            assert not _non_conflicts(results), f"round {rnd}: {results}"
            # the winner's write, and only it, is the committed state
            assert surfaces.node(self.NODE)["title"] == titles[wins[0]]
            # losers' rejections carry the reconciliation payload (REQ-o00062-J)
            for i, r in enumerate(results):
                if i != wins[0]:
                    assert "current_version" in r and "current_state" in r

    def test_cross_surface_race_has_exactly_one_winner(self, surfaces):
        """Verifies REQ-o00062-Q: MCP and HTTP writers guard each other."""
        writers = 8
        for rnd in range(_rounds(10)):
            ver = surfaces.version(self.NODE)
            titles = [f"xsurf-r{rnd}-w{i}" for i in range(writers)]

            def attempt(i: int, titles=titles, ver=ver) -> dict:
                if i % 2 == 0:
                    return surfaces.title_http(self.NODE, titles[i], ver)
                return surfaces.mcp[i // 2].call(
                    "mutate_update_title",
                    {"node_id": self.NODE, "new_title": titles[i], "if_version": ver},
                )

            results = barrier_run(writers, attempt)
            wins = _wins(results)
            assert len(wins) == 1, f"round {rnd}: {len(wins)} winners: {results}"
            assert not _non_conflicts(results), f"round {rnd}: {results}"
            assert surfaces.node(self.NODE)["title"] == titles[wins[0]]

    def test_same_id_creation_race_creates_exactly_once(self, surfaces):
        """Verifies REQ-o00062-I: the parentless-creation exemption still
        cannot mint the same ID twice under concurrency."""
        creators = 6
        for rnd in range(_rounds(6)):
            req_id = f"REQ-d8{rnd:04d}"
            results = barrier_run(
                creators,
                lambda i, req_id=req_id, rnd=rnd: surfaces.mcp[i % len(surfaces.mcp)].call(
                    "mutate_add_requirement",
                    {"req_id": req_id, "title": f"create-r{rnd}-w{i}", "level": "DEV"},
                ),
            )
            wins = _wins(results)
            assert len(wins) == 1, f"round {rnd}: {len(wins)} creators won: {results}"
            winner_title = f"create-r{rnd}-w{wins[0]}"
            assert surfaces.node(req_id)["title"] == winner_title


class TestMutationTipRaces:
    """Verifies REQ-o00062-N: one history actor per tip."""

    NODE = "REQ-p00002"

    def test_tip_guarded_undo_race_has_exactly_one_winner(self, surfaces):
        racers = 6
        for rnd in range(_rounds(6)):
            # Seed two mutations so there is real pending history and a tip.
            for k in range(2):
                ver = surfaces.version(self.NODE)
                res = surfaces.title_http(self.NODE, f"undo-r{rnd}-seed{k}", ver)
                assert res.get("success"), f"seed failed: {res}"
            tip = surfaces.current_tip()
            assert tip, "seeded history must expose a current_tip"

            def attempt(i: int, tip=tip) -> dict:
                if i % 2 == 0:
                    r = surfaces.http.post("/api/mutate/undo", json={"if_mutation_id": tip})
                    body = r.json()
                    body["_status"] = r.status_code
                    return body
                return surfaces.mcp[i // 2].call("undo_last_mutation", {"if_mutation_id": tip})

            results = barrier_run(racers, attempt)
            wins = _wins(results)
            assert len(wins) == 1, f"round {rnd}: {len(wins)} undo winners: {results}"
            assert not _non_conflicts(results), f"round {rnd}: {results}"


class TestStormAndPersistence:
    """Verifies REQ-o00062-I+N+Q end-to-end: a randomized cross-surface
    storm never corrupts the graph, and a tip-guarded save persists every
    accepted final write to disk."""

    NODES = ["REQ-p00001", "REQ-p00002", "REQ-p00003", "REQ-o00001", "REQ-d00001"]

    def test_storm_then_quiesce_save_and_disk_integrity(self, surfaces):
        duration = 6.0 * SCALE
        writers = 8
        stop = time.time() + duration
        counters = {"success": 0, "conflict": 0, "other": 0}
        tally_lock = threading.Lock()

        def worker(i: int) -> None:
            rng = random.Random(4000 + i)
            while time.time() < stop:
                node_id = rng.choice(self.NODES)
                ver = surfaces.version(node_id)
                if rng.random() < 0.15:
                    ver = "stale-" + hex(rng.getrandbits(32))[2:]
                title = f"storm-{i}-{rng.randrange(10**6)}"
                if i % 2 == 0:
                    res = surfaces.title_http(node_id, title, ver)
                else:
                    res = surfaces.mcp[i // 2].call(
                        "mutate_update_title",
                        {"node_id": node_id, "new_title": title, "if_version": ver},
                    )
                with tally_lock:
                    if res.get("success"):
                        counters["success"] += 1
                    elif res.get("code") == "version_conflict":
                        counters["conflict"] += 1
                    else:
                        counters["other"] += 1

        with ThreadPoolExecutor(max_workers=writers) as ex:
            list(ex.map(worker, range(writers)))

        assert counters["other"] == 0, f"malformed responses during storm: {counters}"
        assert counters["success"] > 0, f"storm landed nothing: {counters}"

        # Quiesce: one guarded final write per node must succeed in <=5 tries
        # (bounded interference from nothing — the storm is over).
        finals: dict[str, str] = {}
        for node_id in self.NODES:
            for _ in range(5):
                res = surfaces.title_http(node_id, f"final-{node_id}", surfaces.version(node_id))
                if res.get("success"):
                    finals[node_id] = f"final-{node_id}"
                    break
            assert node_id in finals, f"{node_id}: fresh-token write kept failing"

        # Tip-guarded save persists every accepted write (REQ-o00062-N).
        tip = surfaces.current_tip()
        res = surfaces.mcp[0].call("save_mutations", {"if_tip_mutation_id": tip})
        assert res.get("success"), f"quiesced save must succeed: {res}"

        spec_dir = surfaces.root / "spec"
        spec_text = "\n".join(p.read_text(encoding="utf-8") for p in spec_dir.rglob("*.md"))
        for node_id, title in finals.items():
            assert title in spec_text, (
                f"{node_id}: accepted final write {title!r} missing from disk — "
                "lost update across save"
            )

        # The saved estate must still be internally consistent.
        chk = subprocess.run(
            [sys.executable, "-m", "elspais", "checks", "--lenient"],
            cwd=surfaces.root,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert chk.returncode == 0, (
            f"post-storm saved state fails checks:\n{chk.stdout[-1500:]}\n{chk.stderr[-500:]}"
        )

        # Both surfaces agree on the committed state afterwards (REQ-o00062-Q).
        for node_id, title in finals.items():
            assert surfaces.node(node_id)["title"] == title
            via_mcp = surfaces.mcp[0].call("get_requirement", {"req_id": node_id})
            assert via_mcp.get("title") == title, (
                f"{node_id}: surfaces disagree after save "
                f"(HTTP={title!r}, MCP={via_mcp.get('title')!r})"
            )
