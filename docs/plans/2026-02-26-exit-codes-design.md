# Fix Exit Codes for Diagnostic Commands (CUR-1036)

## Problem

`elspais doctor`, `health`, and `validate` exit 0 when configuration is broken. Only malformed TOML syntax produces non-zero exit. All other misconfigurations — nonexistent paths, invalid project types, missing config files, zero requirements, broken `[associated]` sections, missing associate repos — exit 0.

Root cause: `HealthReport.is_healthy` only counts `severity == "error"` as failures, but many checks that detect real problems use `severity="warning"`.

## Requirements

- **EXIT-1**: `[!!]` and `[XX]` findings exit non-zero
- **EXIT-2**: `validate` exits non-zero when zero requirements found with configured spec dir
- **EXIT-3**: `doctor`/`health` path checks verify directories exist on disk (already works; severity is the issue)
- **EXIT-4**: For `associated` projects, `doctor` validates `[associated]` section exists with non-empty prefix
- **EXIT-5**: For `core` projects with associates, `validate` exits non-zero when associate path is missing/broken

## Approach: Severity Reclassification

Change `severity="warning"` to `severity="error"` on checks that represent actual failures. Keep `severity="warning"` only for truly advisory items. Add missing checks for EXIT-2, EXIT-4, EXIT-5.

## Changes

### doctor.py — Severity reclassification (EXIT-1, EXIT-3)

Remove `severity="warning"` from these checks (default is `severity="error"`):

1. `check_config_required_fields` — missing required config sections
2. `check_config_project_type` — invalid project type
3. `check_config_pattern_tokens` — missing required pattern placeholders
4. `check_config_hierarchy_rules` — 3 failure returns
5. `check_config_paths_exist` — non-list spec_dirs
6. `check_associate_paths` — missing associate paths
7. `check_associate_configs` — invalid associate configs

Keep as warning: `check_cross_repo_in_committed_config` — advisory only.

### doctor.py — New associated section check (EXIT-4)

New `check_config_associated_section`: For `project.type = "associated"`, verify `[associated]` section exists with non-empty `prefix`. Add to `run_config_checks`.

### validate.py — Zero requirements check (EXIT-2)

After graph build, if spec directories are configured and zero requirements found, emit error and exit 1.

### validate.py — Associate requirement count (EXIT-5)

When mode is `combined` and associate paths are configured, if total requirements equals core-only count (associates contributed nothing), emit error and exit 1.

## Files Modified

- `src/elspais/commands/doctor.py`
- `src/elspais/commands/validate.py`
