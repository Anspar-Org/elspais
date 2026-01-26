"""Graph Serialization - Export TraceGraph to various formats.

This module provides functions to serialize TraceGraph and GraphNode
to JSON-compatible dicts, markdown, and CSV formats.
"""

from __future__ import annotations

import csv
import io
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from elspais.arch3.Graph.GraphNode import GraphNode
    from elspais.arch3.Graph.builder import TraceGraph


def serialize_node(node: GraphNode) -> dict[str, Any]:
    """Serialize a GraphNode to a JSON-compatible dict.

    Args:
        node: The node to serialize.

    Returns:
        Dict suitable for JSON serialization.
    """
    from elspais.arch3.Graph import NodeKind

    result: dict[str, Any] = {
        "id": node.id,
        "kind": node.kind.name,
        "label": node.label,
        "content": dict(node.content),
    }

    # Include source location if present
    if node.source:
        result["source"] = {
            "path": node.source.path,
            "line": node.source.line,
            "end_line": node.source.end_line,
        }
        if node.source.repo:
            result["source"]["repo"] = node.source.repo

    # Include child IDs
    if node.children:
        result["children"] = [child.id for child in node.children]

    # Include parent IDs
    if node.parents:
        result["parents"] = [parent.id for parent in node.parents]

    # Include metrics
    if node.metrics:
        result["metrics"] = dict(node.metrics)

    # Include outgoing edges
    if node.outgoing_edges:
        result["edges"] = [
            {
                "target": edge.target.id,
                "kind": edge.kind.name,
            }
            for edge in node.outgoing_edges
        ]

    return result


def serialize_graph(graph: TraceGraph) -> dict[str, Any]:
    """Serialize a TraceGraph to a JSON-compatible dict.

    Args:
        graph: The graph to serialize.

    Returns:
        Dict with nodes, roots, and metadata.
    """
    from elspais.arch3.Graph import NodeKind

    # Serialize all nodes
    nodes = {}
    for node in graph._index.values():
        nodes[node.id] = serialize_node(node)

    # Count by kind
    kind_counts: dict[str, int] = {}
    for node in graph._index.values():
        kind_name = node.kind.name
        kind_counts[kind_name] = kind_counts.get(kind_name, 0) + 1

    return {
        "nodes": nodes,
        "roots": [root.id for root in graph.roots],
        "metadata": {
            "node_count": len(nodes),
            "root_count": len(graph.roots),
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
    from elspais.arch3.Graph import NodeKind

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
        level = node.content.get("level", "")
        title = node.label or ""
        status = node.content.get("status", "")

        # Get implements from incoming edges (what this node implements)
        implements = []
        for edge in node.incoming_edges:
            from elspais.arch3.Graph.relations import EdgeKind
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
    from elspais.arch3.Graph import NodeKind

    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

    # Header
    writer.writerow([
        "id",
        "level",
        "label",
        "status",
        "file_path",
        "line",
        "hash",
        "implements",
    ])

    # Get requirements only
    requirements = list(graph.nodes_by_kind(NodeKind.REQUIREMENT))
    requirements.sort(key=lambda n: n.id)

    for node in requirements:
        file_path = node.source.path if node.source else ""
        line = node.source.line if node.source else ""

        # Get implements from incoming edges (what this node implements)
        implements = []
        for edge in node.incoming_edges:
            from elspais.arch3.Graph.relations import EdgeKind
            if edge.kind == EdgeKind.IMPLEMENTS:
                implements.append(edge.source.id)

        writer.writerow([
            node.id,
            node.content.get("level", ""),
            node.label,
            node.content.get("status", ""),
            file_path,
            line,
            node.content.get("hash", ""),
            "; ".join(implements),
        ])

    return output.getvalue()


__all__ = [
    "serialize_node",
    "serialize_graph",
    "to_markdown",
    "to_csv",
]
