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
    config_path: str | None = None,
    canonical_root: str | None = None,
) -> dict:
    """Run a command via daemon or locally, returning the same dict shape.

    Injects ``graph_source`` metadata into the result dict for traceability.

    Args:
        endpoint: REST path (e.g., "/api/run/checks").
        params: Query parameters as string dict.
        compute_fn: Function(graph, config, params) -> dict for local path.
        skip_daemon: If True, skip daemon entirely (e.g., custom spec_dir).
        config_path: Explicit config file path (local fallback only).
        canonical_root: Canonical repo root for worktree support (local only).

    Returns:
        Result dict from daemon HTTP response or local compute_fn,
        always including a ``graph_source`` key.
    """
    if not skip_daemon:
        daemon_result = _try_daemon(endpoint, params)
        if daemon_result is not None:
            result, source = daemon_result
            if isinstance(result, dict):
                result["graph_source"] = source
            return result

    # Local fallback: build graph (cached) and compute
    graph, config = _ensure_local_graph(config_path=config_path, canonical_root=canonical_root)
    result = compute_fn(graph, config, params)
    result["graph_source"] = {"type": "local"}
    return result


def _build_daemon_source(port: int) -> dict[str, Any]:
    """Build graph_source dict for a daemon result."""
    source: dict[str, Any] = {"type": "daemon", "port": port}
    try:
        from elspais.config import find_git_root
        from elspais.mcp.daemon import get_daemon_info

        repo_root = find_git_root()
        if repo_root:
            info = get_daemon_info(repo_root)
            if info:
                source["started_at"] = info.get("started_at", "")
    except Exception:
        pass
    return source


def _try_daemon(
    endpoint: str,
    params: dict[str, str],
) -> tuple[dict, dict[str, Any]] | None:
    """Try daemon/viewer, auto-starting if allowed.

    Returns (result_dict, source_info) or None.
    """
    from elspais.commands._daemon_client import _get_daemon_port, _try_port

    _VIEWER_PORT = 5001

    # 1. Try viewer
    result = _try_port(_VIEWER_PORT, endpoint, params, "GET")
    if result is not None:
        return result, {"type": "viewer", "port": _VIEWER_PORT}

    # 2. Try existing daemon
    daemon_port = _get_daemon_port()
    if daemon_port and daemon_port != _VIEWER_PORT:
        result = _try_port(daemon_port, endpoint, params, "GET")
        if result is not None:
            source = _build_daemon_source(daemon_port)
            return result, source

    # 3. Auto-start daemon if allowed
    try:
        from elspais.config import find_git_root
        from elspais.mcp.daemon import ensure_daemon

        repo_root = find_git_root()
        if repo_root is None:
            return None

        port = ensure_daemon(repo_root)
        result = _try_port(port, endpoint, params, "GET")
        if result is not None:
            source = _build_daemon_source(port)
            return result, source
    except Exception:
        pass

    return None


def get_graph() -> Any:
    """Return the cached local graph, building it if necessary."""
    graph, _ = _ensure_local_graph()
    return graph


def _ensure_local_graph(
    config_path: str | None = None,
    canonical_root: str | None = None,
) -> tuple[Any, dict[str, Any]]:
    """Build or return the cached local graph and config."""
    global _local_graph, _local_config
    # Use cache only when no explicit overrides are given
    if (
        _local_graph is not None
        and _local_config is not None
        and config_path is None
        and canonical_root is None
    ):
        return _local_graph, _local_config

    from pathlib import Path

    from elspais.config import get_config
    from elspais.graph.factory import build_graph

    config = get_config(config_path)
    cr = Path(canonical_root) if canonical_root else None
    graph = build_graph(config=config, canonical_root=cr)
    _local_graph = graph
    _local_config = config
    return graph, config
