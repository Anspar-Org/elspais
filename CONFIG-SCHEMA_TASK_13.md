# Task 13: Delete Dead Config Helper Functions

## Summary

Deleted `get_project_name()` and `validate_project_config()` from
`src/elspais/config/__init__.py`, and removed both (plus `ConfigValidationError`)
from `__all__`. Updated three files that still had hidden callers.

## Deleted from `config/__init__.py`

| Symbol | Lines removed | Replacement pattern |
|--------|--------------|---------------------|
| `get_project_name()` | ~10 lines | `typed_config.project.name or "unknown"` |
| `validate_project_config()` | ~55 lines | pydantic `ValidationError` from `_validate_config()` |
| `ConfigValidationError` | ~5 lines | (no callers; removed from `__all__` only) |

## Callers Migrated

Three files had remaining callers that the initial grep missed (lazy/deferred imports):

1. **`src/elspais/mcp/server.py`**
   - Removed `get_project_name` from import
   - Line 1333: `get_project_name(config)` → `typed_config.project.name or "unknown"`

2. **`src/elspais/server/app.py`**
   - Removed `get_project_name` from import
   - Line 158: `get_project_name(_state["config"])` → `_state["config"].get("project", {}).get("name") or "unknown"`
   - Note: `_state["config"]` is a raw dict; typed access not yet available here

3. **`src/elspais/commands/doctor.py`**
   - Removed deferred `from elspais.config import validate_project_config`
   - `check_config_project_type()` rewritten to call `_validate_config()` directly and
     catch `pydantic.ValidationError`, extracting error messages from `exc.errors()`

## Retained Functions

The following were explicitly kept (path-resolving or config-logic helpers):

- `get_spec_directories()`, `get_code_directories()`, `get_docs_directories()`
- `get_test_directories()`, `get_ignore_config()`
- `get_associates_config()`, `validate_no_transitive_associates()`
- `get_status_roles()`

## Test Results

2800 passed, 321 deselected (unit/integration tier).
