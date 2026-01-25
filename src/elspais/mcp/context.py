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
from elspais.core.models import ContentRule, Requirement
from elspais.core.parser import RequirementParser
from elspais.core.patterns import PatternConfig


@dataclass
class GraphState:
    """
    Cached state of the traceability graph.

    Tracks the graph, validation result, file modification times,
    and build timestamp for staleness detection.
    """

    graph: TraceGraph
    validation: ValidationResult
    file_mtimes: Dict[Path, float]
    built_at: float


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
        for path, cached_mtime in self._graph_state.file_mtimes.items():
            if not path.exists():
                return True  # File deleted
            if path.stat().st_mtime > cached_mtime:
                return True  # File modified

        # Check for new spec files
        current_mtimes = self._get_spec_file_mtimes()
        for path in current_mtimes:
            if path not in self._graph_state.file_mtimes:
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
        for path, cached_mtime in self._graph_state.file_mtimes.items():
            if not path.exists():
                stale.append(path)  # Deleted
            elif path.stat().st_mtime > cached_mtime:
                stale.append(path)  # Modified

        # Check for new spec files
        current_mtimes = self._get_spec_file_mtimes()
        for path in current_mtimes:
            if path not in self._graph_state.file_mtimes:
                stale.append(path)  # New file

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

        Returns:
            GraphState containing graph, validation, and file mtimes
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

        return GraphState(
            graph=graph,
            validation=validation,
            file_mtimes=file_mtimes,
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

    def _parse_requirements(self) -> Dict[str, Requirement]:
        """Parse requirements from spec directories."""
        if self._parser is None:
            pattern_config = PatternConfig.from_dict(self.config.get("patterns", {}))
            self._parser = RequirementParser(pattern_config)

        spec_dirs = get_spec_directories(None, self.config, self.working_dir)
        skip_files = self.config.get("spec", {}).get("skip_files", [])

        all_requirements: Dict[str, Requirement] = {}

        for spec_dir in spec_dirs:
            if spec_dir.exists():
                requirements = self._parser.parse_directory(spec_dir, skip_files=skip_files)
                all_requirements.update(requirements)

        return all_requirements

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
