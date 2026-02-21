# GIT INTEGRATION

## Git Root Auto-Detection

elspais automatically detects the git repository root and operates
from there, so it works identically from any subdirectory.

For **git worktrees**, elspais also detects the canonical (main)
repository root. This ensures cross-repo paths (e.g. `../sibling`)
resolve from the main repo, not the worktree location.

Use `-v` to see detected roots:

  $ elspais validate -v
  Working from repository root: /home/dev/worktrees/feature-x
  Canonical root (main repo): /home/dev/my-project

## Detecting Changes

  $ elspais changed              # Show all spec changes
  $ elspais changed -j           # Output as JSON
  $ elspais changed -a           # Include non-spec files
  $ elspais changed --base-branch develop  # Compare to different branch

## Command Options

  `--base-branch BRANCH`  Base branch for comparison (default: main)
  `-j, --json`            Output as JSON for tooling
  `-a, --all`             Include all changed files (not just spec)

## What 'Changed' Detects

  **Uncommitted** - Modified/untracked spec files
  **Hash mismatch** - Content changed but hash not updated
  **Moved** - Requirement relocated to different file
  **vs Main** - Changes compared to main/master branch

## In Trace View

The interactive trace view (`elspais trace --view`) shows:

  **◆** Changed vs main branch (diamond indicator)
  Filter buttons: `[Uncommitted]` `[Changed vs Main]`

## Pre-Commit Hook Example

```sh
#!/bin/sh
# .git/hooks/pre-commit
elspais validate || exit 1
```

## Workflow

1. Edit requirements
2. $ elspais validate  # Check format
3. $ elspais fix  # Fix hashes and formatting
4. $ elspais changed  # Review what changed
5. Commit with message referencing requirement IDs
