# Task 19: Delete DEFAULT_CONFIG and ConfigLoader

**Status**: In Progress
**TASK_FILE**: CONFIG-SCHEMA_TASK_19.md

## Description

Remove `DEFAULT_CONFIG` dict and `ConfigLoader` class — all defaults now in Pydantic field defaults, all access via typed `ElspaisConfig`.

## Files to Modify

- `src/elspais/config/__init__.py` — remove `DEFAULT_CONFIG`, `ConfigLoader`, update exports
- `src/elspais/commands/health.py` — replace `ConfigLoader` type annotations and usage
- `src/elspais/commands/doctor.py` — replace `ConfigLoader` type annotations and usage
- `src/elspais/commands/report.py` — replace `ConfigLoader.from_dict()` usage
- `src/elspais/commands/config_cmd.py` — replace `DEFAULT_CONFIG` import
- `src/elspais/commands/edit.py` — replace `DEFAULT_CONFIG` import
- `src/elspais/graph/federated.py` — replace `ConfigLoader` type annotations
- `src/elspais/graph/factory.py` — replace `ConfigLoader.from_dict()` usage
- `src/elspais/mcp/server.py` — replace `ConfigLoader` isinstance checks
- Tests referencing `ConfigLoader` or `DEFAULT_CONFIG`

## Checklist

- [x] **Baseline**: tests pass (2780 passed)
- [x] **Create TASK_FILE**: this file
- [x] **Find assertions**: discover_requirements — no pre-existing assertions found
- [x] **Create assertions**: added REQ-d00207 with assertions A, B, C
- [ ] **Write failing tests**: N/A — dead code removal, no new tests
- [ ] **Implement**: remove DEFAULT_CONFIG, ConfigLoader, update all consumers
- [ ] **Verify**: pytest -x, lint clean
- [ ] **Update docs**: CHANGELOG.md, CLAUDE.md
- [ ] **Bump version**: pyproject.toml
- [ ] **Commit**

## Applicable Assertions

APPLICABLE_ASSERTIONS: REQ-d00207-A, REQ-d00207-B, REQ-d00207-C
