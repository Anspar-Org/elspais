# Implements: REQ-d00010
"""HTTP plumbing for talking to a running viewer or daemon.

Decision logic (when to use daemon vs local) lives in ``_engine.py``.
This module only provides low-level HTTP helpers.
"""
from __future__ import annotations

import json
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

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
