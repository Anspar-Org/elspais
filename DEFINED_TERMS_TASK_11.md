# Task 11: Federated Graph Term Scanner Pass

**Branch**: defined-terms2
**Ticket**: CUR-1082
**Status**: In Progress

## Description

Wire `scan_graph()` into `FederatedGraph` after `_merge_terms()` so that cross-repo term references resolve using the merged `TermDictionary`.

## Applicable Assertions

- REQ-d00239-A: Scanner runs across all repos using merged TermDictionary
- REQ-d00239-B: Each repo's scan uses its own config for `markup_styles` and `exclude_files`

## Progress

- [x] Baseline: tests pass (3460 passed)
- [x] Created TASK_FILE
- [x] Assertions exist: REQ-d00239 A-B
- [ ] Write failing tests
- [ ] Implement
- [ ] Verify
- [ ] Bump version
- [ ] Commit
