# Task 13: code.no_traceability Health Check

**Branch**: defined-terms2
**Ticket**: CUR-1082
**Status**: In Progress

## Description

Add `check_no_traceability()` to report code/test files with no traceability markers. Wire into `run_code_checks()`.

## Applicable Assertions

- REQ-d00241-A: `check_no_traceability()` reports unlinked code/test files
- REQ-d00241-B: Wired into `run_code_checks()` using `graph.iter_unlinked()`
- REQ-d00241-C: Severity from `[rules.format] no_traceability_severity`

## Progress

- [x] Baseline: tests pass
- [x] Created TASK_FILE
- [x] Assertions exist: REQ-d00241 A-C
- [ ] Write failing tests + implement
- [ ] Verify
- [ ] Bump version
- [ ] Commit
