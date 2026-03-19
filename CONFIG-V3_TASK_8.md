# CONFIG-V3 Task 8: Update remaining commands (doctor, index)

## Scope

Only `doctor.py` and `index.py` have remaining v2 config reads. All other commands
(fix_cmd.py, example_cmd.py, rules_cmd.py, edit.py, validate.py, changed.py) are
already migrated.

## Remaining v2 reads

### doctor.py

1. `check_associate_paths()` line 386: `config.get("associates", {}).get("paths", [])`
2. `check_associate_configs()` line 430: `config.get("associates", {}).get("paths", [])`
3. `check_cross_repo_in_committed_config()` line 524: `data.get("spec", {}).get("directories", [])`
4. `check_cross_repo_in_committed_config()` line 530: `data.get("associates", {}).get("paths", [])`

### index.py

5. `_resolve_spec_dir_info()` line 168: `cfg.get("project", {}).get("name")`
6. `_resolve_spec_dir_info()` line 176: `cfg.get("levels", {})`
7. `_resolve_spec_dir_info()` lines 180-181: `level_def.get("rank", 99)`, `level_def.get("display_name")`

## APPLICABLE_ASSERTIONS

- REQ-d00212-F: ElspaisConfig SHALL have `levels`, `scanning`, `output` fields (consumers must use v3 paths)
- REQ-d00212-K: AssociateEntryConfig SHALL contain `path` and `namespace`
- REQ-d00202-A: `get_associates_config()` SHALL read `[associates]` sections and return named mapping
- REQ-d00207-C: All consumer code SHALL use plain dicts / typed config directly

## Baseline

2964 passed, 321 deselected (unit tests only, 2026-03-19)
