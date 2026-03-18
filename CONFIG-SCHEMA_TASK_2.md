# Task 2: Create Pydantic Schema — All Models

## Status: COMPLETE

## Summary

Created `src/elspais/config/schema.py` with all Pydantic models for the `.elspais.toml`
configuration schema. The schema exactly reproduces `DEFAULT_CONFIG` when instantiated
with no arguments. Unknown keys are rejected via `extra="forbid"`. Hyphenated TOML keys
are accepted via field aliases.

## Files Created

- `src/elspais/config/schema.py` — All Pydantic model classes
- `tests/core/test_schema.py` — 5 validation tests

## Models Defined

- `_StrictModel` — base with `extra="forbid"`, `frozen=True`, `populate_by_name=True`
- `ProjectConfig`
- `TypeAliases`, `TypeConfig`
- `ComponentConfig`, `AssertionConfig`, `IdPatternsConfig`
- `SpecConfig`
- `HierarchyConfig` (extra="allow" for dynamic type keys)
- `FormatConfig` (extra="allow")
- `RulesConfig` (extra="allow")
- `TestingConfig`
- `IgnoreSchemaConfig` (uses `alias="global"` for `global_` field)
- `KeywordsConfig`, `ReferenceDefaultsConfig`, `ReferencesConfig`
- `KeywordsSearchConfig`
- `ValidationConfig`
- `GraphConfig`
- `ChangelogConfig`
- `DirectoriesConfig`, `TraceabilityConfig`
- `AssociateEntryConfig`, `CoreConfig`, `AssociatedConfig` (extra="allow")
- `ElspaisConfig` — top-level model, `id_patterns` aliased as `"id-patterns"`

## Tests

All 5 tests pass:

1. `test_default_config_preserves_legacy_values` — roundtrip via `model_dump(by_alias=True)` is superset of DEFAULT_CONFIG
2. `test_unknown_key_rejected` — extra keys raise ValidationError
3. `test_unknown_nested_key_rejected` — extra nested keys raise ValidationError
4. `test_hyphenated_keys_accepted` — `"id-patterns"` alias works
5. `test_type_mismatch_rejected` — wrong types raise ValidationError

## Test Results

```
5 passed in 0.06s
2792 passed, 321 deselected in 26.43s  (full suite, no regressions)
```
