# Task 4: Make render_save() Federation-Aware

**Branch**: claude/cross-cutting-requirements-2Zd0c
**Ticket**: CUR-1082
**Status**: In Progress

## Description

Update render_save() to use per-repo repo_root from FederatedGraph. Default
repo_root parameter to graph.repo_root. Resolve file paths via owning repo.

## Baseline

- 2728 passed, 299 deselected in 34.92s

## Implementation Summary

Updated `src/elspais/graph/render.py` render_save():
- Made `repo_root` parameter optional (defaults to `graph.repo_root`)
- File path resolution uses `graph.repo_for(file_id).repo_root`
- Rename path resolution uses `graph.repo_for(new_file_id).repo_root`
- Graceful fallback via `hasattr(graph, "repo_for")` for bare TraceGraph callers

## Verification

- 2728 passed, 299 deselected (full suite)
- Lint clean (ruff)
