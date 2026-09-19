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


# Implements: REQ-o00076-C
def _get_daemon_record() -> dict | None:
    """The record of a running server, if any.

    Located from the working tree the command is running in, with
    nothing agreed in advance: no port is configured, passed or
    remembered between commands. The whole record rather than its port,
    because the port alone does not say where the server answers.
    """
    try:
        from elspais.config import find_git_root
        from elspais.mcp.daemon import get_daemon_info

        repo_root = find_git_root()
        if repo_root is None:
            return None
        info = get_daemon_info(repo_root)
        return info if info and "port" in info else None
    except Exception:
        return None


# Implements: REQ-o00076-E
def _try_server(
    info: dict,
    endpoint: str,
    params: dict | None,
    method: str,
) -> dict | list | None:
    """Try the server a record describes. Returns parsed JSON or None."""
    from elspais.mcp.daemon import daemon_url

    try:
        url = daemon_url(info, endpoint)
        if method == "GET" and params:
            url += "?" + urlencode(params)

        if method == "POST":
            data = json.dumps(params or {}).encode()
            req = Request(url, data=data, headers={"Content-Type": "application/json"})
        else:
            req = Request(url)

        # Tell the server to bypass its freshness throttle so the graph
        # reflects any file changes since the last request (e.g., after fix).
        req.add_header("X-Force-Fresh", "1")

        with urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except (URLError, OSError, json.JSONDecodeError, ValueError):
        return None
