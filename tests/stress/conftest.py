"""Fixtures for the concurrency stress tier (``pytest -m stress``).

Spawns the real streamable-http daemon — both surfaces live, MCP tools on
FastMCP worker threads and viewer HTTP routes on the event loop — against
a tmp copy of the e2e-standard fixture, then lets genuinely concurrent
writers race. Deselected by default (like e2e/browser); CI runs it only
when concurrency-relevant files change.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tests.e2e.conftest import load_fixture

STARTUP_BUDGET_SECONDS = 30.0


def _log_tail(log_path: Path, lines: int = 30) -> str:
    try:
        return "\n".join(log_path.read_text().splitlines()[-lines:])
    except OSError:
        return "<no daemon log>"


def _await_daemon_port(daemon_json: Path, proc: subprocess.Popen, log_path: Path) -> int:
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
    import urllib.error
    import urllib.request

    deadline = time.monotonic() + STARTUP_BUDGET_SECONDS
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            pytest.fail(
                f"daemon exited before becoming ready (rc={proc.returncode}):\n"
                f"{_log_tail(log_path)}"
            )
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/dirty", timeout=2) as resp:
                if resp.status == 200:
                    return
        except (urllib.error.URLError, OSError) as exc:
            last_error = exc
        time.sleep(0.2)
    pytest.fail(
        f"viewer never answered 200 within budget (last error: {last_error}):\n"
        f"{_log_tail(log_path)}"
    )


@pytest.fixture(scope="session")
def stress_daemon(tmp_path_factory):
    """The real daemon on a tmp e2e-standard project; yields (root, port)."""
    pytest.importorskip("mcp")
    pytest.importorskip("httpx")
    root = tmp_path_factory.mktemp("stress_daemon")
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
        yield root, port
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
