# Task 7B: rename_file graph mutation + render_save support

**MASTER_PLAN**: KNOWN-ISSUES
**Status**: In Progress

## Description

Add `rename_file()` mutation to TraceGraph that renames a FILE node,
updating its ID, index entry, and path fields. Modify `render_save()` to
handle file renames on disk.

## Baseline

- 2683 passed, 299 deselected — all green

## Tests

- 6 tests in `tests/core/test_file_mutations.py::TestRenameFile`
- All pass: rename, undo, non-file error, log, absolute_path, not found

## Implementation

- `src/elspais/graph/builder.py`: Added `rename_file()` method and `_undo_rename_file()`
- `src/elspais/graph/render.py`: Updated `_find_dirty_files()` for rename_file, move_node_to_file, change_edge_targets
- `src/elspais/graph/render.py`: Updated `render_save()` to rename files on disk before rendering

## Verification

- 2689 passed, 299 deselected — all green, +6 new tests
- Lint clean
