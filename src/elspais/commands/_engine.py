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
    request: Any,
    compute_fn: Callable[[Any, dict[str, Any], Any], dict],
    skip_daemon: bool = False,
    config_path: str | None = None,
) -> dict:
    """Run an operation via daemon or locally, returning the same dict shape.

    Injects ``graph_source`` metadata into the result dict for traceability.

    The request is the operation's input on both paths. Only the daemon path
    serializes it, and it does so here -- a caller that had to produce query
    parameters itself would be a caller deciding how its own inputs travel.

    Args:
        endpoint: REST path (e.g., "/api/run/checks").
        request: The operation's input -- a frozen request object carrying
            final values (a resolved scope, a resolved selection, and so on).
            Its ``to_params()`` is what travels to a daemon; ``compute_fn`` is
            called with the request object itself on the local path, so a
            command's ``compute_*`` receives the same shape whether it was
            served or computed here.
        compute_fn: Function(graph, config, request) -> dict for local path.
        skip_daemon: If True, skip daemon entirely (e.g., custom spec_dir).
        config_path: Explicit config file path (local fallback only).

    Returns:
        Result dict from daemon HTTP response or local compute_fn,
        always including a ``graph_source`` key.
    """
    if not skip_daemon:
        daemon_result = _try_daemon(endpoint, request.to_params())
        if daemon_result is not None:
            result, source = daemon_result
            if isinstance(result, dict):
                result["graph_source"] = source
            return result

    # Local fallback: build graph (cached) and compute
    graph, config = _ensure_local_graph(config_path=config_path)
    result = compute_fn(graph, config, request)
    result["graph_source"] = {"type": "local"}
    return result


def _build_daemon_source(info: dict) -> dict[str, Any]:
    """Build graph_source dict from the record of the server that answered."""
    source: dict[str, Any] = {
        "port": info["port"],
        "type": info.get("type", "daemon"),
        "started_at": info.get("started_at", ""),
    }
    if info.get("base_path"):
        source["base_path"] = info["base_path"]
    return source


# Implements: REQ-o00075-B, REQ-o00076-E
def _try_daemon(
    endpoint: str,
    params: dict[str, str],
) -> tuple[dict, dict[str, Any]] | None:
    """Try to serve a request via a running server (viewer or daemon).

    Routing is entirely through daemon.json — no hardcoded ports.
    Both the viewer and headless daemon write daemon.json on startup.

    Returns (result_dict, source_info) or None.
    """
    from elspais.commands._daemon_client import _get_daemon_record, _try_server
    from elspais.config import find_git_root

    repo_root = find_git_root()
    if repo_root is None:
        return None

    # 1. Try existing server (viewer or daemon — both use daemon.json)
    record = _get_daemon_record()
    if record:
        # A server that has committed to stopping still answers and still
        # refuses everything, so it is replaced rather than reused — and
        # only once it has actually gone, since a second process for one
        # working tree would split the graph. A daemon that will not go
        # leaves this command to build its own graph.
        from elspais.mcp.daemon import (
            daemon_is_stopping,
            get_daemon_info,
            replace_stopping_daemon,
        )

        outgoing = get_daemon_info(repo_root)
        if daemon_is_stopping(outgoing):
            if not replace_stopping_daemon(repo_root, outgoing):
                return None
            record = None

    if record:
        # Implements: REQ-p00004-J, REQ-p00015-G, REQ-o00076-I, REQ-o00076-J
        # What differs, and whether a difference may be acted on, are both
        # asked through the one authority in mcp/daemon.py, which
        # ensure_daemon asks too. Two callers deciding this separately
        # would hand a client a different daemon depending on which of
        # them reached it first.
        from elspais.mcp.daemon import (
            daemon_has_unsaved_work,
            ensure_client_registered,
            get_daemon_info,
            notify_serving_difference,
            serving_difference,
        )

        info = get_daemon_info(repo_root)
        # Implements: REQ-o00074-E
        # This is the path a session that never starts a daemon takes on
        # every command, so it is where such a session has to announce
        # itself; otherwise the daemon watches only whoever started it.
        ensure_client_registered(repo_root, info)
        difference = serving_difference(info, repo_root)

        if difference:
            if info is not None and daemon_has_unsaved_work(info):
                # Restarting would force an unasked save of somebody's
                # in-progress session, and lose it outright if that save
                # failed. Answers from an older program are recoverable;
                # that work is not.
                notify_serving_difference(difference, "is holding unsaved changes")
            else:
                from elspais.mcp.daemon import stop_daemon

                stop_daemon(repo_root)
                record = None

        if record:
            result = _try_server(record, endpoint, params, "GET")
            if result is not None:
                source = _build_daemon_source(record)
                if difference.version:
                    from elspais import __version__

                    source["version_mismatch"] = {
                        "daemon": difference.version,
                        "cli": __version__,
                    }
                if difference.executable:
                    source["executable_mismatch"] = True
                if difference.config:
                    source["config_stale"] = True
                return result, source

    # 2. Auto-start daemon if allowed
    try:
        from elspais.mcp.daemon import ensure_daemon

        ensure_daemon(repo_root)
        # The record, not the port ensure_daemon returns: the record is
        # what says where the server answers.
        record = _get_daemon_record()
        if record is None:
            return None
        result = _try_server(record, endpoint, params, "GET")
        if result is not None:
            source = _build_daemon_source(record)
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
