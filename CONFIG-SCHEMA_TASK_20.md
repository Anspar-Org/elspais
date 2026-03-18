# Task 20: JSON Schema export + elspais config schema command

**Status**: In Progress
**TASK_FILE**: CONFIG-SCHEMA_TASK_20.md

## Description

Generate `elspais-schema.json` from `ElspaisConfig.model_json_schema()` for Taplo IDE autocomplete. Add `elspais config schema` subcommand. CI test ensures committed file matches model output.

## Files

- Create: `src/elspais/config/elspais-schema.json`
- Modify: `src/elspais/commands/config_cmd.py` — add `cmd_schema`
- Modify: `src/elspais/commands/args.py` — add `ConfigSchemaArgs`
- Modify: `src/elspais/cli.py` — add schema to action map
- Create: `tests/core/test_json_schema.py`

## Checklist

- [x] **Baseline**: tests pass (2780 passed)
- [x] **Create TASK_FILE**: this file
- [x] **Find assertions**: no pre-existing assertions found
- [ ] **Create assertions**: add to spec file
- [ ] **Write failing tests** (sub-agent)
- [ ] **Implement**
- [ ] **Verify**: pytest, lint
- [ ] **Update docs**: CHANGELOG.md, docs/cli/
- [ ] **Bump version**: pyproject.toml
- [ ] **Commit**

## Applicable Assertions

APPLICABLE_ASSERTIONS: REQ-d00208-A, REQ-d00208-B, REQ-d00208-C
