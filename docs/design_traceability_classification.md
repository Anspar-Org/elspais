# Design: Traceability Classification and Orphan Redesign

## Problem Statement

A single `spec.orphans` health check conflated three distinct concepts into one
warning. After the test scanner began emitting TEST nodes for all test functions
(not just those referencing requirements), 475 "orphaned" TEST nodes appeared —
structurally sound nodes that simply lacked requirement traceability. They are
not errors, but the check treated them identically to genuinely broken nodes.

## The Behavior This Replaced

The builder tracked `_orphan_candidates` — any node that was never the source of
a resolved pending link (IMPLEMENTS, VERIFIES, YIELDS, etc.). At build
finalization, candidates that were not classified as roots became orphans. The
`spec.orphans` health check reported all of them as a single warning.

That conflates:

1. **Structural orphans** — nodes that failed to wire into the graph at all (no
   FILE parent via CONTAINS). These indicate build pipeline bugs.
2. **Unlinked nodes** — nodes with a FILE parent but no traceability edge to any
   requirement. These are traceability gaps that need attention.
3. **Broken references** — nodes whose outgoing edges target non-existent nodes.
   These indicate stale or incorrect references.

## The Model

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

Traceability status is defined by reachability through non-structural edges.
Given a requirement node, the following statuses are computed by walking
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

### Health Checks

The single `spec.orphans` check is replaced by:

| Check | Scope | Severity | Description |
|-------|-------|----------|-------------|
| `spec.structural_orphans` | All node kinds | Error | Nodes without a FILE parent (build bugs) |
| `tests.unlinked` | TEST nodes | Info | Tests not linked to any requirement |
| `code.unlinked` | CODE nodes | Info | Code refs not linked to any requirement |
| `spec.broken_references` | All edges | Warning | Edges targeting non-existent nodes |

The existing `tests.coverage` and `code.coverage` checks already report
requirement-side coverage gaps. The new `*.unlinked` checks report the inverse:
artifact-side gaps.

The per-file `code.references_resolve` and `tests.references_resolve` checks,
which asked only whether a CODE/TEST node had a direct parent edge to a
REQUIREMENT or ASSERTION, are subsumed by the reachability-based `*.unlinked`
checks. Reference resolution itself remains checked on the spec side, by
`spec.implements_resolve` and `spec.refines_resolve`.

### Reachability API

The graph answers the reachability question directly: `is_reachable_to_requirement(node)`
walks the node's ancestors across traceability edges only (excluding CONTAINS
and STRUCTURES) and reports whether any of them is a REQUIREMENT. `iter_unlinked(kind)`
and `iter_structural_orphans()` build on it.

This answers questions like:
- "Is this TEST node connected to any requirement?" (validated)
- "Is this CODE node connected to any requirement?" (implemented)
- "Is this TEST_RESULT connected to a TEST connected to a requirement?" (reported)

The health checks use this API rather than maintaining separate orphan-tracking
state in the builder.

## Impact

- Structural orphan detection is a post-build check on CONTAINS edges rather
  than orphan-candidate bookkeeping during the build.
- Health output is more precise: errors for real problems, info for gaps.
- Test coverage and code coverage checks are unchanged — they already work
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
