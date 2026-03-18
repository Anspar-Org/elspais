# Task 17: Delete --set flag and apply_cli_overrides

**Status**: In Progress
**Branch**: config-refactor

## Description

Remove `--set key=value` CLI flag and `apply_cli_overrides()`. Users should use
`.elspais.local.toml` for overrides. Per CONFIG_DESIGN.md: "There is no `--set`
flag, no CLI-to-config override path."

## Applicable Assertions

No existing assertions cover `--set` or `apply_cli_overrides`. The test file
`tests/test_config_cli_overrides.py` incorrectly references REQ-d00002-A (which
is actually "Review Storage Architecture"). Since this is a deletion task
removing a feature replaced by `.elspais.local.toml`, no new assertions needed.

## Changes Required

1. Remove `config_overrides` field from `GlobalArgs` in `commands/args.py`
2. Remove `overrides` parameter from `get_config()` in `config/__init__.py`
3. Remove `apply_cli_overrides()` function from `config/__init__.py`
4. Remove `apply_cli_overrides` from `__all__` in `config/__init__.py`
5. Remove `overrides=` from all `get_config()` call sites in commands
6. Delete `tests/test_config_cli_overrides.py`
7. Update docs referencing `--set`
