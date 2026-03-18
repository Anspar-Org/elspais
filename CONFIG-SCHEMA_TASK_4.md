# Task 4: Version-gated migration system — COMPLETE

## Status: DONE

## Summary

Formalized `_migrate_legacy_patterns()` into a `MIGRATIONS` registry with sequential
version-gated application before Pydantic validation.

## Changes Made

### `src/elspais/config/__init__.py`

- Added `Callable` to the `typing` import
- Added `CURRENT_CONFIG_VERSION = 2` constant after `_migrate_legacy_patterns`
- Added `MIGRATIONS: dict[int, Callable[[dict], dict]]` registry mapping version 1 to
  `_migrate_legacy_patterns`
- Updated `load_config()` to use version-gated sequential migration loop instead of
  direct `_migrate_legacy_patterns` call
- Fixed a latent bug in `_migrate_legacy_patterns`: the guard that prevented overwriting
  user-defined `[id-patterns]` incorrectly short-circuited when `id-patterns` was absent
  entirely (missing key returned `None`, which did not equal the default canonical string).
  Fixed to allow migration when `canonical` is `None` (absent) or equal to the default.

### `tests/core/test_migration.py` (new)

Three tests covering:
- `test_v1_patterns_migrated_to_v2`: bare v1 config gets `[id-patterns]` synthesized
- `test_v2_config_skips_migration`: v2+ config is returned unchanged
- `test_migration_produces_valid_schema`: migrated config passes Pydantic validation

Note: test uses `copy.deepcopy(DEFAULT_CONFIG)` to prevent mutation of the module-level
default dict (a pre-existing hazard in `_migrate_legacy_patterns` that sets namespace
in-place on the shared project sub-dict).

## Test Results

- `pytest tests/core/test_migration.py -v` — 3 passed
- `pytest tests/core/test_config.py -v` — 19 passed
- `pytest --tb=short -q` — 2798 passed, 321 deselected
