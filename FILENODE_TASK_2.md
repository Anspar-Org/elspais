# FILENODE_TASK_2 -- GraphNode API Changes

**Branch**: claude/cross-cutting-requirements-2Zd0c
**Ticket**: CUR-1082
**Date**: 2026-03-13
**Baseline**: 2483 passed, 94 deselected

## APPLICABLE_ASSERTIONS

- REQ-d00127-A: `GraphNode` SHALL NOT have an `add_child()` method. All parent-child relationships SHALL be created via `link()` with a typed `EdgeKind`.
- REQ-d00127-B: `GraphNode.remove_child()` SHALL be renamed to `unlink()`, retaining identical behavior.
- REQ-d00127-C: `iter_children()`, `iter_parents()`, `walk()`, and `ancestors()` SHALL accept optional `edge_kinds` parameter for filtered traversal.
- REQ-d00127-D: `GraphNode.file_node()` SHALL walk incoming edges to find nearest FILE ancestor, returning None if not found.
- REQ-d00127-E: TEST_RESULT nodes SHALL be linked from TEST nodes via `EdgeKind.YIELDS` (TEST -> TEST_RESULT), not via CONTAINS.

## Assertions Created

Added REQ-d00127 with assertions A-E to `spec/07-graph-architecture.md`.

## Caller Audit

### add_child callers in production code

1. **Line 486** (`_undo_delete_requirement`): Restoring parent link after undo -> migrate to `link(..., EdgeKind.IMPLEMENTS)` (or restore original edge kind from before_state)
2. **Line 1151** (`add_assertion` mutation): Adding assertion to parent req -> migrate to `link(..., EdgeKind.STRUCTURES)`
3. **Line 1781** (`_add_requirement` in GraphBuilder): Adding assertion/section children in document order -> migrate to `link(..., EdgeKind.STRUCTURES)`
4. **Line 2168** (`_instantiate_satisfies_templates`): Cloning assertion parent-child in template -> migrate to `link(..., EdgeKind.STRUCTURES)`

### remove_child callers in production code

1. **Line 312** (`_undo_add_requirement`): Removing restored node from parents -> rename to `unlink()`
2. **Line 414** (`_undo_fix_broken_reference`): Removing fixed edge -> rename to `unlink()`
3. **Line 442** (`_undo_add_assertion`): Removing added assertion -> rename to `unlink()`
4. **Line 816** (`delete_requirement` mutation): Disconnecting from parents -> rename to `unlink()`
5. **Line 827** (`delete_requirement` mutation): Disconnecting non-assertion children -> rename to `unlink()`
6. **Line 1233** (`delete_assertion` mutation): Removing assertion from parent -> rename to `unlink()`

### add_child callers in test files

- tests/core/test_graph_node.py (many)
- tests/core/test_indirect_coverage.py
- tests/test_pdf_assembler.py
- tests/test_server_app.py
- tests/graph/test_keyword_extraction.py
- tests/graph/test_clone.py
- tests/graph/test_keyword_extraction_generalized.py
- tests/test_server_persistence.py
- tests/mcp/test_mcp_keywords.py
- tests/mcp/test_mcp_core.py
- tests/mcp/test_scoped_search.py
- tests/mcp/test_assertion_test_map.py
- tests/mcp/test_mcp_get_subtree.py
- tests/mcp/test_mcp_cursor.py
- tests/mcp/test_mcp_coverage.py
- tests/mcp/test_mcp_mutations.py
- tests/mcp/test_discover_requirements.py

### TEST_RESULT CONTAINS edge

- builder.py line 1971: `self._pending_links.append((result_id, test_id, EdgeKind.CONTAINS))` -> change to YIELDS
- Note: The resolution at line 2362 does `target.link(source, edge_kind)` which creates TEST->TEST_RESULT direction (correct). Only the EdgeKind needs changing.

## Test Summary

21 new tests added to `tests/core/test_graph_node.py` in class `TestGraphNodeAPIChanges`:

- REQ-d00127-A: `test_add_child_does_not_exist`, `test_link_creates_parent_child`
- REQ-d00127-B: `test_remove_child_does_not_exist`, `test_unlink_severs_all_edges`, `test_unlink_returns_false_for_nonchild`
- REQ-d00127-C: 10 tests for filtered `iter_children`, `iter_parents`, `walk` (pre/post/level), `ancestors`
- REQ-d00127-D: 4 tests for `file_node()` (no file, one hop, two hops, on file node)
- REQ-d00127-E: 2 tests for YIELDS edge direction and kind

## Implementation Summary

### GraphNode.py changes

- Removed `add_child()` method entirely
- Renamed `remove_child()` to `unlink()` with identical behavior
- Added `edge_kinds: set[EdgeKind] | None` parameter to `iter_children()`, `iter_parents()`
- Added `edge_kinds` parameter to `walk()`, propagated to `_walk_preorder`, `_walk_postorder`, `_walk_level`
- Added `edge_kinds` parameter to `ancestors()`
- Added `file_node()` method walking incoming edges to find nearest FILE ancestor
- Added `# Implements: REQ-d00127-A, REQ-d00127-B, REQ-d00127-C, REQ-d00127-D` comments

### builder.py changes

- 4 `add_child()` callers migrated to `link(..., EdgeKind.STRUCTURES)`
- 6 `remove_child()` callers renamed to `unlink()`
- TEST_RESULT edge changed from `EdgeKind.CONTAINS` to `EdgeKind.YIELDS`
- Updated docstring for `_add_test_result`

### Test file changes

- 17 test files updated to replace `add_child(x)` with `link(x, EdgeKind.STRUCTURES)`
- TEST->TEST_RESULT edges in 4 test files changed from STRUCTURES to YIELDS
- 3 edge mutation tests updated to filter by edge kind when checking outgoing edges
- Comments in test_builder.py updated (CONTAINS -> YIELDS for TEST_RESULT)
- EdgeKind imports added where needed

## Verification

- **2504 passed, 94 deselected** (21 new tests added to baseline of 2483)
- Zero remaining `add_child(` or `remove_child(` references in `src/`
- `pytest tests/test_doc_sync.py` passes (68 tests)
- Version bumped to 0.104.2
