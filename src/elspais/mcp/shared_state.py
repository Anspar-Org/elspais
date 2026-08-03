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

import threading
import time
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
