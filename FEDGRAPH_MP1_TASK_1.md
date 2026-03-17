# Task 1: Add [associates] Section to Config Loading

**Branch**: claude/cross-cutting-requirements-2Zd0c
**Ticket**: CUR-1082
**Status**: In Progress

## Description

Add `get_associates_config(config)` that reads `[associates.<name>]` sections
from `.elspais.toml` with `path` (required) and `git` (optional) fields.

## Applicable Assertions

- REQ-d00202-A: get_associates_config returns dict mapping name -> {path, git}
- REQ-d00202-B: path required, git optional
- REQ-d00202-C: empty dict when no [associates] section

## Baseline

- 2728 passed, 299 deselected in 35.03s
