# Task 12: New Health Checks

**Branch**: defined-terms2
**Ticket**: CUR-1082
**Status**: In Progress

## Description

Add three new health check functions for term quality: `check_term_unused`, `check_term_bad_definition`, `check_term_collection_empty`. Wire them into `run_term_checks()`.

## Applicable Assertions

- REQ-d00240-A: `check_term_unused()` reports terms with zero references
- REQ-d00240-B: `check_term_bad_definition()` reports blank/trivial definitions
- REQ-d00240-C: `check_term_collection_empty()` reports collection terms with zero references
- REQ-d00240-D: `run_term_checks()` calls all six checks

## Progress

- [x] Baseline: tests pass (3466 passed)
- [x] Created TASK_FILE
- [x] Created assertions: REQ-d00240 A-D
- [ ] Write failing tests
- [ ] Implement
- [ ] Verify
- [ ] Bump version
- [ ] Commit
