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
    CODE_ID_PREFIX,
    DEFINITION_ID_PREFIX,
    FILE_ID_PREFIX,
    REMAINDER_ID_PREFIX,
    STRUCTURAL_ID_PREFIXES,
    TEST_ID_PREFIX,
    FileType,
    GraphNode,
    NodeKind,
    make_code_id,
    make_definition_id,
    make_file_id,
    make_remainder_id,
    make_test_id,
)
from elspais.graph.metrics import CoverageContribution, CoverageSource, RollupMetrics
from elspais.graph.mutations import BrokenReference, MutationEntry, MutationLog
from elspais.graph.relations import Edge, EdgeKind, Stereotype

__all__ = [
    "FileType",
    "NodeKind",
    "GraphNode",
    "FILE_ID_PREFIX",
    "REMAINDER_ID_PREFIX",
    "DEFINITION_ID_PREFIX",
    "CODE_ID_PREFIX",
    "TEST_ID_PREFIX",
    "STRUCTURAL_ID_PREFIXES",
    "make_file_id",
    "make_remainder_id",
    "make_definition_id",
    "make_code_id",
    "make_test_id",
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
