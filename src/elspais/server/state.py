# Implements: REQ-d00010
"""Shared application state with auto-refresh.

Holds the in-memory FederatedGraph, config, and file mtime snapshot.
Detects spec file changes and rebuilds automatically.
"""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from elspais.mcp.shared_state import SharedServerState, rebuild_shared_graph

if TYPE_CHECKING:
    from elspais.graph.federated import FederatedGraph


@dataclass
class DetachedState:
    """Tracks rewind state for a single repo."""

    originating_branch: str
    originating_head: str


def _compute_allowed_roots(repo_root: Path, config: dict[str, Any]) -> list[Path]:
    """Derive the list of filesystem roots allowed for file serving.

    Includes the main repo root plus the root of each configured associate repo.
    Associate repo roots are found by walking up from each associate spec directory
    to locate the nearest ``.elspais.toml`` marker.
    """
    repo_resolved = repo_root.resolve()
    allowed: list[Path] = [repo_resolved]
    try:
        from elspais.associates import get_associate_spec_directories

        spec_dirs, _ = get_associate_spec_directories(config, repo_root)
        for spec_dir in spec_dirs:
            candidate = spec_dir.resolve()
            while candidate != candidate.parent:
                if (candidate / ".elspais.toml").exists():
                    if candidate not in allowed:
                        allowed.append(candidate)
                    break
                candidate = candidate.parent
    except Exception:
        pass  # Associates not configured; repo root is the only allowed dir
    return allowed


class AppState:
    """Mutable application state shared by REST routes and MCP tools."""

    def __init__(
        self,
        graph: FederatedGraph,
        repo_root: Path,
        config: dict[str, Any],
        allowed_roots: list[Path] | None = None,
    ) -> None:
        # Single source of truth for graph/config, shared verbatim with the
        # MCP tools' _state when the MCP server is mounted (create_app passes
        # it to create_server). Both surfaces dereference this one holder, so
        # a rebuild-swap on either side is visible everywhere with nothing to
        # propagate or keep "in sync".
        self.shared = SharedServerState(
            {
                "graph": graph,
                "config": config,
                "working_dir": repo_root,
                "build_time": time.time(),
            }
        )
        self.repo_root = repo_root
        self.allowed_roots = allowed_roots or _compute_allowed_roots(repo_root, config)
        self._mtimes: dict[str, float] = {}
        self._last_stale_check = 0.0
        self.snapshot_mtimes()
        # Change-detection state that lives outside the holder — this object's
        # mtime snapshot, and the config fingerprint recorded for the server
        # this object belongs to. Every rebuild must bring both forward,
        # including one reached through an MCP tool that knows nothing about
        # this object; registering them as hooks is what makes that true of
        # the one rebuild routine instead of each caller (REQ-p00004-O).
        self.shared.post_rebuild_hooks.append(self.snapshot_mtimes)
        self.shared.post_rebuild_hooks.append(self._refresh_daemon_config_hash)
        # Per-repo detached HEAD tracking (for rewind)
        self._repo_detached: dict[str, DetachedState] = {}

    @property
    def graph(self) -> FederatedGraph:
        return self.shared["graph"]

    @graph.setter
    def graph(self, value: FederatedGraph) -> None:
        self.shared["graph"] = value

    @property
    def build_time(self) -> float:
        """When the live graph was last built from disk.

        Lives in the shared holder, not on AppState: the MCP save/refresh
        tools rebuild and swap the graph through the holder, and a
        build_time only this object could update would stay behind, making
        the viewer's staleness check report freshly-saved files as changed.
        """
        return self.shared["build_time"]

    @build_time.setter
    def build_time(self, value: float) -> None:
        self.shared["build_time"] = value

    @property
    def config(self) -> dict[str, Any]:
        return self.shared["config"]

    @config.setter
    def config(self, value: dict[str, Any]) -> None:
        self.shared["config"] = value

    def enter_detached(self, repo_name: str, branch: str, head_commit: str) -> None:
        """Record that a repo has rewound from its branch tip."""
        self._repo_detached[repo_name] = DetachedState(
            originating_branch=branch,
            originating_head=head_commit,
        )

    def leave_detached(self, repo_name: str) -> None:
        """Clear detached state for a specific repo."""
        self._repo_detached.pop(repo_name, None)

    @property
    def is_detached(self) -> bool:
        """True if any repo is in detached HEAD state."""
        return len(self._repo_detached) > 0

    def is_repo_detached(self, repo_name: str) -> bool:
        """Check if a specific repo is detached."""
        return repo_name in self._repo_detached

    def get_detached_state(self, repo_name: str) -> DetachedState | None:
        """Get detached state for a repo, or None."""
        return self._repo_detached.get(repo_name)

    @classmethod
    def from_config(
        cls,
        repo_root: Path,
        config: dict[str, Any] | None = None,
    ) -> AppState:
        """Build graph from config and create state."""
        from elspais.config import get_config
        from elspais.graph.factory import build_graph

        if config is None:
            config = get_config(start_path=repo_root, quiet=True)
        graph = build_graph(config=config, repo_root=repo_root)
        graph.load_comments()
        return cls(
            graph=graph,
            repo_root=repo_root,
            config=config,
        )

    # Implements: REQ-p00004-J
    def snapshot_mtimes(self) -> None:
        """Record current mtimes of all scanned spec/code/test files.

        Also snapshots the config files (.elspais.toml, .elspais.local.toml)
        so a long-running server notices config edits (REQ-p00004-J).
        """
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
        for f in self._config_files():
            if f.is_file():
                try:
                    self._mtimes[str(f)] = f.stat().st_mtime
                except OSError:
                    pass

    # Implements: REQ-p00004-O
    def _refresh_daemon_config_hash(self) -> None:
        """Bring the recorded config fingerprint forward after a rebuild.

        The rebuild re-read configuration from disk, so the fingerprint a CLI
        staleness check compares against must move with it or the CLI tears
        down a server that is already serving exactly that configuration.

        This is registered as a hook rather than performed by the rebuild
        routine so that it happens only for the process that actually owns the
        record — the one serving the graph the daemon file describes. A
        different process rebuilding its own private graph in the same
        repository must not stamp this record: a fingerprint that is falsely
        current suppresses a restart that is needed, which is worse than the
        needless restart a stale one costs.
        """
        from elspais.mcp.daemon import refresh_daemon_config_hash

        refresh_daemon_config_hash(self.repo_root)

    def _config_files(self) -> list[Path]:
        """Config files whose edits must trigger a graph rebuild."""
        return [
            self.repo_root / ".elspais.toml",
            self.repo_root / ".elspais.local.toml",
        ]

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
        # Config file created after the last snapshot (e.g. new local overrides)
        for f in self._config_files():
            if f.is_file() and str(f) not in self._mtimes:
                return True
        return False

    # Implements: REQ-p00015-F, REQ-p00015-B
    def ensure_fresh(self) -> bool:
        """Rebuild graph if files changed.

        Returns True only when a rebuild completed and the new graph is the
        one now being served. A rebuild that was skipped (throttled, pending
        mutations, nothing stale) and a rebuild that was attempted and failed
        both return False: the caller must never be told an effect occurred
        that is not present in the served graph (REQ-p00015-F). A failure is
        reported with its cause on stderr rather than being swallowed
        (REQ-p00015-B).

        Throttled to at most one mtime check per second.

        NEVER rebuilds over pending in-memory mutations: an auto-rebuild is
        a silent discard of every writer's unsaved work, the exact loss the
        mutation-history guards exist to prevent. Discarding requires an
        explicit, tip-guarded revert/reload/refresh. Implements: REQ-o00062-N
        """
        now = time.time()
        if now - self._last_stale_check < 1.0:
            return False
        self._last_stale_check = now
        # The pending-mutations check and the rebuild must be one atomic
        # unit: a writer landing a mutation between the check and the swap
        # would have its accepted work silently discarded by the rebuild.
        with self.shared.write_lock:
            try:
                has_pending = len(self.graph.mutation_log) > 0
            except (AttributeError, TypeError):
                has_pending = False
            if has_pending:
                return False
            if not self.is_stale():
                return False
            try:
                self._rebuild()
            except Exception as exc:
                # Tolerated failure (visible, not swallowed): keep serving the
                # previous graph rather than crashing on a bad file state.
                print(
                    f"warning: auto-refresh rebuild failed, keeping old graph: {exc}",
                    file=sys.stderr,
                )
                return False
            return True

    # Implements: REQ-p00004-J, REQ-p00004-O, REQ-p00015-F
    def _rebuild(self) -> None:
        """Rebuild the graph from disk through the one shared rebuild routine.

        This object owns no rebuild logic of its own. ``rebuild_shared_graph``
        re-reads config, publishes config and graph together under the shared
        write lock, and runs the post-rebuild hooks — this object's mtime
        re-snapshot and its daemon-fingerprint sync among them. It is the same
        routine the explicit reload surfaces reach, so every path leaves
        identical state behind it.

        Raises on failure so ``ensure_fresh()`` keeps serving the previous
        graph and reports honestly that no rebuild happened.
        """
        result = rebuild_shared_graph(self.shared)
        if not result.get("success"):
            raise RuntimeError(result.get("message", "graph rebuild failed"))
