# Workflow

## Read Objective

read MASTER_PLAN.md
DO NOT READ MASTER_PLAN[0-9]+.md

## Read Design Principles

Read `AGENT_DESIGN_PRINCIPLES.md` for architectural directives

Do each of these steps for every Phase in the MASTER_PLAN.md
Check off each step (change [ ] to [x]) after it is complete.

## Current Task: JNY Trace View Enhancements

Wire up JNY→REQ linking in the trace view via Addresses field. See MASTER_PLAN.md for details.

### 0. Identify Assertions

- [x] **ASSERTIONS**: Search spec/ for assertions related to the work being done
- [x] **CREATE IF MISSING**: If no applicable assertion exists, create one in the appropriate spec file
- [x] **RECORD**: Set `CURRENT_ASSERTIONS` in MASTER_PLAN.md (e.g., `CURRENT_ASSERTIONS: REQ-p00004-A, REQ-p00001-C`)
- All code changes, tests, and commits MUST reference one or more assertions from `CURRENT_ASSERTIONS`

### 1. Understand Current State

- [x] **EXPLORE**: Read MASTER_PLAN.md for task details
- [x] **BASELINE**: Ensure tests pass before changes

### 2. Incremental Implementation

- [x] **SMALL STEPS**: Complete one phase at a time
- [x] **PRESERVE BEHAVIOR**: No unintended changes
- [x] **ASSERTION REFERENCES**: Add `# Implements: REQ-xxx` comments to new/modified source files using IDs from `CURRENT_ASSERTIONS`

### 3. Write Tests

- [x] **TEST**: All tests still pass
- [x] **ASSERTION NAMES**: Test functions MUST include assertion IDs from `CURRENT_ASSERTIONS` in their names (e.g., `test_REQ_p00004_A_validates_hash`)
- [x] **CLASS DOCSTRINGS**: Test classes MUST include `Validates REQ-xxx-Y:` in their docstring

### 4. Verification

- [x] **LINT**: Fix all lint errors

### 5. Commit

- [ ] **COMMIT**: Use ticket prefix in subject

### 6. Phase Complete

- [ ] Mark phase complete in MASTER_PLAN.md
- [ ] Archive completed plan: `mv MASTER_PLAN.md ~/archive/YYYY-MM-DD/MASTER_PLANx.md`
- [ ] Promote next plan: `mv MASTER_PLAN[lowest].md MASTER_PLAN.md`
- **CLEAR**: Reset checkboxes for next phase
