# Implements: REQ-d00010
"""Unified engine for CLI commands that need a graph.

Encapsulates the daemon-vs-local decision tree:
  1. skip_daemon? --> local
  2. daemon.json exists for this project? --> HTTP call (viewer or daemon)
  3. cli_ttl != 0? --> auto-start daemon, poll for readiness, HTTP call
  4. fallback --> build graph locally, call compute_fn

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
) -> dict:
    """Run a command via daemon or locally, returning the same dict shape.

    Injects ``graph_source`` metadata into the result dict for traceability.

    Args:
        endpoint: REST path (e.g., "/api/run/checks").
        params: Query parameters as string dict.
        compute_fn: Function(graph, config, params) -> dict for local path.
        skip_daemon: If True, skip daemon entirely (e.g., custom spec_dir).
        config_path: Explicit config file path (local fallback only).

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
    graph, config = _ensure_local_graph(config_path=config_path)
    result = compute_fn(graph, config, params)
    result["graph_source"] = {"type": "local"}
    return result


def _build_daemon_source(port: int) -> dict[str, Any]:
    """Build graph_source dict for a server result."""
    source: dict[str, Any] = {"port": port}
    try:
        from elspais.config import find_git_root
        from elspais.mcp.daemon import get_daemon_info

        repo_root = find_git_root()
        if repo_root:
            info = get_daemon_info(repo_root)
            if info:
                source["type"] = info.get("type", "daemon")
                source["started_at"] = info.get("started_at", "")
            else:
                source["type"] = "daemon"
        else:
            source["type"] = "daemon"
    except Exception:
        source["type"] = "daemon"
    return source


def _try_daemon(
    endpoint: str,
    params: dict[str, str],
) -> tuple[dict, dict[str, Any]] | None:
    """Try to serve a request via a running server (viewer or daemon).

    Routing is entirely through daemon.json — no hardcoded ports.
    Both the viewer and headless daemon write daemon.json on startup.

    Returns (result_dict, source_info) or None.
    """
    from elspais.commands._daemon_client import _get_daemon_port, _try_port
    from elspais.config import find_git_root

    repo_root = find_git_root()
    if repo_root is None:
        return None

    # 1. Try existing server (viewer or daemon — both use daemon.json)
    port = _get_daemon_port()
    if port:
        # Version check: warn on stale daemon, skip if safe
        from elspais import __version__
        from elspais.mcp.daemon import get_daemon_info

        info = get_daemon_info(repo_root)
        daemon_version = info.get("version") if info else None
        version_mismatch = bool(daemon_version and daemon_version != __version__)

        if version_mismatch:
            # Check if daemon has unsaved mutations before skipping
            dirty = _try_port(port, "/api/dirty", {}, "GET")
            has_unsaved = dirty is not None and dirty.get("dirty", False)
            if has_unsaved:
                # Use stale daemon — can't restart without losing work
                import sys

                print(
                    f"Warning: daemon version {daemon_version} != CLI {__version__}"
                    " (unsaved changes prevent restart)",
                    file=sys.stderr,
                )
            else:
                # Safe to restart — no unsaved work
                from elspais.mcp.daemon import stop_daemon

                stop_daemon(repo_root)
                port = None

        if port:
            result = _try_port(port, endpoint, params, "GET")
            if result is not None:
                source = _build_daemon_source(port)
                if version_mismatch:
                    source["version_mismatch"] = {
                        "daemon": daemon_version,
                        "cli": __version__,
                    }
                return result, source

    # 2. Auto-start daemon if allowed
    try:
        from elspais.mcp.daemon import ensure_daemon

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
) -> tuple[Any, dict[str, Any]]:
    """Build or return the cached local graph and config."""
    global _local_graph, _local_config
    # Use cache only when no explicit overrides are given
    if _local_graph is not None and _local_config is not None and config_path is None:
        return _local_graph, _local_config

    from elspais.config import get_config
    from elspais.graph.factory import build_graph

    config = get_config(config_path)
    graph = build_graph(config=config)
    _local_graph = graph
    _local_config = config
    return graph, config
