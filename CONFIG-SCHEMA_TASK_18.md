# Task 18: Delete completion.py (replaced by Tyro)

**Status**: In Progress
**Branch**: config-refactor

## Description

Delete argparse-based `completion.py` which uses argcomplete (incompatible with
Tyro). Remove the `completion` subcommand from the CLI. Update install_cmd to
remove the `elspais completion --install` hint.

## Applicable Assertions

No specific assertions for shell completion removal. This is part of the
argparse-to-Tyro migration.

## Changes Required

1. Delete `src/elspais/commands/completion.py`
2. Remove `CompletionArgs` from `commands/args.py` and the Command union
3. Remove `completion` import and dispatch from `cli.py`
4. Remove `maybe_show_completion_hint()` call from `cli.py`
5. Remove `completion` from `commands/__init__.py`
6. Update `install_cmd.py` to remove `completion --install` hint
7. Remove `"completion"` from `detect_installed_extras` extras map
8. Delete `tests/commands/test_completion.py`
9. Update test_install_cmd.py assertions about completion hint
10. Remove `completion` from help text and pyproject.toml extras
