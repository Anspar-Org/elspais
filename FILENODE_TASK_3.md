# FILENODE_TASK_3: FILE Node Creation in Build Pipeline

**Branch**: claude/cross-cutting-requirements-2Zd0c
**Ticket**: CUR-1082
**Date**: 2026-03-13

## Description

Create FILE nodes for every scanned file in factory.py before parsing. Wire CONTAINS edges from FILE to top-level content nodes in GraphBuilder. Make RemainderParser mandatory for text-based file types (SPEC, JOURNEY, CODE, TEST) but not RESULT.

## APPLICABLE_ASSERTIONS

- REQ-d00128-A: factory.py creates FILE node with `file:<relative-path>` ID
- REQ-d00128-B: FILE node content fields (file_type, paths, repo, git info)
- REQ-d00128-C: git_branch/git_commit captured once per repo
- REQ-d00128-D: CONTAINS edges from FILE to top-level content nodes
- REQ-d00128-E: CONTAINS edge metadata (start_line, end_line, render_order)
- REQ-d00128-F: ASSERTIONs/section REMAINDERs do NOT get CONTAINS from FILE
- REQ-d00128-G: RemainderParser mandatory for SPEC, JOURNEY, CODE, TEST
- REQ-d00128-H: RemainderParser NOT registered for RESULT
- REQ-d00128-I: Additive -- existing behavior unaffected

**New requirement created**: REQ-d00128 in `spec/07-graph-architecture.md`

## Test Summary

24 new tests in `tests/core/test_file_node_build_pipeline.py`:
- TestFileNodeCreation (3 tests): FILE node creation with correct ID format
- TestFileNodeContentFields (4 tests): file_type, paths, repo fields
- TestGitInfoCapture (2 tests): git_branch/git_commit presence and consistency
- TestContainsEdges (3 tests): CONTAINS edges from FILE to REQ/CODE
- TestContainsEdgeMetadata (3 tests): start_line, render_order, sequential ordering
- TestAssertionsNotContained (3 tests): ASSERTIONs/sections NOT CONTAINS children
- TestRemainderParserRegistration (2 tests): REMAINDER nodes in spec/code files
- TestExistingBehaviorUnaffected (4 tests): coverage, roots, orphans, node count

## Implementation Summary

**factory.py**: Added `_capture_git_info()`, `_create_file_node()`, `_get_or_create_file_node()`. Modified all scanning loops to create FILE nodes and pass them to builder. Registered RemainderParser in spec, code, and test registries but NOT result registries.

**builder.py**: Added `register_file_node()` method to index FILE nodes without orphan tracking. Added `_wire_contains_edge()` method for FILE-to-content CONTAINS edges with metadata. Modified `add_parsed_content()` to accept `file_node` parameter and wire CONTAINS edges for all top-level content types.

**validate.py**: Updated orphan detection to ignore FILE parents (CONTAINS edges), preserving existing orphan behavior.

**git.py**: Added `get_current_commit()` utility function.

**spec/07-graph-architecture.md**: Added REQ-d00128 with 9 assertions.

## Test Results

2528 passed, 94 deselected (24 new tests + 2504 existing)

## Progress

- [x] Baseline tests pass (2504 passed)
- [x] Requirement created (REQ-d00128)
- [x] Tests written (24 tests)
- [x] Implementation complete
- [x] All tests pass (2528 passed)
- [x] Docs updated (CHANGELOG.md, CLAUDE.md)
- [x] Version bumped (0.104.3)
- [x] Committed (95a9235)
