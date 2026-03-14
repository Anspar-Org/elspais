# FILENODE5 Task 1: MCP and Traversal Integration

**Branch**: claude/cross-cutting-requirements-2Zd0c
**Ticket**: CUR-1082
**Status**: Complete

## Applicable Assertions

- **REQ-d00133-A**: `_get_subtree()` from FILE walks CONTAINS edges
- **REQ-d00133-B**: `_get_subtree()` from REQUIREMENT walks domain edges (IMPLEMENTS, REFINES, STRUCTURES)
- **REQ-d00133-C**: `_SUBTREE_KIND_DEFAULTS` includes FILE entry
- **REQ-d00133-D**: `_search()` excludes FILE nodes from results
- **REQ-d00133-E**: `_get_graph_status()` includes FILE node counts
- **REQ-d00133-F**: MCP serialization produces identical file/line fields

## New Assertions Added

Created REQ-d00133 "MCP FILE Node Integration" in `spec/08-mcp-server.md` with assertions A-F.

## Test Summary

13 new tests in `tests/mcp/test_mcp_file_node_integration.py`:
- 4 tests for REQ-d00133-A (FILE subtree walks CONTAINS, no domain crossing, markdown/nested formats)
- 2 tests for REQ-d00133-B (REQ subtree walks domain edges, excludes FILE nodes)
- 1 test for REQ-d00133-C (_SUBTREE_KIND_DEFAULTS includes FILE)
- 2 tests for REQ-d00133-D (search excludes FILE nodes, returns only requirements)
- 1 test for REQ-d00133-E (graph status reports FILE count)
- 3 tests for REQ-d00133-F (serialize_test_info, serialize_code_info, relative_source_path)

## Implementation Summary

Changes to `src/elspais/mcp/server.py`:
- Added `NodeKind.FILE` to `_SUBTREE_KIND_DEFAULTS` with `{REQUIREMENT, ASSERTION, REMAINDER}`
- Added `_SUBTREE_EDGE_DEFAULTS` dict mapping root kinds to edge-kind filter sets:
  - FILE -> {CONTAINS}
  - REQUIREMENT -> {IMPLEMENTS, REFINES, STRUCTURES}
- Modified `_collect_subtree()` to use `edge_filter` from `_SUBTREE_EDGE_DEFAULTS` when calling `iter_children(edge_kinds=edge_filter)`
- Modified `_subtree_to_nested()` to accept and propagate `_edge_filter` parameter
- Modified `_get_subtree()` to pass edge filter to `_subtree_to_nested()`

## Verification

- All 2589 tests pass (2576 baseline + 13 new)
- Doc sync tests pass
- No lint issues

## Notes

- REQ-d00133-D/E/F were already satisfied by existing code; tests confirm correctness
- The main implementation work was REQ-d00133-A/B/C: filtered traversal in subtree extraction
