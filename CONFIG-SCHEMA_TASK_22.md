# Task 22: Docs Drift Detection in elspais doctor

**Branch**: config-refactor
**Ticket**: CONFIG-SCHEMA
**Status**: Complete

## Description

Add a `docs.config_drift` health check to `elspais doctor` that walks `ElspaisConfig` fields vs `docs/configuration.md` and reports undocumented/stale fields.

## Applicable Assertions

- **REQ-d00210-A**: `elspais doctor` SHALL include a `docs.config_drift` health check.
- **REQ-d00210-B**: SHALL report undocumented and stale sections.
- **REQ-d00210-C**: SHALL pass when all sections documented, fail otherwise.

## Files

- Modify: `src/elspais/commands/doctor.py`
- Create: `tests/core/test_docs_drift.py`

## Baseline

- 2808 passed, 321 deselected — all green

## Test Summary

- 13 new tests in `tests/core/test_docs_drift.py`
- TestDocsDriftBasic (2 tests) — REQ-d00210-A
- TestDocsDriftPassFail (4 tests) — REQ-d00210-C
- TestDocsDriftDetails (4 tests) — REQ-d00210-B
- TestDocsDriftRealFile (1 test) — REQ-d00210-B
- TestDocsDriftExcludesConditional (2 tests) — REQ-d00210-B

## Implementation Summary

Added `check_docs_drift(docs_path)` to `doctor.py`:
- `_get_schema_sections()` extracts top-level sections from ElspaisConfig fields (alias names)
- `_parse_docs_sections()` extracts `[section]` headers from TOML code blocks in markdown
- Compares and reports undocumented (schema-only) and stale (docs-only) sections
- Excludes conditional sections: associates, core, associated
- Gracefully skips when docs file not found (severity=info)
- Wired into `run()` and added "docs" category to report output

## Verification

- `pytest tests/core/test_docs_drift.py -v` — 13 passed
- `pytest -x -q` — 2821 passed, 321 deselected
