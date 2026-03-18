# Design: Traceability Classification and Orphan Redesign

## Problem Statement

The current `spec.orphans` health check conflates three distinct concepts into a
single warning. After making the test scanner emit TEST nodes for all test
functions (not just those referencing requirements), 475 "orphaned" TEST nodes
appeared — these are structurally sound nodes that simply lack requirement
traceability. They are not errors, but the health check treats them identically
to genuinely broken nodes.

## Current Behavior

The builder tracks `_orphan_candidates` — any node that was never the source of
a resolved pending link (IMPLEMENTS, VERIFIES, YIELDS, etc.). At build
finalization, candidates that aren't classified as roots become orphans. The
`spec.orphans` health check reports all of them as a single warning.

This conflates:

1. **Structural orphans** — nodes that failed to wire into the graph at all (no
   FILE parent via CONTAINS). These indicate build pipeline bugs.
2. **Unlinked nodes** — nodes with a FILE parent but no traceability edge to any
   requirement. These are traceability gaps that need attention.
3. **Broken references** — nodes whose outgoing edges target non-existent nodes.
   These indicate stale or incorrect references.

## Proposed Model

### Edge Classification

Edges serve two distinct purposes:

| Purpose | Edge Kinds | Meaning |
|---------|-----------|---------|
| **Structural** | CONTAINS, STRUCTURES | File organization, internal grouping |
| **Traceability** | IMPLEMENTS, VERIFIES, YIELDS, REFINES, VALIDATES, SATISFIES, INSTANCE, DEFINES | Requirement-to-artifact relationships |

CONTAINS edges represent "this node lives in this file." They are always present
for well-formed nodes but say nothing about whether the node participates in
requirement traceability.

### Reachability Queries

Traceability status should be defined by reachability through non-CONTAINS edges.
Given a requirement node, the following statuses can be computed by walking
traceability edges:

| Status | Path | Meaning |
|--------|------|---------|
| **Implemented** | REQ <- CODE (IMPLEMENTS) | Code claims to implement the requirement |
| **Verified** | REQ <- TEST (VERIFIES) | A test claims to verify the requirement |
| **Reported** | REQ <- TEST <- TEST_RESULT (VERIFIES + YIELDS) | Test execution results exist |
| **Refined** | REQ <- REQ (REFINES) | A child requirement refines it |

These are not mutually exclusive. A requirement can be implemented, validated,
and reported simultaneously.

### Node Classification

From the node's perspective (rather than the requirement's):

| Classification | Condition | Health Severity |
|---------------|-----------|-----------------|
| **Structural orphan** | No FILE parent via CONTAINS | Error — build pipeline bug |
| **Unlinked** | Has FILE parent but no traceability edge to any requirement | Info — traceability gap |
| **Linked** | Has at least one traceability edge to a requirement | OK |
| **Broken reference** | Has outgoing edge targeting non-existent node | Warning — stale reference |

### Proposed Health Checks

Replace the single `spec.orphans` check with:

| Check | Scope | Severity | Description |
|-------|-------|----------|-------------|
| `spec.structural_orphans` | All node kinds | Error | Nodes without a FILE parent (build bugs) |
| `tests.unlinked` | TEST nodes | Info | Tests not linked to any requirement |
| `code.unlinked` | CODE nodes | Info | Code refs not linked to any requirement |
| `spec.broken_references` | All edges | Warning | Edges targeting non-existent nodes (new check — broken refs were tracked internally but not health-checked) |

The existing `tests.coverage` and `code.coverage` checks already report
requirement-side coverage gaps. The new `*.unlinked` checks report the inverse:
artifact-side gaps.

### Overlap with Existing Checks

The existing `code.references_resolve` and `tests.references_resolve` health
checks verify that CODE/TEST nodes have a direct parent edge to a REQUIREMENT
or ASSERTION. The new `*.unlinked` checks use graph reachability instead. The
relationship between these checks will be reconciled during implementation —
`references_resolve` may be merged into or replaced by the reachability-based
checks.

### Generalized Reachability API

The graph could expose a generic reachability query:

```text
graph.is_reachable(
    from_node,
    to_kind=NodeKind.REQUIREMENT,
    exclude_edge_kinds={EdgeKind.CONTAINS, EdgeKind.STRUCTURES}
)
```

This would answer questions like:
- "Is this TEST node connected to any requirement?" (validated)
- "Is this CODE node connected to any requirement?" (implemented)
- "Is this TEST_RESULT connected to a TEST connected to a requirement?" (reported)

The health checks would use this API rather than maintaining separate
orphan-tracking state in the builder.

## Impact

- The builder's `_orphan_candidates` mechanism can be simplified or removed —
  structural orphan detection becomes a post-build check on CONTAINS edges.
- Health output becomes more precise: errors for real problems, info for gaps.
- The MCP server's `get_orphaned_nodes()` tool would need updating.
- Test coverage and code coverage checks remain unchanged — they already work
  from the requirement side.

## Decisions

1. **`tests.unlinked` severity**: Info. Tests without requirement links are
   traceability gaps to close, not errors. Every test should eventually
   reference a requirement — create high-level requirements if needed (e.g.,
   "SHALL have integration tests") rather than leaving tests unlinked.
2. **`# elspais: no-traceability` directive**: Not needed. There is no concept
   of intentionally untraceable tests.
3. **`allow_orphans` config**: Replaced with `allow_structural_orphans`. No
   `allow_unlinked_*` flags — unlinked is always a gap to address.
