# Task 5: New load_config() with shim adapter

## Status: COMPLETE

## Summary

Updated `load_config()` to validate configuration through the Pydantic schema (`ElspaisConfig.model_validate()`) while maintaining full backward compatibility via a shim dict produced by `model_dump(by_alias=True, exclude_none=True)`.

## Changes Made

### `src/elspais/config/__init__.py`

- `load_config()` now strips legacy top-level keys (`patterns`, `requirements`, `paths`) and legacy `associates.paths` (list format) before Pydantic validation
- Validates via `ElspaisConfig.model_validate(merged)`
- Produces shim dict via `model_dump(by_alias=True, exclude_none=True)`
- Restores stripped legacy keys into shim dict so existing `config.get()` calls continue working

### `src/elspais/config/schema.py`

Schema fixes required for real-world configs to pass validation:
- `ReferencesConfig`: Added `enabled: bool = True` field
- `ValidationConfig`: Added `hash_algorithm` and `hash_length` optional fields
- `DirectoriesConfig`: Added `database` optional field, changed to `extra="allow"`
- `TraceabilityConfig`: Added `output_formats` and `output_dir` optional fields, changed to `extra="allow"`
- `SpecConfig`: Changed `patterns` type to `list[str] | dict[str, Any]` (some legacy configs use `[spec.patterns]` as a sub-table)

### `tests/core/test_config.py`

- Added `TestPydanticShim` class with two tests:
  - `test_load_config_validates_schema`: v2 config validates and returns correct values
  - `test_load_config_rejects_unknown_key`: v2 config with unknown top-level key is rejected

## Test Results

All 2800 tests pass (plus 321 deselected e2e/browser tests).
