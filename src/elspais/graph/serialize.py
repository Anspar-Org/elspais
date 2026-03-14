# Implements: REQ-d00064-A, REQ-d00064-B, REQ-d00064-C, REQ-d00064-D, REQ-d00064-E
"""Graph Serialization - Export TraceGraph to various formats.

This module provides functions to serialize TraceGraph and GraphNode
to JSON-compatible dicts, markdown, and CSV formats.
"""

from __future__ import annotations

import csv
import io
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from elspais.graph.builder import TraceGraph
    from elspais.graph.GraphNode import GraphNode


def serialize_node(node: GraphNode) -> dict[str, Any]:
    """Serialize a GraphNode to a JSON-compatible dict.

    Args:
        node: The node to serialize.

    Returns:
        Dict suitable for JSON serialization.
    """

    result: dict[str, Any] = {
        "id": node.id,
        "kind": node.kind.name,
        "label": node.get_label(),
        "uuid": node.uuid,
        "content": {
            k: v.value if isinstance(v, Enum) else v for k, v in node.get_all_content().items()
        },
    }

    # Implements: REQ-d00129-D, REQ-d00129-E, REQ-d00129-F
    # Include source location from FILE parent and parse_line fields
    _fn = node.file_node()
    _parse_line = node.get_field("parse_line")
    if _fn or _parse_line is not None:
        result["source"] = {
            "path": _fn.get_field("relative_path") if _fn else None,
            "line": _parse_line,
            "end_line": node.get_field("parse_end_line"),
        }
        _repo = _fn.get_field("repo") if _fn else None
        if _repo:
            result["source"]["repo"] = _repo

    # Include child IDs
    children = list(node.iter_children())
    if children:
        result["children"] = [child.id for child in children]

    # Include parent IDs
    parents = list(node.iter_parents())
    if parents:
        result["parents"] = [parent.id for parent in parents]

    # Include metrics (filter to JSON-serializable scalar types only;
    # complex objects like RollupMetrics are internal-use)
    if node._metrics:
        serializable = {
            k: v
            for k, v in node._metrics.items()
            if isinstance(v, (str, int, float, bool, type(None)))
        }
        if serializable:
            result["metrics"] = serializable

    # Include outgoing edges
    edges = list(node.iter_outgoing_edges())
    if edges:
        result["edges"] = [
            {
                "target": edge.target.id,
                "kind": edge.kind.name,
            }
            for edge in edges
        ]

    return result


def serialize_graph(graph: TraceGraph) -> dict[str, Any]:
    """Serialize a TraceGraph to a JSON-compatible dict.

    Args:
        graph: The graph to serialize.

    Returns:
        Dict with nodes, roots, and metadata.
    """

    # Serialize all nodes and count by kind in single pass
    nodes = {}
    kind_counts: dict[str, int] = {}
    for node in graph.all_nodes():
        nodes[node.id] = serialize_node(node)
        kind_name = node.kind.name
        kind_counts[kind_name] = kind_counts.get(kind_name, 0) + 1

    roots = list(graph.iter_roots())
    return {
        "nodes": nodes,
        "roots": [root.id for root in roots],
        "metadata": {
            "node_count": len(nodes),
            "root_count": len(roots),
            "repo_root": str(graph.repo_root),
            "by_kind": kind_counts,
        },
    }


def to_markdown(graph: TraceGraph) -> str:
    """Generate a markdown traceability matrix from graph.

    Args:
        graph: The TraceGraph to render.

    Returns:
        Markdown string with traceability matrix.
    """
    from elspais.graph import NodeKind

    lines = [
        "# Traceability Matrix",
        "",
        "| ID | Level | Title | Status | Implements |",
        "|-----|-------|-------|--------|------------|",
    ]

    # Get requirements only
    requirements = list(graph.nodes_by_kind(NodeKind.REQUIREMENT))

    # Sort by ID
    requirements.sort(key=lambda n: n.id)

    for node in requirements:
        req_id = node.id
        level = node.get_field("level", "")
        title = node.get_label() or ""
        status = node.get_field("status", "")

        # Get implements from incoming edges (what this node implements)
        implements = []
        for edge in node.iter_incoming_edges():
            from elspais.graph.relations import EdgeKind

            if edge.kind == EdgeKind.IMPLEMENTS:
                implements.append(edge.source.id)

        implements_str = ", ".join(implements) if implements else "-"

        lines.append(f"| {req_id} | {level} | {title} | {status} | {implements_str} |")

    lines.append("")
    return "\n".join(lines)


def to_csv(graph: TraceGraph) -> str:
    """Generate a CSV export from graph.

    Args:
        graph: The TraceGraph to export.

    Returns:
        CSV string with requirement data.
    """
    from elspais.graph import NodeKind

    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

    # Header
    writer.writerow(
        [
            "id",
            "level",
            "label",
            "status",
            "file_path",
            "line",
            "hash",
            "implements",
        ]
    )

    # Get requirements only
    requirements = list(graph.nodes_by_kind(NodeKind.REQUIREMENT))
    requirements.sort(key=lambda n: n.id)

    for node in requirements:
        _fn = node.file_node()
        file_path = _fn.get_field("relative_path") if _fn else ""
        line = node.get_field("parse_line") or ""

        # Get implements from incoming edges (what this node implements)
        implements = []
        for edge in node.iter_incoming_edges():
            from elspais.graph.relations import EdgeKind

            if edge.kind == EdgeKind.IMPLEMENTS:
                implements.append(edge.source.id)

        writer.writerow(
            [
                node.id,
                node.get_field("level", ""),
                node.get_label(),
                node.get_field("status", ""),
                file_path,
                line,
                node.get_field("hash", ""),
                "; ".join(implements),
            ]
        )

    return output.getvalue()


__all__ = [
    "serialize_node",
    "serialize_graph",
    "to_markdown",
    "to_csv",
]
