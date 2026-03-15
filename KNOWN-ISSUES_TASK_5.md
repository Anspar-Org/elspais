# Task 5: CLI config overrides via --set key=value

## Description

Add a repeatable `--set key=value` CLI flag that applies overrides after config loading,
reusing existing `_set_nested()` and `_try_parse_env_value()`.

## APPLICABLE_ASSERTIONS

- No existing assertion covers CLI config overrides specifically.
- This extends the configuration system (REQ-d00002 area).

## Implementation Plan

1. Add `apply_cli_overrides()` to `config/__init__.py`
2. Add `overrides` parameter to `get_config()`
3. Add `--set` argument to `create_parser()` in `cli.py`
4. Thread overrides through each command handler call site
