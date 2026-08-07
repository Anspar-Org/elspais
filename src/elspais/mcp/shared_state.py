"""elspais.mcp.shared_state - single source of truth for the live graph.

The unified daemon serves two mutation surfaces over one graph: the MCP
tools (sync functions FastMCP runs on worker threads) and the viewer's
HTTP routes (async handlers on the event loop). Both must always
dereference the same graph, including across rebuilds — two references
kept "in sync" is how accepted writes get silently dropped (CUR-1829
stress finding: one save_mutations split the surfaces and a guarded,
accepted HTTP write never reached disk).

SharedServerState is that single point of dereference. It is a dict
(the MCP tools' historical ``_state`` shape: "graph", "config",
"working_dir") so every existing ``_state["graph"]`` read and write is
already a read/write of the shared cell. AppState exposes ``.graph`` /
``.config`` as properties over the same object.

``write_lock`` serializes every mutation critical section
(guard + mutate + log append) and every rebuild-and-swap, across both
surfaces. It is a ``threading.RLock`` — an asyncio lock cannot exclude
the MCP worker threads. Mutations are short synchronous CPU work, so
async handlers may hold it briefly without starving the event loop.
"""

from __future__ import annotations

import sys
import threading
import time
from collections.abc import Callable
from typing import Any


class SharedServerState(dict):
    """Dict-shaped holder for graph/config plus the write lock.

    There is exactly one of these per server process; MCP tool closures
    and AppState both hold a reference to the same instance, so a swap
    (``state["graph"] = new_graph``) is visible to every surface at once
    with nothing to propagate.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.write_lock = threading.RLock()
        # Every rebuild-and-swap stamps this, on either surface. The viewer's
        # staleness check reads it, so a holder that never carried one would
        # report every spec file as changed.
        self.setdefault("build_time", time.time())
        # Callbacks run inside rebuild_shared_graph()'s critical section, after
        # the new config and graph are published. This is how change-detection
        # state that lives outside the holder is brought forward by a rebuild
        # reached through any surface: AppState registers its mtime
        # re-snapshot here rather than each reload path remembering to call it
        # (REQ-p00004-O). A stdio MCP server registers nothing and keeps none.
        self.post_rebuild_hooks: list[Callable[[], None]] = []


# Implements: REQ-p00004-J, REQ-p00004-O, REQ-p00015-F, REQ-d00205-B
def rebuild_shared_graph(state: SharedServerState, full: bool = False) -> dict[str, Any]:
    """Rebuild the live graph from disk and publish it. The only rebuild path.

    Every surface that reloads the graph reaches this function: the viewer's
    automatic freshness check, its ``/api/reload`` and ``/api/revert`` routes,
    the MCP ``refresh_graph`` tool, and the MCP tools that rebuild after
    writing spec files. A rebuild is not just a graph swap — it must also
    re-read configuration from disk (REQ-p00004-J) and leave the tool's
    change-detection state agreeing with what it just loaded (REQ-p00004-O).
    Those two steps are exactly what nine hand-rolled copies of this logic
    kept forgetting, which is why there is now one copy.

    Publication order inside the lock is config, then graph, then
    ``build_time``, then the post-rebuild hooks — hooks read config through
    the holder, so they must see the new one.

    Nothing is published unless the new graph exists. A configuration that
    cannot be parsed is reported as a failure with the previously served
    graph left in place: replacing a working graph with an empty one because
    a config file was mistyped would be a silent, destructive substitution
    (REQ-p00015-F).

    Args:
        state: The process-wide holder. ``working_dir`` names the repo root.
        full: Accepted for caller compatibility; no cache is retained between
            builds, so a full rebuild is what every call already performs.

    Returns:
        ``{"success", "message", "node_count", "config"}``. ``config`` is the
        rebuilt federation's root repo config, already published into the
        holder (REQ-d00205-B); callers need not sync it themselves.
    """
    from elspais.config import get_config
    from elspais.graph.factory import build_graph

    working_dir = state["working_dir"]

    try:
        new_config = get_config(start_path=working_dir, quiet=True)
        new_graph = build_graph(config=new_config, repo_root=working_dir)
    except Exception as exc:
        message = str(exc)
        if ".elspais.toml" in message:
            # Config parse error — a descriptive report, not a stack trace,
            # and the previous graph stays live.
            return {
                "success": False,
                "message": f"CONFIG ERROR: {message}",
                "node_count": 0,
                "config": None,
            }
        raise

    if hasattr(new_graph, "load_comments"):
        new_graph.load_comments()

    # REQ-d00205-B: the published config is the rebuilt federation's root repo
    # config, which is the one every global operation reads.
    root_config = None
    iter_repos = getattr(new_graph, "iter_repos", None)
    if iter_repos is not None:
        for entry in iter_repos():
            if entry.config is not None:
                root_config = entry.config
                break

    with state.write_lock:
        state["config"] = root_config if root_config is not None else new_config
        state["graph"] = new_graph
        state["build_time"] = time.time()
        for hook in state.post_rebuild_hooks:
            hook()

    # Configuration was re-read from disk — bring the running daemon's
    # recorded config fingerprint forward too, so a CLI staleness check does
    # not restart a server that is already current (REQ-p00004-O).
    try:
        from elspais.mcp.daemon import refresh_daemon_config_hash

        refresh_daemon_config_hash(working_dir)
    except Exception as exc:
        # Tolerated failure (visible, not swallowed): a fingerprint that
        # stays behind costs at most one needless daemon restart.
        print(
            f"warning: could not refresh daemon config hash: {exc}",
            file=sys.stderr,
        )

    return {
        "success": True,
        "message": "Graph refreshed successfully",
        "node_count": new_graph.node_count(),
        "config": root_config,
    }
