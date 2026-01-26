"""Graph module - Core graph data structures.

Exports:
- NodeKind: Enum of node types
- SourceLocation: Portable file location reference
- GraphNode: Unified node representation
- Edge: Typed edge between nodes
- EdgeKind: Enum of edge types
- TraceGraph: Container for the complete graph
"""

from elspais.arch3.Graph.GraphNode import (
    GraphNode,
    NodeKind,
    SourceLocation,
)
from elspais.arch3.Graph.relations import Edge, EdgeKind

__all__ = [
    "NodeKind",
    "SourceLocation",
    "GraphNode",
    "Edge",
    "EdgeKind",
]
