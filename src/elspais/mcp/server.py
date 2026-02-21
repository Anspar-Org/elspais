# Implements: REQ-p00060-A, REQ-p00060-B, REQ-p00060-C, REQ-p00060-D, REQ-p00060-E
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
# Implements: REQ-p00006-B
# Implements: REQ-d00074-A, REQ-d00074-B, REQ-d00074-C, REQ-d00074-D
# Implements: REQ-o00067-A, REQ-o00067-B, REQ-o00067-C, REQ-o00067-D, REQ-o00067-E, REQ-o00067-F
# Implements: REQ-d00075-A, REQ-d00075-B, REQ-d00075-C, REQ-d00075-D
# Implements: REQ-d00075-E, REQ-d00075-F, REQ-d00075-G
# Implements: REQ-o00068-A, REQ-o00068-B, REQ-o00068-C, REQ-o00068-D
# Implements: REQ-o00068-E, REQ-o00068-F
# Implements: REQ-d00076-A, REQ-d00076-B, REQ-d00076-C, REQ-d00076-D
# Implements: REQ-d00076-E, REQ-d00076-F, REQ-d00076-G
"""elspais.mcp.server - MCP server implementation.

Creates and runs the MCP server exposing elspais functionality.

This is a pure interface layer - it consumes TraceGraph directly
without creating intermediate data structures (REQ-p00060-B).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

try:
    from mcp.server.fastmcp import FastMCP

    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    FastMCP = None

from elspais.config import find_canonical_root, find_config_file, get_config
from elspais.graph import NodeKind
from elspais.graph.annotators import (
    annotate_graph_git_state,
    count_by_coverage,
    count_by_git_status,
    count_by_level,
)
from elspais.graph.builder import TraceGraph
from elspais.graph.factory import build_graph
from elspais.graph.GraphNode import GraphNode
from elspais.graph.mutations import MutationEntry
from elspais.graph.relations import EdgeKind

# ─────────────────────────────────────────────────────────────────────────────
# Source path helper
# ─────────────────────────────────────────────────────────────────────────────


def _relative_source_path(node: Any, graph: TraceGraph) -> str:
    """Return the node's source file path, relative to repo root.

    Some parsers (notably CodeRefParser) store absolute paths in
    ``node.source.path``.  The REST layer and UI expect repo-relative
    paths so that ``/api/file-content?path=…`` can safely join them
    with the working directory.  This helper normalises the value.
    """
    if not node.source:
        return ""
    raw = node.source.path
    if not raw:
        return ""
    p = Path(raw)
    if p.is_absolute():
        try:
            return str(p.relative_to(graph.repo_root))
        except ValueError:
            return raw  # outside repo, keep as-is
    return raw


# ─────────────────────────────────────────────────────────────────────────────
# Shared coverage traversal iterator (REQ-d00066-B, REQ-d00066-D)
# ─────────────────────────────────────────────────────────────────────────────


def _iter_assertion_coverage(
    req_node: Any,
    kind_filter: NodeKind,
) -> Iterator[tuple[Any, list[str]]]:
    """Yield ``(node, labels)`` for each TEST or CODE node covering *req_node*.

    Two-phase edge traversal:

    Phase 1 — ``req_node.iter_outgoing_edges()``:
      * If ``assertion_targets`` is set → those labels
      * If absent → ALL assertion labels (indirect / blanket coverage)

    Phase 2 — For each ASSERTION child → ``iter_outgoing_edges()``:
      * Yields ``(node, [that_label])``

    The same node may be yielded more than once (e.g. via both phases).
    Callers are responsible for deduplication.
    """
    # Collect all assertion labels for the indirect-coverage case
    all_labels: list[str] = []
    assertion_children: list[tuple[Any, str]] = []  # (assertion_node, label)
    for child in req_node.iter_children():
        if child.kind == NodeKind.ASSERTION:
            label = child.get_field("label", "")
            all_labels.append(label)
            assertion_children.append((child, label))

    # Phase 1: REQ → kind_filter edges
    for edge in req_node.iter_outgoing_edges():
        target = edge.target
        if target.kind != kind_filter:
            continue
        if edge.assertion_targets:
            yield target, list(edge.assertion_targets)
        else:
            yield target, list(all_labels)

    # Phase 2: ASSERTION → kind_filter edges
    for assertion_node, label in assertion_children:
        for edge in assertion_node.iter_outgoing_edges():
            target = edge.target
            if target.kind != kind_filter:
                continue
            yield target, [label]


def _serialize_test_info(test_node: Any, graph: TraceGraph) -> dict[str, Any]:
    """Unified TEST-node serializer (superset of all consumers).

    Returns::

        {"id", "label", "file", "line", "name",
         "results": [{"id", "status", "duration", "file", "line"}]}
    """
    results: list[dict[str, Any]] = []
    for child in test_node.iter_children():
        if child.kind == NodeKind.TEST_RESULT:
            results.append(
                {
                    "id": child.id,
                    "status": child.get_field("status", "unknown"),
                    "duration": child.get_field("duration", 0.0),
                    "file": _relative_source_path(child, graph),
                    "line": child.source.line if child.source else 0,
                }
            )
    return {
        "id": test_node.id,
        "label": test_node.get_label(),
        "file": _relative_source_path(test_node, graph),
        "line": test_node.source.line if test_node.source else 0,
        "name": test_node.get_field("name", ""),
        "results": results,
    }


def _serialize_code_info(code_node: Any, graph: TraceGraph) -> dict[str, Any]:
    """Unified CODE-node serializer.

    Returns::

        {"id", "label", "file", "line"}
    """
    return {
        "id": code_node.id,
        "label": code_node.get_label(),
        "file": _relative_source_path(code_node, graph),
        "line": code_node.source.line if code_node.source else 0,
    }


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


def _serialize_node_generic(node: Any, graph: TraceGraph | None = None) -> dict[str, Any]:
    """Serialize any graph node to full format with kind-specific properties.

    Returns a common envelope (id, kind, title, source, parents, children,
    links, keywords) plus a ``properties`` dict with kind-specific fields.

    REQ-d00064-B: Returns all fields including assertions and edges.
    REQ-d00064-C: Reads from node.get_field() and node.get_label().
    """
    from elspais.graph.relations import EdgeKind as EK

    kind = node.kind

    # ── Common: children ──
    children = []
    for child in node.iter_children():
        if child.kind == NodeKind.ASSERTION:
            children.append(
                {
                    "kind": "assertion",
                    "id": child.id,
                    "label": child.get_field("label"),
                    "text": child.get_label(),
                    "line": child.source.line if child.source else None,
                }
            )
        elif child.kind == NodeKind.REMAINDER:
            children.append(
                {
                    "kind": "remainder",
                    "id": child.id,
                    "heading": child.get_field("heading"),
                    "text": child.get_field("text"),
                    "line": child.source.line if child.source else None,
                }
            )
        else:
            children.append(
                {
                    "kind": child.kind.value,
                    "id": child.id,
                    "title": child.get_label(),
                    "line": child.source.line if child.source else None,
                }
            )

    # ── Common: parents with edge_kind ──
    edge_map = {e.source.id: e.kind.value for e in node.iter_incoming_edges()}
    parents = []
    for parent in node.iter_parents():
        parents.append(
            {
                "id": parent.id,
                "kind": parent.kind.value,
                "title": parent.get_label(),
                "edge_kind": edge_map.get(parent.id, "unknown"),
            }
        )

    # ── Common: non-hierarchical links (ADDRESSES, VALIDATES, etc.) ──
    links = []
    for edge in node.iter_incoming_edges():
        if edge.kind not in (EK.IMPLEMENTS, EK.REFINES, EK.CONTAINS):
            links.append(
                {
                    "id": edge.source.id,
                    "kind": edge.source.kind.value,
                    "title": edge.source.get_label(),
                    "edge_kind": edge.kind.value,
                }
            )
    for edge in node.iter_outgoing_edges():
        if edge.kind not in (EK.IMPLEMENTS, EK.REFINES, EK.CONTAINS):
            links.append(
                {
                    "id": edge.target.id,
                    "kind": edge.target.kind.value,
                    "title": edge.target.get_label(),
                    "edge_kind": edge.kind.value,
                }
            )

    # ── Common: keywords ──
    keywords = node.get_field("keywords", []) or []

    # ── Kind-specific properties ──
    properties: dict[str, Any] = {}
    if kind == NodeKind.REQUIREMENT:
        properties = {
            "level": node.get_field("level"),
            "status": node.get_field("status"),
            "hash": node.get_field("hash"),
            "body_text": node.get_field("body_text"),
        }
    elif kind == NodeKind.USER_JOURNEY:
        descriptor = None
        m = re.match(r"JNY-(.+)-\d+$", node.id)
        if m:
            descriptor = m.group(1)
        properties = {
            "actor": node.get_field("actor", ""),
            "goal": node.get_field("goal", ""),
            "description": node.get_field("body", "") or node.get_field("description", ""),
            "descriptor": descriptor,
        }
    elif kind == NodeKind.TEST:
        properties = {
            "function_name": node.get_field("function_name", ""),
            "class_name": node.get_field("class_name", ""),
        }
    elif kind == NodeKind.TEST_RESULT:
        properties = {
            "status": node.get_field("status", ""),
            "duration": node.get_field("duration", 0.0),
            "message": node.get_field("message", ""),
            "classname": node.get_field("classname", ""),
        }
    elif kind == NodeKind.CODE:
        properties = {
            "function_name": node.get_field("function_name", ""),
            "class_name": node.get_field("class_name", ""),
            "function_line": node.get_field("function_line", 0),
        }
    elif kind == NodeKind.ASSERTION:
        properties = {
            "label": node.get_field("label"),
            "text": node.get_label(),
        }
    elif kind == NodeKind.REMAINDER:
        properties = {
            "heading": node.get_field("heading"),
            "text": node.get_field("text"),
        }

    return {
        "id": node.id,
        "kind": kind.value,
        "title": node.get_label(),
        "source": {
            "path": (
                _relative_source_path(node, graph)
                if graph
                else (node.source.path if node.source else None)
            ),
            "line": node.source.line if node.source else None,
        },
        "keywords": keywords,
        "parents": parents,
        "children": children,
        "links": links,
        "properties": properties,
    }


def _serialize_node_summary(node: Any) -> dict[str, Any]:
    """Serialize any graph node to lightweight summary format.

    Returns id, kind, title, plus kind-specific filterable properties.
    """
    kind = node.kind
    summary: dict[str, Any] = {
        "id": node.id,
        "kind": kind.value,
        "title": node.get_label(),
    }

    # Add filterable properties per kind
    if kind == NodeKind.REQUIREMENT:
        summary["level"] = node.get_field("level")
        summary["status"] = node.get_field("status")
    elif kind == NodeKind.USER_JOURNEY:
        summary["actor"] = node.get_field("actor", "")
        summary["goal"] = node.get_field("goal", "")
    elif kind == NodeKind.TEST_RESULT:
        summary["status"] = node.get_field("status", "")
    elif kind == NodeKind.TEST:
        summary["function_name"] = node.get_field("function_name", "")

    return summary


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
    canonical_root: Path | None = None,
) -> tuple[dict[str, Any], TraceGraph]:
    """Rebuild the graph from spec files.

    REQ-o00060-B: Forces graph rebuild.

    Args:
        repo_root: Repository root path.
        full: If True, clear all caches before rebuild.
        canonical_root: Canonical (non-worktree) repo root for cross-repo paths.

    Returns:
        Tuple of (result dict, new TraceGraph).
    """
    # Build fresh graph
    new_graph = build_graph(repo_root=repo_root, canonical_root=canonical_root)

    return {
        "success": True,
        "message": "Graph refreshed successfully",
        "node_count": new_graph.node_count(),
    }, new_graph


def _matches_query(
    node: GraphNode,
    field: str,
    regex: bool,
    compiled_pattern: re.Pattern[str] | None,
    query_lower: str | None,
) -> bool:
    """Check if a node matches a query against specified fields.

    Reusable matching logic shared by search() and scoped_search().

    REQ-d00061-B: Supports field parameter (id, title, body, keywords, all).
    REQ-d00061-C: Supports regex=True for regex matching.
    REQ-p00050-D: Single code path for query matching.

    Args:
        node: The graph node to check.
        field: Which field(s) to match: "id", "title", "body", "keywords", or "all".
        regex: Whether to use regex matching.
        compiled_pattern: Pre-compiled regex pattern (required when regex=True).
        query_lower: Lowercased query string (required when regex=False).
    """
    # Implements: REQ-d00061-B, REQ-d00061-C, REQ-p00050-D
    if field in ("id", "all"):
        if regex:
            if compiled_pattern.search(node.id):  # type: ignore[union-attr]
                return True
        else:
            if query_lower in node.id.lower():  # type: ignore[operator]
                return True

    if field in ("title", "all"):
        title = node.get_label() or ""
        if regex:
            if compiled_pattern.search(title):  # type: ignore[union-attr]
                return True
        else:
            if query_lower in title.lower():  # type: ignore[operator]
                return True

    if field in ("body", "all"):
        body = node.get_field("body_text", "")
        if body:
            if regex:
                if compiled_pattern.search(body):  # type: ignore[union-attr]
                    return True
            else:
                if query_lower in body.lower():  # type: ignore[operator]
                    return True

    if field in ("keywords", "all"):
        keywords = node.get_field("keywords", [])
        for keyword in keywords:
            if regex:
                if compiled_pattern.search(keyword):  # type: ignore[union-attr]
                    return True
            else:
                if query_lower in keyword.lower():  # type: ignore[operator]
                    return True

    return False


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
    compiled_pattern = None
    query_lower = None
    if regex:
        try:
            compiled_pattern = re.compile(query, re.IGNORECASE)
        except re.error:
            return []
    else:
        # Simple case-insensitive substring match
        query_lower = query.lower()

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        if _matches_query(node, field, regex, compiled_pattern, query_lower):
            results.append(_serialize_requirement_summary(node))
            if len(results) >= limit:
                break

    return results


def _minimize_requirement_set(
    graph: TraceGraph,
    req_ids: list[str],
    edge_kinds: set[EdgeKind],
) -> dict[str, Any]:
    """Prune a requirement set to its most-specific members.

    Removes ancestors already covered by more-specific descendants in the set.

    REQ-d00077-A: Resolves each ID via graph index, separating found/not_found.
    REQ-d00077-B: Walks UP via iter_outgoing_edges() filtered by edge_kinds.
    REQ-d00077-C: Prunes req R if another req C has R in its ancestor set.
    REQ-d00077-D: Records superseded_by for each pruned req.
    REQ-d00077-E: Returns {minimal_set, pruned, not_found, stats}.
    """
    # Implements: REQ-o00069-A, REQ-o00069-B, REQ-o00069-C, REQ-o00069-D, REQ-o00069-E
    # Implements: REQ-d00077-A, REQ-d00077-B, REQ-d00077-C, REQ-d00077-D, REQ-d00077-E

    # REQ-d00077-A: Resolve IDs, separating found/not_found
    found: dict[str, GraphNode] = {}
    not_found: list[str] = []
    for req_id in req_ids:
        node = graph.find_by_id(req_id)
        if node is not None and node.kind == NodeKind.REQUIREMENT:
            found[req_id] = node
        else:
            not_found.append(req_id)

    if not found:
        return {
            "minimal_set": [],
            "pruned": [],
            "not_found": not_found,
            "stats": {"input_count": len(req_ids), "minimal_count": 0, "pruned_count": 0},
        }

    found_ids = set(found.keys())

    # REQ-d00077-B: For each found req, collect transitive ancestors
    ancestor_map: dict[str, set[str]] = {}
    for req_id, node in found.items():
        ancestors: set[str] = set()
        visited: set[str] = set()
        stack = [node]
        while stack:
            current = stack.pop()
            for edge in current.iter_outgoing_edges():
                if edge.kind in edge_kinds:
                    parent = edge.target
                    if parent.id not in visited:
                        visited.add(parent.id)
                        ancestors.add(parent.id)
                        stack.append(parent)
        ancestor_map[req_id] = ancestors

    # REQ-d00077-C: Prune — R is redundant if another C in the set has R in its ancestors
    # REQ-d00077-D: Record superseded_by
    pruned_items: dict[str, list[str]] = {}  # pruned_id -> [superseding_ids]
    for req_id in found_ids:
        for other_id in found_ids:
            if other_id != req_id and req_id in ancestor_map[other_id]:
                if req_id not in pruned_items:
                    pruned_items[req_id] = []
                pruned_items[req_id].append(other_id)

    minimal_ids = found_ids - set(pruned_items.keys())

    # REQ-d00077-E: Build result
    minimal_set = [
        _serialize_requirement_summary(found[rid]) for rid in req_ids if rid in minimal_ids
    ]
    pruned = [
        {**_serialize_requirement_summary(found[rid]), "superseded_by": sorted(pruned_items[rid])}
        for rid in req_ids
        if rid in pruned_items
    ]

    return {
        "minimal_set": minimal_set,
        "pruned": pruned,
        "not_found": not_found,
        "stats": {
            "input_count": len(req_ids),
            "minimal_count": len(minimal_set),
            "pruned_count": len(pruned),
        },
    }


def _collect_scope_ids(
    graph: TraceGraph,
    scope_id: str,
    direction: str,
) -> set[str] | None:
    """Collect node IDs reachable from scope_id in the given direction.

    REQ-d00078-A: BFS via iter_children() for descendants, walk via iter_parents() for ancestors.
    REQ-d00078-B: Includes scope_id itself, uses visited set for DAG dedup.

    Returns:
        Set of reachable node IDs, or None if scope_id not found.
    """
    # Implements: REQ-d00078-A, REQ-d00078-B
    scope_node = graph.find_by_id(scope_id)
    if scope_node is None:
        return None

    visited: set[str] = {scope_id}
    stack: list[GraphNode] = [scope_node]

    while stack:
        current = stack.pop()
        if direction == "descendants":
            neighbors = current.iter_children()
        else:  # ancestors
            neighbors = current.iter_parents()
        for neighbor in neighbors:
            if neighbor.id not in visited:
                visited.add(neighbor.id)
                stack.append(neighbor)

    return visited


def _scoped_search(
    graph: TraceGraph,
    query: str,
    scope_id: str,
    direction: str = "descendants",
    field: str = "all",
    regex: bool = False,
    include_assertions: bool = False,
    limit: int = 50,
) -> dict[str, Any]:
    """Search requirements within a scoped subgraph.

    REQ-d00078-C: Iterates only REQUIREMENT nodes in the scope set.
    REQ-d00078-D: Checks assertion text when include_assertions=True.
    REQ-d00078-E: Returns results plus scope_id and direction metadata.
    REQ-o00070-E: Reuses _matches_query() for matching.
    """
    # Implements: REQ-o00070-A, REQ-o00070-B, REQ-o00070-C, REQ-o00070-D, REQ-o00070-E
    # Implements: REQ-d00078-C, REQ-d00078-D, REQ-d00078-E

    # REQ-o00070-D: Return error if scope_id not found
    scope_ids = _collect_scope_ids(graph, scope_id, direction)
    if scope_ids is None:
        return {"error": f"Scope node '{scope_id}' not found"}

    # Compile pattern for matching
    compiled_pattern = None
    query_lower = None
    if regex:
        try:
            compiled_pattern = re.compile(query, re.IGNORECASE)
        except re.error:
            return {"results": [], "scope_id": scope_id, "direction": direction}
    else:
        query_lower = query.lower()

    results: list[dict[str, Any]] = []

    # REQ-d00078-C: Iterate only REQUIREMENT nodes in scope
    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        if node.id not in scope_ids:
            continue

        matched = _matches_query(node, field, regex, compiled_pattern, query_lower)
        matched_assertions: list[dict[str, Any]] = []

        # REQ-d00078-D / REQ-o00070-C: Check assertion text
        if include_assertions:
            for child in node.iter_children():
                if child.kind == NodeKind.ASSERTION:
                    assertion_text = child.get_label() or ""
                    if regex:
                        if compiled_pattern and compiled_pattern.search(assertion_text):
                            matched_assertions.append(_serialize_assertion(child))
                    else:
                        if query_lower and query_lower in assertion_text.lower():
                            matched_assertions.append(_serialize_assertion(child))

        if matched or matched_assertions:
            entry = _serialize_requirement_summary(node)
            if matched_assertions:
                entry["matched_assertions"] = matched_assertions
            results.append(entry)
            if len(results) >= limit:
                break

    return {"results": results, "scope_id": scope_id, "direction": direction}


def _discover_requirements(
    graph: TraceGraph,
    query: str,
    scope_id: str,
    direction: str = "descendants",
    field: str = "all",
    regex: bool = False,
    include_assertions: bool = False,
    limit: int = 50,
    edge_kinds: set[EdgeKind] | None = None,
) -> dict[str, Any]:
    """Search within a subgraph and return only the most-specific matches.

    Chains _scoped_search() with _minimize_requirement_set() to prune
    ancestors from results.

    REQ-d00079-A: Calls _scoped_search(), extracts IDs, passes to _minimize_requirement_set().
    REQ-d00079-B: Returns {results, pruned, stats} with minimal-set items.
    REQ-d00079-C: Preserves matched_assertions metadata on minimal-set items.
    REQ-o00071-B: Chains scoped_search through minimize_requirement_set.
    """
    # Implements: REQ-o00071-A, REQ-o00071-B, REQ-o00071-C, REQ-o00071-D
    # Implements: REQ-d00079-A, REQ-d00079-B, REQ-d00079-C

    if edge_kinds is None:
        edge_kinds = {EdgeKind.IMPLEMENTS, EdgeKind.REFINES}

    # REQ-d00079-A: Get candidates via scoped_search
    scoped_result = _scoped_search(
        graph, query, scope_id, direction, field, regex, include_assertions, limit
    )

    # Propagate errors
    if "error" in scoped_result:
        return scoped_result

    candidates = scoped_result.get("results", [])
    if not candidates:
        return {
            "results": [],
            "pruned": [],
            "scope_id": scope_id,
            "direction": direction,
            "stats": {"candidate_count": 0, "minimal_count": 0, "pruned_count": 0},
        }

    # Extract IDs and call minimize
    candidate_ids = [r["id"] for r in candidates]
    minimize_result = _minimize_requirement_set(graph, candidate_ids, edge_kinds)

    # Build lookup for candidate data (preserves matched_assertions)
    candidate_lookup = {r["id"]: r for r in candidates}
    minimal_ids = {r["id"] for r in minimize_result["minimal_set"]}

    # REQ-d00079-C: Preserve matched_assertions from scoped_search
    results = [candidate_lookup[rid] for rid in candidate_ids if rid in minimal_ids]

    # Build pruned list with superseded_by from minimize
    pruned = minimize_result["pruned"]

    return {
        "results": results,
        "pruned": pruned,
        "scope_id": scope_id,
        "direction": direction,
        "stats": {
            "candidate_count": len(candidates),
            "minimal_count": len(results),
            "pruned_count": len(pruned),
        },
    }


def _get_node(graph: TraceGraph, node_id: str) -> dict[str, Any]:
    """Get any graph node by ID.

    Returns the generic node envelope with kind-specific properties.
    No kind restriction — any node kind is valid.

    Args:
        graph: The TraceGraph to query.
        node_id: The node ID to look up.

    Returns:
        Serialized node dict, or dict with 'error' key if not found.
    """
    node = graph.find_by_id(node_id)
    if node is None:
        return {"error": f"Node '{node_id}' not found"}
    return _serialize_node_generic(node, graph)


def _get_requirement(graph: TraceGraph, req_id: str) -> dict[str, Any]:
    """Get single requirement details.

    Thin wrapper around _get_node() with a kind == REQUIREMENT guard.
    Preserves the function signature used by ~15 tests and the MCP tool.

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

    return _serialize_node_generic(node, graph)


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


def _get_project_summary(
    graph: TraceGraph, working_dir: Path, config: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Get project summary statistics.

    REQ-o00061-B: Returns requirement counts by level, coverage statistics, and change metrics.
    REQ-o00061-C: Uses graph aggregate functions from annotators module.

    Args:
        graph: The TraceGraph to analyze.
        working_dir: The repository root directory.
        config: Optional config dict for deriving level keys.

    Returns:
        Project summary dict.
    """
    # Use aggregate functions from annotators (REQ-o00061-C)
    level_counts = count_by_level(graph, config=config)
    coverage_stats = count_by_coverage(graph)
    # Annotate git state before counting (idempotent, safe to call multiple times)
    annotate_graph_git_state(graph)
    change_metrics = count_by_git_status(graph)

    return {
        "requirements_by_level": level_counts,
        "coverage": coverage_stats,
        "changes": change_metrics,
        "total_nodes": graph.node_count(),
        "orphan_count": graph.orphan_count(),
        "broken_reference_count": len(graph.broken_references()),
    }


def _get_changed_requirements(graph: TraceGraph) -> dict[str, Any]:
    """Get requirements with git changes.

    Annotates the graph with git state, then filters for requirement nodes
    where any git flag is True.

    Args:
        graph: The TraceGraph to analyze.

    Returns:
        Dict with 'requirements' list and 'summary' counts.
    """
    annotate_graph_git_state(graph)

    changed: list[dict[str, Any]] = []
    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        is_uncommitted = node.get_metric("is_uncommitted", False)
        is_branch_changed = node.get_metric("is_branch_changed", False)
        is_moved = node.get_metric("is_moved", False)

        if is_uncommitted or is_branch_changed or is_moved:
            entry = _serialize_requirement_summary(node)
            entry["git_state"] = {
                "is_uncommitted": is_uncommitted,
                "is_untracked": node.get_metric("is_untracked", False),
                "is_modified": node.get_metric("is_modified", False),
                "is_branch_changed": is_branch_changed,
                "is_moved": is_moved,
                "is_new": node.get_metric("is_new", False),
            }
            entry["source"] = _relative_source_path(node, graph) or None
            changed.append(entry)

    summary = count_by_git_status(graph)

    return {
        "requirements": changed,
        "count": len(changed),
        "summary": summary,
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

    Returns nodes that have been orphaned — parentless nodes that are
    not roots. Includes all node kinds (REQUIREMENT, TEST, TEST_RESULT, CODE).
    """
    orphans: list[dict[str, Any]] = []
    by_kind: dict[str, list[dict[str, Any]]] = {}

    for node in graph.orphaned_nodes():
        if node.kind == NodeKind.REQUIREMENT:
            entry = _serialize_requirement_summary(node)
        else:
            entry = {
                "id": node.id,
                "kind": node.kind.value,
                "label": node.get_label(),
            }
            if node.source:
                entry["source"] = f"{node.source.path}:{node.source.line}"
        entry["kind"] = node.kind.value
        orphans.append(entry)

        kind_name = node.kind.value
        if kind_name not in by_kind:
            by_kind[kind_name] = []
        by_kind[kind_name].append(entry)

    return {
        "orphans": orphans,
        "count": len(orphans),
        "by_kind": {k: {"items": v, "count": len(v)} for k, v in by_kind.items()},
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
    kind: str | None = None,
) -> dict[str, Any]:
    """Find nodes containing specified keywords.

    Args:
        graph: The TraceGraph to search.
        keywords: List of keywords to search for.
        match_all: If True, node must contain ALL keywords (AND).
                   If False, node must contain ANY keyword (OR).
        kind: Optional NodeKind value string to filter by (e.g. "requirement").

    Returns:
        Dict with 'success', 'results', and 'count'.
    """
    from elspais.graph.annotators import find_by_keywords

    kind_enum = None
    if kind:
        try:
            kind_enum = NodeKind(kind)
        except ValueError:
            return {"success": False, "error": f"Unknown kind: {kind}", "results": [], "count": 0}

    nodes = find_by_keywords(graph, keywords, match_all, kind=kind_enum)
    results = [_serialize_node_summary(node) for node in nodes]

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


def _query_nodes(
    graph: TraceGraph,
    kind: str | None = None,
    keywords: list[str] | None = None,
    match_all: bool = True,
    filters: dict[str, str] | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Combined property + keyword filter query for any node kind.

    Starts with nodes filtered by kind (or all nodes), narrows by keywords
    using existing annotator infrastructure, then post-filters by property
    values.

    Args:
        graph: The TraceGraph to query.
        kind: Optional NodeKind value string (e.g. "requirement", "journey").
        keywords: Optional list of keywords to filter by.
        match_all: If True, node must contain ALL keywords.
        filters: Optional dict of property name → value for post-filtering.
        limit: Maximum results to return.

    Returns:
        Dict with 'results', 'count', and 'truncated' flag.
    """
    # 1. Start with nodes by kind (or all)
    kind_enum = None
    if kind:
        try:
            kind_enum = NodeKind(kind)
        except ValueError:
            return {"results": [], "count": 0, "truncated": False}
        candidates = list(graph.nodes_by_kind(kind_enum))
    else:
        candidates = list(graph.all_nodes())

    # 2. Keyword filter (if provided)
    if keywords:
        from elspais.graph.annotators import find_by_keywords

        keyword_ids = {n.id for n in find_by_keywords(graph, keywords, match_all, kind=kind_enum)}
        candidates = [n for n in candidates if n.id in keyword_ids]

    # 3. Property post-filters (known safe keys only)
    allowed_filter_keys = {"level", "status", "actor"}
    if filters:
        for key, value in filters.items():
            if key not in allowed_filter_keys:
                continue
            candidates = [
                n for n in candidates if (n.get_field(key, "") or "").upper() == value.upper()
            ]

    # 4. Serialize and limit
    total = len(candidates)
    results = [_serialize_node_summary(n) for n in candidates[:limit]]

    return {
        "results": results,
        "count": total,
        "truncated": total > limit,
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
    node = graph.find_by_id(req_id)
    if node is None:
        return {"success": False, "error": f"Requirement {req_id} not found"}

    if node.kind != NodeKind.REQUIREMENT:
        return {"success": False, "error": f"{req_id} is not a requirement"}

    # Collect assertions
    assertions: list[tuple[str, str]] = []
    for child in node.iter_children():
        if child.kind == NodeKind.ASSERTION:
            assertions.append((child.id, child.get_field("label", "")))

    assertion_ids = [a[0] for a in assertions]
    label_to_id = {label: aid for aid, label in assertions}

    # Deduplicated test serialization via shared iterator
    seen_test_ids: set[str] = set()
    test_nodes: list[dict[str, Any]] = []
    result_nodes: list[dict[str, Any]] = []
    covered_assertion_ids: set[str] = set()

    for test_node, labels in _iter_assertion_coverage(node, NodeKind.TEST):
        # Track covered assertions
        for label in labels:
            if label in label_to_id:
                covered_assertion_ids.add(label_to_id[label])

        if test_node.id in seen_test_ids:
            continue
        seen_test_ids.add(test_node.id)

        info = _serialize_test_info(test_node, graph)
        test_nodes.append(info)
        # Flatten results for MCP contract compatibility
        for r in info["results"]:
            result_nodes.append({**r, "test_id": info["id"]})

    covered_assertions = sorted(covered_assertion_ids)
    uncovered_assertions = sorted(set(assertion_ids) - covered_assertion_ids)

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


def _get_assertion_test_map(graph: TraceGraph, req_id: str) -> dict[str, Any]:
    """Build per-assertion test coverage map for a requirement.

    Returns a structure mapping each assertion label to its tests and their
    results, enabling the UI to show validation buttons per assertion.

    Uses ``_iter_assertion_coverage`` for the shared two-phase traversal
    and ``_serialize_test_info`` for the unified serializer.

    Args:
        graph: The TraceGraph to query.
        req_id: The requirement ID.

    Returns:
        Dict with per-assertion test lists, coverage stats.
    """
    node = graph.find_by_id(req_id)
    if node is None:
        return {"success": False, "error": f"Requirement {req_id} not found"}

    if node.kind != NodeKind.REQUIREMENT:
        return {"success": False, "error": f"{req_id} is not a requirement"}

    # Collect assertions
    assertions: list[tuple[str, str]] = []
    for child in node.iter_children():
        if child.kind == NodeKind.ASSERTION:
            assertions.append((child.id, child.get_field("label", "")))

    # Per-assertion buckets
    assertion_tests: dict[str, dict[str, Any]] = {}
    for aid, label in assertions:
        assertion_tests[label] = {"assertion_id": aid, "tests": []}

    seen_per_assertion: dict[str, set[str]] = {label: set() for _, label in assertions}

    for test_node, labels in _iter_assertion_coverage(node, NodeKind.TEST):
        info = _serialize_test_info(test_node, graph)
        for label in labels:
            if label not in assertion_tests:
                continue
            if test_node.id in seen_per_assertion[label]:
                continue
            seen_per_assertion[label].add(test_node.id)
            assertion_tests[label]["tests"].append(info)

    total = len(assertions)
    covered_count = sum(1 for label in assertion_tests if assertion_tests[label]["tests"])
    coverage_pct = (covered_count / total * 100) if total > 0 else 0.0

    return {
        "success": True,
        "req_id": req_id,
        "assertion_tests": assertion_tests,
        "total_assertions": total,
        "covered_count": covered_count,
        "coverage_pct": round(coverage_pct, 1),
    }


def _get_assertion_code_map(graph: TraceGraph, req_id: str) -> dict[str, Any]:
    """Build per-assertion code implementation map for a requirement.

    Returns a structure mapping each assertion label to its CODE nodes,
    enabling the UI to show "Implemented" buttons per assertion.

    Uses ``_iter_assertion_coverage`` for the shared two-phase traversal
    and ``_serialize_code_info`` for the unified serializer.

    Args:
        graph: The TraceGraph to query.
        req_id: The requirement ID.

    Returns:
        Dict with per-assertion code lists, coverage stats.
    """
    node = graph.find_by_id(req_id)
    if node is None:
        return {"success": False, "error": f"Requirement {req_id} not found"}

    if node.kind != NodeKind.REQUIREMENT:
        return {"success": False, "error": f"{req_id} is not a requirement"}

    # Collect assertions
    assertions: list[tuple[str, str]] = []
    for child in node.iter_children():
        if child.kind == NodeKind.ASSERTION:
            assertions.append((child.id, child.get_field("label", "")))

    # Per-assertion buckets
    assertion_code: dict[str, dict[str, Any]] = {}
    for aid, label in assertions:
        assertion_code[label] = {"assertion_id": aid, "code_refs": []}

    seen_per_assertion: dict[str, set[str]] = {label: set() for _, label in assertions}

    for code_node, labels in _iter_assertion_coverage(node, NodeKind.CODE):
        info = _serialize_code_info(code_node, graph)
        for label in labels:
            if label not in assertion_code:
                continue
            if code_node.id in seen_per_assertion[label]:
                continue
            seen_per_assertion[label].add(code_node.id)
            assertion_code[label]["code_refs"].append(info)

    total = len(assertions)
    covered_count = sum(1 for label in assertion_code if assertion_code[label]["code_refs"])
    coverage_pct = (covered_count / total * 100) if total > 0 else 0.0

    return {
        "success": True,
        "req_id": req_id,
        "assertion_code": assertion_code,
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

    Uses ``_iter_assertion_coverage`` to build the covered-labels set,
    which correctly handles indirect coverage (tests with no
    ``assertion_targets`` covering ALL assertions).

    Args:
        graph: The TraceGraph to query.
        req_id: Optional requirement ID to filter by. If None, scan all requirements.
        limit: Maximum number of results to return.

    Returns:
        Dict with success and list of uncovered assertions with parent context.
    """

    def _covered_labels_for_req(req_node: Any) -> set[str]:
        """Return the set of assertion labels covered by at least one TEST."""
        covered: set[str] = set()
        for _test_node, labels in _iter_assertion_coverage(req_node, NodeKind.TEST):
            covered.update(labels)
        return covered

    uncovered: list[dict[str, Any]] = []

    if req_id is not None:
        node = graph.find_by_id(req_id)
        if node is None:
            return {"success": False, "error": f"Requirement {req_id} not found"}

        if node.kind != NodeKind.REQUIREMENT:
            return {"success": False, "error": f"{req_id} is not a requirement"}

        covered = _covered_labels_for_req(node)

        for child in node.iter_children():
            if child.kind != NodeKind.ASSERTION:
                continue
            if child.get_field("label", "") in covered:
                continue

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
        # REQ-d00067-A: Scan all requirements, collect uncovered assertions
        req_assertions: dict[str, list[Any]] = {}

        for req_node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
            covered = _covered_labels_for_req(req_node)

            for child in req_node.iter_children():
                if child.kind != NodeKind.ASSERTION:
                    continue
                if child.get_field("label", "") in covered:
                    continue

                if req_node.id not in req_assertions:
                    req_assertions[req_node.id] = []
                req_assertions[req_node.id].append((child, req_node))

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
    Delegates core file I/O to ``utilities.spec_writer.change_reference_type``.

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
    from elspais.utilities.spec_writer import change_reference_type as _crt

    # Find the spec file containing req_id
    spec_dir = repo_root / "spec"
    if not spec_dir.exists():
        return {"success": False, "error": "spec/ directory not found"}

    target_file = None
    for md_file in spec_dir.rglob("*.md"):
        content = md_file.read_text(encoding="utf-8")
        if f"## {req_id}:" in content or f"### {req_id}:" in content:
            target_file = md_file
            break

    if target_file is None:
        return {"success": False, "error": f"Requirement {req_id} not found in spec files"}

    # Create safety branch if requested (REQ-o00063-D)
    safety_branch = None
    if save_branch:
        branch_result = create_safety_branch(repo_root, req_id)
        if not branch_result["success"]:
            error_msg = branch_result.get("error", "Failed to create safety branch")
            return {"success": False, "error": error_msg}
        safety_branch = branch_result["branch_name"]

    # Delegate to spec_writer for the actual file modification
    result = _crt(target_file, req_id, target_id, new_type)

    if result.get("success") and safety_branch:
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
    Delegates core file I/O to ``utilities.spec_writer.move_requirement``.

    Args:
        repo_root: Repository root path.
        req_id: ID of the requirement to move.
        target_file: Relative path to the target file.
        save_branch: If True, create a safety branch before modifying.

    Returns:
        Success status and optional safety_branch name.
    """
    from elspais.utilities.git import create_safety_branch
    from elspais.utilities.spec_writer import move_requirement as _move_req

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

    # Create safety branch if requested (REQ-o00063-D)
    safety_branch = None
    if save_branch:
        branch_result = create_safety_branch(repo_root, req_id)
        if not branch_result["success"]:
            error_msg = branch_result.get("error", "Failed to create safety branch")
            return {"success": False, "error": error_msg}
        safety_branch = branch_result["branch_name"]

    # Delegate to spec_writer for the actual file modification
    result = _move_req(source_file, target_path, req_id)

    if result.get("success") and safety_branch:
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
# Link Suggestion (REQ-d00074)
# ─────────────────────────────────────────────────────────────────────────────


def _suggest_links_impl(
    graph: TraceGraph,
    working_dir: Path,
    file_path: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Suggest requirement links for unlinked test nodes.

    REQ-d00074-A: Returns structured suggestions from the core engine.
    REQ-d00074-C: Delegates to core engine, no analysis logic here.
    """
    from elspais.graph.link_suggest import suggest_links

    suggestions = suggest_links(
        graph,
        working_dir,
        file_path=file_path,
        limit=limit,
    )
    return {
        "suggestions": [s.to_dict() for s in suggestions],
        "count": len(suggestions),
    }


def _apply_link_impl(
    state: dict[str, Any],
    file_path: str,
    line: int,
    requirement_id: str,
) -> dict[str, Any]:
    """Apply a link by inserting a # Implements: comment.

    REQ-d00074-B: Inserts comment and refreshes graph.
    REQ-d00074-D: Validates target requirement exists before modifying.
    """
    from elspais.graph.link_suggest import apply_link_to_file

    graph = state["graph"]
    working_dir = state["working_dir"]

    # Validate requirement exists
    target = graph.find_by_id(requirement_id)
    if target is None:
        return {
            "success": False,
            "error": f"Requirement '{requirement_id}' not found in graph",
        }

    abs_path = working_dir / file_path
    result = apply_link_to_file(abs_path, line, requirement_id)

    if result is None:
        return {
            "success": False,
            "error": f"Could not write to file: {file_path}",
        }

    # Refresh graph after file modification
    _, new_graph = _refresh_graph(working_dir, canonical_root=state.get("canonical_root"))
    state["graph"] = new_graph

    return {
        "success": True,
        "comment": result,
        "file": file_path,
        "line": line,
        "requirement_id": requirement_id,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Subtree Extraction (REQ-o00067, REQ-d00075)
# ─────────────────────────────────────────────────────────────────────────────

# Conservative kind defaults per root kind (REQ-d00075-F)
_SUBTREE_KIND_DEFAULTS: dict[NodeKind, set[NodeKind]] = {
    NodeKind.REQUIREMENT: {NodeKind.REQUIREMENT, NodeKind.ASSERTION},
    NodeKind.USER_JOURNEY: {NodeKind.USER_JOURNEY},
}


def _compute_coverage_summary(req_node: Any) -> dict[str, Any]:
    """Lightweight coverage summary reusing _iter_assertion_coverage().

    REQ-d00075-B: Returns {total, covered, pct}.
    """
    # Count total assertions
    total = 0
    for child in req_node.iter_children():
        if child.kind == NodeKind.ASSERTION:
            total += 1

    if total == 0:
        return {"total": 0, "covered": 0, "pct": 0.0}

    # Collect covered assertion labels from both TEST and CODE edges
    covered_labels: set[str] = set()
    for _node, labels in _iter_assertion_coverage(req_node, NodeKind.TEST):
        covered_labels.update(labels)
    for _node, labels in _iter_assertion_coverage(req_node, NodeKind.CODE):
        covered_labels.update(labels)

    covered = len(covered_labels)
    return {
        "total": total,
        "covered": covered,
        "pct": round(covered / total * 100, 1) if total > 0 else 0.0,
    }


def _collect_subtree(
    graph: TraceGraph,
    root_id: str,
    depth: int = 0,
    include_kinds: set[NodeKind] | None = None,
) -> list[tuple[Any, int]]:
    """BFS from root with depth tracking, kind filtering, DAG dedup.

    REQ-d00075-A: Uses node.iter_children() with visited set.
    REQ-o00067-A: BFS traversal from root.
    REQ-o00067-B: depth=0 means unlimited, depth=N limits to N levels.
    REQ-o00067-E: Deduplicates via visited set.

    Returns:
        List of (node, depth_level) tuples in BFS order.
    """
    root_node = graph.find_by_id(root_id)
    if root_node is None:
        return []

    # Determine kind filter (REQ-o00067-C, REQ-d00075-F)
    if include_kinds is None:
        include_kinds = _SUBTREE_KIND_DEFAULTS.get(
            root_node.kind,
            {root_node.kind},
        )
        # Always include ASSERTION when REQUIREMENT is present
        if NodeKind.REQUIREMENT in include_kinds:
            include_kinds = include_kinds | {NodeKind.ASSERTION}

    visited: set[str] = {root_id}
    result: list[tuple[Any, int]] = [(root_node, 0)]
    queue: list[tuple[Any, int]] = [(root_node, 0)]

    while queue:
        current, current_depth = queue.pop(0)

        # Depth limit: don't expand children beyond limit
        if depth > 0 and current_depth >= depth:
            continue

        for child in current.iter_children():
            if child.id in visited:
                continue
            if child.kind not in include_kinds:
                continue
            visited.add(child.id)
            result.append((child, current_depth + 1))
            queue.append((child, current_depth + 1))

    return result


def _subtree_to_markdown(
    collected: list[tuple[Any, int]],
    graph: TraceGraph,
) -> str:
    """Render subtree as indented markdown.

    REQ-d00075-C: Indented headings + assertion bullets + coverage stats.
    """
    if not collected:
        return "*(empty subtree)*"

    lines: list[str] = []
    for node, depth_level in collected:
        indent = "  " * depth_level

        if node.kind == NodeKind.ASSERTION:
            label = node.get_field("label", "")
            text = node.get_label()
            lines.append(f"{indent}- **{label}**: {text}")
        elif node.kind == NodeKind.REQUIREMENT:
            level_str = node.get_field("level", "")
            status = node.get_field("status", "")
            title = node.get_label()
            # Coverage summary (REQ-o00067-F)
            cov = _compute_coverage_summary(node)
            cov_str = f" [{cov['covered']}/{cov['total']} covered, {cov['pct']}%]"
            lines.append(
                f"{indent}{'#' * min(depth_level + 1, 6)} {node.id}: {title} "
                f"({level_str}, {status}){cov_str}"
            )
        else:
            title = node.get_label()
            lines.append(f"{indent}{'#' * min(depth_level + 1, 6)} {node.id}: {title}")

    return "\n".join(lines)


def _subtree_to_flat(
    collected: list[tuple[Any, int]],
    graph: TraceGraph,
    root_id: str,
) -> dict[str, Any]:
    """Render subtree as flat JSON structure.

    REQ-d00075-D: Returns {root_id, nodes, edges, stats}.
    """
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    total_reqs = 0
    total_assertions = 0

    for node, depth_level in collected:
        entry: dict[str, Any] = {
            "id": node.id,
            "kind": node.kind.value,
            "title": node.get_label(),
            "depth": depth_level,
        }

        if node.kind == NodeKind.REQUIREMENT:
            entry["level"] = node.get_field("level")
            entry["status"] = node.get_field("status")
            entry["coverage"] = _compute_coverage_summary(node)
            total_reqs += 1
        elif node.kind == NodeKind.ASSERTION:
            entry["label"] = node.get_field("label")
            entry["text"] = node.get_label()
            total_assertions += 1

        nodes.append(entry)

        # Collect edges to children that are in the collected set
        collected_ids = {n.id for n, _ in collected}
        for edge in node.iter_outgoing_edges():
            if edge.target.id in collected_ids:
                edges.append(
                    {
                        "source": node.id,
                        "target": edge.target.id,
                        "kind": edge.kind.value,
                    }
                )

    return {
        "root_id": root_id,
        "nodes": nodes,
        "edges": edges,
        "stats": {
            "total_nodes": len(nodes),
            "requirements": total_reqs,
            "assertions": total_assertions,
        },
    }


def _subtree_to_nested(
    node: Any,
    depth_limit: int,
    kind_filter: set[NodeKind],
    graph: TraceGraph,
    _current_depth: int = 0,
    _visited: set[str] | None = None,
) -> dict[str, Any]:
    """Render subtree as recursive nested JSON.

    REQ-d00075-E: Recursive JSON with children arrays.
    """
    if _visited is None:
        _visited = set()
    _visited.add(node.id)

    entry: dict[str, Any] = {
        "id": node.id,
        "kind": node.kind.value,
        "title": node.get_label(),
    }

    if node.kind == NodeKind.REQUIREMENT:
        entry["level"] = node.get_field("level")
        entry["status"] = node.get_field("status")
        entry["coverage"] = _compute_coverage_summary(node)
    elif node.kind == NodeKind.ASSERTION:
        entry["label"] = node.get_field("label")
        entry["text"] = node.get_label()

    # Recurse into children
    children: list[dict[str, Any]] = []
    if depth_limit == 0 or _current_depth < depth_limit:
        for child in node.iter_children():
            if child.id in _visited:
                continue
            if child.kind not in kind_filter:
                continue
            children.append(
                _subtree_to_nested(
                    child,
                    depth_limit,
                    kind_filter,
                    graph,
                    _current_depth + 1,
                    _visited,
                )
            )
    entry["children"] = children
    return entry


def _get_subtree(
    graph: TraceGraph,
    root_id: str,
    depth: int = 0,
    include_kinds: str = "",
    format: str = "markdown",
) -> dict[str, Any]:
    """Dispatcher for subtree extraction.

    REQ-o00067-A through REQ-o00067-F.
    """
    root_node = graph.find_by_id(root_id)
    if root_node is None:
        return {"error": f"Node '{root_id}' not found"}

    # Parse kind filter
    kind_set: set[NodeKind] | None = None
    if include_kinds:
        kind_set = set()
        for k in include_kinds.split(","):
            k = k.strip().lower()
            try:
                kind_set.add(NodeKind(k))
            except ValueError:
                return {"error": f"Unknown node kind: '{k}'"}

    if format == "nested":
        # Nested uses recursive approach directly
        if kind_set is None:
            kind_set = _SUBTREE_KIND_DEFAULTS.get(
                root_node.kind,
                {root_node.kind},
            )
            if NodeKind.REQUIREMENT in kind_set:
                kind_set = kind_set | {NodeKind.ASSERTION}
        result = _subtree_to_nested(root_node, depth, kind_set, graph)
        return {"format": "nested", "root_id": root_id, "tree": result}

    # BFS-based formats: markdown and flat
    collected = _collect_subtree(graph, root_id, depth, kind_set)

    if format == "markdown":
        return {
            "format": "markdown",
            "root_id": root_id,
            "content": _subtree_to_markdown(collected, graph),
        }
    elif format == "flat":
        return {
            "format": "flat",
            **_subtree_to_flat(collected, graph, root_id),
        }
    else:
        return {"error": f"Unknown format: '{format}'. Use 'markdown', 'flat', or 'nested'."}


# ─────────────────────────────────────────────────────────────────────────────
# Cursor Protocol (REQ-o00068, REQ-d00076)
# ─────────────────────────────────────────────────────────────────────────────


class CursorState:
    """Single-cursor state for incremental iteration over query results.

    REQ-d00076-A: Stores query, params, batch_size, materialized items, position.
    """

    __slots__ = ("query", "params", "batch_size", "items", "position")

    def __init__(
        self,
        query: str,
        params: dict[str, Any],
        batch_size: int,
        items: list[dict[str, Any]],
    ) -> None:
        self.query = query
        self.params = params
        self.batch_size = batch_size
        self.items = items
        self.position: int = 0


def _reshape_for_batch_size(
    nodes: list[tuple[Any, int]],
    batch_size: int,
    graph: TraceGraph,
) -> list[dict[str, Any]]:
    """Reshape collected nodes based on batch_size semantics.

    REQ-o00068-E: batch_size controls item granularity.
      -1: Assertions as first-class items
       0: Each node is one item (requirements include assertions inline)
       1: Each node is one item + immediate children summaries

    REQ-d00076-G: Reuses existing serializers.
    """
    items: list[dict[str, Any]] = []

    for node, depth in nodes:
        if batch_size == -1:
            # Assertions as first-class items
            if node.kind == NodeKind.REQUIREMENT:
                items.append(
                    {
                        "id": node.id,
                        "kind": "requirement",
                        "title": node.get_label(),
                        "level": node.get_field("level"),
                        "status": node.get_field("status"),
                        "depth": depth,
                    }
                )
                # Emit each assertion as a separate item
                for child in node.iter_children():
                    if child.kind == NodeKind.ASSERTION:
                        items.append(_serialize_assertion(child))
            elif node.kind == NodeKind.ASSERTION:
                # Already emitted inline above when parent was processed;
                # skip if traversed independently
                continue
            else:
                items.append(_serialize_node_summary(node))

        elif batch_size == 0:
            # Each node is one item with assertions inline
            if node.kind == NodeKind.REQUIREMENT:
                assertions = []
                for child in node.iter_children():
                    if child.kind == NodeKind.ASSERTION:
                        assertions.append(_serialize_assertion(child))
                items.append(
                    {
                        "id": node.id,
                        "kind": "requirement",
                        "title": node.get_label(),
                        "level": node.get_field("level"),
                        "status": node.get_field("status"),
                        "depth": depth,
                        "assertions": assertions,
                        "coverage": _compute_coverage_summary(node),
                    }
                )
            elif node.kind == NodeKind.ASSERTION:
                continue  # Inlined in parent
            else:
                items.append(_serialize_node_summary(node))

        else:
            # batch_size >= 1: Node + immediate children summaries
            if node.kind == NodeKind.REQUIREMENT:
                assertions = []
                for child in node.iter_children():
                    if child.kind == NodeKind.ASSERTION:
                        assertions.append(_serialize_assertion(child))
                children_summaries = []
                for child in node.iter_children():
                    if child.kind == NodeKind.REQUIREMENT:
                        children_summaries.append(_serialize_requirement_summary(child))
                items.append(
                    {
                        "id": node.id,
                        "kind": "requirement",
                        "title": node.get_label(),
                        "level": node.get_field("level"),
                        "status": node.get_field("status"),
                        "depth": depth,
                        "assertions": assertions,
                        "coverage": _compute_coverage_summary(node),
                        "children": children_summaries,
                    }
                )
            elif node.kind == NodeKind.ASSERTION:
                continue  # Inlined in parent
            else:
                items.append(_serialize_node_summary(node))

    return items


def _materialize_cursor_items(
    query: str,
    params: dict[str, Any],
    batch_size: int,
    graph: TraceGraph,
) -> list[dict[str, Any]]:
    """Run query and reshape results for cursor iteration.

    REQ-d00076-B: Dispatches to existing query helpers.
    REQ-o00068-F: Supports subtree, search, hierarchy, query_nodes,
                  test_coverage, uncovered_assertions, scoped_search.
    """
    if query == "subtree":
        root_id = params.get("root_id", "")
        depth = params.get("depth", 0)
        include_kinds_str = params.get("include_kinds", "")

        # Parse kind filter
        kind_set: set[NodeKind] | None = None
        if include_kinds_str:
            kind_set = set()
            for k in include_kinds_str.split(","):
                k = k.strip().lower()
                try:
                    kind_set.add(NodeKind(k))
                except ValueError:
                    return []

        collected = _collect_subtree(graph, root_id, depth, kind_set)
        return _reshape_for_batch_size(collected, batch_size, graph)

    elif query == "search":
        results = _search(
            graph,
            query=params.get("query", ""),
            field=params.get("field", "all"),
            regex=params.get("regex", False),
            limit=params.get("limit", 50),
        )
        return results  # Already serialized dicts

    elif query == "hierarchy":
        result = _get_hierarchy(graph, params.get("req_id", ""))
        if "error" in result:
            return []
        # Flatten: ancestors then children
        items: list[dict[str, Any]] = []
        for anc in result.get("ancestors", []):
            anc["_section"] = "ancestor"
            items.append(anc)
        for child in result.get("children", []):
            child["_section"] = "child"
            items.append(child)
        return items

    elif query == "query_nodes":
        kw_str = params.get("keywords")
        kw_list = None
        if kw_str:
            kw_list = [k.strip() for k in kw_str.split(",") if k.strip()]
        filters: dict[str, str] = {}
        if params.get("level"):
            filters["level"] = params["level"]
        if params.get("status"):
            filters["status"] = params["status"]
        if params.get("actor"):
            filters["actor"] = params["actor"]
        result = _query_nodes(
            graph,
            kind=params.get("kind"),
            keywords=kw_list,
            match_all=params.get("match_all", True),
            filters=filters or None,
            limit=params.get("limit", 50),
        )
        return result.get("results", [])

    elif query == "test_coverage":
        result = _get_test_coverage(graph, params.get("req_id", ""))
        if not result.get("success"):
            return []
        # Return test nodes as items
        return result.get("test_nodes", [])

    elif query == "uncovered_assertions":
        result = _get_uncovered_assertions(
            graph,
            req_id=params.get("req_id"),
            limit=params.get("limit", 100),
        )
        if not result.get("success"):
            return []
        return result.get("uncovered", [])

    elif query == "scoped_search":
        # Implements: REQ-o00068-F, REQ-d00076-B
        result = _scoped_search(
            graph,
            query=params.get("query", ""),
            scope_id=params.get("scope_id", ""),
            direction=params.get("direction", "descendants"),
            field=params.get("field", "all"),
            regex=params.get("regex", False),
            include_assertions=params.get("include_assertions", False),
            limit=params.get("limit", 50),
        )
        return result.get("results", [])

    else:
        return []


def _open_cursor(
    state: dict[str, Any],
    query: str,
    params: dict[str, Any],
    batch_size: int,
) -> dict[str, Any]:
    """Open a new cursor, auto-closing any previous one.

    REQ-o00068-A: Materializes results and returns first item + metadata.
    REQ-o00068-D: Single active cursor; new cursor discards previous.
    REQ-d00076-C: Stored in _state["cursor"].
    REQ-d00076-D: Returns first item, total count, and query metadata.
    """
    graph = state["graph"]
    items = _materialize_cursor_items(query, params, batch_size, graph)

    cursor = CursorState(
        query=query,
        params=params,
        batch_size=batch_size,
        items=items,
    )
    state["cursor"] = cursor

    first_item = items[0] if items else None
    if first_item is not None:
        cursor.position = 1

    return {
        "success": True,
        "query": query,
        "batch_size": batch_size,
        "total": len(items),
        "position": cursor.position,
        "remaining": len(items) - cursor.position,
        "current": first_item,
    }


def _cursor_next(
    state: dict[str, Any],
    count: int = 1,
) -> dict[str, Any]:
    """Advance cursor and return next items.

    REQ-o00068-B: Returns next count items, advances position.
    REQ-d00076-E: Returns items at [position:position+count], empty at end.
    """
    cursor = state.get("cursor")
    if cursor is None:
        return {"success": False, "error": "No active cursor. Use open_cursor() first."}

    start = cursor.position
    end = min(start + count, len(cursor.items))
    items = cursor.items[start:end]
    cursor.position = end

    return {
        "success": True,
        "items": items,
        "count": len(items),
        "position": cursor.position,
        "total": len(cursor.items),
        "remaining": len(cursor.items) - cursor.position,
    }


def _cursor_info(
    state: dict[str, Any],
) -> dict[str, Any]:
    """Return cursor position info without advancing.

    REQ-o00068-C: Returns position/total/remaining without advancing.
    REQ-d00076-F: Read-only, returns {position, total, remaining, query, batch_size}.
    """
    cursor = state.get("cursor")
    if cursor is None:
        return {"success": False, "error": "No active cursor. Use open_cursor() first."}

    return {
        "success": True,
        "position": cursor.position,
        "total": len(cursor.items),
        "remaining": len(cursor.items) - cursor.position,
        "query": cursor.query,
        "batch_size": cursor.batch_size,
    }


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
6. `discover_requirements(query, scope_id)` - Find most-specific matches in a subgraph

## Tools Overview

### Graph Status & Control
- `get_graph_status()` - Node counts, orphan/broken reference flags
- `refresh_graph(full=False)` - Rebuild after spec file changes

### Search & Navigation
- `search(query, field="all", regex=False, limit=50)` - Find requirements
  - field: "id", "title", "body", or "all"
  - regex: treat query as regex pattern
- `scoped_search(query, scope_id, direction="descendants", ...)` - Search within a subgraph
  - Restricts search to descendants or ancestors of scope_id
  - include_assertions: also match against assertion text
  - Returns results with scope context metadata
- `get_requirement(req_id)` - Full details with assertions and relationships
- `get_hierarchy(req_id)` - Ancestors (to roots) and direct children
- `minimize_requirement_set(req_ids, edge_kinds="")` - Prune to most-specific
  - Removes ancestors that are superseded by more-specific descendants
  - Returns minimal_set, pruned items with superseded_by, and stats
- `discover_requirements(query, scope_id, ...)` - Search + minimize in one step
  - Chains scoped_search with minimize_requirement_set
  - Returns only the most-specific matches within a subgraph
  - Pruned ancestors include superseded_by metadata

### Workspace Context
- `get_workspace_info()` - Repo path, project name, configuration
- `get_project_summary()` - Counts by level, coverage stats, change metrics
- `get_changed_requirements()` - Requirements with uncommitted or branch changes

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

### Link Suggestion
- `suggest_links(file_path?, limit?)` - Suggest requirement links for unlinked tests
  - Uses heuristics: import chain, function name, file proximity, keyword overlap
  - Returns suggestions with confidence scores and reasons
- `apply_link(file_path, line, requirement_id)` - Insert # Implements: comment
  - Validates requirement exists before modifying files
  - Refreshes graph after insertion

### Subtree Extraction
- `get_subtree(root_id, depth=0, include_kinds="", format="markdown")` - Extract subgraph
  - depth: 0 = unlimited, N = max N levels from root
  - include_kinds: comma-separated NodeKind values (empty = smart defaults)
  - format: "markdown" (indented headings), "flat" (JSON with nodes/edges/stats),
    "nested" (recursive JSON with children arrays)
  - Includes coverage summary stats per requirement node
  - Deduplicates in DAG structures

### Cursor Protocol (Incremental Iteration)
- `open_cursor(query, params={}, batch_size=1)` - Open cursor over query results
  - query: "subtree", "search", "hierarchy", "query_nodes",
    "test_coverage", "uncovered_assertions", "scoped_search"
  - params: query-specific parameters (e.g. {root_id: "REQ-p00001"})
  - batch_size: -1 (assertions as separate items), 0 (nodes with inline assertions),
    1 (nodes with children summaries)
  - Returns first item + total/position/remaining metadata
  - Opening a new cursor auto-closes any previous cursor
- `cursor_next(count=1)` - Get next items and advance position
- `cursor_info()` - Check position/total/remaining without advancing

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

**Extracting a scoped subtree for sub-agent consumption:**
1. get_subtree("REQ-p00001") for markdown overview
2. get_subtree("REQ-p00001", format="flat") for structured data
3. get_subtree("REQ-p00001", depth=2) to limit depth

**Incrementally exploring results with cursor:**
1. open_cursor("subtree", {"root_id": "REQ-p00001"}, batch_size=0)
2. cursor_info() to check how many items remain
3. cursor_next() to get next item, repeat as needed

**Discovering requirements for a ticket:**
1. discover_requirements("authentication", scope_id="REQ-p00001") for most-specific matches
2. get_requirement() on each result for full details and assertions
3. Or use scoped_search() + minimize_requirement_set() separately for more control

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

    # Load config for the working directory
    config = get_config(start_path=working_dir, quiet=True)

    # Compute canonical root for worktree-aware path resolution
    canonical_root = find_canonical_root(working_dir)

    # Build initial graph if not provided
    if graph is None:
        graph = build_graph(config=config, repo_root=working_dir, canonical_root=canonical_root)

    # Create server with instructions for AI agents (REQ-d00065)
    mcp = FastMCP("elspais", instructions=MCP_SERVER_INSTRUCTIONS)

    # Store graph in closure for tools
    _state: dict[str, Any] = {
        "graph": graph,
        "working_dir": working_dir,
        "config": config,
        "canonical_root": canonical_root,
    }

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
        result, new_graph = _refresh_graph(
            _state["working_dir"],
            full=full,
            canonical_root=_state.get("canonical_root"),
        )
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
    def minimize_requirement_set(
        req_ids: list[str],
        edge_kinds: str = "implements,refines",
    ) -> dict[str, Any]:
        """Prune a requirement set to its most-specific members.

        Removes ancestors already covered by more-specific descendants in the
        input set. Useful when agents list both leaf requirements and their
        broad ancestors for a ticket.

        REQ-d00077-F: Delegates to helper, performing only parameter parsing.

        Args:
            req_ids: List of requirement IDs to minimize.
            edge_kinds: Comma-separated edge kinds to follow when determining
                ancestry. Default: "implements,refines".

        Returns:
            Dict with minimal_set, pruned (with superseded_by metadata),
            not_found, and stats.
        """
        # REQ-d00077-F: Parse edge_kinds string to EdgeKind set
        parsed_kinds: set[EdgeKind] = set()
        for kind_str in edge_kinds.split(","):
            kind_str = kind_str.strip().lower()
            try:
                parsed_kinds.add(EdgeKind(kind_str))
            except ValueError:
                pass
        if not parsed_kinds:
            parsed_kinds = {EdgeKind.IMPLEMENTS, EdgeKind.REFINES}
        return _minimize_requirement_set(_state["graph"], req_ids, parsed_kinds)

    @mcp.tool()
    def scoped_search(
        query: str,
        scope_id: str,
        direction: str = "descendants",
        field: str = "all",
        regex: bool = False,
        include_assertions: bool = False,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Search requirements within a subgraph rooted at scope_id.

        Restricts search to descendants or ancestors of the scope node,
        preventing over-matching across unrelated parts of the graph.

        REQ-d00078-F: Delegates to helper, performing only parameter validation.

        Args:
            query: Search string or regex pattern.
            scope_id: Root node ID defining the search scope.
            direction: "descendants" (default) or "ancestors".
            field: Field to search: 'id', 'title', 'body', or 'all'.
            regex: If True, treat query as regex pattern.
            include_assertions: If True, also match assertion text.
            limit: Maximum results to return (default 50).

        Returns:
            Dict with results list, scope_id, and direction.
        """
        return _scoped_search(
            _state["graph"], query, scope_id, direction, field, regex, include_assertions, limit
        )

    @mcp.tool()
    def discover_requirements(
        query: str,
        scope_id: str,
        direction: str = "descendants",
        field: str = "all",
        regex: bool = False,
        include_assertions: bool = False,
        limit: int = 50,
        edge_kinds: str = "implements,refines",
    ) -> dict[str, Any]:
        """Search within a subgraph and return only the most-specific matches.

        Chains scoped_search with minimize_requirement_set to prune ancestors
        from results, returning only the most-specific requirements that match.

        REQ-d00079-D: Delegates to helper, performing only edge_kinds parsing.

        Args:
            query: Search string or regex pattern.
            scope_id: Root node ID defining the search scope.
            direction: "descendants" (default) or "ancestors".
            field: Field to search: 'id', 'title', 'body', or 'all'.
            regex: If True, treat query as regex pattern.
            include_assertions: If True, also match assertion text.
            limit: Maximum results to return (default 50).
            edge_kinds: Comma-separated edge kinds for ancestor pruning.
                Default: "implements,refines".

        Returns:
            Dict with results (minimal set), pruned (with superseded_by),
            scope_id, direction, and stats.
        """
        # REQ-d00079-D: Parse edge_kinds and delegate
        parsed_kinds: set[EdgeKind] = set()
        for kind_str in edge_kinds.split(","):
            kind_str = kind_str.strip().lower()
            try:
                parsed_kinds.add(EdgeKind(kind_str))
            except ValueError:
                pass
        if not parsed_kinds:
            parsed_kinds = {EdgeKind.IMPLEMENTS, EdgeKind.REFINES}
        return _discover_requirements(
            _state["graph"],
            query,
            scope_id,
            direction,
            field,
            regex,
            include_assertions,
            limit,
            parsed_kinds,
        )

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
    def get_node(node_id: str) -> dict[str, Any]:
        """Get full details for any graph node by ID.

        Works for any node kind: requirement, journey, test, result, code,
        assertion, remainder. Returns a common envelope plus kind-specific
        properties.

        Args:
            node_id: The node ID (e.g., 'REQ-p00001', 'JNY-Login-01').

        Returns:
            Node details with kind-specific properties.
        """
        return _get_node(_state["graph"], node_id)

    @mcp.tool()
    def query_nodes(
        kind: str | None = None,
        keywords: str | None = None,
        match_all: bool = True,
        level: str | None = None,
        status: str | None = None,
        actor: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Combined property + keyword filter query for any node kind.

        Args:
            kind: Filter by NodeKind value: requirement, journey, test, result, code.
            keywords: Comma-separated keywords to search for.
            match_all: True (default) = AND, False = OR for keywords.
            level: Property filter: PRD, OPS, DEV (requirements only).
            status: Property filter for requirement or test result status.
            actor: Property filter: journey actor.
            limit: Max results (default 50).

        Returns:
            Results list with count and truncated flag.
        """
        kw_list = None
        if keywords:
            kw_list = [k.strip() for k in keywords.split(",") if k.strip()]
        filters = {}
        if level:
            filters["level"] = level
        if status:
            filters["status"] = status
        if actor:
            filters["actor"] = actor
        return _query_nodes(_state["graph"], kind, kw_list, match_all, filters or None, limit)

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
        return _get_project_summary(_state["graph"], _state["working_dir"], _state["config"])

    @mcp.tool()
    def get_changed_requirements() -> dict[str, Any]:
        """Get requirements with git changes.

        Returns requirements that have uncommitted changes, differ from the main
        branch, or have been moved between files. Each result includes the
        requirement summary, git state flags, and source file path.

        Returns:
            Changed requirements with git state and summary counts.
        """
        return _get_changed_requirements(_state["graph"])

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
            new_result, new_graph = _refresh_graph(
                _state["working_dir"],
                canonical_root=_state.get("canonical_root"),
            )
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
            new_result, new_graph = _refresh_graph(
                _state["working_dir"],
                canonical_root=_state.get("canonical_root"),
            )
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
            new_result, new_graph = _refresh_graph(
                _state["working_dir"],
                canonical_root=_state.get("canonical_root"),
            )
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

    # ─────────────────────────────────────────────────────────────────────
    # Link Suggestion Tools (REQ-d00074)
    # ─────────────────────────────────────────────────────────────────────

    @mcp.tool()
    def suggest_links(
        file_path: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Suggest requirement links for unlinked test nodes.

        Analyzes unlinked TEST nodes and proposes requirement associations
        using heuristics: import chain, function name matching, file path
        proximity, and keyword overlap.

        Args:
            file_path: Optional file path to restrict analysis to.
            limit: Maximum suggestions to return (default 50).

        Returns:
            List of suggestions with test_id, requirement_id, confidence, and reasons.
        """
        return _suggest_links_impl(
            _state["graph"],
            _state["working_dir"],
            file_path=file_path,
            limit=limit,
        )

    @mcp.tool()
    def apply_link(
        file_path: str,
        line: int,
        requirement_id: str,
    ) -> dict[str, Any]:
        """Apply a link suggestion by inserting a # Implements: comment.

        Inserts a ``# Implements: <requirement_id>`` comment into the specified
        file at the given line number. Refreshes the graph afterward.

        Args:
            file_path: Path to the file to modify (relative to repo root).
            line: Line number to insert at (1-based). 0 means top of file.
            requirement_id: Requirement ID to reference (e.g., 'REQ-p00001').

        Returns:
            Success status and the comment that was inserted.
        """
        return _apply_link_impl(
            _state,
            file_path=file_path,
            line=line,
            requirement_id=requirement_id,
        )

    # ─────────────────────────────────────────────────────────────────────
    # Subtree Extraction Tool (REQ-o00067)
    # ─────────────────────────────────────────────────────────────────────

    @mcp.tool()
    def get_subtree(
        root_id: str,
        depth: int = 0,
        include_kinds: str = "",
        format: str = "markdown",
    ) -> dict[str, Any]:
        """Extract a subgraph rooted at a given node.

        Returns a scoped subtree for focused analysis. Supports three output
        formats and configurable depth/kind filtering.

        Args:
            root_id: Required node ID to root the subtree at.
            depth: Max depth from root (0 = unlimited, N = N levels).
            include_kinds: Comma-separated NodeKind values to include.
                Empty string uses conservative defaults per root kind.
            format: Output format: 'markdown', 'flat', or 'nested'.

        Returns:
            Subtree data in the requested format.
        """
        return _get_subtree(
            _state["graph"],
            root_id=root_id,
            depth=depth,
            include_kinds=include_kinds,
            format=format,
        )

    # ─────────────────────────────────────────────────────────────────────
    # Cursor Protocol Tools (REQ-o00068)
    # ─────────────────────────────────────────────────────────────────────

    @mcp.tool()
    def open_cursor(
        query: str,
        params: dict[str, Any] | None = None,
        batch_size: int = 1,
    ) -> dict[str, Any]:
        """Open a cursor for incremental iteration over query results.

        Materializes query results and returns the first item. Opening a new
        cursor auto-closes any previous cursor.

        Args:
            query: Query type: 'subtree', 'search', 'hierarchy',
                'query_nodes', 'test_coverage', 'uncovered_assertions'.
            params: Query-specific parameters as a dict.
            batch_size: Item granularity (-1=assertions first-class,
                0=nodes with inline assertions, 1=nodes with children).

        Returns:
            First item, total count, and cursor metadata.
        """
        return _open_cursor(
            _state,
            query=query,
            params=params or {},
            batch_size=batch_size,
        )

    @mcp.tool()
    def cursor_next(
        count: int = 1,
    ) -> dict[str, Any]:
        """Advance cursor and return next items.

        Args:
            count: Number of items to return (default 1).

        Returns:
            Next items, position, and remaining count.
        """
        return _cursor_next(_state, count=count)

    @mcp.tool()
    def cursor_info() -> dict[str, Any]:
        """Get cursor position info without advancing.

        Returns:
            Current position, total, remaining, query type, and batch_size.
        """
        return _cursor_info(_state)

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
