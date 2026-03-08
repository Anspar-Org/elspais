# Task 1: JUnit XML Renderer

**Status**: Complete

## Description

Add `_render_junit(report: HealthReport) -> str` to `commands/health.py`. Use
`xml.etree.ElementTree` (stdlib). Map categories to `<testsuite>` elements, checks
to `<testcase>` elements. Wire into `_output_report()` as `--format junit`.

**Files:** `src/elspais/commands/health.py`, `src/elspais/cli.py`

## Assertions

APPLICABLE_ASSERTIONS: REQ-d00085-H (new — JUnit XML output format)

## Progress

- [x] Baseline: 2184 passed, 66 deselected
- [x] Create TASK_FILE
- [x] Find/create assertions: Added REQ-d00085-H to spec/dev-cli-report.md
- [x] Write failing tests: 10 tests in tests/commands/test_health_junit.py
- [x] Implement: _render_junit in health.py, --format junit in cli.py, FORMAT_SUPPORT updated
- [x] Verify: 2194 passed, lint clean
- [x] Update docs: health.md JUnit section, CHANGELOG.md entry, doc sync passes
- [x] Bump version: 0.91.0 -> 0.92.0
- [x] Commit

## Test Summary

10 tests in TestRenderJunit class:
1. test_REQ_d00085_H_produces_valid_xml_with_testsuites_root
2. test_REQ_d00085_H_category_maps_to_testsuite
3. test_REQ_d00085_H_check_maps_to_testcase
4. test_REQ_d00085_H_passing_check_has_no_failure
5. test_REQ_d00085_H_failed_error_produces_failure_element
6. test_REQ_d00085_H_failed_warning_produces_system_err
7. test_REQ_d00085_H_info_check_produces_system_out
8. test_REQ_d00085_H_format_report_dispatches_junit
9. test_REQ_d00085_H_testsuite_counts
10. test_REQ_d00085_H_empty_report_produces_valid_xml

## Implementation Summary

- Added `_render_junit()` to health.py using xml.etree.ElementTree
- Added `_format_details()` helper for dict-to-text conversion in XML bodies
- Updated `_format_report()` to dispatch format="junit"
- Updated CLI --format choices to include "junit"
- Updated FORMAT_SUPPORT in report.py
