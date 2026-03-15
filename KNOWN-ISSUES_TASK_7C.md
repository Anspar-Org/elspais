# Task 7C: MCP + Flask + Viewer integration for file mutations

**MASTER_PLAN**: KNOWN-ISSUES
**Status**: In Progress

## Description

Expose `move_node_to_file` and `rename_file` via MCP tools, Flask API
endpoints, and basic viewer UI.

## Baseline

- 2689 passed, 299 deselected — all green

## Tests

- 4 tests in `tests/mcp/test_mcp_mutations.py` (TestMutateMoveNodeToFile, TestMutateRenameFile)

## Implementation

- `src/elspais/mcp/server.py`: Added MCP tools `mutate_change_edge_targets`, `mutate_move_node_to_file`, `mutate_rename_file`
- `src/elspais/mcp/server.py`: Added helper functions `_mutate_move_node_to_file`, `_mutate_rename_file`
- `src/elspais/server/app.py`: Added Flask endpoints `/api/mutate/move-to-file`, `/api/mutate/rename-file`
- `src/elspais/html/templates/partials/js/_card-stack.js.j2`: Added "Move" button in metadata
- `src/elspais/html/templates/partials/js/_edit-engine.js.j2`: Added `onMoveToFile()`, `onRenameFile()`
- `src/elspais/html/templates/partials/js/_file-viewer.js.j2`: Show rename button when file loaded
- `src/elspais/html/templates/partials/_file_viewer.html.j2`: Added rename button
- `src/elspais/html/templates/partials/css/_card-stack.css.j2`: Added move button styles

## Manual Test Plan

1. Open card, click "Move" button next to source path
2. Enter target file ID, confirm — card updates with new source
3. Open file viewer, click "Rename" button
4. Enter new path, confirm — file renames on save

## Verification

- 2693 passed, 299 deselected — all green, +4 new tests
- Lint clean
