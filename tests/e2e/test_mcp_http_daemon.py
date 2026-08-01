# Validates: REQ-o00062-Q
"""E2E: the daemon's MCP-over-HTTP surface and the viewer share one graph.

Validates REQ-o00062-Q: when the daemon serves HTTP, its MCP interface
accepts sessions at the documented endpoint (``/mcp``) and operates on the
same in-memory graph as the review server's HTTP interface, so agent and
human writers are guarded against each other rather than only against
writers on their own transport.

The daemon is spawned the real way -- ``elspais mcp serve --transport
streamable-http --port 0`` as a subprocess against a tmp copy of the
hht-like fixture (never the checked-in fixture directory in place). MCP
sessions use the real client from the installed ``mcp`` package.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from .conftest import load_fixture

pytestmark = [pytest.mark.e2e]

# The daemon builds the whole graph before serving; ~10s is normal.
STARTUP_BUDGET_SECONDS = 30.0
SCENARIO_BUDGET_SECONDS = 60.0


# ---------------------------------------------------------------------------
# Daemon fixture
# ---------------------------------------------------------------------------


def _log_tail(log_path: Path, lines: int = 30) -> str:
    try:
        return "\n".join(log_path.read_text().splitlines()[-lines:])
    except OSError:
        return "<no daemon log>"


def _await_daemon_port(daemon_json: Path, proc: subprocess.Popen, log_path: Path) -> int:
    """Poll daemon.json for the bound port (written by run_server)."""
    deadline = time.monotonic() + STARTUP_BUDGET_SECONDS
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            pytest.fail(
                f"daemon exited during startup (rc={proc.returncode}):\n{_log_tail(log_path)}"
            )
        if daemon_json.is_file():
            try:
                info = json.loads(daemon_json.read_text())
            except (json.JSONDecodeError, OSError):
                info = {}
            port = info.get("port")
            if isinstance(port, int):
                return port
        time.sleep(0.2)
    pytest.fail(f"daemon.json never appeared within budget:\n{_log_tail(log_path)}")


def _await_viewer_ready(port: int, proc: subprocess.Popen, log_path: Path) -> None:
    """Poll the viewer surface until /api/dirty answers 200."""
    deadline = time.monotonic() + STARTUP_BUDGET_SECONDS
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            pytest.fail(
                f"daemon exited before becoming ready (rc={proc.returncode}):\n"
                f"{_log_tail(log_path)}"
            )
        try:
            _http_get_json(f"http://127.0.0.1:{port}/api/dirty")
            return
        except (urllib.error.URLError, OSError, ValueError) as exc:
            last_error = exc
            time.sleep(0.2)
    pytest.fail(
        f"viewer /api/dirty never answered 200 within budget (last error: {last_error}):\n"
        f"{_log_tail(log_path)}"
    )


@pytest.fixture(scope="module")
def daemon(tmp_path_factory):
    """Spawn the real streamable-http daemon on a tmp hht-like project."""
    pytest.importorskip("mcp")
    root = tmp_path_factory.mktemp("mcp_http_daemon")
    load_fixture("hht-like", root)

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
        "10",
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
        yield root, port, log_path
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


# ---------------------------------------------------------------------------
# HTTP helpers (viewer surface)
# ---------------------------------------------------------------------------


def _http_get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.loads(resp.read().decode())


def _http_post_json(url: str, payload: dict) -> tuple[int, dict]:
    """POST JSON; return (status_code, body) even for HTTP error statuses."""
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())


# ---------------------------------------------------------------------------
# MCP helpers (agent surface, real mcp client over streamable-http)
# ---------------------------------------------------------------------------


def _mcp_url(port: int) -> str:
    """The DOCUMENTED endpoint: /mcp on the daemon's port, not /mcp/mcp."""
    return f"http://127.0.0.1:{port}/mcp"


def _run(coro):
    """Run an async MCP scenario in a sync test with an overall deadline."""
    return asyncio.run(asyncio.wait_for(coro, SCENARIO_BUDGET_SECONDS))


def _tool_payload(result) -> dict:
    """Parse the JSON dict a tool returned from its text content blocks."""
    texts = [c.text for c in result.content if getattr(c, "type", "") == "text"]
    assert texts, f"tool result carried no text content: {result!r}"
    return json.loads("".join(texts))


def _assert_readiness(port: int) -> None:
    """Prove the daemon's viewer surface is up before attempting MCP.

    A failure past this point is the MCP layer, not fixture setup.
    """
    dirty = _http_get_json(f"http://127.0.0.1:{port}/api/dirty")
    assert "mutation_count" in dirty, f"/api/dirty missing mutation_count: {dirty}"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_REQ_o00062_Q_initialize_succeeds_at_documented_endpoint(daemon):
    """Validates REQ-o00062-Q: MCP sessions are accepted at the documented /mcp.

    The daemon must answer streamable-http MCP at ``/mcp`` on its single
    port -- not buried at ``/mcp/mcp`` by a stacked internal path, and not
    rejected because the session manager's lifespan never started.
    """
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    _root, port, _log = daemon
    _assert_readiness(port)

    async def scenario() -> list[str]:
        async with streamablehttp_client(_mcp_url(port)) as (read, write, _get_sid):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                return [tool.name for tool in tools.tools]

    tool_names = _run(scenario())
    mutate_tools = [name for name in tool_names if name.startswith("mutate_")]
    assert "mutate_update_title" in tool_names, f"mutate_update_title missing: {tool_names}"
    assert mutate_tools, f"no mutate_* tools listed: {tool_names}"


def test_REQ_o00062_Q_http_mcp_and_viewer_share_one_graph(daemon):
    """Validates REQ-o00062-Q: MCP-over-HTTP mutates the viewer's own graph.

    A mutation performed over the MCP HTTP session must be visible on the
    viewer surface without any refresh (/api/dirty counts it), and the
    viewer must reject a write carrying the stale pre-mutation token with
    the shared 409 version_conflict shape -- cross-surface guarding.
    """
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    _root, port, _log = daemon
    _assert_readiness(port)
    req_id = "REQ-p00001"

    async def scenario() -> tuple[str, str]:
        async with streamablehttp_client(_mcp_url(port)) as (read, write, _get_sid):
            async with ClientSession(read, write) as session:
                await session.initialize()
                req = _tool_payload(await session.call_tool("get_requirement", {"req_id": req_id}))
                assert req.get("version"), f"get_requirement returned no version: {req}"
                stale = req["version"]
                result = _tool_payload(
                    await session.call_tool(
                        "mutate_update_title",
                        {
                            "node_id": req_id,
                            "new_title": "User Authentication (renamed over MCP HTTP)",
                            "if_version": stale,
                        },
                    )
                )
                assert result.get("success"), f"MCP mutation failed: {result}"
                assert result.get("version"), f"mutation reported no resulting version: {result}"
                return stale, result["version"]

    stale_version, new_version = _run(scenario())
    assert new_version != stale_version

    # Same in-memory graph: the viewer sees the pending mutation immediately.
    dirty = _http_get_json(f"http://127.0.0.1:{port}/api/dirty")
    assert dirty["mutation_count"] >= 1, f"viewer saw no pending mutations: {dirty}"
    assert dirty["tip"], f"viewer reported no mutation-log tip: {dirty}"

    # Cross-surface guard: the stale pre-mutation token must be refused.
    status, body = _http_post_json(
        f"http://127.0.0.1:{port}/api/mutate/title",
        {
            "node_id": req_id,
            "new_title": "Viewer write with stale token",
            "if_version": stale_version,
        },
    )
    assert status == 409, f"expected 409 for stale viewer write, got {status}: {body}"
    assert body.get("code") == "version_conflict", f"unexpected rejection shape: {body}"
    assert body.get("current_version") == new_version, (
        f"viewer's current_version should be the MCP mutation's resulting "
        f"version {new_version}: {body}"
    )


def test_REQ_o00062_Q_two_http_sessions_conflict_detected(daemon):
    """Validates REQ-o00062-Q: two MCP HTTP clients are guarded against each other.

    Both sessions read the same node; the first writes; the second's write
    with its now-stale token is rejected as version_conflict carrying the
    first writer's resulting version, and a retry with it succeeds.
    """
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    _root, port, _log = daemon
    _assert_readiness(port)
    req_id = "REQ-p00002"
    url = _mcp_url(port)

    async def scenario() -> None:
        async with streamablehttp_client(url) as (read_a, write_a, _sid_a):
            async with ClientSession(read_a, write_a) as alpha:
                await alpha.initialize()
                async with streamablehttp_client(url) as (read_b, write_b, _sid_b):
                    async with ClientSession(read_b, write_b) as beta:
                        await beta.initialize()

                        seen_alpha = _tool_payload(
                            await alpha.call_tool("get_requirement", {"req_id": req_id})
                        )
                        seen_beta = _tool_payload(
                            await beta.call_tool("get_requirement", {"req_id": req_id})
                        )
                        assert seen_alpha.get("version") == seen_beta.get("version")

                        won = _tool_payload(
                            await alpha.call_tool(
                                "mutate_update_title",
                                {
                                    "node_id": req_id,
                                    "new_title": "Data Privacy (first writer wins)",
                                    "if_version": seen_alpha["version"],
                                },
                            )
                        )
                        assert won.get("success"), f"first writer failed: {won}"

                        lost = _tool_payload(
                            await beta.call_tool(
                                "mutate_update_title",
                                {
                                    "node_id": req_id,
                                    "new_title": "Data Privacy (second writer, stale)",
                                    "if_version": seen_beta["version"],
                                },
                            )
                        )
                        assert (
                            lost.get("code") == "version_conflict"
                        ), f"stale second write not rejected as version_conflict: {lost}"
                        assert lost.get("current_version") == won.get("version"), (
                            f"rejection must carry the first writer's resulting version "
                            f"{won.get('version')}: {lost}"
                        )

                        retried = _tool_payload(
                            await beta.call_tool(
                                "mutate_update_title",
                                {
                                    "node_id": req_id,
                                    "new_title": "Data Privacy (second writer, reconciled)",
                                    "if_version": lost["current_version"],
                                },
                            )
                        )
                        assert retried.get("success"), f"reconciled retry failed: {retried}"

    _run(scenario())
