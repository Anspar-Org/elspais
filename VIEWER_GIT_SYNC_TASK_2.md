# Task 2: Branch Creation Function

## Description

Add `create_and_switch_branch()` to `utilities/git.py` -- creates new branch
and switches to it, using stash to carry dirty working tree changes.

## Assertions

Searched with `discover_requirements("git branch create switch stash")` under REQ-p00001 and REQ-p00004 scopes -- no existing assertion found.

**Created**: REQ-p00004-D: "The tool SHALL create and switch to a new git branch, using stash to preserve dirty working tree changes across the switch."

## Tests

- `test_REQ_p00004_D_clean_switch` -- switch on clean tree
- `test_REQ_p00004_D_dirty_stash_preserves_changes` -- stash/pop round-trip
- `test_REQ_p00004_D_invalid_branch_name` -- rejects invalid names
- `test_REQ_p00004_D_duplicate_branch_name` -- rejects existing branch

## Implementation

- Function: `create_and_switch_branch(repo_root, branch_name)` in `src/elspais/utilities/git.py`
- Reuses: `get_modified_files()`, `get_current_branch()`, `_clean_git_env()`
- `# Implements: REQ-p00004-D` comment
- Added to `__all__`

## Files Changed

- `spec/prd-elspais.md` -- added assertion D
- `src/elspais/utilities/git.py` -- new function
- `tests/core/test_git.py` -- new test class
- `CHANGELOG.md` -- entry under v1.1.0
