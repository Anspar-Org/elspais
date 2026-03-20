"""Shared daemon/viewer client for CLI commands.

Provides try_daemon() which attempts to run a command via a running
server's REST API, falling back to None if unavailable.

Also provides try_daemon_or_start() which auto-starts a daemon if
none is running (respects cli_ttl config: 0 = don't auto-start).
"""

from __future__ import annotations

import json
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

_VIEWER_PORT = 5001


def try_daemon(
    endpoint: str,
    params: dict | None = None,
    method: str = "GET",
) -> dict | list | None:
    """Try to call a REST endpoint on a running viewer or daemon.

    Args:
        endpoint: REST path (e.g., "/api/run/checks")
        params: Query params (GET) or JSON body (POST)
        method: HTTP method

    Returns:
        Parsed JSON response, or None if no server is available.
    """
    # Try viewer first, then daemon
    ports = [_VIEWER_PORT]
    daemon_port = _get_daemon_port()
    if daemon_port and daemon_port != _VIEWER_PORT:
        ports.append(daemon_port)

    for port in ports:
        result = _try_port(port, endpoint, params, method)
        if result is not None:
            return result
    return None


def try_daemon_or_start(
    endpoint: str,
    params: dict | None = None,
    method: str = "GET",
) -> dict | list | None:
    """Like try_daemon(), but auto-starts a daemon if none is running.

    Respects cli_ttl config: 0 = don't auto-start, just try existing servers.
    """
    result = try_daemon(endpoint, params, method)
    if result is not None:
        return result

    # Auto-start daemon
    try:
        from elspais.config import find_git_root
        from elspais.mcp.daemon import ensure_daemon

        repo_root = find_git_root()
        if repo_root is None:
            return None

        port = ensure_daemon(repo_root)
        return _try_port(port, endpoint, params, method)
    except Exception:
        return None


def _get_daemon_port() -> int | None:
    """Get port of a running daemon, if any."""
    try:
        from elspais.config import find_git_root
        from elspais.mcp.daemon import get_daemon_info

        repo_root = find_git_root()
        if repo_root is None:
            return None
        info = get_daemon_info(repo_root)
        return info["port"] if info else None
    except Exception:
        return None


def _try_port(
    port: int,
    endpoint: str,
    params: dict | None,
    method: str,
) -> dict | list | None:
    """Try a single port. Returns parsed JSON or None."""
    try:
        url = f"http://127.0.0.1:{port}{endpoint}"
        if method == "GET" and params:
            url += "?" + urlencode(params)

        if method == "POST":
            data = json.dumps(params or {}).encode()
            req = Request(url, data=data, headers={"Content-Type": "application/json"})
        else:
            req = Request(url)

        with urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except (URLError, OSError, json.JSONDecodeError, ValueError):
        return None
