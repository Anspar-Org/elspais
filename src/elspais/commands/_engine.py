# Implements: REQ-d00010
"""Unified engine for CLI commands that need a graph.

Encapsulates the daemon-vs-local decision tree:
  1. skip_daemon? --> local
  2. viewer running? --> HTTP call
  3. daemon running + version ok? --> HTTP call
  4. cli_ttl != 0? --> auto-start daemon, poll for readiness, HTTP call
  5. fallback --> build graph locally, call compute_fn

Both daemon and local paths return the same dict shape.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from elspais.graph.federated import FederatedGraph

# Lazy-cached local graph for the lifetime of the process.
_local_graph: FederatedGraph | None = None
_local_config: dict[str, Any] | None = None


def call(
    endpoint: str,
    params: dict[str, str],
    compute_fn: Callable[[Any, dict[str, Any], dict[str, str]], dict],
    skip_daemon: bool = False,
) -> dict:
    """Run a command via daemon or locally, returning the same dict shape.

    Args:
        endpoint: REST path (e.g., "/api/run/checks").
        params: Query parameters as string dict.
        compute_fn: Function(graph, config, params) -> dict for local path.
        skip_daemon: If True, skip daemon entirely (e.g., custom spec_dir).

    Returns:
        Result dict from daemon HTTP response or local compute_fn.
    """
    if not skip_daemon:
        result = _try_daemon(endpoint, params)
        if result is not None:
            return result

    # Local fallback: build graph (cached) and compute
    graph, config = _ensure_local_graph()
    return compute_fn(graph, config, params)


def _try_daemon(
    endpoint: str,
    params: dict[str, str],
) -> dict | None:
    """Try daemon/viewer, auto-starting if allowed. Returns dict or None."""
    from elspais.commands._daemon_client import _get_daemon_port, _try_port

    _VIEWER_PORT = 5001

    # 1. Try viewer
    result = _try_port(_VIEWER_PORT, endpoint, params, "GET")
    if result is not None:
        return result

    # 2. Try existing daemon
    daemon_port = _get_daemon_port()
    if daemon_port and daemon_port != _VIEWER_PORT:
        result = _try_port(daemon_port, endpoint, params, "GET")
        if result is not None:
            return result

    # 3. Auto-start daemon if allowed
    try:
        from elspais.config import find_git_root
        from elspais.mcp.daemon import ensure_daemon

        repo_root = find_git_root()
        if repo_root is None:
            return None

        port = ensure_daemon(repo_root)
        return _try_port(port, endpoint, params, "GET")
    except Exception:
        return None


def get_graph() -> Any:
    """Return the cached local graph, building it if necessary."""
    graph, _ = _ensure_local_graph()
    return graph


def _ensure_local_graph() -> tuple[Any, dict[str, Any]]:
    """Build or return the cached local graph and config."""
    global _local_graph, _local_config
    if _local_graph is not None and _local_config is not None:
        return _local_graph, _local_config

    from elspais.config import get_config
    from elspais.graph.factory import build_graph

    config = get_config()
    graph = build_graph(config=config)
    _local_graph = graph
    _local_config = config
    return graph, config
