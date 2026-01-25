"""
elspais.mcp.context - Workspace context for MCP server.

Manages workspace state including configuration, requirements cache,
traceability graph cache, and content rules.
"""

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from elspais.config.loader import find_config_file, get_spec_directories, load_config
from elspais.core.content_rules import load_content_rules
from elspais.core.graph import TraceGraph
from elspais.core.graph_builder import TraceGraphBuilder, ValidationResult
from elspais.core.graph_schema import GraphSchema
from elspais.core.loader import create_parser, load_requirements_from_directories
from elspais.core.models import ContentRule, Requirement
from elspais.core.parser import RequirementParser  # Only for _parser type in partial_refresh


@dataclass
class TrackedFile:
    """
    Tracks a spec file and the nodes it contains.

    Used for incremental graph updates - when a file changes, only nodes
    from that file need to be re-parsed and re-linked.

    Attributes:
        path: Absolute path to the file
        mtime: File modification time at time of graph build
        node_ids: List of node IDs that originate from this file
    """

    path: Path
    mtime: float
    node_ids: List[str] = field(default_factory=list)


@dataclass
class GraphState:
    """
    Cached state of the traceability graph.

    Tracks the graph, validation result, tracked files (with their nodes),
    and build timestamp for staleness detection.
    """

    graph: TraceGraph
    validation: ValidationResult
    tracked_files: Dict[Path, TrackedFile]
    built_at: float

    @property
    def file_mtimes(self) -> Dict[Path, float]:
        """
        Get file modification times (backward compatibility).

        Returns:
            Dict mapping file paths to their mtime values
        """
        return {path: tf.mtime for path, tf in self.tracked_files.items()}


@dataclass
class WorkspaceContext:
    """
    Manages workspace state for MCP server operations.

    Provides caching of parsed requirements and traceability graph,
    and access to configuration, content rules, and other workspace resources.
    """

    working_dir: Path
    config: Dict[str, Any] = field(default_factory=dict)
    _requirements_cache: Optional[Dict[str, Requirement]] = field(default=None, repr=False)
    _parser: Optional[RequirementParser] = field(default=None, repr=False)
    _graph_state: Optional[GraphState] = field(default=None, repr=False)

    @classmethod
    def from_directory(cls, directory: Path) -> "WorkspaceContext":
        """
        Initialize context from a working directory.

        Loads configuration from .elspais.toml if found.

        Args:
            directory: Working directory path

        Returns:
            Initialized WorkspaceContext
        """
        directory = directory.resolve()
        config_path = find_config_file(directory)

        if config_path:
            config = load_config(config_path)
        else:
            # Use defaults
            from elspais.config.defaults import DEFAULT_CONFIG

            config = DEFAULT_CONFIG.copy()

        return cls(working_dir=directory, config=config)

    def get_requirements(self, force_refresh: bool = False) -> Dict[str, Requirement]:
        """
        Get all parsed requirements, with caching.

        Args:
            force_refresh: If True, ignore cache and re-parse

        Returns:
            Dict mapping requirement IDs to Requirement objects
        """
        if self._requirements_cache is None or force_refresh:
            self._requirements_cache = self._parse_requirements()
        return self._requirements_cache

    def get_requirement(self, req_id: str) -> Optional[Requirement]:
        """
        Get a single requirement by ID.

        Args:
            req_id: Requirement ID (e.g., "REQ-p00001")

        Returns:
            Requirement if found, None otherwise
        """
        requirements = self.get_requirements()
        return requirements.get(req_id)

    def get_content_rules(self) -> List[ContentRule]:
        """
        Get all configured content rules.

        Returns:
            List of ContentRule objects
        """
        return load_content_rules(self.config, self.working_dir)

    def search_requirements(
        self,
        query: str,
        field: str = "all",
        regex: bool = False,
    ) -> List[Requirement]:
        """
        Search requirements by pattern.

        Args:
            query: Search query string
            field: Field to search - "all", "id", "title", "body", "assertions"
            regex: If True, treat query as regex pattern

        Returns:
            List of matching requirements
        """
        requirements = self.get_requirements()
        results = []

        if regex:
            pattern = re.compile(query, re.IGNORECASE)
        else:
            pattern = re.compile(re.escape(query), re.IGNORECASE)

        for req in requirements.values():
            if self._matches(req, pattern, field):
                results.append(req)

        return results

    def invalidate_cache(self) -> None:
        """Clear cached requirements and graph (call after edits)."""
        self._requirements_cache = None
        self._graph_state = None

    def get_graph(
        self, force_refresh: bool = False
    ) -> Tuple[TraceGraph, ValidationResult]:
        """
        Get the traceability graph, with caching and lazy refresh.

        The graph is rebuilt if:
        - No cached graph exists
        - force_refresh=True is passed
        - Any spec file has been modified since last build (staleness check)

        When rebuilding due to staleness, the requirements cache is also
        invalidated to ensure fresh data.

        Args:
            force_refresh: If True, ignore cache and rebuild graph

        Returns:
            Tuple of (TraceGraph, ValidationResult)
        """
        needs_rebuild = self._graph_state is None or force_refresh or self.is_graph_stale()
        if needs_rebuild:
            # Invalidate requirements cache to ensure fresh data
            self._requirements_cache = None
            self._graph_state = self._build_graph()
        return self._graph_state.graph, self._graph_state.validation

    def is_graph_stale(self) -> bool:
        """
        Check if the cached graph is stale.

        Returns True if:
        - No graph has been built yet
        - Any tracked file has been modified since last build
        - Any tracked file has been deleted
        - New spec files have been added

        Returns:
            True if graph needs rebuild, False otherwise
        """
        if self._graph_state is None:
            return True

        # Check tracked files for modifications or deletions
        for path, tracked_file in self._graph_state.tracked_files.items():
            if not path.exists():
                return True  # File deleted
            if path.stat().st_mtime > tracked_file.mtime:
                return True  # File modified

        # Check for new spec files
        current_mtimes = self._get_spec_file_mtimes()
        for path in current_mtimes:
            if path not in self._graph_state.tracked_files:
                return True  # New file added

        return False

    def get_stale_files(self) -> List[Path]:
        """
        Get list of files that have changed since last graph build.

        Returns:
            List of paths that are stale (modified, deleted, or new)
        """
        if self._graph_state is None:
            return []

        stale = []

        # Check tracked files for modifications or deletions
        for path, tracked_file in self._graph_state.tracked_files.items():
            if not path.exists():
                stale.append(path)  # Deleted
            elif path.stat().st_mtime > tracked_file.mtime:
                stale.append(path)  # Modified

        # Check for new spec files
        current_mtimes = self._get_spec_file_mtimes()
        for path in current_mtimes:
            if path not in self._graph_state.tracked_files:
                stale.append(path)  # New file

        return stale

    def get_stale_tracked_files(self) -> List[TrackedFile]:
        """
        Get TrackedFile objects for files that have changed.

        More detailed than get_stale_files() - includes node_ids for
        each changed file, enabling targeted incremental updates.

        Returns:
            List of TrackedFile objects for stale files (excludes new files)
        """
        if self._graph_state is None:
            return []

        stale = []

        for path, tracked_file in self._graph_state.tracked_files.items():
            if not path.exists():
                stale.append(tracked_file)  # Deleted (still has old node_ids)
            elif path.stat().st_mtime > tracked_file.mtime:
                stale.append(tracked_file)  # Modified

        return stale

    def get_graph_built_at(self) -> Optional[float]:
        """
        Get the timestamp when the graph was last built.

        Returns:
            Unix timestamp, or None if no graph has been built
        """
        if self._graph_state is None:
            return None
        return self._graph_state.built_at

    def _build_graph(self) -> GraphState:
        """
        Build the traceability graph from requirements.

        Creates a TraceGraph with all requirements, assertions,
        and their relationships. Computes metrics for coverage.
        Tracks which nodes come from which files for incremental updates.

        Returns:
            GraphState containing graph, validation, tracked files, and build time
        """
        # Get current file mtimes before parsing
        file_mtimes = self._get_spec_file_mtimes()

        # Get requirements (may use cache if still valid)
        requirements = self.get_requirements()

        # Build schema from config
        schema = GraphSchema.from_config(self.config)

        # Build graph
        builder = TraceGraphBuilder(repo_root=self.working_dir, schema=schema)
        builder.add_requirements(requirements)

        # Build and validate
        graph, validation = builder.build_and_validate()

        # Compute metrics
        metrics_config = self.config.get("rules", {}).get("metrics", {})
        exclude_status = metrics_config.get("exclude_from_metrics", [])
        strict_mode = metrics_config.get("strict_mode", False)
        builder.compute_metrics(graph, exclude_status=exclude_status, strict_mode=strict_mode)

        # Build tracked files with node_ids
        tracked_files = self._build_tracked_files(graph, file_mtimes)

        return GraphState(
            graph=graph,
            validation=validation,
            tracked_files=tracked_files,
            built_at=time.time(),
        )

    def _get_spec_file_mtimes(self) -> Dict[Path, float]:
        """
        Get modification times for all spec files.

        Returns:
            Dict mapping file paths to their mtime values
        """
        mtimes: Dict[Path, float] = {}
        spec_dirs = get_spec_directories(None, self.config, self.working_dir)
        skip_files = self.config.get("spec", {}).get("skip_files", [])

        for spec_dir in spec_dirs:
            if spec_dir.exists():
                for md_file in spec_dir.rglob("*.md"):
                    # Check skip patterns
                    rel_path = md_file.name
                    if any(rel_path == skip for skip in skip_files):
                        continue
                    mtimes[md_file.resolve()] = md_file.stat().st_mtime

        return mtimes

    def _build_tracked_files(
        self, graph: TraceGraph, file_mtimes: Dict[Path, float]
    ) -> Dict[Path, TrackedFile]:
        """
        Build TrackedFile entries from graph nodes.

        Groups nodes by their source file path, enabling incremental
        graph updates when specific files change.

        Args:
            graph: The built traceability graph
            file_mtimes: Dict of file paths to modification times

        Returns:
            Dict mapping file paths to TrackedFile entries with node_ids
        """
        # Initialize tracked files from known mtimes
        tracked: Dict[Path, TrackedFile] = {
            path: TrackedFile(path=path, mtime=mtime, node_ids=[])
            for path, mtime in file_mtimes.items()
        }

        # Group nodes by source file
        for node in graph.all_nodes():
            if node.source and node.source.path:
                # Convert repo-relative path to absolute
                abs_path = (self.working_dir / node.source.path).resolve()
                if abs_path in tracked:
                    tracked[abs_path].node_ids.append(node.id)

        return tracked

    def get_tracked_files(self) -> Dict[Path, TrackedFile]:
        """
        Get all tracked files and their node mappings.

        Returns:
            Dict mapping file paths to TrackedFile entries,
            or empty dict if no graph has been built
        """
        if self._graph_state is None:
            return {}
        return self._graph_state.tracked_files

    def get_nodes_for_file(self, file_path: Path) -> List[str]:
        """
        Get node IDs that originate from a specific file.

        Args:
            file_path: Path to the spec file

        Returns:
            List of node IDs, or empty list if file not tracked
        """
        if self._graph_state is None:
            return []

        abs_path = file_path.resolve()
        tracked_file = self._graph_state.tracked_files.get(abs_path)
        return tracked_file.node_ids if tracked_file else []

    def partial_refresh(
        self, changed_files: Optional[List[Path]] = None
    ) -> Tuple[TraceGraph, ValidationResult]:
        """
        Refresh the graph incrementally by only re-parsing changed files.

        This method provides a performance optimization over full refresh by:
        - Only re-parsing files that have changed (modified, deleted, new)
        - Preserving requirements from unchanged files in the cache
        - Rebuilding the graph structure from merged requirements

        If no graph exists yet, falls back to full build.

        Args:
            changed_files: Optional list of specific files to re-parse.
                          If None, automatically detects stale files.

        Returns:
            Tuple of (TraceGraph, ValidationResult)
        """
        if self._graph_state is None:
            # No existing graph, do full build
            return self.get_graph(force_refresh=True)

        # Determine which files changed
        if changed_files is None:
            stale = self.get_stale_files()
        else:
            stale = [f.resolve() for f in changed_files]

        if not stale:
            # No changes, return cached graph
            return self._graph_state.graph, self._graph_state.validation

        # Get current file mtimes
        current_mtimes = self._get_spec_file_mtimes()

        # Split into categories
        deleted_files = [f for f in stale if not f.exists()]
        modified_files = [
            f for f in stale if f.exists() and f in self._graph_state.tracked_files
        ]
        new_files = [
            f for f in stale if f.exists() and f not in self._graph_state.tracked_files
        ]

        # Start with existing requirements
        if self._requirements_cache is None:
            # Shouldn't happen but handle gracefully
            return self.get_graph(force_refresh=True)

        requirements = dict(self._requirements_cache)  # Copy

        # Get requirement IDs to remove (from deleted/modified files)
        req_ids_to_remove = self._get_requirement_ids_for_files(
            deleted_files + modified_files
        )
        for req_id in req_ids_to_remove:
            requirements.pop(req_id, None)

        # Re-parse modified and new files
        if self._parser is None:
            self._parser = create_parser(self.config)

        for path in modified_files + new_files:
            file_reqs = self._parser.parse_file(path)
            requirements.update(file_reqs)

        # Update requirements cache
        self._requirements_cache = requirements

        # Rebuild graph from merged requirements
        schema = GraphSchema.from_config(self.config)
        builder = TraceGraphBuilder(repo_root=self.working_dir, schema=schema)
        builder.add_requirements(requirements)
        graph, validation = builder.build_and_validate()

        # Compute metrics
        metrics_config = self.config.get("rules", {}).get("metrics", {})
        exclude_status = metrics_config.get("exclude_from_metrics", [])
        strict_mode = metrics_config.get("strict_mode", False)
        builder.compute_metrics(
            graph, exclude_status=exclude_status, strict_mode=strict_mode
        )

        # Build new tracked files
        tracked_files = self._build_tracked_files(graph, current_mtimes)

        # Update graph state
        self._graph_state = GraphState(
            graph=graph,
            validation=validation,
            tracked_files=tracked_files,
            built_at=time.time(),
        )

        return graph, validation

    def _get_requirement_ids_for_files(self, file_paths: List[Path]) -> List[str]:
        """
        Get requirement IDs (not assertion IDs) from tracked files.

        Filters out assertion IDs (e.g., REQ-p00001-A) to return only
        requirement IDs (e.g., REQ-p00001).

        Args:
            file_paths: List of file paths to get requirement IDs for

        Returns:
            List of requirement IDs from those files
        """
        if self._graph_state is None:
            return []

        req_ids = []
        for path in file_paths:
            tracked_file = self._graph_state.tracked_files.get(path)
            if tracked_file:
                for node_id in tracked_file.node_ids:
                    # Assertion IDs end with -A, -B, etc. (single capital letter)
                    # This heuristic works for most patterns
                    if not self._is_assertion_id(node_id):
                        req_ids.append(node_id)
        return req_ids

    def _is_assertion_id(self, node_id: str) -> bool:
        """
        Check if a node ID is an assertion ID (vs requirement ID).

        Assertion IDs have format like REQ-p00001-A or REQ-p00001-01.
        They are the requirement ID with an assertion label suffix.

        Args:
            node_id: The node ID to check

        Returns:
            True if this is an assertion ID
        """
        if "-" not in node_id:
            return False

        # Split off the last part after the final hyphen
        parts = node_id.rsplit("-", 1)
        if len(parts) != 2:
            return False

        suffix = parts[1]

        # Check for assertion label patterns:
        # - Single uppercase letter (A, B, C, ..., Z)
        # - Two-digit number (00, 01, ..., 99)
        # - Single digit (1-9 for 1-based)
        if len(suffix) == 1 and suffix.isupper() and suffix.isalpha():
            return True
        if len(suffix) <= 2 and suffix.isdigit():
            return True

        return False

    def _parse_requirements(self) -> Dict[str, Requirement]:
        """Parse requirements from spec directories.

        Uses the centralized loader from elspais.core.loader.
        """
        spec_dirs = get_spec_directories(None, self.config, self.working_dir)
        existing_dirs = [d for d in spec_dirs if d.exists()]

        if not existing_dirs:
            return {}

        return load_requirements_from_directories(existing_dirs, self.config, recursive=True)

    def _matches(self, req: Requirement, pattern: re.Pattern, field: str) -> bool:
        """Check if requirement matches search pattern."""
        if field == "id":
            return bool(pattern.search(req.id))
        elif field == "title":
            return bool(pattern.search(req.title))
        elif field == "body":
            return bool(pattern.search(req.body))
        elif field == "assertions":
            for assertion in req.assertions:
                if pattern.search(assertion.text):
                    return True
            return False
        else:  # "all"
            if pattern.search(req.id):
                return True
            if pattern.search(req.title):
                return True
            if pattern.search(req.body):
                return True
            for assertion in req.assertions:
                if pattern.search(assertion.text):
                    return True
            return False
