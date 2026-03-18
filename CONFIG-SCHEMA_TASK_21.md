# Task 21: Schema-Driven Init Template Generation

**Branch**: config-refactor
**Ticket**: CONFIG-SCHEMA
**Status**: Complete

## Description

Replace hardcoded `generate_config()` template strings in `commands/init.py` with a schema walker that produces TOML from the `ElspaisConfig` Pydantic model. This ensures `elspais init` always generates config that validates against the current schema.

## Applicable Assertions

- **REQ-d00209-A**: `generate_config("core")` SHALL produce TOML that passes `ElspaisConfig.model_validate()` without error.
- **REQ-d00209-B**: `generate_config("associated")` SHALL produce TOML that passes `ElspaisConfig.model_validate()` without error when given a valid prefix.
- **REQ-d00209-C**: The generated TOML SHALL include all sections present in the current hardcoded templates.
- **REQ-d00209-D**: The generated TOML SHALL include human-readable comments.

## Files

- Modify: `src/elspais/commands/init.py`
- Create: `tests/core/test_init_template.py`

## Baseline

- 2786 passed, 321 deselected — all green

## Test Summary

- 22 new tests in `tests/core/test_init_template.py`
- TestCoreConfigValidation (6 tests) — REQ-d00209-A
- TestAssociatedConfigValidation (6 tests) — REQ-d00209-B
- TestGeneratedSections (6 tests) — REQ-d00209-C
- TestGeneratedComments (4 tests) — REQ-d00209-D

## Implementation Summary

Replaced hardcoded f-string templates in `generate_config()` with a schema walker:
- Uses `config_defaults()` (from Pydantic model) as data source
- Applies project-type-specific overrides via `_CORE_OVERRIDES` dict
- Builds `tomlkit.document()` with section comments from `_SECTION_COMMENTS`
- Both core and associated templates now include all schema-defined sections
- Added `version = 2` top-level key (was missing from hardcoded templates)

## Verification

- `pytest tests/core/test_init_template.py -v` — 22 passed
- `pytest -x -q` — 2808 passed, 321 deselected
- `pytest tests/test_doc_sync.py -v` — 68 passed
