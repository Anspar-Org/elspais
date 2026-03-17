# Master Plan: FederatedGraph — Legacy Removal and Health Check Federation

**Branch**: claude/cross-cutting-requirements-2Zd0c
**Ticket**: CUR-1082
**Status**: Not Started
**Depends on**: MASTER_PLAN1.md (Config + Multi-Repo) must be complete first

**Background**: With multi-repo federation working (MASTER_PLAN1.md), this plan removes the legacy `sponsors.yml` / YAML-based associate system and replaces all usage with the new `[associates]` config. It also ensures health checks run per-repo with the correct config, which was a primary motivator for the FederatedGraph design.

**Spec**: `docs/superpowers/specs/2026-03-16-federated-graph-design.md`

## Execution Rules

These rules apply to EVERY task below. Do not skip steps. Do not reorder.
If you find yourself writing implementation code without a TASK_FILE and
failing tests, STOP and return to step 1 of the current task.

Read `AGENT_DESIGN_PRINCIPLES.md` before starting the first task.

## Plan

### Task 1: Redirect associate call sites to new config system

Grep for `load_associates_config`, `get_associate_spec_directories`, `sponsors`, `SponsorsConfig` across `src/` and `tests/`. Redirect each call site in `factory.py`, `health.py`, and other commands from the old associate functions to the new multi-repo build pipeline (MASTER_PLAN1 Task 3). Do not delete dead code yet — just redirect consumers.

**TASK_FILE**: `FEDGRAPH_MP2_TASK_1.md`

- [x] **Baseline**: 2743 passed
- [x] **Create TASK_FILE**: FEDGRAPH_MP2_TASK_1.md
- [x] **Implement**: Skip legacy scan_sponsors when [associates] present
- [x] **Verify**: 2743 passed, tested on hht_diary+callisto
- [x] **Update docs**: CHANGELOG.md
- [x] **Bump version**: 0.104.33
- [x] **Commit**: done

---

### Task 2: Remove dead legacy associate code

Remove legacy YAML loading from `associates.py`, `Sponsor`/`SponsorsConfig` aliases, `sponsors.yml` handling, and `sponsors.local.yml` override logic. Remove or update tests that exercise the old system. Keep only what's needed for the new `[associates]` config (or move into config module if appropriate).

**TASK_FILE**: `FEDGRAPH_MP2_TASK_2.md`

- [x] **Baseline**: 2743 passed
- [x] **Create TASK_FILE**: FEDGRAPH_MP2_TASK_2.md
- [x] **Find assertions**: REQ-d00202, REQ-d00203, REQ-p00005-C/D/E/F
- [x] **Write failing tests**: 15 tests in `tests/core/test_legacy_sponsor_removal.py`
- [x] **Implement**: removed all legacy YAML code, aliases, scan_sponsors param
- [x] **Verify**: 2755 passed, doc sync clean
- [x] **Update docs**: CHANGELOG.md, CLAUDE.md
- [x] **Bump version**: 0.104.34
- [x] **Commit**: 8554c9a

---

### Task 3: Per-repo health check delegation with config isolation

Modify health check functions in `commands/health.py` to iterate `fg.iter_repos()`, running config-sensitive checks per-repo with `entry.config`: hierarchy rules, format rules, hash mode, changelog checks. Merge results. Cross-repo broken references (spanning repos) reported separately from within-repo broken refs. Test with a multi-repo federation where two repos have different `[rules.hierarchy]` or `[rules.format]` configs and assert the correct config is applied to each repo's nodes.

**TASK_FILE**: `FEDGRAPH_MP2_TASK_3.md`

- [x] **Baseline**: 2755 passed
- [x] **Create TASK_FILE**: FEDGRAPH_MP2_TASK_3.md
- [x] **Find assertions**: Created REQ-d00204-A..F in spec/07-graph-architecture.md
- [x] **Write failing tests**: 10 tests in tests/commands/test_health_per_repo.py
- [x] **Implement**: per-repo delegation in run_spec_checks, enhanced check_broken_references
- [x] **Verify**: 2765 passed (10 new), doc sync 68 passed
- [x] **Update docs**: CHANGELOG.md
- [x] **Bump version**: 0.104.35
- [ ] **Commit**: pending

---

## Recovery

After `/clear` or context compaction:
1. Read this file (`MASTER_PLAN.md`)
2. Read `AGENT_DESIGN_PRINCIPLES.md`
3. Find the first unchecked box — that is where you resume
4. Read the corresponding TASK_FILE for context on work already done

## Archive

When ALL tasks are complete:

- [ ] Move plan: `mv MASTER_PLAN.md ~/archive/2026-03-16/MASTER_PLAN_CUR-1082_FEDGRAPH_LEGACY.md`
- [ ] Move all TASK_FILEs to the same archive directory
- [ ] Promote next queued plan if one exists: `mv MASTER_PLAN3.md MASTER_PLAN.md`
