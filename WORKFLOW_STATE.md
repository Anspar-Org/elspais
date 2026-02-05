# Workflow

## Read Objective

read MASTER_PLAN.md
DO NOT READ MASTER_PLAN[0-9]+.md

## Read Design Principles

Read `AGENT_DESIGN_PRINCIPLES.md` for architectural directives

Do each of these steps for every Phase in the MASTER_PLAN.md
Check off each step (change [ ] to [x]) after it is complete.

## Current Task: [CUR-514] Configurable Hash Mode (full-text / normalized-text)

Add `hash_mode` config setting with two modes: `full-text` (default, current behavior) and `normalized-text` (assertions-only + cosmetic normalization). See MASTER_PLAN.md for 6-phase breakdown.

### 1. Understand Current State

- [x] **EXPLORE**: Read MASTER_PLAN.md for task details
- [x] **BASELINE**: Ensure tests pass before changes (896 passed)

### 2. Incremental Implementation

- [x] **SMALL STEPS**: Complete one phase at a time
- [x] **PRESERVE BEHAVIOR**: No unintended changes

### 3. Verification

- [x] **TEST**: All tests still pass (933 passed)
- [x] **LINT**: Fix all lint errors

### 4. Commit

- [x] **COMMIT**: Use ticket prefix in subject (6 commits: Phase 1-6)

### 5. Phase Complete

- [x] Mark phase complete in MASTER_PLAN.md
- [ ] Archive completed plan: `mv MASTER_PLAN.md ~/archive/YYYY-MM-DD/MASTER_PLANx.md`
- [ ] Promote next plan: `mv MASTER_PLAN[lowest].md MASTER_PLAN.md`
- **CLEAR**: Reset checkboxes for next phase

### Session Progress (2026-02-05)

Completed all 6 phases of MASTER_PLAN:
- Phase 1: Spec update (680de48)
- Phase 2: Config defaults (3fa89af)
- Phase 3: Hasher normalization functions (cf0b08e)
- Phase 4: Builder + Commands hash mode branching (8e24019)
- Phase 5: Tests — 37 new tests, 933 total (91eb841)
- Phase 6: Fixture alignment + file_mutations.py bug fix (e7dc4e7)

Key finding: body_text extraction differs between main branch and feature branch
(metadata line inclusion). Neither full-text nor normalized-text matches hht_diary
stored hashes — main branch skips metadata line, feature branch includes it.

Next: Switch to normalized-text mode and fix body_text extraction parity.
