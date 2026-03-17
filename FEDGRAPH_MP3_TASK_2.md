# Task 2: Viewer/Server Repo Staleness and Flask App Update

**Ticket**: CUR-1082
**Branch**: claude/cross-cutting-requirements-2Zd0c
**Baseline**: 2770 passed

## Objective

Add `/api/repos` endpoint that lists federated repos with staleness info. Update
`/api/status` to include federation repo metadata. Staleness is informational only.

## APPLICABLE_ASSERTIONS

- NEW REQ-d00206: Server Federation and Staleness

## Scope

### 1. `/api/repos` endpoint

Returns federation repo info from `graph.iter_repos()`:

- name, path, status (ok/error), git\_origin, error message
- staleness: uses `git_status_summary()` per-repo to check `remote_diverged`

### 2. Update `/api/status`

Replace the `associated_repos` field (which used removed `get_associates_config`)
with federation info from `graph.iter_repos()`.

### 3. Staleness detection

Per repo with `git_origin`, call `git_status_summary(repo_root)` and include:

- `remote_diverged`, `fast_forward_possible`, `branch`

## Progress

- [x] Baseline: 2770 passed
- [x] Create TASK\_FILE: this file
- [x] Find/create assertions: REQ-d00206-A..D in spec/dev-traceview-review.md
- [x] Write failing tests: 6 tests in tests/server/test\_server\_federation.py
- [x] Implement: /api/repos endpoint, /api/status federation update
- [x] Verify: 2776 passed (6 new), doc sync 68 passed
- [x] Update docs: CHANGELOG.md
- [x] Bump version: 0.104.37
- [ ] Commit
