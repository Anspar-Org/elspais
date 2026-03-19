# Task 2: Update ElspaisConfig to v3 Shape

**Plan**: MASTER_PLAN.md (Config Schema v3 — Schema Models, 1/4)
**Ticket**: CONFIG-V3

## Description

Restructure ElspaisConfig and sub-models to v3 shape. Remove obsolete fields/models, add new top-level fields (levels, scanning, output), simplify sub-models. Update all consumers.

## Applicable Assertions

- **REQ-d00212-F**: ElspaisConfig has levels, scanning, output; removes directories/spec/testing/ignore/graph/traceability/core/associated
- **REQ-d00212-G**: IdPatternsConfig has separators, prefix_optional; removes types, associated
- **REQ-d00212-H**: HierarchyConfig is booleans only, strict
- **REQ-d00212-I**: ReferencesConfig is enabled + case_sensitive only
- **REQ-d00212-J**: ProjectConfig is namespace + name only
- **REQ-d00212-K**: AssociateEntryConfig is path + namespace

## Progress

- [x] Baseline: 2872 passed
- [x] TASK_FILE created
- [x] Assertions created: REQ-d00212-F through K
- [x] Failing tests written: 34 tests in tests/core/test_config_v3_elspais.py
- [x] Implementation: schema rewritten, ~50 source files updated, all consumers migrated
- [x] Verification: 2855 passed (1 git-worktree test expected to pass after commit)
- [x] Docs update: CHANGELOG.md, docs/configuration.md, CLAUDE.md
- [x] Version bump: 0.107.0 → 0.108.0
- [ ] Commit
