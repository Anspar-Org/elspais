# Task 3: Commit-and-Push Function

## Description

Add `commit_and_push_spec_files()` to `utilities/git.py` -- stages all modified
spec files, commits with message, optionally pushes. Refuses on main/master.

## Assertions

- **REQ-p00004-E**: The tool SHALL commit modified spec files and optionally push, refusing to operate on main/master branches.

Found via `discover_requirements("git commit push spec files")` -- no existing assertion covered this.
Created assertion E on REQ-p00004 in `spec/prd-elspais.md`.

## Tests

- `test_REQ_p00004_E_commit_dirty_spec_files` -- commits modified spec files
- `test_REQ_p00004_E_refuse_on_main` -- refuses to commit on main/master
- `test_REQ_p00004_E_nothing_to_commit` -- returns error when no dirty spec files
- `test_REQ_p00004_E_includes_untracked_spec_files` -- stages and commits untracked spec files

## Implementation

- Function: `commit_and_push_spec_files()` in `src/elspais/utilities/git.py`
- Reuses: `get_current_branch()`, `get_modified_files()`, `_clean_git_env()`
- Added to `__all__` exports
