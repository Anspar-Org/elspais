"""Simple MCP tool usage statistics.

Tracks per-tool call counts and response sizes (bytes), flushing to
a file every N calls and at process exit.

Configured via the ``stats`` key in ``.elspais.toml`` or the
``ELSPAIS_STATS`` environment variable (env var sets the same key).
"""

from __future__ import annotations

import atexit
import json
import sys
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any

# Flush to disk every N tool calls
_FLUSH_INTERVAL = 10


class ToolStats:
    """Accumulates per-tool call counts and response byte totals."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._started = datetime.now(timezone.utc).isoformat()
        self._tools: dict[str, dict[str, int]] = {}
        self._total_calls = 0
        self._unflushed = 0

        # Load existing stats file so we accumulate across restarts
        if self._path.exists():
            try:
                existing = json.loads(self._path.read_text())
                self._tools = existing.get("tools", {})
                self._total_calls = existing.get("total_calls", 0)
                self._started = existing.get("started", self._started)
            except (json.JSONDecodeError, KeyError):
                pass  # corrupt file — start fresh

        atexit.register(self.flush)

    def record(self, tool_name: str, response_bytes: int) -> None:
        """Record one tool invocation."""
        entry = self._tools.setdefault(tool_name, {"calls": 0, "bytes": 0})
        entry["calls"] += 1
        entry["bytes"] += response_bytes
        self._total_calls += 1
        self._unflushed += 1

        if self._unflushed >= _FLUSH_INTERVAL:
            self.flush()

    def flush(self) -> None:
        """Write current stats to disk."""
        if self._unflushed == 0 and self._path.exists():
            return
        data = {
            "started": self._started,
            "last_flush": datetime.now(timezone.utc).isoformat(),
            "total_calls": self._total_calls,
            "tools": dict(sorted(self._tools.items())),
        }
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(data, indent=2) + "\n")
            self._unflushed = 0
        except OSError as exc:
            print(f"elspais stats: failed to write {self._path}: {exc}", file=sys.stderr)


def instrument(fn: Any, tool_name: str, stats: ToolStats) -> Any:
    """Wrap a tool function to record call stats."""

    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        result = fn(*args, **kwargs)
        try:
            response_bytes = len(json.dumps(result, default=str).encode())
        except (TypeError, ValueError):
            response_bytes = 0
        stats.record(tool_name, response_bytes)
        return result

    return wrapper
