# TERMS-001 Task 7: CLI Registration and Fix Integration

## Description
Register `elspais glossary` and `elspais term-index` commands. Wire generation into `elspais fix`.

## Applicable Assertions
- **REQ-d00225-A**: GlossaryArgs/TermIndexArgs in args.py, Command union, _CMD_MAP
- **REQ-d00225-B**: elspais fix calls glossary + term-index generation

## Progress
- [x] Baseline: 3265 passed
- [x] TASK_FILE created
- [x] Assertions created: REQ-d00225 A-B
- [x] Failing tests written: tests/test_cli_terms.py (9 tests)
- [x] Implementation complete
- [x] Verification passed: 3274 passed, 321 deselected
- [x] Version bumped: 0.111.86 -> 0.111.87
- [x] Committed
