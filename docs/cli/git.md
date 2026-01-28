# GIT INTEGRATION

## Detecting Changes

  $ elspais changed            # Show all spec changes
  $ elspais changed --staged   # Only staged changes
  $ elspais changed --hash     # Only hash mismatches

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
elspais hash verify || echo "Warning: stale hashes"
```

## Workflow

1. Edit requirements
2. $ elspais validate  # Check format
3. $ elspais hash update  # Update hashes
4. $ elspais changed  # Review what changed
5. Commit with message referencing requirement IDs
