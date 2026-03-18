# CONFIG-SCHEMA Task 8: Migrate mcp/server.py

## Status: COMPLETE

## Summary

Converted all config dict access in `src/elspais/mcp/server.py` to typed `ElspaisConfig` attribute access.

## Changes Made

### Added to `mcp/server.py`

- Import: `from elspais.config.schema import ElspaisConfig`
- `_SCHEMA_FIELDS` constant for filtering non-schema keys
- `_validate_config()` helper function (same pattern as `graph/factory.py`)

### Migrated Config Access (21 calls across 10 functions)

| Function | Old Pattern | New Pattern |
|----------|-------------|-------------|
| `_add_changelog_for_active_mutations` | `config.get("changelog", {}).get("id_source", "gh")` | `typed_config.changelog.id_source` |
| `_build_base_workspace_info` | `config.get("project", {}).get("namespace", "REQ")` | `typed_config.project.namespace` |
| | `config.get("spec", {}).get("directories", ["spec"])` | `typed_config.spec.directories` |
| | `config.get("testing", {}).get("enabled", False)` | `typed_config.testing.enabled` |
| | `config.get("project", {}).get("type")` | `typed_config.project.type` |
| `_build_id_patterns` | `config.get("id-patterns", {})` chain | `typed_config.id_patterns.*` |
| `_build_assertion_format` | `config.get("id-patterns", {})` chain | `typed_config.id_patterns.*` |
| `_build_hierarchy_rules` | `config.get("rules", {}).get("hierarchy", {})` | `typed_config.rules.hierarchy.*` |
| `_workspace_profile_testing` | `config.get("testing", {})` chain | `typed_config.testing.*` |
| `_workspace_profile_code_refs` | `config.get("references", {}).get("defaults", {})` | `typed_config.references.defaults.*` |
| | `config.get("directories", {}).get("code", [])` | `typed_config.directories.code` |
| `_workspace_profile_retrofit` | Same patterns as code_refs + testing | `typed_config.references.defaults.*`, `typed_config.testing.*` |
| `_workspace_profile_worktree` | `config.get("spec", {}).get("directories", ...)` | `typed_config.spec.directories` |
| `_workspace_profile_all` | Combined patterns from all profiles | All typed accessors |
| `save_mutations` (handler) | `config.get("changelog", {}).get("enforce", True)` | `typed_config.changelog.enforce` |

### Functions NOT changed (no config dict access)

- `_build_coverage_stats` - delegates to `get_status_roles(config)` (raw dict still needed)
- `_build_associates_info` - delegates to `get_associates_config(config)` (raw dict still needed)
- `_normalize_assertion_targets` - uses `build_resolver(config)` (raw dict still needed)
- `_get_agent_instructions` - delegates to `load_content_rules(config, ...)` (raw dict still needed)

Function signatures remain `dict[str, Any]` -- conversion happens at the boundary inside each function.

## Test Results

- MCP tests: 464 passed
- Full suite: 2800 passed, 321 deselected
