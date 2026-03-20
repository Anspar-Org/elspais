"""Daemon management for persistent MCP server.

Provides lifecycle management (start/stop/ensure) for a background MCP
server process, and lightweight clients for querying a running server
(viewer or MCP daemon) from the CLI.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

_DEFAULT_TTL = 30  # minutes
_VIEWER_PORT = 5001


def get_cli_ttl(repo_root: Path | None = None) -> int:
    """Read cli_ttl from .elspais.toml config.

    Returns:
        >0: auto-start daemon with this TTL in minutes
         0: never auto-launch daemon (manual only)
        <0: auto-start daemon that never times out
    Default: 30 (minutes).
    """
    if repo_root is None:
        return _DEFAULT_TTL
    try:
        from elspais.config import get_config

        config = get_config(start_path=repo_root, quiet=True)
        return int(config.get("cli_ttl", _DEFAULT_TTL))
    except Exception:
        return _DEFAULT_TTL


# ── Viewer detection (fast path) ─────────────────────────────────────────


def search_via_viewer(
    query: str,
    field: str = "all",
    regex: bool = False,
    limit: int = 50,
    port: int = _VIEWER_PORT,
) -> list[dict] | None:
    """Query a running viewer server's /api/search endpoint.

    Returns results list, or None if the viewer is not running.
    """
    from urllib.parse import quote_plus

    url = (
        f"http://127.0.0.1:{port}/api/search"
        f"?q={quote_plus(query)}&field={field}"
        f"&regex={'true' if regex else 'false'}&limit={limit}"
    )
    try:
        with urlopen(url, timeout=3) as resp:
            return json.loads(resp.read())
    except (URLError, OSError, json.JSONDecodeError, ValueError):
        return None


# ── Daemon lifecycle ─────────────────────────────────────────────────────


def _daemon_dir(repo_root: Path) -> Path:
    return repo_root / ".elspais"


def _daemon_json_path(repo_root: Path) -> Path:
    return _daemon_dir(repo_root) / "daemon.json"


def get_daemon_info(repo_root: Path) -> dict | None:
    """Read daemon.json and verify the process is alive.

    Returns dict with pid/port/repo_root/started_at, or None if
    the daemon is not running or the state file is stale.
    """
    path = _daemon_json_path(repo_root)
    if not path.exists():
        return None
    try:
        info = json.loads(path.read_text())
        pid = info["pid"]
        os.kill(pid, 0)  # check alive
        return info
    except (json.JSONDecodeError, KeyError, OSError):
        path.unlink(missing_ok=True)
        return None


def start_daemon(repo_root: Path, ttl_minutes: int = _DEFAULT_TTL) -> int:
    """Start a background MCP server and return its port.

    Spawns ``elspais mcp serve --transport streamable-http --port 0
    --ttl <ttl>`` as a detached process.  The server writes daemon.json
    after binding; this function polls for it.

    Args:
        ttl_minutes: >0 = exit after N minutes idle.
                     <0 = run forever (no timeout).
                      0 = should not be called (caller should check).
    """
    daemon_json = _daemon_json_path(repo_root)
    daemon_json.parent.mkdir(parents=True, exist_ok=True)
    daemon_json.unlink(missing_ok=True)

    log_path = _daemon_dir(repo_root) / "daemon.log"

    # Negative TTL → run forever (pass 0 to mcp serve, which means no timeout)
    serve_ttl = max(ttl_minutes, 0)

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
        str(serve_ttl),
    ]

    with open(log_path, "w") as log_file:
        subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=log_file,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            cwd=str(repo_root),
            env={**os.environ, "_ELSPAIS_DAEMON_JSON": str(daemon_json)},
        )

    # Poll for daemon.json (server writes it after binding)
    deadline = time.time() + 15
    while time.time() < deadline:
        info = get_daemon_info(repo_root)
        if info and "port" in info:
            return info["port"]
        time.sleep(0.2)

    raise RuntimeError("Daemon failed to start (timed out waiting for daemon.json)")


def stop_daemon(repo_root: Path) -> bool:
    """Stop a running daemon. Returns True if stopped."""
    info = get_daemon_info(repo_root)
    if info is None:
        return False
    try:
        os.kill(info["pid"], signal.SIGTERM)
    except OSError:
        pass
    _daemon_json_path(repo_root).unlink(missing_ok=True)
    return True


def ensure_daemon(repo_root: Path, ttl_minutes: int | None = None) -> int:
    """Return port of a running daemon, starting one if needed.

    Reads ``cli_ttl`` from config if ttl_minutes is not provided.
    Raises RuntimeError if cli_ttl=0 (daemon disabled) and no daemon running.
    """
    # Always connect to an existing daemon regardless of cli_ttl
    info = get_daemon_info(repo_root)
    if info:
        return info["port"]

    if ttl_minutes is None:
        ttl_minutes = get_cli_ttl(repo_root)

    # cli_ttl=0 means never auto-launch
    if ttl_minutes == 0:
        raise RuntimeError("Daemon auto-launch disabled (cli_ttl=0)")

    return start_daemon(repo_root, ttl_minutes=ttl_minutes)


def search_via_daemon(
    port: int,
    query: str,
    field: str = "all",
    regex: bool = False,
    limit: int = 50,
) -> list[dict] | None:
    """Query daemon via REST /api/search (same endpoint as viewer)."""
    return search_via_viewer(query, field, regex, limit, port=port)
