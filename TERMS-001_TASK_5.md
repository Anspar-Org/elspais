# TERMS-001 Task 5: Health Checks — Duplicate, Undefined, Unmarked

## Description
Add three term-related health checks to `commands/health.py` with configurable severity.

## Applicable Assertions
- **REQ-d00223-A**: check_term_duplicates() with duplicate_severity
- **REQ-d00223-B**: check_undefined_terms() with undefined_severity
- **REQ-d00223-C**: check_unmarked_usage() with unmarked_severity, indexed only
- **REQ-d00223-D**: severity "off" skips check (returns passed info)

## Progress
- [x] Baseline: 3247 passed
- [x] TASK_FILE created
- [x] Assertions created: REQ-d00223 A-D
- [x] Failing tests written: tests/test_term_health.py (9 tests)
- [x] Implementation complete
- [x] Verification passed: 3256 passed, 321 deselected
- [x] Version bumped: 0.111.84 -> 0.111.85
- [x] Committed

## Tests
- `test_REQ_d00223_A_duplicates_reported` / `test_REQ_d00223_A_no_duplicates_passes`
- `test_REQ_d00223_B_undefined_terms_reported` / `test_REQ_d00223_B_no_undefined_passes`
- `test_REQ_d00223_C_unmarked_usage_reported` / `test_REQ_d00223_C_no_unmarked_passes`
- `test_REQ_d00223_D_off_severity_skips_duplicates/undefined/unmarked`

## Implementation
- `src/elspais/commands/health.py`: Added check_term_duplicates(), check_undefined_terms(), check_unmarked_usage() with HealthCheck/HealthFinding returns and severity="off" support
