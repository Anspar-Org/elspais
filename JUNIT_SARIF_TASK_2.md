# Task 2: HealthFinding Dataclass and Serialization

**Status**: Complete

## Description

Add `HealthFinding` dataclass to `commands/health.py` with fields: `message`,
`file_path`, `line`, `node_id`, `related`. Add `findings: list[HealthFinding]`
field to `HealthCheck`. Update `to_dict()` to include findings. Existing renderers
remain unchanged.

**Files:** `src/elspais/commands/health.py`

## Assertions

APPLICABLE_ASSERTIONS: REQ-d00085-I (new — HealthFinding dataclass)

## Progress

- [x] Baseline: 2194 passed, 66 deselected
- [x] Create TASK_FILE
- [x] Find/create assertions: Added REQ-d00085-I and REQ-d00085-J (for Task 4)
- [x] Write failing tests: 11 tests in tests/commands/test_health_finding.py
- [x] Implement: HealthFinding dataclass, findings field on HealthCheck, to_dict serialization
- [x] Verify: 2205 passed, lint clean
- [x] Update docs: CHANGELOG.md entry
- [x] Bump version: 0.92.0 -> 0.93.0
- [x] Commit
