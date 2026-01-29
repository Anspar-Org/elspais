"""elspais.mcp.server - MCP server implementation.

Creates and runs the MCP server exposing elspais functionality.

This is a pure interface layer - it consumes TraceGraph directly
without creating intermediate data structures (REQ-p00060-B).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

try:
    from mcp.server.fastmcp import FastMCP

    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    FastMCP = None

from elspais.config import find_config_file, get_config
from elspais.graph import NodeKind
from elspais.graph.annotators import count_by_coverage, count_by_git_status, count_by_level
from elspais.graph.builder import TraceGraph
from elspais.graph.factory import build_graph

# ─────────────────────────────────────────────────────────────────────────────
# Serializers (REQ-d00064)
# ─────────────────────────────────────────────────────────────────────────────


def _serialize_requirement_summary(node: Any) -> dict[str, Any]:
    """Serialize a requirement node to summary format.

    REQ-d00064-A: Returns id, title, level, status only.
    REQ-d00064-C: Reads from node.get_field() and node.get_label().
    """
    return {
        "id": node.id,
        "title": node.get_label(),
        "level": node.get_field("level"),
        "status": node.get_field("status"),
    }


def _serialize_assertion(node: Any) -> dict[str, Any]:
    """Serialize an assertion node."""
    return {
        "id": node.id,
        "label": node.get_field("label"),
        "text": node.get_label(),
    }


def _serialize_requirement_full(node: Any) -> dict[str, Any]:
    """Serialize a requirement node to full format.

    REQ-d00064-B: Returns all fields including assertions and edges.
    REQ-d00064-C: Reads from node.get_field() and node.get_label().
    """
    # Get assertions from children
    assertions = []
    children = []
    for child in node.iter_children():
        if child.kind == NodeKind.ASSERTION:
            assertions.append(_serialize_assertion(child))
        else:
            children.append(_serialize_requirement_summary(child))

    # Get parents
    parents = []
    for parent in node.iter_parents():
        if parent.kind == NodeKind.REQUIREMENT:
            parents.append(_serialize_requirement_summary(parent))

    return {
        "id": node.id,
        "title": node.get_label(),
        "level": node.get_field("level"),
        "status": node.get_field("status"),
        "hash": node.get_field("hash"),
        "assertions": assertions,
        "children": children,
        "parents": parents,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Core Tool Functions (REQ-o00060)
# ─────────────────────────────────────────────────────────────────────────────


def _get_graph_status(graph: TraceGraph) -> dict[str, Any]:
    """Get graph status.

    REQ-d00060-A: Returns is_stale from metadata.
    REQ-d00060-B: Returns node_counts by calling nodes_by_kind().
    REQ-d00060-D: Returns root_count using graph.root_count().
    REQ-d00060-E: Does NOT iterate full graph for counts.
    """
    # Count nodes by kind using the efficient nodes_by_kind iterator
    node_counts: dict[str, int] = {}
    for kind in NodeKind:
        count = sum(1 for _ in graph.nodes_by_kind(kind))
        if count > 0:
            node_counts[kind.value] = count

    return {
        "root_count": graph.root_count(),
        "node_counts": node_counts,
        "total_nodes": graph.node_count(),
        "has_orphans": graph.has_orphans(),
        "has_broken_references": graph.has_broken_references(),
    }


def _refresh_graph(
    repo_root: Path,
    full: bool = False,
) -> tuple[dict[str, Any], TraceGraph]:
    """Rebuild the graph from spec files.

    REQ-o00060-B: Forces graph rebuild.

    Args:
        repo_root: Repository root path.
        full: If True, clear all caches before rebuild.

    Returns:
        Tuple of (result dict, new TraceGraph).
    """
    # Build fresh graph
    new_graph = build_graph(repo_root=repo_root)

    return {
        "success": True,
        "message": "Graph refreshed successfully",
        "node_count": new_graph.node_count(),
    }, new_graph


def _search(
    graph: TraceGraph,
    query: str,
    field: str = "all",
    regex: bool = False,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Search requirements.

    REQ-d00061-A: Iterates graph.nodes_by_kind(REQUIREMENT).
    REQ-d00061-B: Supports field parameter (id, title, body, all).
    REQ-d00061-C: Supports regex=True for regex matching.
    REQ-d00061-D: Returns serialized requirement summaries.
    REQ-d00061-E: Limits results to prevent unbounded sizes.
    """
    results = []

    # Compile pattern if regex mode
    if regex:
        try:
            pattern = re.compile(query, re.IGNORECASE)
        except re.error:
            return []
    else:
        # Simple case-insensitive substring match
        query_lower = query.lower()

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        match = False

        if field in ("id", "all"):
            if regex:
                if pattern.search(node.id):
                    match = True
            else:
                if query_lower in node.id.lower():
                    match = True

        if not match and field in ("title", "all"):
            title = node.get_label() or ""
            if regex:
                if pattern.search(title):
                    match = True
            else:
                if query_lower in title.lower():
                    match = True

        if match:
            results.append(_serialize_requirement_summary(node))
            if len(results) >= limit:
                break

    return results


def _get_requirement(graph: TraceGraph, req_id: str) -> dict[str, Any]:
    """Get single requirement details.

    REQ-d00062-A: Uses graph.find_by_id() for O(1) lookup.
    REQ-d00062-B: Returns node fields.
    REQ-d00062-C: Returns assertions from iter_children().
    REQ-d00062-D: Returns relationships from iter_outgoing_edges().
    REQ-d00062-F: Returns error for non-existent requirements.
    """
    node = graph.find_by_id(req_id)

    if node is None:
        return {"error": f"Requirement '{req_id}' not found"}

    if node.kind != NodeKind.REQUIREMENT:
        return {"error": f"Node '{req_id}' is not a requirement"}

    return _serialize_requirement_full(node)


def _get_hierarchy(graph: TraceGraph, req_id: str) -> dict[str, Any]:
    """Get requirement hierarchy.

    REQ-d00063-A: Returns ancestors by walking iter_parents() recursively.
    REQ-d00063-B: Returns children from iter_children().
    REQ-d00063-D: Returns node summaries (id, title, level).
    REQ-d00063-E: Handles DAG with multiple parents.
    """
    node = graph.find_by_id(req_id)

    if node is None:
        return {"error": f"Requirement '{req_id}' not found"}

    # Collect ancestors recursively (handles DAG)
    ancestors = []
    visited = set()

    def walk_ancestors(n):
        for parent in n.iter_parents():
            if parent.id not in visited and parent.kind == NodeKind.REQUIREMENT:
                visited.add(parent.id)
                ancestors.append(_serialize_requirement_summary(parent))
                walk_ancestors(parent)

    walk_ancestors(node)

    # Collect children (only requirements, not assertions)
    children = []
    for child in node.iter_children():
        if child.kind == NodeKind.REQUIREMENT:
            children.append(_serialize_requirement_summary(child))

    return {
        "id": req_id,
        "ancestors": ancestors,
        "children": children,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Workspace Context Tools (REQ-o00061)
# ─────────────────────────────────────────────────────────────────────────────


def _get_workspace_info(working_dir: Path) -> dict[str, Any]:
    """Get workspace information.

    REQ-o00061-A: Returns repository path, project name, and configuration summary.
    REQ-o00061-D: Reads configuration from unified config system.

    Args:
        working_dir: The repository root directory.

    Returns:
        Workspace information dict.
    """
    config = get_config(start_path=working_dir, quiet=True)

    # Get project name from config, fallback to directory name
    project_name = config.get("project", {}).get("name")
    if not project_name:
        project_name = working_dir.name

    # Build configuration summary
    config_summary = {
        "prefix": config.get("patterns", {}).get("prefix", "REQ"),
        "spec_directories": config.get("spec", {}).get("directories", ["spec"]),
        "testing_enabled": config.get("testing", {}).get("enabled", False),
        "project_type": config.get("project", {}).get("type"),
    }

    # Check if config file exists
    config_file = find_config_file(working_dir)

    return {
        "repo_path": str(working_dir),
        "project_name": project_name,
        "config_file": str(config_file) if config_file else None,
        "config_summary": config_summary,
    }


def _get_project_summary(graph: TraceGraph, working_dir: Path) -> dict[str, Any]:
    """Get project summary statistics.

    REQ-o00061-B: Returns requirement counts by level, coverage statistics, and change metrics.
    REQ-o00061-C: Uses graph aggregate functions from annotators module.

    Args:
        graph: The TraceGraph to analyze.
        working_dir: The repository root directory.

    Returns:
        Project summary dict.
    """
    # Use aggregate functions from annotators (REQ-o00061-C)
    level_counts = count_by_level(graph)
    coverage_stats = count_by_coverage(graph)
    change_metrics = count_by_git_status(graph)

    return {
        "requirements_by_level": level_counts,
        "coverage": coverage_stats,
        "changes": change_metrics,
        "total_nodes": graph.node_count(),
        "orphan_count": graph.orphan_count(),
        "broken_reference_count": len(list(graph.broken_references())),
    }


# ─────────────────────────────────────────────────────────────────────────────
# MCP Server Instructions
# ─────────────────────────────────────────────────────────────────────────────

MCP_SERVER_INSTRUCTIONS = """\
elspais MCP Server - AI-Driven Requirements Management

This server provides tools to navigate and analyze a requirements traceability graph.
The graph is the single source of truth - all tools read directly from it.

## Quick Start

1. `get_workspace_info()` - Understand what project you're working with
2. `get_project_summary()` - Get overview statistics and health metrics
3. `search(query)` - Find requirements by keyword
4. `get_requirement(req_id)` - Get full details including assertions
5. `get_hierarchy(req_id)` - Navigate parent/child relationships

## Tools Overview

### Graph Status & Control
- `get_graph_status()` - Node counts, orphan/broken reference flags
- `refresh_graph(full=False)` - Rebuild after spec file changes

### Search & Navigation
- `search(query, field="all", regex=False, limit=50)` - Find requirements
  - field: "id", "title", "body", or "all"
  - regex: treat query as regex pattern
- `get_requirement(req_id)` - Full details with assertions and relationships
- `get_hierarchy(req_id)` - Ancestors (to roots) and direct children

### Workspace Context
- `get_workspace_info()` - Repo path, project name, configuration
- `get_project_summary()` - Counts by level, coverage stats, change metrics

## Requirement Levels

Requirements follow a three-tier hierarchy:
- **PRD** (Product): High-level product requirements
- **OPS** (Operations): Operational/process requirements
- **DEV** (Development): Technical implementation requirements

Children implement parents: DEV -> OPS -> PRD

**Note:** The exact ID syntax (prefixes, patterns) and hierarchy rules are
configurable per project via `.elspais.toml`. Use `get_workspace_info()` to
see the current project's configuration including the ID prefix and pattern.

## Common Patterns

**Understanding a requirement:**
1. get_requirement("REQ-p00001") for details and assertions
2. get_hierarchy("REQ-p00001") to see where it fits

**Finding related requirements:**
1. search("authentication") to find by keyword
2. get_hierarchy() on results to navigate relationships

**Checking project health:**
1. get_graph_status() for orphans/broken refs
2. get_project_summary() for coverage gaps

**After editing spec files:**
1. refresh_graph() to rebuild
2. get_graph_status() to verify health
"""


# ─────────────────────────────────────────────────────────────────────────────
# MCP Server Factory
# ─────────────────────────────────────────────────────────────────────────────


def create_server(
    graph: TraceGraph | None = None,
    working_dir: Path | None = None,
) -> FastMCP:
    """Create the MCP server with all tools registered.

    Args:
        graph: Optional pre-built graph (for testing).
        working_dir: Working directory for graph building.

    Returns:
        FastMCP server instance.
    """
    if not MCP_AVAILABLE:
        raise ImportError("MCP dependencies not installed. Install with: pip install elspais[mcp]")

    # Initialize working directory
    if working_dir is None:
        working_dir = Path.cwd()

    # Build initial graph if not provided
    if graph is None:
        graph = build_graph(repo_root=working_dir)

    # Create server with instructions for AI agents (REQ-d00065)
    mcp = FastMCP("elspais", instructions=MCP_SERVER_INSTRUCTIONS)

    # Store graph in closure for tools
    _state = {"graph": graph, "working_dir": working_dir}

    # ─────────────────────────────────────────────────────────────────────
    # Register Tools
    # ─────────────────────────────────────────────────────────────────────

    @mcp.tool()
    def get_graph_status() -> dict[str, Any]:
        """Get current graph status.

        Returns node counts by kind, root count, and detection flags.
        Use this to check graph health and staleness.
        """
        return _get_graph_status(_state["graph"])

    @mcp.tool()
    def refresh_graph(full: bool = False) -> dict[str, Any]:
        """Force graph rebuild from spec files.

        Args:
            full: If True, clear all caches before rebuild.

        Returns:
            Success status and new node count.
        """
        result, new_graph = _refresh_graph(_state["working_dir"], full=full)
        _state["graph"] = new_graph
        return result

    @mcp.tool()
    def search(
        query: str,
        field: str = "all",
        regex: bool = False,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Search requirements by ID, title, or content.

        Args:
            query: Search string or regex pattern.
            field: Field to search: 'id', 'title', 'body', or 'all'.
            regex: If True, treat query as regex pattern.
            limit: Maximum results to return (default 50).

        Returns:
            List of matching requirement summaries.
        """
        return _search(_state["graph"], query, field, regex, limit)

    @mcp.tool()
    def get_requirement(req_id: str) -> dict[str, Any]:
        """Get full details for a single requirement.

        Args:
            req_id: The requirement ID (e.g., 'REQ-p00001').

        Returns:
            Requirement details including assertions and relationships.
        """
        return _get_requirement(_state["graph"], req_id)

    @mcp.tool()
    def get_hierarchy(req_id: str) -> dict[str, Any]:
        """Get requirement hierarchy (ancestors and children).

        Args:
            req_id: The requirement ID.

        Returns:
            Ancestors (walking up to roots) and direct children.
        """
        return _get_hierarchy(_state["graph"], req_id)

    # ─────────────────────────────────────────────────────────────────────
    # Workspace Context Tools (REQ-o00061)
    # ─────────────────────────────────────────────────────────────────────

    @mcp.tool()
    def get_workspace_info() -> dict[str, Any]:
        """Get information about the current workspace.

        Returns repository path, project name, and configuration summary.
        Use this to understand what project you're working with.

        Returns:
            Workspace information including repo path, project name, and config.
        """
        return _get_workspace_info(_state["working_dir"])

    @mcp.tool()
    def get_project_summary() -> dict[str, Any]:
        """Get summary statistics for the project.

        Returns requirement counts by level (PRD/OPS/DEV), coverage statistics,
        and change metrics (uncommitted, branch changed).

        Returns:
            Project summary with counts, coverage, and change metrics.
        """
        return _get_project_summary(_state["graph"], _state["working_dir"])

    return mcp


def run_server(
    working_dir: Path | None = None,
    transport: str = "stdio",
) -> None:
    """Run the MCP server.

    Args:
        working_dir: Working directory for graph building.
        transport: Transport type ('stdio' or 'sse').
    """
    mcp = create_server(working_dir=working_dir)
    mcp.run(transport=transport)
