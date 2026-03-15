# Task 7A: move_node_to_file graph mutation + undo

**MASTER_PLAN**: KNOWN-ISSUES
**Status**: In Progress

## Description

Add `move_node_to_file()` mutation to TraceGraph that moves a requirement
(or other top-level content node) from one FILE parent to another by
re-wiring the CONTAINS edge. ASSERTION and REMAINDER children follow via
STRUCTURES edges (not CONTAINS), so only the top-level CONTAINS edge needs moving.

## Baseline

- 2677 passed, 299 deselected — all green

## Applicable Assertions

- **REQ-o00063**: MCP File Mutation Tools (move_node_to_file is the graph-level support)

## Tests

- 6 tests in `tests/core/test_file_mutations.py::TestMoveNodeToFile`
- All pass: move, undo, non-file error, orphan error, log, render_order

## Implementation

- `src/elspais/graph/builder.py`: Added `move_node_to_file()` method
- `src/elspais/graph/builder.py`: Added `_undo_move_node_to_file()` method
- `src/elspais/graph/builder.py`: Added `move_node_to_file` dispatch in `_apply_undo()`

## Verification

- 2683 passed, 299 deselected — all green, +6 new tests
- Lint clean
