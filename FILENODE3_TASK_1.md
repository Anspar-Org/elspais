# Task 1: Render Protocol

**Branch**: claude/cross-cutting-requirements-2Zd0c
**Ticket**: CUR-1082
**Status**: Complete

## Description

Each domain NodeKind learns to render itself back to text. Walking a FILE node's CONTAINS children in render_order and concatenating output produces the file's content.

## APPLICABLE_ASSERTIONS

- REQ-d00131-A: Each NodeKind SHALL have a render() function dispatched by kind
- REQ-d00131-B: REQUIREMENT renders full block (header, metadata, body, assertions, sections, End marker with hash)
- REQ-d00131-C: ASSERTION rendered by parent REQUIREMENT, not independently (ValueError if called directly)
- REQ-d00131-D: REMAINDER renders raw text verbatim
- REQ-d00131-E: USER_JOURNEY renders full block
- REQ-d00131-F: CODE renders # Implements: comment line(s)
- REQ-d00131-G: TEST renders # Tests: / # Validates: comment line(s)
- REQ-d00131-H: TEST_RESULT raises ValueError (read-only)
- REQ-d00131-I: FILE node renders by walking CONTAINS children sorted by render_order
- REQ-d00131-J: Order-independent assertion hashing (sort individual hashes before combining)

## Assertions Created

Added REQ-d00131 with assertions A-J to spec/07-graph-architecture.md.

## Test Summary

31 tests in tests/core/test_render_protocol.py:
- TestRenderDispatch: 3 tests (A - dispatch, import, unknown kind)
- TestRequirementRender: 9 tests (B - header, metadata, implements, end marker, assertions, sections, body, separator, full structure)
- TestAssertionRender: 1 test (C - raises ValueError)
- TestRemainderRender: 3 tests (D - verbatim, whitespace, empty)
- TestJourneyRender: 2 tests (E - body, actor/goal)
- TestCodeRender: 2 tests (F - single line, multi line)
- TestTestRender: 2 tests (G - single line, validates)
- TestTestResultRender: 1 test (H - raises ValueError)
- TestFileRender: 4 tests (I - children in order, render_order, empty, mixed kinds)
- TestOrderIndependentHashing: 4 tests (J - order independence, text change, length, sort)

## Implementation Summary

New file: src/elspais/graph/render.py
- render_node(node) - dispatches by NodeKind
- render_file(node) - walks CONTAINS children by render_order
- compute_requirement_hash(assertions) - order-independent hashing
- _render_requirement(node) - full REQ block
- _render_remainder(node) - raw text verbatim
- _render_journey(node) - full journey body
- _render_code(node) - raw_text field
- _render_test(node) - raw_text field

Modified: src/elspais/graph/builder.py
- CODE nodes now store raw_text field
- TEST nodes now store raw_text field
- REQUIREMENT nodes now store implements_refs, refines_refs, satisfies_refs

## Verify

- 2562 tests pass (2531 original + 31 new)
- Lint clean
- Doc sync tests pass

## Progress

- [x] Baseline: 2531 tests passing
- [x] Create TASK_FILE
- [x] Find assertions
- [x] Create assertions (REQ-d00131 A-J)
- [x] Write failing tests (31 tests)
- [x] Implement
- [x] Verify: 2562 passed, lint clean
- [x] Update docs (CHANGELOG.md, CLAUDE.md)
- [x] Bump version (0.104.6)
- [x] Commit
