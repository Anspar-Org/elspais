# TERMS-001 Task 1: Config Schema — TermsConfig

## Description
Add `TermsConfig` Pydantic model to `config/schema.py` and `terms` field to `ElspaisConfig`.

## Applicable Assertions
- **REQ-d00212-L**: A `TermsConfig` model SHALL define defined-terms configuration: `output_dir` (str, default "spec/_generated"), `duplicate_severity` (str, default "error"), `undefined_severity` (str, default "warning"), `unmarked_severity` (str, default "warning"). `ElspaisConfig` SHALL include a `terms` field of type `TermsConfig` with factory default.

## Progress
- [x] Baseline: 3219 passed, 321 deselected
- [x] TASK_FILE created
- [x] Assertions found/created: REQ-d00212-L added to spec/dev-graph-config.md
- [x] Failing tests written: tests/test_terms_config.py (5 tests)
- [x] Implementation complete: TermsConfig added to config/schema.py, terms field added to ElspaisConfig
- [x] Verification passed: 3224 passed, 321 deselected
- [x] Docs updated: docs/configuration.md, init.py templates, JSON schema regenerated, docs drift test updated
- [x] Version bumped: 0.111.80 -> 0.111.81
- [x] Committed

## Tests
- `test_REQ_d00212_L_terms_config_defaults` — verifies defaults
- `test_REQ_d00212_L_elspais_config_has_terms` — verifies ElspaisConfig.terms field
- `test_REQ_d00212_L_toml_with_terms_validates` — verifies TOML parsing
- `test_REQ_d00212_L_terms_config_rejects_unknown` — verifies extra="forbid"
- `test_REQ_d00212_L_terms_config_custom_values` — verifies custom values

## Implementation
- `src/elspais/config/schema.py`: Added `TermsConfig(_StrictModel)` with 4 fields, added `terms` field to `ElspaisConfig`
- `docs/configuration.md`: Added `[terms]` section with all fields documented
- `src/elspais/commands/init.py`: Added "terms" to section lists and comments
- `src/elspais/config/elspais-schema.json`: Regenerated
- `tests/core/test_docs_drift.py`: Added "terms" to EXPECTED_SCHEMA_SECTIONS
- `spec/dev-graph-config.md`: Added assertion REQ-d00212-L
