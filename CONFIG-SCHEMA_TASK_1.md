# CONFIG-SCHEMA Task 1: Add Pydantic Dependency

**Status:** Complete
**Branch:** config-refactor

## Task Description

Add `"pydantic>=2.0"` to `pyproject.toml` core dependencies. Install and verify existing tests still pass.

## Assertions

**APPLICABLE_ASSERTIONS:** None — no existing requirements cover config schema/Pydantic. Requirements will be created in Task 2.

## Test Summary

No new tests needed — this is a dependency addition. Existing `tests/core/test_config.py` still passes.

**Baseline:** 2787 passed, 321 deselected (27.83s)
**Post-change:** 2787 passed, 321 deselected (25.95s)

## Implementation Summary

- Added `"pydantic>=2.0"` to `pyproject.toml` core dependencies (line 29)
- Updated dependency comment to reflect both tomlkit and pydantic
- Installed pydantic 2.12.5 via `pip install -e ".[dev]"`
- Bumped version 0.104.43 -> 0.104.44
- Updated CHANGELOG.md

## Verify

- All 2787 tests pass
- pydantic 2.12.5 importable
