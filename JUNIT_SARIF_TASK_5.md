# Task 5: CLI Integration and Documentation

**Status**: Complete

## Description

Add `--skip-passing-details` / `--include-passing-details` flags. Wire flags through
renderers. Update docs.

**Files:** `src/elspais/cli.py`, `src/elspais/commands/health.py`, `docs/cli/health.md`

## Assertions

APPLICABLE_ASSERTIONS: REQ-d00085-E, REQ-d00085-F

## Progress

- [x] Baseline: 2233 passed, 66 deselected
- [x] Create TASK_FILE
- [x] Find assertions
- [x] Write failing tests: 11 tests in test_health_detail_flags.py
- [x] Implement: CLI flags, _format_report threading, text/markdown/junit renderers
- [x] Verify: 2244 passed, lint clean
- [x] Update docs: health.md, CHANGELOG.md, CLI epilog
- [x] Bump version: 0.95.0 -> 0.96.0
- [x] Commit
