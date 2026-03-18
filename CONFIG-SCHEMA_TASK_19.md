# Task 19: Delete DEFAULT_CONFIG and ConfigLoader

**Status**: Complete
**TASK_FILE**: CONFIG-SCHEMA_TASK_19.md

## Description

Remove `DEFAULT_CONFIG` dict and `ConfigLoader` class — all defaults now in Pydantic field defaults, all access via typed `ElspaisConfig`.

## Files Modified

- `src/elspais/config/__init__.py` — removed `DEFAULT_CONFIG`, `ConfigLoader`, added `config_defaults()`, updated exports
- `src/elspais/commands/health.py` — replaced `ConfigLoader` type annotations and `.get_raw()` calls
- `src/elspais/commands/doctor.py` — replaced `ConfigLoader` type annotations and `.get_raw()` calls
- `src/elspais/commands/report.py` — replaced `ConfigLoader.from_dict()` and `.get_raw()`
- `src/elspais/commands/config_cmd.py` — replaced `DEFAULT_CONFIG` import, fixed `.get()` calls
- `src/elspais/commands/edit.py` — replaced `DEFAULT_CONFIG` import
- `src/elspais/commands/example_cmd.py` — removed `get_raw()` compat checks
- `src/elspais/commands/rules_cmd.py` — removed `.get_raw()` calls
- `src/elspais/graph/federated.py` — replaced `ConfigLoader` type annotations
- `src/elspais/graph/factory.py` — replaced `ConfigLoader.from_dict()` calls
- `src/elspais/mcp/server.py` — removed `ConfigLoader` isinstance checks
- `src/elspais/server/app.py` — removed `.get_raw()` call
- 16 test files updated to remove ConfigLoader/DEFAULT_CONFIG imports
- `spec/07-graph-architecture.md` — added REQ-d00207

## Checklist

- [x] **Baseline**: tests pass (2780 passed)
- [x] **Create TASK_FILE**: this file
- [x] **Find assertions**: discover_requirements — no pre-existing assertions found
- [x] **Create assertions**: added REQ-d00207 with assertions A, B, C
- [x] **Write failing tests**: N/A — dead code removal, no new tests
- [x] **Implement**: removed DEFAULT_CONFIG, ConfigLoader, added config_defaults(), updated 32 files
- [x] **Verify**: 2780 passed, lint clean
- [x] **Update docs**: CHANGELOG.md, CLAUDE.md updated
- [x] **Bump version**: 0.105.9 → 0.106.0
- [x] **Commit**: 8c78dd3 [CUR-1082] Task 19: delete ConfigLoader and DEFAULT_CONFIG

## Applicable Assertions

APPLICABLE_ASSERTIONS: REQ-d00207-A, REQ-d00207-B, REQ-d00207-C
