# Implements: REQ-d00127-C
"""Canonical EdgeKind sets used across the codebase.

Single source of truth for grouped EdgeKind frozensets. Do NOT redefine
these inline elsewhere -- import from here.
"""
from __future__ import annotations

from elspais.graph.relations import EdgeKind

# Edges that represent physical file structure: FILE -> content (CONTAINS),
# and REQUIREMENT -> ASSERTION/REMAINDER (STRUCTURES).
STRUCTURAL_EDGE_KINDS: frozenset[EdgeKind] = frozenset({EdgeKind.CONTAINS, EdgeKind.STRUCTURES})

# Narrower subset: STRUCTURES only. Used by comment-anchor resolution to find
# the parent REQUIREMENT of an ASSERTION without crossing CONTAINS into a FILE.
ASSERTION_STRUCTURE_EDGES: frozenset[EdgeKind] = frozenset({EdgeKind.STRUCTURES})

# All requirement-traceability edge kinds.
TRACEABILITY_EDGE_KINDS: frozenset[EdgeKind] = frozenset(
    {
        EdgeKind.IMPLEMENTS,
        EdgeKind.REFINES,
        EdgeKind.SATISFIES,
        EdgeKind.VERIFIES,
        EdgeKind.VALIDATES,
        EdgeKind.INSTANCE,
        EdgeKind.DEFINES,
        EdgeKind.YIELDS,
        # Implements: REQ-d00252
        EdgeKind.INTEGRATES,
    }
)

# Narrower subset used by health checks for "can this non-spec node reach a
# REQUIREMENT?" -- only kinds whose source can be a CODE/TEST/JOURNEY node.
# REFINES is req->req only and must NOT count for non-spec reachability.
REACHABILITY_TRACEABILITY_EDGES: frozenset[EdgeKind] = frozenset(
    {EdgeKind.IMPLEMENTS, EdgeKind.VERIFIES, EdgeKind.VALIDATES}
)
