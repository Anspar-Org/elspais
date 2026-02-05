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

- [ ] **SMALL STEPS**: Complete one phase at a time
- [ ] **PRESERVE BEHAVIOR**: No unintended changes

### 3. Verification

- [ ] **TEST**: All tests still pass
- [ ] **LINT**: Fix all lint errors

### 4. Commit

- [ ] **COMMIT**: Use ticket prefix in subject

### 5. Phase Complete

- [ ] Mark phase complete in MASTER_PLAN.md
- [ ] Archive completed plan: `mv MASTER_PLAN.md ~/archive/YYYY-MM-DD/MASTER_PLANx.md`
- [ ] Promote next plan: `mv MASTER_PLAN[lowest].md MASTER_PLAN.md`
- **CLEAR**: Reset checkboxes for next phase
