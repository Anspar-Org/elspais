# Task 10: Graph-Wide Term Scan

**Branch**: defined-terms2
**Ticket**: CUR-1082
**Status**: In Progress

## Description

Implement `scan_graph()` in `src/elspais/graph/term_scanner.py` that populates `TermEntry.references` by scanning graph nodes for term occurrences.

## Applicable Assertions

- REQ-d00238-A: `scan_graph()` populates `TermEntry.references`
- REQ-d00238-B: REQUIREMENT, ASSERTION, REMAINDER (not definition_block), JOURNEY scanned via full text
- REQ-d00238-C: CODE and TEST nodes scanned via comment extraction only
- REQ-d00238-D: `exclude_files` glob patterns skip matching files

## Progress

- [x] Baseline: tests pass (3449 passed)
- [x] Created TASK_FILE
- [x] Assertions exist: REQ-d00238 A-D
- [ ] Write failing tests
- [ ] Implement
- [ ] Verify
- [ ] Bump version
- [ ] Commit
