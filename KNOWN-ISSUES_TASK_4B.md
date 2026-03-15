# Task 4B: Assertion target picker UI (server + viewer)

**MASTER_PLAN**: KNOWN-ISSUES
**Status**: In Progress

## Description

Expose `change_edge_targets` via the Flask API and add an assertion target
picker dropdown in the card edge UI.

## Baseline

- 2674 passed, 299 deselected — all green

## Applicable Assertions

- **REQ-o00062-C**: Edge mutations SHALL include change_edge_targets.
- **REQ-o00062-E**: All mutations SHALL return a MutationEntry for audit and undo.
- **REQ-d00065-D**: Mutation tools SHALL NOT implement mutation logic.

## Tests

- 3 tests in `tests/mcp/test_mcp_mutations.py::TestMutateChangeEdgeTargets`
- All pass: delegation, mutation entry, error case

## Implementation

- `src/elspais/mcp/server.py`: Added `_mutate_change_edge_targets()` helper
- `src/elspais/server/app.py`: Added `change_targets` action to `/api/mutate/edge`, imported helper
- `src/elspais/html/templates/partials/js/_card-stack.js.j2`: Added assertion targets display and picker button
- `src/elspais/html/templates/partials/js/_edit-engine.js.j2`: Added `editEdgeTargets()` and `applyEdgeTargets()` functions
- `src/elspais/html/templates/partials/css/_card-stack.css.j2`: Added styles for targets display/picker

## Manual Test Plan

1. Open card with edge to requirement that has assertions
2. Click vertical-ellipsis button on edge row (edit mode)
3. Checkbox popup shows target's assertions
4. Check/uncheck assertions, confirm
5. Edge updates to show assertion targets

## Verification

- 2677 passed, 299 deselected — all green, +3 new tests
- Lint clean
