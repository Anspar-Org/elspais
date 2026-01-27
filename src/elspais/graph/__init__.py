"""Graph module - Core graph data structures.

Exports:
- NodeKind: Enum of node types
- SourceLocation: Portable file location reference
- GraphNode: Unified node representation
- Edge: Typed edge between nodes
- EdgeKind: Enum of edge types

Note: TraceGraph is in elspais.graph.builder (use graph.factory.build_graph() to construct)
"""

from elspais.graph.GraphNode import (
    GraphNode,
    NodeKind,
    SourceLocation,
)
from elspais.graph.relations import Edge, EdgeKind

__all__ = [
    "NodeKind",
    "SourceLocation",
    "GraphNode",
    "Edge",
    "EdgeKind",
]
