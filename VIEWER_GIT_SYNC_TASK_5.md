# Task 5: Flask Git Endpoints

## Status: Complete

## What was done

Added four git sync REST API routes to `src/elspais/server/app.py`:

- `GET /api/git/status` — delegates to `git_status_summary()`, returns branch, is_main, dirty_spec_files, remote_diverged, fast_forward_possible
- `POST /api/git/branch` — delegates to `create_and_switch_branch()`, validates name is non-empty (400), returns success/error
- `POST /api/git/push` — delegates to `commit_and_push_spec_files()`, validates message is non-empty (400), returns 403 for protected branch refusal
- `POST /api/git/pull` — delegates to `pull_ff_only()`, returns success/error

## Assertions validated

- REQ-p00004-C: Git status summary endpoint
- REQ-p00004-D: Branch creation endpoint
- REQ-p00004-E: Commit and push endpoint (with main branch protection → 403)
- REQ-p00004-F: Pull fast-forward endpoint

## Tests added (13 tests)

In `tests/test_server_app.py`:
- `TestGitStatus` (2 tests): status returns expected fields, uses config spec dir
- `TestGitBranch` (4 tests): creates branch, empty name 400, missing name 400, failure 400
- `TestGitPush` (4 tests): success, empty message 400, main refused 403, generic error 400
- `TestGitPull` (3 tests): success, no remote 400, diverged 400

## Files changed

- `src/elspais/server/app.py` — added git sync endpoint section
- `tests/test_server_app.py` — added 13 tests in 4 test classes
- `CHANGELOG.md` — added entry under v1.1.0
