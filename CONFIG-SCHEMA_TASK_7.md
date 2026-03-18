# Task 7: Migrate graph/factory.py (21 config.get() calls)

**Status:** Complete
**Date:** 2026-03-18

## Summary

Converted all 21 `config.get("x", {}).get("y")` chains in `graph/factory.py` to typed
`ElspaisConfig` attribute access. Two functions were migrated:

- `_resolve_spec_dir_config()` — 5 config.get() calls on `repo_config`
- `build_graph()` — 16 config.get() calls on `config`

## Changes

### `src/elspais/graph/factory.py`

1. Added import of `ElspaisConfig` from `elspais.config.schema`
2. Added `_SCHEMA_FIELDS` set and `_validate_config()` helper to handle legacy keys
   (`patterns`, legacy `associates.paths`) that exist in the config dict but are not
   in the Pydantic schema (which uses `extra="forbid"`)
3. Added typed config conversion at function boundary in both `_resolve_spec_dir_config()`
   and `build_graph()` using the pattern:
   ```python
   if isinstance(config, dict):
       typed_config = _validate_config(config)
   else:
       typed_config = config
   ```
4. Replaced all 21 config.get() chains with typed attribute access:
   - `config.get("references", {})` -> `typed_config.references.model_dump(by_alias=True)`
   - `config.get("spec", {}).get("patterns", ...)` -> `typed_config.spec.patterns`
   - `config.get("validation", {}).get("hash_mode", ...)` -> `typed_config.validation.hash_mode`
   - `config.get("graph", {}).get("satellite_kinds", None)` -> `typed_config.graph.satellite_kinds`
   - `config.get("traceability", {}).get("scan_patterns", [])` -> `typed_config.traceability.scan_patterns`
   - `config.get("directories", {}).get("ignore", [])` -> `typed_config.directories.ignore`
   - `config.get("testing", {}).get(...)` -> `typed_config.testing.*` (6 fields)
   - `config.get("traceability", {}).get("source_roots", None)` -> `typed_config.traceability.source_roots`

## Function signatures NOT changed

Both `_resolve_spec_dir_config()` and `build_graph()` still receive config as dict.
The typed conversion is internal only (Phase 2 pattern).

## Calls left as raw dict access

- `get_spec_directories(None, config, repo_root)` — helper expects dict
- `build_resolver(config)` — helper expects dict
- `get_ignore_config(config)` — helper expects dict
- `get_code_directories(config, repo_root)` — helper expects dict
- `get_associates_config(config)` — helper expects dict, returns legacy format
- `associates_config[name]["path"]` / `.get("git")` — runtime dict from helper
- `ConfigLoader.from_dict(config)` — adapter expects dict

These will be migrated when their respective helper functions are updated (Tasks 12-13).

## Notes

- `_validate_config()` strips non-schema top-level keys before Pydantic validation
  because the config dict from `get_config()` may retain legacy keys like `patterns`
  (from v1 migration) that are not removed after migration
- Legacy `associates` format (`{paths: [...]}`) is also stripped since it's incompatible
  with the schema's `dict[str, AssociateEntryConfig]` type
- `ReferenceResolver.from_config()` still expects a dict, so we pass
  `typed_config.references.model_dump(by_alias=True)` for now

## Test Results

- Targeted: 193 passed (factory/build_graph/graph tests)
- Full suite: 2800 passed, 321 deselected
