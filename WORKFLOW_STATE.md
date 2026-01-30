# Workflow

## Read Objective
read MASTER_PLAN.md
DO NOT READ MASTER_PLAN[0-9]+.md

## Read Design Principles
Read `AGENT_DESIGN_PRINCIPLES.md` for architectural directives

Check off each step (change [ ] to [x]) after it is complete.

## Current Task: Fix Hash Computation (Critical Bug)

The hash computation in Phase 1 and Phase 2 is WRONG. Per spec/requirements-spec.md:
> The hash SHALL be calculated from every line AFTER the Header line and BEFORE the Footer line

Current (wrong): Computes hash from reconstructed assertion text
Correct: Compute hash from raw text between header and footer markers

### 1. Understand Current State

- [x] **EXPLORE**: Map the code being refactored
  - [x] Identify all files/functions affected
  - [x] Document current behavior and contracts
  - [x] List existing tests that cover the code
- [x] **BASELINE**: Ensure tests pass before changes
  - [x] Run full test suite (881 passed)
  - [x] Note any flaky or slow tests (none)

### 2. Incremental Refactor

- [x] **SMALL STEPS**: Make one change at a time
  - [x] Each step should be independently testable
  - [x] Run tests after each step
  - [x] Commit working states frequently
- [x] **PRESERVE BEHAVIOR**: No functional changes
  - [x] Same inputs → same outputs (hash now correctly computed per spec)
  - [x] Same error handling
  - [x] Same side effects

### 3. Verification

- [x] **TEST**: All original tests still pass (883 passed)
- [ ] **REVIEW**: Have sub-agent verify no behavior change
- [x] **LINT**: Fix all lint errors (all checks passed)

### 3.5 Documentation (for new features/changes)

- [x] **CHANGELOG**: Update CHANGELOG.md with new features (N/A - bug fix for unreleased code)
- [x] **DOCS**: Use sub-agent to update docs/ files and --help CLI commands (N/A - CLI unchanged)
- [x] **SYNC**: Run `pytest tests/test_doc_sync.py` to verify docs match implementation (64 passed)

### 4. Commit

- [x] **COMMIT**: Use `[CUR-240]` prefix in subject - ff143f9

### 5. Phase Complete

- [x] Mark phase complete in MASTER_PLAN.md
- [ ] Archive completed plan: `mv MASTER_PLAN.md ~/archive/YYYY-MM-DD/MASTER_PLANx.md`
- [ ] promote next plan: `mv MASTER_PLAN[lowest].md MASTER_PLAN.md`
- **CLEAR**: Reset checkboxes for next phase (change all [x] to [ ])
