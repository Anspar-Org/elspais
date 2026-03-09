# Task 1: Git Status Summary Function

**Ticket:** CUR-1081
**Status:** In Progress

## Requirement Traceability

**Discovered via:** `discover_requirements("git status branch viewer")` MCP tool

**Relevant requirements:**
- REQ-p00004 — Change Detection and Auditability
- REQ-p00004-B — The tool SHALL detect uncommitted and branch-relative changes to requirement files using git.
- REQ-p00004-C — The tool SHALL provide a git status summary reporting current branch, main-branch detection, dirty spec files, and remote divergence state. *(created for this task)*

**Assertion created:** REQ-p00004-C (added to `spec/prd-elspais.md`)

## Description

Add `git_status_summary()` to `utilities/git.py` — returns branch name,
is_main flag, dirty spec files list, remote divergence info.

## Implementation

- **Function:** `git_status_summary(repo_root, spec_dir, main_branches) -> dict[str, Any]`
- **Location:** `src/elspais/utilities/git.py` after `get_current_branch()` (~line 433)
- **Reuses:** `get_current_branch()`, `get_modified_files()`, `_clean_git_env()`
- **Implements comment:** `# Implements: REQ-p00004-C`

## Tests

- `test_REQ_p00004_C_clean_feature_branch` — clean feature branch returns expected defaults
- `test_REQ_p00004_C_main_branch_dirty_spec` — main + dirty spec files detected
- `test_REQ_p00004_C_non_spec_dirty_excluded` — non-spec dirty files excluded from dirty_spec_files

## Files Changed

- `spec/prd-elspais.md` — assertion REQ-p00004-C added
- `src/elspais/utilities/git.py` — `git_status_summary()` function added
- `tests/core/test_git.py` — 3 new tests added
- `CHANGELOG.md` — updated
- `pyproject.toml` — version bumped
