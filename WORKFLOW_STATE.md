# Workflow

## Read Objective

read MASTER_PLAN.md
DO NOT READ MASTER_PLAN[0-9]+.md

## Read Design Principles

Read `AGENT_DESIGN_PRINCIPLES.md` for architectural directives

Do each of these steps for every Phase in the MASTER_PLAN.md
Check off each step (change [ ] to [x]) after it is complete.

## Current Task: Remediate Critical Code Review Findings

Address the 7 CRITICAL issues identified during systematic codebase review.

### 1. Understand Current State

- [ ] **EXPLORE**: Read MASTER_PLAN.md for remediation plan
  - [ ] Understand each critical finding
  - [ ] Understand the solution approach
- [ ] **BASELINE**: Ensure tests pass before changes
  - [ ] Run full test suite

### 2. Incremental Refactor

- [ ] **SMALL STEPS**: Complete one phase at a time
  - [ ] Each phase should be independently reviewable
  - [ ] Test after each change
  - [ ] Commit after each phase
- [ ] **PRESERVE BEHAVIOR**: No functional changes unless fixing bugs
  - [ ] Same inputs → same outputs
  - [ ] Same error handling
  - [ ] Same side effects

### 3. Verification

- [ ] **TEST**: All tests still pass after fixes
- [ ] **LINT**: Fix all lint errors

### 4. Commit

- [ ] **COMMIT**: Use `[CUR-240]` prefix in subject

### 5. Phase Complete

- [ ] Mark phase complete in MASTER_PLAN.md
- [ ] Archive completed plan: `mv MASTER_PLAN.md ~/archive/YYYY-MM-DD/MASTER_PLANx.md`
- [ ] promote next plan: `mv MASTER_PLAN[lowest].md MASTER_PLAN.md`
- **CLEAR**: Reset checkboxes for next phase (change all [x] to [ ])
