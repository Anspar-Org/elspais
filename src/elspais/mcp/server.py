# Implements: REQ-o00060-A, REQ-o00060-B, REQ-o00060-C, REQ-o00060-D, REQ-o00060-E, REQ-o00060-F
# Implements: REQ-o00061-A, REQ-o00061-B, REQ-o00061-C, REQ-o00061-D
# Implements: REQ-o00062-A, REQ-o00062-B, REQ-o00062-C, REQ-o00062-D
# Implements: REQ-o00062-E, REQ-o00062-F, REQ-o00062-G
# Implements: REQ-o00063-A, REQ-o00063-B, REQ-o00063-C, REQ-o00063-D, REQ-o00063-E, REQ-o00063-F
# Implements: REQ-o00064-A, REQ-o00064-B, REQ-o00064-C, REQ-o00064-D, REQ-o00064-E
# Implements: REQ-d00060-A, REQ-d00060-B, REQ-d00060-C, REQ-d00060-D, REQ-d00060-E
# Implements: REQ-d00061-A, REQ-d00061-B, REQ-d00061-C, REQ-d00061-D, REQ-d00061-E
# Implements: REQ-d00062-A, REQ-d00062-B, REQ-d00062-C, REQ-d00062-D
# Implements: REQ-d00062-E, REQ-d00062-F
# Implements: REQ-d00063-A, REQ-d00063-B, REQ-d00063-C, REQ-d00063-D, REQ-d00063-E
# Implements: REQ-d00064-A, REQ-d00064-B, REQ-d00064-C, REQ-d00064-D, REQ-d00064-E
# Implements: REQ-d00065-A, REQ-d00065-B, REQ-d00065-C, REQ-d00065-D, REQ-d00065-E
# Implements: REQ-d00066-A, REQ-d00066-B, REQ-d00066-C, REQ-d00066-D
# Implements: REQ-d00066-E, REQ-d00066-F, REQ-d00066-G
# Implements: REQ-d00067-A, REQ-d00067-B, REQ-d00067-C, REQ-d00067-D
# Implements: REQ-d00067-E, REQ-d00067-F
# Implements: REQ-d00068-A, REQ-d00068-B, REQ-d00068-C, REQ-d00068-D
# Implements: REQ-d00068-E, REQ-d00068-F
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
from elspais.graph.mutations import MutationEntry
from elspais.graph.relations import EdgeKind

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


def _serialize_mutation_entry(entry: MutationEntry) -> dict[str, Any]:
    """Serialize a MutationEntry to dict format.

    REQ-o00062-E: Returns MutationEntry for audit trail.
    """
    return {
        "id": entry.id,
        "operation": entry.operation,
        "target_id": entry.target_id,
        "before_state": entry.before_state,
        "after_state": entry.after_state,
        "affects_hash": entry.affects_hash,
        "timestamp": entry.timestamp.isoformat(),
    }


def _serialize_broken_reference(ref: Any) -> dict[str, Any]:
    """Serialize a BrokenReference to dict format."""
    return {
        "source_id": ref.source_id,
        "target_id": ref.target_id,
        "edge_kind": str(ref.edge_kind) if hasattr(ref.edge_kind, "value") else ref.edge_kind,
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
    REQ-d00061-B: Supports field parameter (id, title, body, keywords, all).
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

        if not match and field in ("keywords", "all"):
            # Search in keywords field
            keywords = node.get_field("keywords", [])
            for keyword in keywords:
                if regex:
                    if pattern.search(keyword):
                        match = True
                        break
                else:
                    if query_lower in keyword.lower():
                        match = True
                        break

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
        "broken_reference_count": len(graph.broken_references()),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Mutation Tool Functions (REQ-o00062)
# ─────────────────────────────────────────────────────────────────────────────


def _mutate_rename_node(graph: TraceGraph, old_id: str, new_id: str) -> dict[str, Any]:
    """Rename a node.

    REQ-d00065-A: Delegates to graph.rename_node().
    REQ-o00062-E: Returns MutationEntry for audit.
    """
    try:
        entry = graph.rename_node(old_id, new_id)
        return {
            "success": True,
            "mutation": _serialize_mutation_entry(entry),
            "message": f"Renamed {old_id} to {new_id}",
        }
    except (ValueError, KeyError) as e:
        return {"success": False, "error": str(e)}


def _mutate_update_title(graph: TraceGraph, node_id: str, new_title: str) -> dict[str, Any]:
    """Update requirement title.

    REQ-d00065-D: Only parameter validation and delegation.
    REQ-o00062-E: Returns MutationEntry for audit.
    """
    try:
        entry = graph.update_title(node_id, new_title)
        return {
            "success": True,
            "mutation": _serialize_mutation_entry(entry),
            "message": f"Updated title of {node_id}",
        }
    except (ValueError, KeyError) as e:
        return {"success": False, "error": str(e)}


def _mutate_change_status(graph: TraceGraph, node_id: str, new_status: str) -> dict[str, Any]:
    """Change requirement status.

    REQ-d00065-D: Only parameter validation and delegation.
    REQ-o00062-E: Returns MutationEntry for audit.
    """
    try:
        entry = graph.change_status(node_id, new_status)
        return {
            "success": True,
            "mutation": _serialize_mutation_entry(entry),
            "message": f"Changed status of {node_id} to {new_status}",
        }
    except (ValueError, KeyError) as e:
        return {"success": False, "error": str(e)}


def _mutate_add_requirement(
    graph: TraceGraph,
    req_id: str,
    title: str,
    level: str,
    status: str = "Draft",
    parent_id: str | None = None,
    edge_kind: str | None = None,
) -> dict[str, Any]:
    """Add a new requirement.

    REQ-d00065-B: Delegates to graph.add_requirement().
    REQ-o00062-E: Returns MutationEntry for audit.
    """
    try:
        # Convert edge_kind string to EdgeKind enum if provided
        edge_kind_enum = None
        if edge_kind:
            edge_kind_enum = EdgeKind[edge_kind.upper()]

        entry = graph.add_requirement(
            req_id=req_id,
            title=title,
            level=level,
            status=status,
            parent_id=parent_id,
            edge_kind=edge_kind_enum,
        )
        return {
            "success": True,
            "mutation": _serialize_mutation_entry(entry),
            "message": f"Added requirement {req_id}",
        }
    except (ValueError, KeyError) as e:
        return {"success": False, "error": str(e)}


def _mutate_delete_requirement(
    graph: TraceGraph, node_id: str, confirm: bool = False
) -> dict[str, Any]:
    """Delete a requirement.

    REQ-d00065-C: Calls graph.delete_requirement() only if confirm=True.
    REQ-o00062-F: Requires confirm=True for destructive operations.
    REQ-o00062-E: Returns MutationEntry for audit.
    """
    if not confirm:
        return {
            "success": False,
            "error": "Destructive operation requires confirm=True",
        }

    try:
        entry = graph.delete_requirement(node_id)
        return {
            "success": True,
            "mutation": _serialize_mutation_entry(entry),
            "message": f"Deleted requirement {node_id}",
        }
    except (ValueError, KeyError) as e:
        return {"success": False, "error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# Assertion Mutation Functions (REQ-o00062-B)
# ─────────────────────────────────────────────────────────────────────────────


def _mutate_add_assertion(graph: TraceGraph, req_id: str, label: str, text: str) -> dict[str, Any]:
    """Add assertion to requirement.

    REQ-d00065-D: Only parameter validation and delegation.
    REQ-o00062-E: Returns MutationEntry for audit.
    """
    try:
        entry = graph.add_assertion(req_id, label, text)
        return {
            "success": True,
            "mutation": _serialize_mutation_entry(entry),
            "message": f"Added assertion {req_id}-{label}",
        }
    except (ValueError, KeyError) as e:
        return {"success": False, "error": str(e)}


def _mutate_update_assertion(graph: TraceGraph, assertion_id: str, new_text: str) -> dict[str, Any]:
    """Update assertion text.

    REQ-d00065-D: Only parameter validation and delegation.
    REQ-o00062-E: Returns MutationEntry for audit.
    """
    try:
        entry = graph.update_assertion(assertion_id, new_text)
        return {
            "success": True,
            "mutation": _serialize_mutation_entry(entry),
            "message": f"Updated assertion {assertion_id}",
        }
    except (ValueError, KeyError) as e:
        return {"success": False, "error": str(e)}


def _mutate_delete_assertion(
    graph: TraceGraph,
    assertion_id: str,
    compact: bool = True,
    confirm: bool = False,
) -> dict[str, Any]:
    """Delete assertion.

    REQ-o00062-F: Requires confirm=True for destructive operations.
    REQ-o00062-E: Returns MutationEntry for audit.
    """
    if not confirm:
        return {
            "success": False,
            "error": "Destructive operation requires confirm=True",
        }

    try:
        entry = graph.delete_assertion(assertion_id, compact=compact)
        return {
            "success": True,
            "mutation": _serialize_mutation_entry(entry),
            "message": f"Deleted assertion {assertion_id}",
        }
    except (ValueError, KeyError) as e:
        return {"success": False, "error": str(e)}


def _mutate_rename_assertion(graph: TraceGraph, old_id: str, new_label: str) -> dict[str, Any]:
    """Rename assertion label.

    REQ-d00065-D: Only parameter validation and delegation.
    REQ-o00062-E: Returns MutationEntry for audit.
    """
    try:
        entry = graph.rename_assertion(old_id, new_label)
        return {
            "success": True,
            "mutation": _serialize_mutation_entry(entry),
            "message": f"Renamed assertion {old_id} to new label {new_label}",
        }
    except (ValueError, KeyError) as e:
        return {"success": False, "error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# Edge Mutation Functions (REQ-o00062-C)
# ─────────────────────────────────────────────────────────────────────────────


def _mutate_add_edge(
    graph: TraceGraph,
    source_id: str,
    target_id: str,
    edge_kind: str,
    assertion_targets: list[str] | None = None,
) -> dict[str, Any]:
    """Add an edge between nodes.

    REQ-d00065-D: Only parameter validation and delegation.
    REQ-o00062-E: Returns MutationEntry for audit.
    """
    try:
        edge_kind_enum = EdgeKind[edge_kind.upper()]
        entry = graph.add_edge(
            source_id=source_id,
            target_id=target_id,
            edge_kind=edge_kind_enum,
            assertion_targets=assertion_targets,
        )
        return {
            "success": True,
            "mutation": _serialize_mutation_entry(entry),
            "message": f"Added edge {source_id} --[{edge_kind}]--> {target_id}",
        }
    except (ValueError, KeyError) as e:
        return {"success": False, "error": str(e)}


def _mutate_change_edge_kind(
    graph: TraceGraph,
    source_id: str,
    target_id: str,
    new_kind: str,
) -> dict[str, Any]:
    """Change edge type.

    REQ-d00065-D: Only parameter validation and delegation.
    REQ-o00062-E: Returns MutationEntry for audit.
    """
    try:
        new_kind_enum = EdgeKind[new_kind.upper()]
        entry = graph.change_edge_kind(source_id, target_id, new_kind_enum)
        return {
            "success": True,
            "mutation": _serialize_mutation_entry(entry),
            "message": f"Changed edge {source_id} -> {target_id} to {new_kind}",
        }
    except (ValueError, KeyError) as e:
        return {"success": False, "error": str(e)}


def _mutate_delete_edge(
    graph: TraceGraph,
    source_id: str,
    target_id: str,
    confirm: bool = False,
) -> dict[str, Any]:
    """Delete an edge.

    REQ-o00062-F: Requires confirm=True for destructive operations.
    REQ-o00062-E: Returns MutationEntry for audit.
    """
    if not confirm:
        return {
            "success": False,
            "error": "Destructive operation requires confirm=True",
        }

    try:
        entry = graph.delete_edge(source_id, target_id)
        return {
            "success": True,
            "mutation": _serialize_mutation_entry(entry),
            "message": f"Deleted edge {source_id} -> {target_id}",
        }
    except (ValueError, KeyError) as e:
        return {"success": False, "error": str(e)}


def _mutate_fix_broken_reference(
    graph: TraceGraph,
    source_id: str,
    old_target_id: str,
    new_target_id: str,
) -> dict[str, Any]:
    """Fix a broken reference by redirecting to a valid target.

    REQ-d00065-D: Only parameter validation and delegation.
    REQ-o00062-E: Returns MutationEntry for audit.
    """
    try:
        entry = graph.fix_broken_reference(source_id, old_target_id, new_target_id)
        return {
            "success": True,
            "mutation": _serialize_mutation_entry(entry),
            "message": f"Fixed reference {source_id}: {old_target_id} -> {new_target_id}",
        }
    except (ValueError, KeyError) as e:
        return {"success": False, "error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# Undo Operations (REQ-o00062-G)
# ─────────────────────────────────────────────────────────────────────────────


def _undo_last_mutation(graph: TraceGraph) -> dict[str, Any]:
    """Undo the most recent mutation.

    REQ-o00062-G: Reverses mutations using graph.undo_last().
    """
    entry = graph.undo_last()
    if entry is None:
        return {"success": False, "error": "No mutations to undo"}

    return {
        "success": True,
        "mutation": _serialize_mutation_entry(entry),
        "message": f"Undid {entry.operation} on {entry.target_id}",
    }


def _undo_to_mutation(graph: TraceGraph, mutation_id: str) -> dict[str, Any]:
    """Undo all mutations back to a specific point.

    REQ-o00062-G: Reverses mutations using graph.undo_to().
    """
    try:
        entries = graph.undo_to(mutation_id)
        return {
            "success": True,
            "mutations_undone": len(entries),
            "mutations": [_serialize_mutation_entry(e) for e in entries],
            "message": f"Undid {len(entries)} mutations",
        }
    except (ValueError, KeyError) as e:
        return {"success": False, "error": str(e)}


def _get_mutation_log(graph: TraceGraph, limit: int = 50) -> dict[str, Any]:
    """Get mutation history.

    Returns the most recent mutations from the log.
    """
    mutations = []
    for entry in graph.mutation_log.iter_entries():
        mutations.append(_serialize_mutation_entry(entry))
        if len(mutations) >= limit:
            break

    return {
        "mutations": mutations,
        "count": len(mutations),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Inspection Functions
# ─────────────────────────────────────────────────────────────────────────────


def _get_orphaned_nodes(graph: TraceGraph) -> dict[str, Any]:
    """Get all orphaned nodes (nodes with no parents).

    Returns nodes that have been orphaned due to edge deletions.
    """
    orphans = []
    for node in graph.orphaned_nodes():
        if node.kind == NodeKind.REQUIREMENT:
            orphans.append(_serialize_requirement_summary(node))

    return {
        "orphans": orphans,
        "count": len(orphans),
    }


def _get_broken_references(graph: TraceGraph) -> dict[str, Any]:
    """Get all broken references.

    Returns edges that point to non-existent nodes.
    """
    refs = [_serialize_broken_reference(ref) for ref in graph.broken_references()]

    return {
        "broken_references": refs,
        "count": len(refs),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Keyword Search Tools (Phase 4)
# ─────────────────────────────────────────────────────────────────────────────


def _find_by_keywords(
    graph: TraceGraph,
    keywords: list[str],
    match_all: bool = True,
) -> dict[str, Any]:
    """Find requirements containing specified keywords.

    Args:
        graph: The TraceGraph to search.
        keywords: List of keywords to search for.
        match_all: If True, node must contain ALL keywords (AND).
                   If False, node must contain ANY keyword (OR).

    Returns:
        Dict with 'success', 'results', and 'count'.
    """
    from elspais.graph.annotators import find_by_keywords

    nodes = find_by_keywords(graph, keywords, match_all)
    results = [_serialize_requirement_summary(node) for node in nodes]

    return {
        "success": True,
        "results": results,
        "count": len(results),
    }


def _get_all_keywords(graph: TraceGraph) -> dict[str, Any]:
    """Get all unique keywords from the graph.

    Args:
        graph: The TraceGraph to scan.

    Returns:
        Dict with 'success', 'keywords', and 'count'.
    """
    from elspais.graph.annotators import collect_all_keywords

    keywords = collect_all_keywords(graph)

    return {
        "success": True,
        "keywords": keywords,
        "count": len(keywords),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Test Coverage Tools (REQ-o00064)
# ─────────────────────────────────────────────────────────────────────────────


def _get_test_coverage(graph: TraceGraph, req_id: str) -> dict[str, Any]:
    """Get test coverage information for a requirement.

    REQ-d00066-A: SHALL accept req_id parameter identifying the target requirement.
    REQ-d00066-B: SHALL return TEST nodes by finding edges targeting the requirement.
    REQ-d00066-C: SHALL return TEST_RESULT nodes linked to each TEST node.
    REQ-d00066-D: SHALL identify covered assertions via edge assertion_targets.
    REQ-d00066-E: SHALL return uncovered assertions as those with no incoming TEST edges.
    REQ-d00066-F: SHALL return coverage summary with percentage.
    REQ-d00066-G: SHALL use iterator-only API, not traverse full graph.

    Args:
        graph: The TraceGraph to query.
        req_id: The requirement ID to get coverage for.

    Returns:
        Dict with success, test_nodes, result_nodes, covered/uncovered assertions,
        and coverage statistics.
    """
    # REQ-d00066-A: Get requirement by ID
    node = graph.find_by_id(req_id)
    if node is None:
        return {"success": False, "error": f"Requirement {req_id} not found"}

    if node.kind != NodeKind.REQUIREMENT:
        return {"success": False, "error": f"{req_id} is not a requirement"}

    # Collect assertions from children
    assertions: list[tuple[str, str]] = []  # [(assertion_id, label), ...]

    for child in node.iter_children():
        if child.kind == NodeKind.ASSERTION:
            label = child.get_field("label", "")
            assertions.append((child.id, label))

    assertion_ids = [a[0] for a in assertions]

    # Track TEST nodes and covered assertions
    test_nodes: list[dict[str, Any]] = []
    result_nodes: list[dict[str, Any]] = []
    covered_assertion_ids: set[str] = set()
    seen_test_ids: set[str] = set()  # Deduplicate tests

    # REQ-d00066-B: Find TEST nodes via two patterns:
    # 1. Edges from requirement with assertion_targets (real graph pattern)
    # 2. Edges from assertions to TEST nodes (test fixture pattern)

    # Pattern 1: Edges from requirement (e.g., annotate_coverage pattern)
    for edge in node.iter_outgoing_edges():
        target = edge.target
        if target.kind != NodeKind.TEST:
            continue

        if target.id not in seen_test_ids:
            seen_test_ids.add(target.id)
            test_nodes.append(
                {
                    "id": target.id,
                    "label": target.get_label(),
                    "file": target.get_field("file", ""),
                    "name": target.get_field("name", ""),
                }
            )

            # REQ-d00066-C: Get TEST_RESULT children
            for child in target.iter_children():
                if child.kind == NodeKind.TEST_RESULT:
                    result_nodes.append(
                        {
                            "id": child.id,
                            "status": child.get_field("status", "unknown"),
                            "duration": child.get_field("duration", 0.0),
                            "test_id": target.id,
                        }
                    )

        # REQ-d00066-D: Track which assertions this test covers
        if edge.assertion_targets:
            for label in edge.assertion_targets:
                # Find assertion ID by label
                for aid, alabel in assertions:
                    if alabel == label:
                        covered_assertion_ids.add(aid)
                        break

    # Pattern 2: Edges from assertions (test fixture pattern)
    for assertion_id, _label in assertions:
        assertion_node = graph.find_by_id(assertion_id)
        if assertion_node is None:
            continue

        for edge in assertion_node.iter_outgoing_edges():
            target = edge.target
            if target.kind != NodeKind.TEST:
                continue

            # This assertion is covered by this test
            covered_assertion_ids.add(assertion_id)

            if target.id not in seen_test_ids:
                seen_test_ids.add(target.id)
                test_nodes.append(
                    {
                        "id": target.id,
                        "label": target.get_label(),
                        "file": target.get_field("file", ""),
                        "name": target.get_field("name", ""),
                    }
                )

                # REQ-d00066-C: Get TEST_RESULT children
                for child in target.iter_children():
                    if child.kind == NodeKind.TEST_RESULT:
                        result_nodes.append(
                            {
                                "id": child.id,
                                "status": child.get_field("status", "unknown"),
                                "duration": child.get_field("duration", 0.0),
                                "test_id": target.id,
                            }
                        )

    # REQ-d00066-E: Determine uncovered assertions
    covered_assertions = sorted(covered_assertion_ids)
    uncovered_assertions = sorted(set(assertion_ids) - covered_assertion_ids)

    # REQ-d00066-F: Calculate coverage percentage
    total = len(assertion_ids)
    covered_count = len(covered_assertions)
    coverage_pct = (covered_count / total * 100) if total > 0 else 0.0

    return {
        "success": True,
        "req_id": req_id,
        "test_nodes": test_nodes,
        "result_nodes": result_nodes,
        "covered_assertions": covered_assertions,
        "uncovered_assertions": uncovered_assertions,
        "total_assertions": total,
        "covered_count": covered_count,
        "coverage_pct": round(coverage_pct, 1),
    }


def _get_uncovered_assertions(
    graph: TraceGraph,
    req_id: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Find assertions lacking test coverage.

    REQ-d00067-A: SHALL accept optional req_id parameter; when None, scan all requirements.
    REQ-d00067-B: SHALL iterate assertions using nodes_by_kind(ASSERTION).
    REQ-d00067-C: SHALL check each assertion for incoming edges from TEST nodes.
    REQ-d00067-D: SHALL return assertion details: id, text, label, parent requirement context.
    REQ-d00067-E: SHALL return parent requirement id and title for context.
    REQ-d00067-F: SHALL limit results to prevent unbounded response sizes.

    Args:
        graph: The TraceGraph to query.
        req_id: Optional requirement ID to filter by. If None, scan all requirements.
        limit: Maximum number of results to return.

    Returns:
        Dict with success and list of uncovered assertions with parent context.
    """

    def _is_assertion_covered(assertion_node: Any) -> bool:
        """Check if an assertion has any TEST coverage."""
        # Check outgoing edges from assertion (test fixture pattern)
        for edge in assertion_node.iter_outgoing_edges():
            if edge.target.kind == NodeKind.TEST:
                return True

        # Check if parent requirement has edges to TEST with this assertion as target
        for parent in assertion_node.iter_parents():
            if parent.kind != NodeKind.REQUIREMENT:
                continue
            label = assertion_node.get_field("label", "")
            for edge in parent.iter_outgoing_edges():
                if edge.target.kind != NodeKind.TEST:
                    continue
                if edge.assertion_targets and label in edge.assertion_targets:
                    return True

        return False

    uncovered: list[dict[str, Any]] = []

    if req_id is not None:
        # REQ-d00067-B: Filter to specific requirement's assertions
        node = graph.find_by_id(req_id)
        if node is None:
            return {"success": False, "error": f"Requirement {req_id} not found"}

        if node.kind != NodeKind.REQUIREMENT:
            return {"success": False, "error": f"{req_id} is not a requirement"}

        for child in node.iter_children():
            if child.kind != NodeKind.ASSERTION:
                continue
            if _is_assertion_covered(child):
                continue

            # REQ-d00067-D, REQ-d00067-E: Include assertion and parent context
            uncovered.append(
                {
                    "id": child.id,
                    "label": child.get_field("label", ""),
                    "text": child.get_label(),
                    "parent_id": req_id,
                    "parent_title": node.get_label(),
                }
            )

            if len(uncovered) >= limit:
                break
    else:
        # REQ-d00067-A: Scan all assertions
        # Group by parent requirement for sorted output
        req_assertions: dict[str, list[Any]] = {}

        for node in graph.nodes_by_kind(NodeKind.ASSERTION):
            if _is_assertion_covered(node):
                continue

            # Find parent requirement
            parent_req = None
            for parent in node.iter_parents():
                if parent.kind == NodeKind.REQUIREMENT:
                    parent_req = parent
                    break

            if parent_req is None:
                continue

            if parent_req.id not in req_assertions:
                req_assertions[parent_req.id] = []
            req_assertions[parent_req.id].append((node, parent_req))

        # Sort by requirement ID and build output
        for req_id_key in sorted(req_assertions.keys()):
            for assertion_node, parent_req in req_assertions[req_id_key]:
                uncovered.append(
                    {
                        "id": assertion_node.id,
                        "label": assertion_node.get_field("label", ""),
                        "text": assertion_node.get_label(),
                        "parent_id": parent_req.id,
                        "parent_title": parent_req.get_label(),
                    }
                )

                if len(uncovered) >= limit:
                    break

            if len(uncovered) >= limit:
                break

    return {
        "success": True,
        "assertions": uncovered,
        "count": len(uncovered),
    }


def _find_assertions_by_keywords(
    graph: TraceGraph,
    keywords: list[str],
    match_all: bool = True,
) -> dict[str, Any]:
    """Find assertions containing specified keywords.

    REQ-d00068-A: SHALL accept keywords list parameter with search terms.
    REQ-d00068-B: SHALL accept match_all boolean; True requires all keywords.
    REQ-d00068-C: SHALL search assertion text (SHALL statement content).
    REQ-d00068-D: SHALL return assertion id, text, label, and parent context.
    REQ-d00068-E: SHALL perform case-insensitive matching by default.
    REQ-d00068-F: SHALL complement find_by_keywords() which searches requirements.

    Args:
        graph: The TraceGraph to query.
        keywords: List of keywords to search for.
        match_all: If True, assertion must contain ALL keywords (AND).
                   If False, assertion must contain ANY keyword (OR).

    Returns:
        Dict with success and list of matching assertions with parent context.
    """
    from elspais.graph.annotators import find_by_keywords

    # REQ-d00068-C: Use graph API to search assertion nodes by keyword
    # REQ-d00068-E: find_by_keywords handles case normalization
    nodes = find_by_keywords(graph, keywords, match_all, kind=NodeKind.ASSERTION)

    # REQ-d00068-D: Format results with parent context
    results: list[dict[str, Any]] = []
    for node in nodes:
        # Find parent requirement
        parent_req = None
        for parent in node.iter_parents():
            if parent.kind == NodeKind.REQUIREMENT:
                parent_req = parent
                break

        results.append(
            {
                "id": node.id,
                "label": node.get_field("label", ""),
                "text": node.get_label() or "",
                "parent_id": parent_req.id if parent_req else None,
                "parent_title": parent_req.get_label() if parent_req else None,
            }
        )

    return {
        "success": True,
        "assertions": results,
        "count": len(results),
    }


# ─────────────────────────────────────────────────────────────────────────────
# File Mutation Tools (REQ-o00063)
# ─────────────────────────────────────────────────────────────────────────────


def _change_reference_type(
    repo_root: Path,
    req_id: str,
    target_id: str,
    new_type: str,
    save_branch: bool = False,
) -> dict[str, Any]:
    """Change a reference type in a spec file (Implements -> Refines or vice versa).

    REQ-o00063-A: Modify Implements/Refines relationships in spec files.

    Args:
        repo_root: Repository root path.
        req_id: ID of the requirement to modify.
        target_id: ID of the target requirement being referenced.
        new_type: New reference type ('IMPLEMENTS' or 'REFINES').
        save_branch: If True, create a safety branch before modifying.

    Returns:
        Success status and optional safety_branch name.
    """
    from elspais.utilities.git import create_safety_branch

    # Normalize type
    new_type_lower = new_type.lower()
    if new_type_lower not in ("implements", "refines"):
        return {"success": False, "error": f"Invalid reference type: {new_type}"}

    # Find the spec file containing req_id
    spec_dir = repo_root / "spec"
    if not spec_dir.exists():
        return {"success": False, "error": "spec/ directory not found"}

    # Search for the requirement in spec files
    target_file = None
    for md_file in spec_dir.rglob("*.md"):
        content = md_file.read_text(encoding="utf-8")
        if f"## {req_id}:" in content or f"### {req_id}:" in content:
            target_file = md_file
            break

    if target_file is None:
        return {"success": False, "error": f"Requirement {req_id} not found in spec files"}

    content = target_file.read_text(encoding="utf-8")

    # Create safety branch if requested
    safety_branch = None
    if save_branch:
        branch_result = create_safety_branch(repo_root, req_id)
        if not branch_result["success"]:
            error_msg = branch_result.get("error", "Failed to create safety branch")
            return {"success": False, "error": error_msg}
        safety_branch = branch_result["branch_name"]

    # Find and replace the reference pattern
    # Match patterns like: **Implements**: REQ-p00001 or **Refines**: REQ-p00001
    old_patterns = [
        f"**Implements**: {target_id}",
        f"**Refines**: {target_id}",
        f"Implements: {target_id}",
        f"Refines: {target_id}",
    ]

    # Capitalize for display
    new_type_display = new_type_lower.capitalize()
    new_text = f"**{new_type_display}**: {target_id}"

    modified = False
    for pattern in old_patterns:
        if pattern in content:
            content = content.replace(pattern, new_text)
            modified = True
            break

    if not modified:
        return {"success": False, "error": f"Reference to {target_id} not found in {req_id}"}

    # Write the modified content
    target_file.write_text(content, encoding="utf-8")

    result: dict[str, Any] = {"success": True}
    if safety_branch:
        result["safety_branch"] = safety_branch

    return result


def _move_requirement(
    repo_root: Path,
    req_id: str,
    target_file: str,
    save_branch: bool = False,
) -> dict[str, Any]:
    """Move a requirement from one spec file to another.

    REQ-o00063-B: Relocate a requirement between spec files.

    Args:
        repo_root: Repository root path.
        req_id: ID of the requirement to move.
        target_file: Relative path to the target file.
        save_branch: If True, create a safety branch before modifying.

    Returns:
        Success status and optional safety_branch name.
    """
    from elspais.utilities.git import create_safety_branch

    spec_dir = repo_root / "spec"
    if not spec_dir.exists():
        return {"success": False, "error": "spec/ directory not found"}

    target_path = repo_root / target_file
    if not target_path.exists():
        return {"success": False, "error": f"Target file {target_file} not found"}

    # Find the source file containing req_id
    source_file = None
    for md_file in spec_dir.rglob("*.md"):
        content = md_file.read_text(encoding="utf-8")
        if f"## {req_id}:" in content or f"### {req_id}:" in content:
            source_file = md_file
            break

    if source_file is None:
        return {"success": False, "error": f"Requirement {req_id} not found in spec files"}

    if source_file == target_path:
        return {"success": False, "error": "Source and target files are the same"}

    # Create safety branch if requested
    safety_branch = None
    if save_branch:
        branch_result = create_safety_branch(repo_root, req_id)
        if not branch_result["success"]:
            error_msg = branch_result.get("error", "Failed to create safety branch")
            return {"success": False, "error": error_msg}
        safety_branch = branch_result["branch_name"]

    # Extract the requirement block from source
    source_content = source_file.read_text(encoding="utf-8")

    # Find the requirement block (from header to *End* marker or next ## header)
    # Pattern: ## REQ-xxx: Title ... *End* *Title* | **Hash**: xxx
    header_pattern = re.compile(
        rf"(^##+ {re.escape(req_id)}:.*?(?:\*End\*.*?(?:\*\*Hash\*\*:.*?\n|$)|(?=^##+ REQ-)))",
        re.MULTILINE | re.DOTALL,
    )

    match = header_pattern.search(source_content)
    if not match:
        return {"success": False, "error": f"Could not parse requirement block for {req_id}"}

    req_block = match.group(1)

    # Remove from source
    new_source_content = source_content[: match.start()] + source_content[match.end() :]
    # Clean up multiple consecutive blank lines
    from elspais.utilities.patterns import BLANK_LINE_CLEANUP_RE

    new_source_content = BLANK_LINE_CLEANUP_RE.sub("\n\n", new_source_content)

    # Append to target
    target_content = target_path.read_text(encoding="utf-8")
    if not target_content.endswith("\n\n"):
        if not target_content.endswith("\n"):
            target_content += "\n"
        target_content += "\n"
    target_content += "---\n\n" + req_block

    # Write both files
    source_file.write_text(new_source_content, encoding="utf-8")
    target_path.write_text(target_content, encoding="utf-8")

    result: dict[str, Any] = {"success": True}
    if safety_branch:
        result["safety_branch"] = safety_branch

    return result


def _restore_from_safety_branch(
    repo_root: Path,
    branch_name: str,
) -> dict[str, Any]:
    """Restore spec files from a safety branch.

    REQ-o00063-E: Revert file changes from a safety branch.

    Args:
        repo_root: Repository root path.
        branch_name: Name of the safety branch to restore from.

    Returns:
        Success status.
    """
    from elspais.utilities.git import restore_from_safety_branch

    return restore_from_safety_branch(repo_root, branch_name)


def _list_safety_branches_impl(repo_root: Path) -> dict[str, Any]:
    """List all safety branches.

    Args:
        repo_root: Repository root path.

    Returns:
        List of safety branch names.
    """
    from elspais.utilities.git import list_safety_branches

    branches = list_safety_branches(repo_root)
    return {"branches": branches, "count": len(branches)}


# ─────────────────────────────────────────────────────────────────────────────
# MCP Server Instructions
# ─────────────────────────────────────────────────────────────────────────────

MCP_SERVER_INSTRUCTIONS = """\
elspais MCP Server - AI-Driven Requirements Management

This server provides tools to navigate, analyze, and mutate a requirements traceability graph.
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

### Node Mutations (in-memory)
- `mutate_rename_node(old_id, new_id)` - Rename requirement
- `mutate_update_title(node_id, new_title)` - Change title
- `mutate_change_status(node_id, new_status)` - Change status
- `mutate_add_requirement(req_id, title, level, ...)` - Create requirement
- `mutate_delete_requirement(node_id, confirm=True)` - Delete requirement (requires confirm)

### Assertion Mutations (in-memory)
- `mutate_add_assertion(req_id, label, text)` - Add assertion
- `mutate_update_assertion(assertion_id, new_text)` - Update text
- `mutate_delete_assertion(assertion_id, confirm=True)` - Delete (requires confirm)
- `mutate_rename_assertion(old_id, new_label)` - Rename label

### Edge Mutations (in-memory)
- `mutate_add_edge(source_id, target_id, edge_kind)` - Add relationship
- `mutate_change_edge_kind(source_id, target_id, new_kind)` - Change type
- `mutate_delete_edge(source_id, target_id, confirm=True)` - Delete (requires confirm)
- `mutate_fix_broken_reference(source_id, old_target, new_target)` - Fix broken ref

### Undo & Inspection
- `undo_last_mutation()` - Undo most recent mutation
- `undo_to_mutation(mutation_id)` - Undo back to specific point
- `get_mutation_log(limit=50)` - View mutation history
- `get_orphaned_nodes()` - List orphaned nodes
- `get_broken_references()` - List broken references

### Test Coverage Analysis
- `get_test_coverage(req_id)` - Get TEST nodes and coverage stats for a requirement
  - Returns test_nodes, result_nodes, covered/uncovered assertions
  - Includes coverage percentage calculation
- `get_uncovered_assertions(req_id=None)` - Find assertions with no test coverage
  - When req_id is None, scans all requirements
  - Returns assertion details with parent requirement context
- `find_assertions_by_keywords(keywords, match_all=True)` - Search assertion text
  - match_all=True requires ALL keywords, False requires ANY
  - Complements find_by_keywords() which searches requirement titles

## Requirement Levels

Requirements follow a three-tier hierarchy:
- **PRD** (Product): High-level product requirements
- **OPS** (Operations): Operational/process requirements
- **DEV** (Development): Technical implementation requirements

Children implement parents: DEV -> OPS -> PRD

**Note:** The exact ID syntax (prefixes, patterns) and hierarchy rules are
configurable per project via `.elspais.toml`. Use `get_workspace_info()` to
see the current project's configuration including the ID prefix and pattern.

## Important: In-Memory vs File Mutations

Mutation tools modify the **in-memory graph only**. Changes are NOT persisted
to spec files automatically. This allows you to:
1. Draft changes and review them
2. Use undo to revert mistakes
3. Refresh the graph to discard all changes

To persist changes, use the file mutation tools:

### File Mutations (persistent)
- `change_reference_type(req_id, target_id, new_type, save_branch)` - Change Implements/Refines
- `move_requirement(req_id, target_file, save_branch)` - Move requirement to different file
- `restore_from_safety_branch(branch_name)` - Revert file changes
- `list_safety_branches()` - List available safety branches

Use `save_branch=True` to create a safety branch before modifications, allowing rollback.

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

**Drafting requirement changes:**
1. mutate_add_requirement() to create draft
2. mutate_add_assertion() to add assertions
3. get_mutation_log() to review changes
4. undo_last_mutation() if needed

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

    # ─────────────────────────────────────────────────────────────────────
    # Node Mutation Tools (REQ-o00062-A)
    # ─────────────────────────────────────────────────────────────────────

    @mcp.tool()
    def mutate_rename_node(old_id: str, new_id: str) -> dict[str, Any]:
        """Rename a requirement node.

        Updates the node's ID and all references to it.

        Args:
            old_id: Current node ID.
            new_id: New node ID.

        Returns:
            Success status and mutation entry for undo.
        """
        return _mutate_rename_node(_state["graph"], old_id, new_id)

    @mcp.tool()
    def mutate_update_title(node_id: str, new_title: str) -> dict[str, Any]:
        """Update a requirement's title.

        Does not affect the content hash.

        Args:
            node_id: The requirement ID.
            new_title: New title text.

        Returns:
            Success status and mutation entry for undo.
        """
        return _mutate_update_title(_state["graph"], node_id, new_title)

    @mcp.tool()
    def mutate_change_status(node_id: str, new_status: str) -> dict[str, Any]:
        """Change a requirement's status.

        Args:
            node_id: The requirement ID.
            new_status: New status (e.g., 'Active', 'Draft', 'Deprecated').

        Returns:
            Success status and mutation entry for undo.
        """
        return _mutate_change_status(_state["graph"], node_id, new_status)

    @mcp.tool()
    def mutate_add_requirement(
        req_id: str,
        title: str,
        level: str,
        status: str = "Draft",
        parent_id: str | None = None,
        edge_kind: str | None = None,
    ) -> dict[str, Any]:
        """Create a new requirement.

        Args:
            req_id: ID for the new requirement.
            title: Requirement title.
            level: Level (PRD, OPS, DEV).
            status: Initial status (default 'Draft').
            parent_id: Optional parent requirement to link to.
            edge_kind: Edge type if parent_id set ('IMPLEMENTS' or 'REFINES').

        Returns:
            Success status and mutation entry for undo.
        """
        return _mutate_add_requirement(
            _state["graph"], req_id, title, level, status, parent_id, edge_kind
        )

    @mcp.tool()
    def mutate_delete_requirement(node_id: str, confirm: bool = False) -> dict[str, Any]:
        """Delete a requirement.

        DESTRUCTIVE: Requires confirm=True to execute.

        Args:
            node_id: The requirement ID to delete.
            confirm: Must be True to confirm deletion.

        Returns:
            Success status and mutation entry for undo.
        """
        return _mutate_delete_requirement(_state["graph"], node_id, confirm)

    # ─────────────────────────────────────────────────────────────────────
    # Assertion Mutation Tools (REQ-o00062-B)
    # ─────────────────────────────────────────────────────────────────────

    @mcp.tool()
    def mutate_add_assertion(req_id: str, label: str, text: str) -> dict[str, Any]:
        """Add an assertion to a requirement.

        Args:
            req_id: Parent requirement ID.
            label: Assertion label (e.g., 'A', 'B', 'C').
            text: Assertion text (SHALL statement).

        Returns:
            Success status and mutation entry for undo.
        """
        return _mutate_add_assertion(_state["graph"], req_id, label, text)

    @mcp.tool()
    def mutate_update_assertion(assertion_id: str, new_text: str) -> dict[str, Any]:
        """Update an assertion's text.

        Recomputes the parent requirement's hash.

        Args:
            assertion_id: The assertion ID (e.g., 'REQ-p00001-A').
            new_text: New assertion text.

        Returns:
            Success status and mutation entry for undo.
        """
        return _mutate_update_assertion(_state["graph"], assertion_id, new_text)

    @mcp.tool()
    def mutate_delete_assertion(
        assertion_id: str, compact: bool = True, confirm: bool = False
    ) -> dict[str, Any]:
        """Delete an assertion.

        DESTRUCTIVE: Requires confirm=True to execute.

        Args:
            assertion_id: The assertion ID to delete.
            compact: If True, renumber subsequent assertions.
            confirm: Must be True to confirm deletion.

        Returns:
            Success status and mutation entry for undo.
        """
        return _mutate_delete_assertion(_state["graph"], assertion_id, compact, confirm)

    @mcp.tool()
    def mutate_rename_assertion(old_id: str, new_label: str) -> dict[str, Any]:
        """Rename an assertion's label.

        Args:
            old_id: Current assertion ID (e.g., 'REQ-p00001-A').
            new_label: New label (e.g., 'X').

        Returns:
            Success status and mutation entry for undo.
        """
        return _mutate_rename_assertion(_state["graph"], old_id, new_label)

    # ─────────────────────────────────────────────────────────────────────
    # Edge Mutation Tools (REQ-o00062-C)
    # ─────────────────────────────────────────────────────────────────────

    @mcp.tool()
    def mutate_add_edge(
        source_id: str,
        target_id: str,
        edge_kind: str,
        assertion_targets: list[str] | None = None,
    ) -> dict[str, Any]:
        """Add an edge between nodes.

        Args:
            source_id: Child node ID.
            target_id: Parent node ID.
            edge_kind: Relationship type ('IMPLEMENTS' or 'REFINES').
            assertion_targets: Optional list of assertion IDs to target.

        Returns:
            Success status and mutation entry for undo.
        """
        return _mutate_add_edge(_state["graph"], source_id, target_id, edge_kind, assertion_targets)

    @mcp.tool()
    def mutate_change_edge_kind(source_id: str, target_id: str, new_kind: str) -> dict[str, Any]:
        """Change an edge's relationship type.

        Args:
            source_id: Child node ID.
            target_id: Parent node ID.
            new_kind: New relationship type ('IMPLEMENTS' or 'REFINES').

        Returns:
            Success status and mutation entry for undo.
        """
        return _mutate_change_edge_kind(_state["graph"], source_id, target_id, new_kind)

    @mcp.tool()
    def mutate_delete_edge(source_id: str, target_id: str, confirm: bool = False) -> dict[str, Any]:
        """Delete an edge between nodes.

        DESTRUCTIVE: Requires confirm=True to execute.

        Args:
            source_id: Child node ID.
            target_id: Parent node ID.
            confirm: Must be True to confirm deletion.

        Returns:
            Success status and mutation entry for undo.
        """
        return _mutate_delete_edge(_state["graph"], source_id, target_id, confirm)

    @mcp.tool()
    def mutate_fix_broken_reference(
        source_id: str, old_target_id: str, new_target_id: str
    ) -> dict[str, Any]:
        """Fix a broken reference by redirecting to a valid target.

        Args:
            source_id: Node with the broken reference.
            old_target_id: Invalid target ID.
            new_target_id: Valid target ID to redirect to.

        Returns:
            Success status and mutation entry for undo.
        """
        return _mutate_fix_broken_reference(
            _state["graph"], source_id, old_target_id, new_target_id
        )

    # ─────────────────────────────────────────────────────────────────────
    # Undo & Inspection Tools (REQ-o00062-G)
    # ─────────────────────────────────────────────────────────────────────

    @mcp.tool()
    def undo_last_mutation() -> dict[str, Any]:
        """Undo the most recent mutation.

        Returns:
            Success status and the mutation that was undone.
        """
        return _undo_last_mutation(_state["graph"])

    @mcp.tool()
    def undo_to_mutation(mutation_id: str) -> dict[str, Any]:
        """Undo all mutations back to a specific point.

        Args:
            mutation_id: ID of the mutation to undo back to (inclusive).

        Returns:
            Success status and list of mutations undone.
        """
        return _undo_to_mutation(_state["graph"], mutation_id)

    @mcp.tool()
    def get_mutation_log(limit: int = 50) -> dict[str, Any]:
        """Get mutation history.

        Args:
            limit: Maximum number of mutations to return.

        Returns:
            List of recent mutations.
        """
        return _get_mutation_log(_state["graph"], limit)

    @mcp.tool()
    def get_orphaned_nodes() -> dict[str, Any]:
        """Get all orphaned nodes.

        Returns nodes that have no parent relationships.

        Returns:
            List of orphaned nodes with summaries.
        """
        return _get_orphaned_nodes(_state["graph"])

    @mcp.tool()
    def get_broken_references() -> dict[str, Any]:
        """Get all broken references.

        Returns edges that point to non-existent nodes.

        Returns:
            List of broken references.
        """
        return _get_broken_references(_state["graph"])

    # ─────────────────────────────────────────────────────────────────────
    # Keyword Search Tools (Phase 4)
    # ─────────────────────────────────────────────────────────────────────

    @mcp.tool()
    def find_by_keywords(
        keywords: list[str],
        match_all: bool = True,
    ) -> dict[str, Any]:
        """Find requirements containing specified keywords.

        Keywords are extracted from requirement titles and assertion text.

        Args:
            keywords: List of keywords to search for.
            match_all: If True, requirement must contain ALL keywords (AND).
                       If False, requirement must contain ANY keyword (OR).

        Returns:
            List of matching requirements with their summaries.
        """
        return _find_by_keywords(_state["graph"], keywords, match_all)

    @mcp.tool()
    def get_all_keywords() -> dict[str, Any]:
        """Get all unique keywords from the graph.

        Keywords are extracted from requirement titles and assertion text.
        Use this to discover available keywords for filtering.

        Returns:
            Sorted list of all unique keywords and total count.
        """
        return _get_all_keywords(_state["graph"])

    # ─────────────────────────────────────────────────────────────────────
    # Test Coverage Tools (REQ-o00064)
    # ─────────────────────────────────────────────────────────────────────

    @mcp.tool()
    def get_test_coverage(req_id: str) -> dict[str, Any]:
        """Get test coverage for a requirement.

        Returns TEST nodes that reference the requirement and their TEST_RESULT nodes.
        Identifies assertion coverage gaps (assertions with no tests).

        Args:
            req_id: The requirement ID to get coverage for.

        Returns:
            Test nodes, result nodes, covered/uncovered assertions, and coverage percentage.
        """
        return _get_test_coverage(_state["graph"], req_id)

    @mcp.tool()
    def get_uncovered_assertions(req_id: str | None = None) -> dict[str, Any]:
        """Get all assertions lacking test coverage.

        Returns assertions that have no TEST node references.
        Include parent requirement context in results.

        Args:
            req_id: Optional requirement ID. When None, scan all requirements.

        Returns:
            List of uncovered assertions with their parent requirement context.
        """
        return _get_uncovered_assertions(_state["graph"], req_id)

    @mcp.tool()
    def find_assertions_by_keywords(
        keywords: list[str],
        match_all: bool = True,
    ) -> dict[str, Any]:
        """Find assertions containing specified keywords.

        Search assertion text for matching keywords.
        Return assertion id, text, label, and parent requirement context.
        Complement to existing find_by_keywords() which finds requirements.

        Args:
            keywords: List of keywords to search for.
            match_all: If True, assertion must contain ALL keywords (AND).
                       If False, assertion must contain ANY keyword (OR).

        Returns:
            List of matching assertions with their summaries.
        """
        return _find_assertions_by_keywords(_state["graph"], keywords, match_all)

    # ─────────────────────────────────────────────────────────────────────
    # File Mutation Tools (REQ-o00063)
    # ─────────────────────────────────────────────────────────────────────

    @mcp.tool()
    def change_reference_type(
        req_id: str,
        target_id: str,
        new_type: str,
        save_branch: bool = False,
    ) -> dict[str, Any]:
        """Change a reference type in a spec file.

        Modifies Implements/Refines relationships in spec files on disk.
        Optionally creates a safety branch for rollback.

        Args:
            req_id: ID of the requirement to modify.
            target_id: ID of the target requirement being referenced.
            new_type: New reference type ('IMPLEMENTS' or 'REFINES').
            save_branch: If True, create a safety branch before modifying.

        Returns:
            Success status and optional safety_branch name.
        """
        result = _change_reference_type(
            _state["working_dir"], req_id, target_id, new_type, save_branch
        )
        # REQ-o00063-F: Refresh graph after file mutations
        if result.get("success"):
            new_result, new_graph = _refresh_graph(_state["working_dir"])
            _state["graph"] = new_graph
        return result

    @mcp.tool()
    def move_requirement(
        req_id: str,
        target_file: str,
        save_branch: bool = False,
    ) -> dict[str, Any]:
        """Move a requirement to a different spec file.

        Relocates a requirement from its current file to the target file.
        Optionally creates a safety branch for rollback.

        Args:
            req_id: ID of the requirement to move.
            target_file: Relative path to the target file (e.g., 'spec/other.md').
            save_branch: If True, create a safety branch before modifying.

        Returns:
            Success status and optional safety_branch name.
        """
        result = _move_requirement(_state["working_dir"], req_id, target_file, save_branch)
        # REQ-o00063-F: Refresh graph after file mutations
        if result.get("success"):
            new_result, new_graph = _refresh_graph(_state["working_dir"])
            _state["graph"] = new_graph
        return result

    @mcp.tool()
    def restore_from_safety_branch(branch_name: str) -> dict[str, Any]:
        """Restore spec files from a safety branch.

        Reverts file changes by restoring from a previously created safety branch.

        Args:
            branch_name: Name of the safety branch to restore from.

        Returns:
            Success status and list of files restored.
        """
        result = _restore_from_safety_branch(_state["working_dir"], branch_name)
        # REQ-o00063-F: Refresh graph after file mutations
        if result.get("success"):
            new_result, new_graph = _refresh_graph(_state["working_dir"])
            _state["graph"] = new_graph
        return result

    @mcp.tool()
    def list_safety_branches() -> dict[str, Any]:
        """List all safety branches.

        Returns available safety branches that can be used with restore_from_safety_branch.

        Returns:
            List of branch names and count.
        """
        return _list_safety_branches_impl(_state["working_dir"])

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
