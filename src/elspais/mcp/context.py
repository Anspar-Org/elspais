# Implements: REQ-int-d00003 (MCP Server)
"""
elspais.mcp.context - Workspace context for MCP server.

Provides cached access to the traceability graph and requirements.
Uses the graph factory for graph construction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, Optional

from elspais.config import find_config_file, get_config
from elspais.content_rules import load_content_rules
from elspais.graph import GraphNode, NodeKind
from elspais.graph.builder import TraceGraph
from elspais.graph.factory import build_graph


@dataclass
class GraphState:
    """State container for cached graph."""

    graph: TraceGraph
    validation: list[Any] = field(default_factory=list)
    built_at: datetime = field(default_factory=datetime.now)
    source_files: set[str] = field(default_factory=set)


class WorkspaceContext:
    """Workspace context providing cached access to requirements and graph.

    This is the primary interface used by MCP tools. It caches the graph
    and provides convenient methods for requirement access.
    """

    def __init__(self, working_dir: Path, config: dict[str, Any]) -> None:
        """Initialize workspace context.

        Args:
            working_dir: Working directory (usually repo root).
            config: Configuration dictionary.
        """
        self.working_dir = working_dir
        self.config = config
        self._graph_state: Optional[GraphState] = None
        self._requirements_cache: Optional[dict[str, GraphNode]] = None
        self._content_rules_cache: Optional[list[Any]] = None

    @classmethod
    def from_directory(cls, working_dir: Optional[Path] = None) -> WorkspaceContext:
        """Create context from a working directory.

        Args:
            working_dir: Directory to use (defaults to cwd).

        Returns:
            Configured WorkspaceContext.
        """
        if working_dir is None:
            working_dir = Path.cwd()

        config_path = find_config_file(working_dir)
        config = get_config(config_path, working_dir)

        return cls(working_dir, config)

    def get_graph(self, force_refresh: bool = False) -> tuple[TraceGraph, list[Any]]:
        """Get the traceability graph, building if needed.

        Args:
            force_refresh: If True, rebuild even if cached.

        Returns:
            Tuple of (TraceGraph, validation_results).
        """
        if self._graph_state is None or force_refresh:
            graph = build_graph(
                config=self.config,
                repo_root=self.working_dir,
            )

            # Track source files for staleness detection
            source_files = set()
            for node in graph.all_nodes():
                if node.source and node.source.path:
                    source_files.add(node.source.path)

            self._graph_state = GraphState(
                graph=graph,
                validation=[],
                built_at=datetime.now(),
                source_files=source_files,
            )
            self._requirements_cache = None

        return self._graph_state.graph, self._graph_state.validation

    def get_requirements(self, force_refresh: bool = False) -> dict[str, GraphNode]:
        """Get all requirements as a dict.

        Args:
            force_refresh: If True, rebuild graph.

        Returns:
            Dict mapping requirement ID to GraphNode.
        """
        if self._requirements_cache is None or force_refresh:
            graph, _ = self.get_graph(force_refresh)
            self._requirements_cache = {}
            for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
                self._requirements_cache[node.id] = node

        return self._requirements_cache

    def get_requirement(self, req_id: str) -> Optional[GraphNode]:
        """Get a single requirement by ID.

        Args:
            req_id: The requirement ID.

        Returns:
            GraphNode if found, None otherwise.
        """
        requirements = self.get_requirements()
        return requirements.get(req_id)

    def search_requirements(
        self, query: str, search_field: str = "all", regex: bool = False
    ) -> list[GraphNode]:
        """Search requirements by query.

        Args:
            query: Search string or regex pattern.
            search_field: Field to search ("all", "id", "title", "body").
            regex: If True, treat query as regex.

        Returns:
            List of matching GraphNode objects.
        """
        requirements = self.get_requirements()
        results = []

        if regex:
            pattern = re.compile(query, re.IGNORECASE)
        else:
            pattern = re.compile(re.escape(query), re.IGNORECASE)

        for node in requirements.values():
            match = False

            if search_field in ("all", "id"):
                if pattern.search(node.id):
                    match = True

            if search_field in ("all", "title"):
                if node.label and pattern.search(node.label):
                    match = True

            if search_field in ("all", "body"):
                body = node.get_field("body", "")
                if body and pattern.search(body):
                    match = True

            if match:
                results.append(node)

        return results

    def get_content_rules(self) -> list[Any]:
        """Get configured content rules.

        Returns:
            List of ContentRule objects.
        """
        if self._content_rules_cache is None:
            rules_config = self.config.get("rules", {}).get("content_rules", [])
            self._content_rules_cache = load_content_rules(
                rules_config, self.working_dir
            )

        return self._content_rules_cache

    def is_graph_stale(self) -> bool:
        """Check if graph may be stale due to file changes.

        Returns:
            True if files have been modified since graph was built.
        """
        if self._graph_state is None:
            return True

        # Check if any tracked files have been modified
        for file_path in self._graph_state.source_files:
            try:
                path = Path(file_path)
                if not path.is_absolute():
                    path = self.working_dir / path
                if path.exists():
                    mtime = datetime.fromtimestamp(path.stat().st_mtime)
                    if mtime > self._graph_state.built_at:
                        return True
            except (OSError, ValueError):
                continue

        return False

    def get_stale_files(self) -> list[str]:
        """Get list of files modified since graph was built.

        Returns:
            List of file paths that are newer than the graph.
        """
        if self._graph_state is None:
            return []

        stale = []
        for file_path in self._graph_state.source_files:
            try:
                path = Path(file_path)
                if not path.is_absolute():
                    path = self.working_dir / path
                if path.exists():
                    mtime = datetime.fromtimestamp(path.stat().st_mtime)
                    if mtime > self._graph_state.built_at:
                        stale.append(file_path)
            except (OSError, ValueError):
                continue

        return stale

    def get_graph_built_at(self) -> Optional[str]:
        """Get timestamp when graph was last built.

        Returns:
            ISO format timestamp or None if not built.
        """
        if self._graph_state is None:
            return None
        return self._graph_state.built_at.isoformat()

    def invalidate_cache(self) -> None:
        """Invalidate all caches, forcing rebuild on next access."""
        self._graph_state = None
        self._requirements_cache = None
        self._content_rules_cache = None


__all__ = ["WorkspaceContext", "GraphState"]
