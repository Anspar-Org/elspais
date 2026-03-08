# Task 6: End-to-End Verification

**Status**: Complete

## Description

E2E subprocess tests for all new formats and flags.

**Files:** `tests/e2e/test_cli_commands.py`

## Assertions

APPLICABLE_ASSERTIONS: REQ-p00013-B, REQ-d00085-H, REQ-d00085-J

## Progress

- [x] Baseline: 2244 passed, 66 deselected
- [x] Create TASK_FILE
- [x] Find assertions
- [x] Write tests: 7 e2e tests in TestHealth class
- [x] Verify: 2316 passed (incl e2e), 1 skipped
- [x] Update docs: CHANGELOG.md
- [x] Bump version: 0.96.0 -> 0.97.0
- [x] Commit

## Test Summary

7 e2e tests:
1. health_junit_produces_valid_xml
2. health_junit_has_testsuites
3. health_sarif_produces_valid_json
4. health_sarif_has_runs
5. health_junit_output_to_file
6. health_sarif_output_to_file
7. health_include_passing_details
