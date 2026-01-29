"""Graph module - Core graph data structures.

Exports:
- NodeKind: Enum of node types
- SourceLocation: Portable file location reference
- GraphNode: Unified node representation
- Edge: Typed edge between nodes
- EdgeKind: Enum of edge types
- BrokenReference: Reference to non-existent target (detection)
- CoverageSource: Enum for coverage origin type
- CoverageContribution: Single coverage claim on an assertion
- RollupMetrics: Aggregated coverage metrics for a requirement

Note: TraceGraph is in elspais.graph.builder (use graph.factory.build_graph() to construct)
"""

from elspais.graph.annotators import annotate_coverage
from elspais.graph.GraphNode import (
    GraphNode,
    NodeKind,
    SourceLocation,
)
from elspais.graph.metrics import CoverageContribution, CoverageSource, RollupMetrics
from elspais.graph.mutations import BrokenReference, MutationEntry, MutationLog
from elspais.graph.relations import Edge, EdgeKind

__all__ = [
    "NodeKind",
    "SourceLocation",
    "GraphNode",
    "Edge",
    "EdgeKind",
    "BrokenReference",
    "MutationEntry",
    "MutationLog",
    "CoverageSource",
    "CoverageContribution",
    "RollupMetrics",
    "annotate_coverage",
]
