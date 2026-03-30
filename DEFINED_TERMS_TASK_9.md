# Task 9: Term Reference Scanner Core

**Branch**: defined-terms2
**Ticket**: CUR-1082
**Status**: In Progress

## Description

Implement `scan_text_for_terms()` in `src/elspais/graph/term_scanner.py` with three-way classification: marked, wrong-marking, and unmarked term references.

## Applicable Assertions

- REQ-d00237-A: `scan_text_for_terms()` returns `list[TermRef]` with three-way classification
- REQ-d00237-B: Configured markup styles detected as `marked=True`
- REQ-d00237-C: Non-configured emphasis delimiters detected as `wrong_marking`
- REQ-d00237-D: Indexed terms get whole-word case-insensitive unmarked scanning
- REQ-d00237-E: Non-indexed terms skip unmarked scanning

## Progress

- [x] Baseline: tests pass (3436 passed)
- [x] Created TASK_FILE
- [x] Assertions exist: REQ-d00237 A-E
- [ ] Write failing tests
- [ ] Implement
- [ ] Verify
- [ ] Bump version
- [ ] Commit
