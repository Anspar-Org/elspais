# CONFIG-SCHEMA Task 3: Cross-field validators

## Status: COMPLETE

## Summary

Added Pydantic `@model_validator(mode="after")` cross-field constraint to `ElspaisConfig`.

### Changes

**`src/elspais/config/schema.py`**
- Added `model_validator` to pydantic imports
- Added `check_associated_requires_core` method to `ElspaisConfig`: raises `ValueError` when `project.type='associated'` and `core` is `None`

**`tests/core/test_schema.py`**
- Added `test_associated_requires_core`: verifies ValidationError is raised when associated project lacks `[core]`
- Added `test_associated_with_core_passes`: verifies valid associated+core config passes
- Added `test_status_roles_reference_allowed_statuses`: verifies `status_roles` + `allowed_statuses` coexistence works

### Test Results

- `pytest tests/core/test_schema.py -v`: 8/8 passed
- `pytest --tb=short -q`: 2795 passed, 321 deselected (no regressions)
