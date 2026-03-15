# Task 4A: change_edge_targets graph mutation + undo

**MASTER_PLAN**: KNOWN-ISSUES
**Status**: In Progress

## Description

Add a `change_edge_targets()` mutation to TraceGraph that changes the
assertion_targets on an existing IMPLEMENTS/REFINES edge without requiring
delete+add. This enables changing a REQ->REQ link to target specific
assertions or vice versa.

## Baseline

- 2666 passed, 299 deselected (33.54s) — all green

## Applicable Assertions

- **REQ-o00062-C** (updated): Edge mutations SHALL include: add_edge, change_edge_kind, change_edge_targets, delete_edge, fix_broken_reference.
- **REQ-o00062-D**: All mutations SHALL delegate to TraceGraph mutation methods.
- **REQ-o00062-E**: All mutations SHALL return a MutationEntry for audit and undo.
- **REQ-o00062-G**: undo_last_mutation() and undo_to_mutation(id) SHALL reverse mutations.
- **REQ-d00065-D**: Mutation tools SHALL NOT implement mutation logic — only parameter validation and delegation.
- **REQ-d00065-E**: Mutation tools SHALL return the MutationEntry from the graph method for audit trail.

## Spec Changes

- Updated REQ-o00062-C in `spec/08-mcp-server.md:97` to include `change_edge_targets`.

## Tests

- 8 tests in `tests/core/test_edge_mutations.py::TestChangeEdgeTargets`
- All pass: req-to-assertion, assertion-to-req, mutation entry, undo, error cases, log

## Implementation

- `src/elspais/graph/builder.py`: Added `change_edge_targets()` method (after `change_edge_kind()`)
- `src/elspais/graph/builder.py`: Added `_undo_change_edge_targets()` method (after `_undo_change_edge_kind()`)
- `src/elspais/graph/builder.py`: Added `change_edge_targets` dispatch in `_apply_undo()`

## Verification

- 2674 passed, 299 deselected (33.81s) — all green, +8 new tests
- Lint clean
