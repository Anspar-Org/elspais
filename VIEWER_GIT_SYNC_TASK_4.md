# Task 4: Pull Fast-Forward-Only Function

## Description

Add `pull_ff_only()` to `utilities/git.py` -- fetches and merges with `--ff-only`.
Aborts if not fast-forwardable. Elspais never rebases or merges.

## Assertions

- **REQ-p00004-F**: The tool SHALL fetch and fast-forward-merge from the remote tracking branch, aborting if the merge is not fast-forwardable.

Found via `discover_requirements("git pull fast forward merge")` -- no existing assertion covered this.
Created assertion F on REQ-p00004 in `spec/prd-elspais.md`.

## Tests

- `test_REQ_p00004_F_no_remote_returns_error` -- returns error when no remote configured
- `test_REQ_p00004_F_ff_pull_succeeds` -- fast-forward pull succeeds (bare remote + two clones)
- `test_REQ_p00004_F_not_fast_forwardable_returns_error` -- diverged history returns error

## Implementation

- Function: `pull_ff_only()` in `src/elspais/utilities/git.py`
- Reuses: `_clean_git_env()`
- Added to `__all__` exports
