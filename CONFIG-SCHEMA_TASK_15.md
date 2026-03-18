# Task 15: Create Command Arg Dataclasses

**Phase**: 3 — CLI Rewrite
**Status**: In Progress

## Description

Create `src/elspais/commands/args.py` with Tyro-compatible dataclasses for all ~25 subcommands.
Nested subcommands (`config show/get/set/...`, `mcp serve/install/...`, `link suggest`,
`rules list/show`) use nested Union types.

## Assertions

APPLICABLE_ASSERTIONS: None — new infrastructure for Tyro CLI migration, no existing spec assertions.

## Files

- Create: `src/elspais/commands/args.py`
- Test: `tests/core/test_cli_args.py`
