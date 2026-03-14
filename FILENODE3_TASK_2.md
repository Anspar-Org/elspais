# Task 2: Render-Based Save (replace persistence.py)

**Branch**: claude/cross-cutting-requirements-2Zd0c
**Ticket**: CUR-1082
**Status**: Complete

## Description

`save_mutations()` writes dirty FILE nodes to disk by rendering their CONTAINS children. `persistence.py` is deleted. After saving, graph is rebuilt from disk and compared to in-memory graph as consistency check.

## APPLICABLE_ASSERTIONS

- REQ-d00132-A: save_mutations() identifies dirty FILE nodes and renders them to disk
- REQ-d00132-B: Safety branches created when save_branch=True
- REQ-d00132-C: Consistency check (rebuild + compare) on by default, skippable
- REQ-d00132-D: persistence.py deleted and replaced
- REQ-d00132-E: Mutation log and undo continue to work, log cleared after save
- REQ-d00132-F: Derives implements/refines from live graph edges

## Assertions Created

Added REQ-d00132 with assertions A-F to spec/07-graph-architecture.md.

## Test Summary

17 tests in tests/core/test_render_save.py:
- TestRenderSaveDirtyFiles: 7 tests (A - change_status, update_title, update_assertion, delete_assertion, add_assertion, no_mutations, add_requirement)
- TestRenderSaveMutationLog: 2 tests (E - log cleared, log not cleared on error)
- TestRenderSaveEdgeDerivation: 3 tests (F - implements from edges, add edge reflected, delete edge reflected)
- TestConsistencyCheck: 4 tests (C - passes, detects mismatch, skipped by default, handles rebuild failure)
- TestPersistenceDeleted: 1 test (D - persistence.py deleted)

26 tests in tests/test_server_persistence.py (migrated from replay_mutations_to_disk to render_save):
- TestSaveChangeStatus, TestSaveUpdateTitle, TestSaveUpdateAssertion, TestSaveAddAssertion
- TestSaveEdgeMutations, TestMultipleMutationsSameReq, TestNoSourceFile, TestEmptyMutationLog
- TestEdgeCoalescing, TestAssertionTargetPersistence, TestSaveRefinesEdge
- TestSaveDeleteAssertion, TestSaveRenameAssertion, TestSaveAddRequirement, TestSaveDeleteRequirement

## Implementation Summary

Modified: src/elspais/graph/render.py
- render_save() now accepts consistency_check and rebuild_fn parameters
- _run_consistency_check() compares requirement/assertion nodes between original and rebuilt graph
- `render_save()` already existed from Task 1 with `_find_dirty_files`, `_wire_new_requirements_to_files`

Deleted: src/elspais/server/persistence.py
- replay_mutations_to_disk() removed (replaced by render_save)
- check_for_external_changes() removed
- All imports and references cleaned up

Migrated: tests/test_server_persistence.py
- All 26 tests rewritten to use render_save() instead of replay_mutations_to_disk()
- Graph fixtures use FILE nodes, CONTAINS edges, STRUCTURES edges
- Tests validate same behaviors: status changes, title updates, assertion mutations, edge coalescing, refines edges, assertion targets, delete/rename assertions, add/delete requirements

Fixed: tests/core/test_render_save.py
- Fixed test_REQ_d00132_F_add_edge_reflected: was passing string "IMPLEMENTS" instead of EdgeKind.IMPLEMENTS
- Added 4 consistency check tests (REQ-d00132-C)

## Verify

- 2570 tests pass (2562 baseline - 7 removed old persistence tests + 4 consistency + 11 other new/adjusted)
- Lint clean
- Doc sync tests pass

## Progress

- [x] Baseline: 2562 tests passing (with 2 expected failures)
- [x] Create TASK_FILE
- [x] Find assertions
- [x] Create assertions (REQ-d00132 A-F)
- [x] Write failing tests (already existed from prior session)
- [x] Implement
- [x] Verify: 2570 passed, lint clean
- [x] Update docs (CHANGELOG.md, CLAUDE.md)
- [x] Bump version (0.104.7)
- [x] Commit
