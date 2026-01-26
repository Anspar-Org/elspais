"""
elspais.mcp.context - Workspace context for MCP server.

Manages workspace state including configuration, requirements cache,
traceability graph cache, and content rules.

UPDATED: Now uses arch3 graph system.
"""

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from elspais.arch3 import (
    ContentRule,
    create_parser,
    find_config_file,
    get_spec_directories,
    load_config,
    load_content_rules,
    load_requirements_from_directories,
    Requirement,
    RequirementParser,
    DEFAULT_CONFIG,
)
from elspais.arch3.Graph.builder import GraphBuilder, TraceGraph
from elspais.arch3.Graph.MDparser import ParsedContent


@dataclass
class ValidationResult:
    """Result of graph validation.

    Simple container for validation errors and warnings.
    """

    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """True if no errors were found."""
        return len(self.errors) == 0


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
            config = load_config(config_path).get_raw()
        else:
            config = dict(DEFAULT_CONFIG)

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

        try:
            if regex:
                pattern = re.compile(query, re.IGNORECASE)
            else:
                pattern = re.compile(re.escape(query), re.IGNORECASE)
        except re.error:
            # Invalid regex pattern - return empty results
            return []

        for req in requirements.values():
            if self._matches(req, pattern, field):
                results.append(req)

        return results

    def _matches(self, req: Requirement, pattern: re.Pattern, field: str) -> bool:
        """Check if requirement matches search pattern."""
        if field == "id":
            return bool(pattern.search(req.id))
        elif field == "title":
            return bool(pattern.search(req.title))
        elif field == "body":
            return bool(pattern.search(req.body))
        elif field == "assertions":
            return any(pattern.search(a.text) for a in req.assertions)
        else:  # "all"
            return (
                bool(pattern.search(req.id))
                or bool(pattern.search(req.title))
                or bool(pattern.search(req.body))
                or any(pattern.search(a.text) for a in req.assertions)
            )

    def invalidate_cache(self) -> None:
        """Clear cached requirements and graph (call after edits)."""
        self._requirements_cache = None
        self._graph_state = None

    def get_graph(
        self, force_refresh: bool = False
    ) -> Tuple[TraceGraph, ValidationResult]:
        """
        Get the traceability graph, with caching and lazy refresh.

        Args:
            force_refresh: If True, ignore cache and rebuild graph

        Returns:
            Tuple of (TraceGraph, ValidationResult)
        """
        needs_rebuild = self._graph_state is None or force_refresh or self.is_graph_stale()
        if needs_rebuild:
            self._requirements_cache = None
            self._graph_state = self._build_graph()
        return self._graph_state.graph, self._graph_state.validation

    def is_graph_stale(self) -> bool:
        """
        Check if the cached graph is stale.

        Returns:
            True if graph needs rebuild, False otherwise
        """
        if self._graph_state is None:
            return True

        # Check tracked files for modifications or deletions
        for path, tracked_file in self._graph_state.tracked_files.items():
            if not path.exists():
                return True
            if path.stat().st_mtime > tracked_file.mtime:
                return True

        # Check for new spec files
        current_mtimes = self._get_spec_file_mtimes()
        for path in current_mtimes:
            if path not in self._graph_state.tracked_files:
                return True

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

        for path, tracked_file in self._graph_state.tracked_files.items():
            if not path.exists():
                stale.append(path)
            elif path.stat().st_mtime > tracked_file.mtime:
                stale.append(path)

        current_mtimes = self._get_spec_file_mtimes()
        for path in current_mtimes:
            if path not in self._graph_state.tracked_files:
                stale.append(path)

        return stale

    def get_graph_built_at(self) -> Optional[float]:
        """Get the timestamp when the graph was last built."""
        if self._graph_state is None:
            return None
        return self._graph_state.built_at

    def _build_graph(self) -> GraphState:
        """
        Build the traceability graph from requirements.

        Returns:
            GraphState containing graph, validation, tracked files, and build time
        """
        file_mtimes = self._get_spec_file_mtimes()
        requirements = self.get_requirements()

        # Build graph using arch3 GraphBuilder
        builder = GraphBuilder(repo_root=self.working_dir)

        # Convert requirements to ParsedContent and add to builder
        for req_id, req in requirements.items():
            parsed_data = {
                "id": req.id,
                "title": req.title,
                "level": req.level,
                "status": req.status,
                "hash": req.hash,
                "implements": req.implements,
                "refines": req.refines,
                "assertions": [
                    {"label": a.label, "text": a.text}
                    for a in req.assertions
                ],
            }
            content = ParsedContent(
                content_type="requirement",
                start_line=req.line_number or 1,
                end_line=req.line_number or 1,
                parsed_data=parsed_data,
                raw_text="",
            )
            builder.add_parsed_content(content)

        graph = builder.build()

        # Basic validation (arch3 doesn't have full validation yet)
        validation = ValidationResult()

        # Check for orphans (requirements with no parent and no Implements)
        for node in graph.roots:
            if not node.parents and node.content.get("level") not in ("PRD", "prd", "1"):
                validation.warnings.append(
                    f"{node.id}: Non-PRD requirement has no parent"
                )

        # Build tracked files
        tracked_files = self._build_tracked_files(graph, file_mtimes)

        return GraphState(
            graph=graph,
            validation=validation,
            tracked_files=tracked_files,
            built_at=time.time(),
        )

    def _parse_requirements(self) -> Dict[str, Requirement]:
        """Parse requirements from spec directories."""
        spec_dirs = get_spec_directories(None, self.config, self.working_dir)
        if not spec_dirs:
            return {}
        return load_requirements_from_directories(spec_dirs, self.config)

    def _get_spec_file_mtimes(self) -> Dict[Path, float]:
        """Get modification times for all spec files."""
        mtimes: Dict[Path, float] = {}
        spec_dirs = get_spec_directories(None, self.config, self.working_dir)
        skip_files = self.config.get("spec", {}).get("skip_files", [])
        skip_dirs = self.config.get("spec", {}).get("skip_dirs", [])

        for spec_dir in spec_dirs:
            if spec_dir.exists():
                for md_file in spec_dir.rglob("*.md"):
                    if md_file.name in skip_files:
                        continue

                    if skip_dirs:
                        rel_path = md_file.relative_to(spec_dir)
                        if any(skip_dir in rel_path.parts for skip_dir in skip_dirs):
                            continue

                    mtimes[md_file.resolve()] = md_file.stat().st_mtime

        return mtimes

    def _build_tracked_files(
        self, graph: TraceGraph, file_mtimes: Dict[Path, float]
    ) -> Dict[Path, TrackedFile]:
        """Build TrackedFile entries from graph nodes."""
        tracked: Dict[Path, TrackedFile] = {
            path: TrackedFile(path=path, mtime=mtime, node_ids=[])
            for path, mtime in file_mtimes.items()
        }

        for node in graph.all_nodes():
            if node.source and node.source.path:
                abs_path = (self.working_dir / node.source.path).resolve()
                if abs_path in tracked:
                    tracked[abs_path].node_ids.append(node.id)

        return tracked

    def get_tracked_files(self) -> Dict[Path, TrackedFile]:
        """Get all tracked files and their node mappings."""
        if self._graph_state is None:
            return {}
        return self._graph_state.tracked_files

    def get_nodes_for_file(self, file_path: Path) -> List[str]:
        """Get node IDs that originate from a specific file."""
        if self._graph_state is None:
            return []

        abs_path = file_path.resolve()
        tracked_file = self._graph_state.tracked_files.get(abs_path)
        return tracked_file.node_ids if tracked_file else []
