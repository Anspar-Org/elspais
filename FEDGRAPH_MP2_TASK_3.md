# Task 3: Per-Repo Health Check Delegation with Config Isolation

**Ticket**: CUR-1082
**Branch**: claude/cross-cutting-requirements-2Zd0c
**Baseline**: 2755 passed

## Objective

Modify health check functions in `commands/health.py` to iterate `fg.iter_repos()`, running
config-sensitive checks per-repo with `entry.config`. Merge results. Cross-repo broken references
reported separately from within-repo broken refs.

## APPLICABLE_ASSERTIONS

- REQ-d00204-A: Config-sensitive checks run per-repo with repo's own config
- REQ-d00204-B: Non-config-sensitive checks run once on full federation
- REQ-d00204-C: Per-repo results merged with repo attribution in findings
- REQ-d00204-D: HealthFinding supports optional `repo` field
- REQ-d00204-E: Broken refs: within-repo=error, cross-repo with error-state target=warning
- REQ-d00204-F: run_spec_checks iterates iter_repos() using from_single() per repo

## Approach

### Per-Repo Delegation in `run_spec_checks`

Split checks into:

**Global checks** (run on full federation):
- `check_spec_files_parseable`
- `check_spec_no_duplicates`
- `check_broken_references` (with cross-repo attribution)
- `check_spec_hash_integrity`
- `check_spec_index_current`

**Per-repo checks** (run per-repo with repo's own config):
- `check_spec_hierarchy_levels`
- `check_spec_format_rules`
- `check_spec_implements_resolve` / `check_spec_refines_resolve`
- `check_structural_orphans`
- `check_spec_changelog_present/current/format`

For per-repo checks: iterate `graph.iter_repos()`, create `FederatedGraph.from_single()` per repo,
run check with that repo's config, merge findings with repo attribution.

### Cross-Repo Broken References

Enhance `check_broken_references` to annotate findings with source/target repo names.
Within-repo broken refs are errors; cross-repo broken refs (when target repo is missing/error-state)
are reported as warnings with clone assistance info.

### HealthFinding Enhancement

Add optional `repo` field to `HealthFinding` for per-repo attribution in reports.

## Implementation Summary

### HealthFinding (REQ-d00204-D)

- Added `repo: str | None = None` field to `HealthFinding` dataclass
- Updated `to_dict()` to include `repo` field

### run_spec_checks (REQ-d00204-A, B, F)

- Split checks into global (non-config-sensitive) and per-repo (config-sensitive)
- Global checks run once on full federation: files_parseable, no_duplicates, broken_references, hash_integrity
- Per-repo checks iterate `graph.iter_repos()`, create `FederatedGraph.from_single()` per repo
- Config normalization: handles both raw dict and ConfigLoader in RepoEntry.config
- Backward compat: wraps bare TraceGraph in FederatedGraph if passed

### check_broken_references (REQ-d00204-E)

- Within-repo broken refs: severity="error"
- Cross-repo broken refs (target repo in error state): severity="warning"
- All findings annotated with source repo name via `repo_for()`
- Backward compat: handles bare TraceGraph (no iter_repos)

### _annotate_findings helper (REQ-d00204-C)

- Stamps all findings in a HealthCheck with the source repo name

## Progress

- [x] Baseline: 2755 passed
- [x] Create TASK_FILE: this file
- [x] Find/create assertions: REQ-d00204-A..F in spec/07-graph-architecture.md
- [x] Write failing tests: 10 tests in tests/commands/test_health_per_repo.py
- [x] Implement: health.py changes + existing test updates
- [x] Verify: 2765 passed (10 net new), doc sync 68 passed
- [x] Update docs: CHANGELOG.md
- [x] Bump version: 0.104.35
- [ ] Commit
