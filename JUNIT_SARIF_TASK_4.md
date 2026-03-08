# Task 4: SARIF JSON Renderer

**Status**: Complete

## Description

Add `_render_sarif(report: HealthReport) -> str` to `commands/health.py`. SARIF v2.1.0
compliant. One `reportingDescriptor` per unique check name, one `result` per
`HealthFinding` with physical locations. Passing checks omitted. Coverage stats
in `run.properties`. Wire into `_output_report()` as `--format sarif`.

**Files:** `src/elspais/commands/health.py`, `src/elspais/cli.py`

## Assertions

APPLICABLE_ASSERTIONS: REQ-d00085-J (SARIF output format)

## Progress

- [x] Baseline: 2214 passed, 66 deselected
- [x] Create TASK_FILE
- [x] Find assertions: REQ-d00085-J (created in Task 2)
- [x] Write failing tests: 19 tests in test_health_sarif.py
- [x] Implement: _render_sarif in health.py, --format sarif in cli.py, FORMAT_SUPPORT updated
- [x] Verify: 2233 passed, lint clean
- [x] Update docs: health.md SARIF section, CHANGELOG.md entry
- [x] Bump version: 0.94.0 -> 0.95.0
- [x] Commit

## Test Summary

19 tests across 11 classes covering:
- SARIF envelope (schema, version, tool driver)
- reportingDescriptor mapping
- Result per HealthFinding
- Severity mapping (error/warning/info → error/warning/note)
- Physical locations (file_path → artifactLocation.uri)
- Region (line → startLine)
- Passing checks omitted
- Format dispatch integration
- All-passing empty results
- run.properties coverage stats
- ruleIndex correspondence
