# Task 23: Viewer UI Integration

**Branch**: config-refactor
**Ticket**: CONFIG-SCHEMA
**Status**: Complete

## Description

Wire `ElspaisConfig` values into viewer UI template context. No hardcoded value lists in frontend code for requirement types, statuses, or relationship kinds.

## Applicable Assertions

- **REQ-d00211-A**: Template context SHALL include `config_types` from `ElspaisConfig.id_patterns.types`.
- **REQ-d00211-B**: Template context SHALL include `config_relationship_kinds` (implements, refines, satisfies).
- **REQ-d00211-C**: Template context SHALL include `config_statuses` from `ElspaisConfig.rules.format.allowed_statuses`.

## Files

- Modify: `src/elspais/server/app.py`
- Modify: `src/elspais/html/templates/partials/js/_nav-tree.js.j2`
- Modify: `src/elspais/html/templates/partials/js/_edit-engine.js.j2`
- Modify: `src/elspais/html/templates/partials/_header.html.j2`

## Baseline

- 2821 passed, 321 deselected — all green

## Test Summary

- 10 new tests in `tests/core/test_viewer_config.py`
- TestExtractViewerConfigTypes (4 tests) — REQ-d00211-A
- TestExtractViewerConfigRelationshipKinds (3 tests) — REQ-d00211-B
- TestExtractViewerConfigStatuses (3 tests) — REQ-d00211-C

## Implementation Summary

Added `_extract_viewer_config(config)` to `app.py`:
- Extracts requirement types (name, letter, level) from `ElspaisConfig.id_patterns.types`
- Returns user-selectable relationship kinds (implements, refines, satisfies)
- Returns allowed statuses from `ElspaisConfig.rules.format.allowed_statuses`
- Injected into template context via `**viewer_cfg` in `render_template()`

Updated JS templates:
- `_edit-engine.js.j2`: relationship kind list and dropdown options now use Jinja2 variables
- `_nav-tree.js.j2`: level counts dict now uses config_types

## Verification

- `pytest tests/core/test_viewer_config.py -v` — 10 passed
- `pytest -x -q` — 2831 passed, 321 deselected
