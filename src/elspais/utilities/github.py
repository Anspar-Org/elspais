"""Opening a pull request on GitHub for a branch the remote already has.

The call is made against GitHub's REST API with the standard library, so
the tool gains no dependency for a single request. The opener is injectable
because the only interesting behaviour — an existing pull request answering
a repeat request, a refusal naming what is missing — has to be exercised
without a network.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

API_ROOT = "https://api.github.com"

#: Seconds to wait on the API before giving up.
REQUEST_TIMEOUT = 20

Opener = Callable[[urllib.request.Request, float], Any]

_HTTPS_REMOTE = re.compile(
    r"^https?://(?:[^@/]+@)?github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$"
)
_SSH_REMOTE = re.compile(
    r"^(?:ssh://)?git@github\.com[:/](?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$"
)


# Implements: REQ-d00297-C
def parse_owner_repo(remote_url: str) -> tuple[str, str] | None:
    """The ``(owner, repo)`` a GitHub remote URL names, or None.

    None means the remote is not GitHub's, which the caller reports rather
    than guessing an API to talk to.
    """
    url = (remote_url or "").strip()
    for pattern in (_HTTPS_REMOTE, _SSH_REMOTE):
        match = pattern.match(url)
        if match:
            return match.group("owner"), match.group("repo")
    return None


def _default_opener(request: urllib.request.Request, timeout: float) -> Any:
    return urllib.request.urlopen(request, timeout=timeout)  # noqa: S310


def _api_request(
    method: str,
    path: str,
    token: str,
    payload: dict[str, Any] | None = None,
) -> urllib.request.Request:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(f"{API_ROOT}{path}", data=data, method=method)
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("X-GitHub-Api-Version", "2022-11-28")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    return request


# Implements: REQ-d00297-E
def find_open_pull_request(
    owner: str,
    repo: str,
    head_branch: str,
    token: str,
    opener: Opener | None = None,
) -> dict[str, Any] | None:
    """The open pull request already proposing ``head_branch``, or None.

    A branch name may carry characters a query string reads as structure, so
    the filter is escaped: an unescaped one would drop the filter and let an
    unrelated pull request answer for this branch.
    """
    send = opener or _default_opener
    query = urllib.parse.urlencode({"head": f"{owner}:{head_branch}", "state": "open"})
    path = f"/repos/{owner}/{repo}/pulls?{query}"
    try:
        response = send(_api_request("GET", path, token), REQUEST_TIMEOUT)
    except urllib.error.HTTPError:
        return None
    body = json.loads(response.read().decode("utf-8"))
    if isinstance(body, list) and body:
        return body[0]
    return None


# Implements: REQ-d00297-A, REQ-d00297-E
def open_pull_request(
    owner: str,
    repo: str,
    head_branch: str,
    base_branch: str,
    title: str,
    body: str,
    token: str,
    opener: Opener | None = None,
) -> dict[str, Any]:
    """Open a pull request, or report the one that already proposes this work.

    Returns ``{"success": True, "url": ..., "number": ..., "existing": bool}``
    or ``{"success": False, "error": ...}``.
    """
    send = opener or _default_opener
    payload = {"title": title, "body": body, "head": head_branch, "base": base_branch}
    try:
        response = send(
            _api_request("POST", f"/repos/{owner}/{repo}/pulls", token, payload),
            REQUEST_TIMEOUT,
        )
    except urllib.error.HTTPError as exc:
        detail = _error_detail(exc)
        if exc.code == 422:
            existing = find_open_pull_request(owner, repo, head_branch, token, opener=send)
            if existing:
                return {
                    "success": True,
                    "url": existing.get("html_url", ""),
                    "number": existing.get("number"),
                    "existing": True,
                }
        return {"success": False, "error": detail}
    except urllib.error.URLError as exc:
        return {"success": False, "error": f"Could not reach GitHub: {exc.reason}"}

    created = json.loads(response.read().decode("utf-8"))
    return {
        "success": True,
        "url": created.get("html_url", ""),
        "number": created.get("number"),
        "existing": False,
    }


def _error_detail(exc: urllib.error.HTTPError) -> str:
    """What GitHub said went wrong, falling back to the status line."""
    try:
        body = json.loads(exc.read().decode("utf-8"))
    except Exception:
        return f"GitHub returned {exc.code}"
    message = body.get("message") if isinstance(body, dict) else None
    errors = body.get("errors") if isinstance(body, dict) else None
    if errors:
        parts = [e.get("message", "") for e in errors if isinstance(e, dict)]
        joined = "; ".join(p for p in parts if p)
        if joined:
            return f"{message}: {joined}" if message else joined
    return message or f"GitHub returned {exc.code}"
