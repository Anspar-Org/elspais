# Workflow

## Read Objective

read MASTER_PLAN.md
DO NOT READ MASTER_PLAN[0-9]+.md

## Read Design Principles

Read `AGENT_DESIGN_PRINCIPLES.md` for architectural directives

Do each of these steps for every Phase in the MASTER_PLAN.md
Check off each step (change [ ] to [x]) after it is complete.

## Current Task: Codebase Review for Design Principle Violations

Systematic review of the elspais codebase to identify design principle violations, anti-patterns, and code duplication.

### 1. Understand Current State

- [ ] **EXPLORE**: Read MASTER_PLAN.md for review methodology
  - [ ] Understand review phases (MCP Server, Graph Builder, CLI, etc.)
  - [ ] Understand severity levels (CRITICAL, HIGH, MEDIUM, LOW)
  - [ ] Understand output format for findings
- [ ] **BASELINE**: Ensure tests pass before changes
  - [ ] Run full test suite
  - [ ] Note any flaky or slow tests

### 2. Incremental Refactor

- [ ] **SMALL STEPS**: Complete one phase at a time
  - [ ] Each phase should be independently reviewable
  - [ ] Document findings after each phase
  - [ ] Commit any fixes made
- [ ] **PRESERVE BEHAVIOR**: No functional changes unless fixing bugs
  - [ ] Same inputs → same outputs
  - [ ] Same error handling
  - [ ] Same side effects

### 3. Verification

- [ ] **TEST**: All tests still pass after any fixes
- [ ] **REVIEW**: Findings documented in MASTER_PLAN.md
- [ ] **LINT**: Fix all lint errors

### 3.5 Documentation (for new features/changes)

- [ ] **CHANGELOG**: Update CHANGELOG.md if changes made
- [ ] **DOCS**: Update docs if needed
- [ ] **SYNC**: Run `pytest tests/test_doc_sync.py` to verify docs match implementation

### 4. Commit

- [ ] **COMMIT**: Use `[CUR-240]` prefix in subject (if making fixes)

### 5. Phase Complete

- [ ] Mark phase complete in MASTER_PLAN.md
- [ ] Archive completed plan: `mv MASTER_PLAN.md ~/archive/YYYY-MM-DD/MASTER_PLANx.md`
- [ ] promote next plan: `mv MASTER_PLAN[lowest].md MASTER_PLAN.md`
- **CLEAR**: Reset checkboxes for next phase (change all [x] to [ ])
