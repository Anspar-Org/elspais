# Implements: REQ-d00010
"""Shared application state with auto-refresh.

Holds the in-memory FederatedGraph, config, and file mtime snapshot.
Detects spec file changes and rebuilds automatically.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any


class AppState:
    """Mutable application state shared by REST routes and MCP tools."""

    def __init__(
        self,
        graph: Any,
        repo_root: Path,
        config: dict[str, Any],
        canonical_root: Path | None = None,
        allowed_roots: list[Path] | None = None,
    ) -> None:
        self.graph = graph
        self.repo_root = repo_root
        self.config = config
        self.canonical_root = canonical_root or repo_root
        self.allowed_roots = allowed_roots or [repo_root]
        self.build_time = time.time()
        self._mtimes: dict[str, float] = {}
        self._mcp_state: dict[str, Any] | None = None  # set by link_mcp_state
        self._last_stale_check = 0.0
        self.snapshot_mtimes()

    @classmethod
    def from_config(
        cls,
        repo_root: Path,
        config: dict[str, Any] | None = None,
        canonical_root: Path | None = None,
    ) -> AppState:
        """Build graph from config and create state."""
        from elspais.config import get_config
        from elspais.graph.factory import build_graph

        if config is None:
            config = get_config(start_path=repo_root, quiet=True)
        graph = build_graph(config=config, repo_root=repo_root, canonical_root=canonical_root)
        return cls(
            graph=graph,
            repo_root=repo_root,
            config=config,
            canonical_root=canonical_root,
        )

    def snapshot_mtimes(self) -> None:
        """Record current mtimes of all scanned spec/code/test files."""
        self._mtimes = {}
        scan_dirs = self._get_scan_dirs()
        for d in scan_dirs:
            if not d.is_dir():
                continue
            for f in d.rglob("*"):
                if f.is_file():
                    try:
                        self._mtimes[str(f)] = f.stat().st_mtime
                    except OSError:
                        pass

    def _get_scan_dirs(self) -> list[Path]:
        """Return directories that contribute to the graph."""
        dirs: list[Path] = []
        spec = self.config.get("scanning", {}).get("spec", {})
        spec_dirs = spec.get("directories", ["spec"])
        for d in spec_dirs:
            dirs.append(self.repo_root / d)

        code = self.config.get("scanning", {}).get("code", {})
        code_dirs = code.get("directories", [])
        for d in code_dirs:
            dirs.append(self.repo_root / d)

        test = self.config.get("scanning", {}).get("test", {})
        test_dirs = test.get("directories", [])
        for d in test_dirs:
            dirs.append(self.repo_root / d)

        return dirs

    def is_stale(self) -> bool:
        """Check if any scanned files changed since last snapshot."""
        for path_str, old_mtime in self._mtimes.items():
            try:
                current = Path(path_str).stat().st_mtime
                if current != old_mtime:
                    return True
            except OSError:
                return True  # file deleted = stale

        # Check for new files
        scan_dirs = self._get_scan_dirs()
        for d in scan_dirs:
            if not d.is_dir():
                continue
            for f in d.rglob("*"):
                if f.is_file() and str(f) not in self._mtimes:
                    return True
        return False

    def ensure_fresh(self) -> bool:
        """Rebuild graph if files changed. Returns True if rebuilt.

        Throttled to at most one mtime check per second.
        """
        now = time.time()
        if now - self._last_stale_check < 1.0:
            return False
        self._last_stale_check = now
        if not self.is_stale():
            return False
        self._rebuild()
        return True

    def _rebuild(self) -> None:
        """Rebuild graph from disk. Propagates to MCP _state if linked."""
        from elspais.config import get_config
        from elspais.graph.factory import build_graph

        self.config = get_config(start_path=self.repo_root, quiet=True)
        self.graph = build_graph(
            config=self.config,
            repo_root=self.repo_root,
            canonical_root=self.canonical_root,
        )
        self.build_time = time.time()
        self.snapshot_mtimes()
        # Propagate to MCP tools' _state dict (shared reference)
        if self._mcp_state is not None:
            self._mcp_state["graph"] = self.graph
            self._mcp_state["config"] = self.config

    def link_mcp_state(self, mcp_state: dict[str, Any]) -> None:
        """Link an MCP _state dict so rebuilds propagate to MCP tools."""
        self._mcp_state = mcp_state
        # Ensure current graph is in sync
        mcp_state["graph"] = self.graph
        mcp_state["config"] = self.config
