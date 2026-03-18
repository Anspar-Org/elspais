# Task 16: Rewrite cli.py with Tyro

**Phase**: 3 — CLI Rewrite
**Status**: Complete

## Description

Replace argparse `create_parser()` + `main()` with `tyro.cli(GlobalArgs)`.
Compatibility shim converts typed dataclasses to `argparse.Namespace` so
existing command `run()` functions work without signature changes.

## Assertions

APPLICABLE_ASSERTIONS: None — infrastructure migration task.

## Implementation Summary

- Rewrote `cli.py` to use `tyro.cli(GlobalArgs)` for argument parsing
- Added `OmitSubcommandPrefixes` and `OmitArgPrefixes` markers for clean CLI syntax
- Added `tyro.conf.Positional` for positional args (topic, req_id, key, value, etc.)
- Added `tyro.conf.arg(name=...)` aliases to preserve `--spec`/`--code`/`--tests` flag names
- Added `tyro.conf.arg(aliases=[...])` for short flags (`-o`, `-v`, `-q`, `-C`, `-n`, `-m`, `-a`)
- Created `_to_namespace()` shim for backward-compatible command dispatch
- Added `parse_args()` helper for tests migrated from `create_parser().parse_args()`
- Fixed `content_rules.py` ConfigLoader.items() bug
- Fixed Pydantic schema: `TypeConfig.aliases` made optional, `ComponentConfig.max_length` added

## Verification

- 2813 unit tests pass
- 314 e2e tests pass (1 skipped)
