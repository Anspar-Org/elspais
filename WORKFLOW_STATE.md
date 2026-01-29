# Workflow

## Read Objective
read MASTER_PLAN.md
DO NOT READ MASTER_PLAN[0-9]+.md 

## Read Design Principles
Read `AGENT_DESIGN_PRINCIPLES.md` for architectural directives

### 1. Understand Current State

- [ ] **EXPLORE**: Map the code being refactored
  - [ ] Identify all files/functions affected
  - [ ] Document current behavior and contracts
  - [ ] List existing tests that cover the code
- [ ] **BASELINE**: Ensure tests pass before changes
  - [ ] Run full test suite
  - [ ] Note any flaky or slow tests

### 2. Incremental Refactor

- [ ] **SMALL STEPS**: Make one change at a time
  - [ ] Each step should be independently testable
  - [ ] Run tests after each step
  - [ ] Commit working states frequently
- [ ] **PRESERVE BEHAVIOR**: No functional changes
  - [ ] Same inputs → same outputs
  - [ ] Same error handling
  - [ ] Same side effects

### 3. Verification

- [ ] **TEST**: All original tests still pass
- [ ] **REVIEW**: Have sub-agent verify no behavior change
- [ ] **LINT**: Fix all lint errors

### 4. Commit

- [ ] **COMMIT**: Use `[TICKET]` prefix in subject (replace with actual ticket ID)
- [ ] Mark phase complete

### 5. Phase Complete

- Archive completed plan: `mv MASTER_PLAN.md ~/archive/YYYY-MM-DD/MASTER_PLANx.md`
- promote next plan: `mv MASTER_PLAN[lowest].md MASTER_PLAN.md`
- [ ] **CLEAR**: Reset checkboxes for next phase

---

## Usage

1. Copy this template to repo as WORKFLOW_STATE.md 
2. Replace `[TICKET]` with actual ticket ID (e.g., `[CUR-240]`)
3. Replace `YYYY-MM-DD` with current date
2. Remove the "Usage" section from WORKFLOW_STATE.md

## File Naming Convention

- `MASTER_PLAN.md` - Current active phase (no number)
- `MASTER_PLAN2.md` through `MASTER_PLANn.md` - Queued phases
- `~/archive/YYYY-MM-DD/MASTER_PLANx.md` - Completed phases
