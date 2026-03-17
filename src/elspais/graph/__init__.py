"""Graph module - Core graph data structures.

Exports:
- NodeKind: Enum of node types
- FileType: Enum of source file classifications
- GraphNode: Unified node representation
- Edge: Typed edge between nodes
- EdgeKind: Enum of edge types
- Stereotype: Node classification for template-instance pattern
- BrokenReference: Reference to non-existent target (detection)
- CoverageSource: Enum for coverage origin type
- CoverageContribution: Single coverage claim on an assertion
- RollupMetrics: Aggregated coverage metrics for a requirement

Note: TraceGraph is internal to graph/builder.py.
Use FederatedGraph (the public API) via graph.factory.build_graph().
"""

from elspais.graph.annotators import annotate_coverage
from elspais.graph.federated import FederatedGraph
from elspais.graph.GraphNode import (
    FileType,
    GraphNode,
    NodeKind,
)
from elspais.graph.metrics import CoverageContribution, CoverageSource, RollupMetrics
from elspais.graph.mutations import BrokenReference, MutationEntry, MutationLog
from elspais.graph.relations import Edge, EdgeKind, Stereotype

__all__ = [
    "FileType",
    "NodeKind",
    "GraphNode",
    "Edge",
    "EdgeKind",
    "Stereotype",
    "BrokenReference",
    "MutationEntry",
    "MutationLog",
    "CoverageSource",
    "CoverageContribution",
    "RollupMetrics",
    "FederatedGraph",
    "annotate_coverage",
]
