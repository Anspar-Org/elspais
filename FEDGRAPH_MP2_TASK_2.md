# Task 2: Remove Dead Legacy Associate Code

**Ticket**: CUR-1082
**Branch**: claude/cross-cutting-requirements-2Zd0c
**Baseline**: 2743 passed

## Objective

Remove legacy YAML-based associate/sponsor system from `associates.py` and all callers.
The new `[associates.<name>]` TOML config + federation pipeline (MASTER_PLAN1) replaces it.

## APPLICABLE_ASSERTIONS

- REQ-d00202-A..D: New associates config loading (must still pass after removal)
- REQ-d00203-A..E: Multi-repo build pipeline (must still pass after removal)
- REQ-p00005-C: CLI-based associate path configuration (keep path-based loading)
- REQ-p00005-D: Auto-discovery of associate identity (keep discover_associate_from_path)
- REQ-p00005-E: Clear error for invalid paths (keep error reporting)
- REQ-p00005-F: Canonical root worktree resolution (keep in get_associate_spec_directories)

## Scope

### Remove from associates.py

- `Sponsor` alias
- `AssociatesConfig` / `SponsorsConfig` dataclass + aliases
- `parse_yaml()`, `_parse_yaml_value()`
- `load_associates_yaml()` / `load_sponsors_yaml()`
- `_parse_associates_yaml()`
- `load_associates_config()` / `load_sponsors_config()`
- `resolve_associate_spec_dir()` / `resolve_sponsor_spec_dir()`
- `get_sponsor_spec_directories` alias
- Section 1 (YAML loading) from `get_associate_spec_directories()`

### Keep in associates.py

- `Associate` dataclass
- `discover_associate_from_path()`
- `get_associate_spec_directories()` (sections 0 and 2 only)

### Remove from factory.py

- `scan_sponsors` parameter from `build_graph()`
- Legacy sponsor scanning block (lines 357-372)
- Import of `get_associate_spec_directories`

### Update callers

- `commands/validate.py`: remove `scan_sponsors`, remove manual sponsor dir gathering
- `commands/index.py`: remove `scan_sponsors`, remove manual sponsor dir gathering
- `commands/fix_cmd.py`: remove `scan_sponsors`
- `utilities/git.py`: remove `scan_sponsors` parameter
- `mcp/server.py`: redirect `_build_associates_info` to use `get_associates_config`
- `server/app.py`: redirect /api/status to use `get_associates_config`

### Update tests

- Remove `scan_sponsors=False` from all `build_graph()` calls in tests
- Remove `TestResolveAssociateSpecDirCanonicalRoot` from `test_associates_canonical.py`
- Remove imports of `AssociatesConfig`, `resolve_associate_spec_dir` from tests
- Keep `test_associates_paths.py` (tests section 2, path-based loading)
- Keep `test_associate_cli_integration.py` (tests path-based + discovery)

## Progress

- [x] Baseline: 2743 passed
- [x] Write failing tests: 15 tests in `tests/core/test_legacy_sponsor_removal.py`
- [x] Implement: all legacy code removed, callers updated
- [x] Verify: 2755 passed (12 net new tests), doc sync 68 passed
- [x] Commit
