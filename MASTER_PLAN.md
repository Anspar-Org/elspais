# MASTER PLAN

> **Principles:** Read `AGENT_DESIGN_PRINCIPLES.md` for architectural directives

## Overview

**Goal**: Complete MCP server test coverage tools and achieve full test-requirement traceability.

**Completed Phases**: See `~/PLAN-2026-01-28.md` for Phases 0-5 (MCP Server core implementation).

---

## Workflow Steps

**Structure:** `For each Phase → Do each Workflow Step → Clear checkboxes → Next Phase`

Use this checklist for the **current phase**. After committing, reset all boxes to `[ ]`.

### 1. Core Implementation

- [ ] **SPEC**: Verify or create requirement in `spec/` (for code features)
  - [ ] Search for existing specs related to work
  - [ ] Create/update spec with assertions if needed
  - [ ] Note assertion IDs (e.g., REQ-xxx-A) for TEST phase
- [ ] **TEST**: Write tests BEFORE implementation - TDD (for code features)
  - [ ] Search for existing tests
  - [ ] Include assertion refs in test names (e.g., `test_REQ_xxx_A_validates_input`)
  - [ ] Tests should FAIL until IMPL phase
- [ ] **IMPL**: Implement the feature
- [ ] **DEBUG**: Run tests, verify all pass

### 2. Review (use sub-agent)

- [ ] **REVIEW**: Have sub-agent evaluate implementation
  - [ ] Using existing APIs appropriately?
  - [ ] Complies with spec requirements?
  - [ ] No unnecessary complexity?

### 3. Documentation Chores (delegate to sub-agents in parallel)

- [ ] Update CHANGELOG.md with new version entry
- [ ] Bump version in pyproject.toml
- [ ] Update CLAUDE.md if architecture changed

### 4. Quality & Commit

- [ ] **LINT**: Fix ALL lint errors (ruff, black, markdownlint)
- [ ] **COMMIT**: Git commit with `[TICKET]` prefix

> ⚠️ **DO NOT use `--no-verify`** to skip pre-commit hooks. Fix markdown lint
> errors (blank lines around headings/lists) before committing.

### 5. Phase Complete

- [ ] Mark phase complete below
- [ ] **CLEAR**: Reset all checkboxes in Workflow Steps above to `[ ]` for next phase

---

## Refactor Workflow

Use this workflow when restructuring existing code without changing behavior.

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

- [ ] **COMMIT**: Use `refactor:` or `chore:` prefix
- [ ] **CLEAR**: Reset checkboxes for next refactor

---

## Phase 6: Test Coverage Tools

**Goal**: Add MCP tools for analyzing test-requirement relationships, discovered as high-priority gaps during dogfooding.

### 6.1 Specification

- [x] Add requirements to `spec/08-mcp-server.md` for coverage tools
- [x] Define tool signatures and return types

### 6.2 Implement `get_test_coverage()`

- [x] Create tool: `get_test_coverage(req_id: str) -> dict`
- [x] Returns TEST nodes that reference the requirement
- [x] Returns TEST_RESULT nodes for those tests
- [x] Identifies assertion coverage gaps (assertions with no tests)
- [x] Add tests with REQ-assertion naming pattern

### 6.3 Implement `get_uncovered_assertions()`

- [x] Create tool: `get_uncovered_assertions(req_id: str = None) -> list`
- [x] When `req_id` is None, scan all requirements
- [x] Return assertions that have no TEST node references
- [x] Include parent requirement context in results
- [x] Add tests with REQ-assertion naming pattern

### 6.4 Implement `find_assertions_by_keywords()`

- [x] Create tool: `find_assertions_by_keywords(keywords: list[str], match_all: bool = True) -> list`
- [x] Search assertion text for matching keywords
- [x] Return assertion id, text, label, and parent requirement context
- [x] Complement to existing `find_by_keywords()` which finds requirements
- [x] Add tests with REQ-assertion naming pattern

### 6.5 Documentation

- [x] Update MCP server help/instructions
- [x] Add usage examples to dogfooding report

---

## Phase 7: Comprehensive Assertion Coverage

**Goal**: Achieve full test-requirement traceability. Every test should reference an assertion. Every code module should trace to a requirement. Use Phase 6 tools to systematically close coverage gaps.

### 7.1 Analyze Current State

- [x] Run `get_uncovered_assertions()` to get full gap list
- [x] Generate initial coverage report: assertions covered vs total
- [x] Create `docs/NEW_SPECS.md` to track proposed requirements
- [x] **BUG FIX**: TestParser regex now captures assertion suffixes (e.g., `_A` in `test_REQ_xxx_A_...`)

### 7.2 Test File Analysis (Subagent Loop)

For each test file in `tests/`:

- [ ] Use subagent to analyze test file purpose
- [ ] Match tests to existing requirements using `find_assertions_by_keywords()`
- [ ] Identify tests that validate undocumented behavior
- [ ] For unmatched tests, either:
  - Rename test to reference existing assertion, OR
  - Add proposed requirement to `NEW_SPECS.md`

**Subagent Instructions:**

> Analyze this test file. For each test function:
>
> 1. What behavior does it validate?
> 2. Search for matching assertions using keywords from the test
> 3. If match found: propose test rename to `test_REQ_xxx_A_description`
> 4. If no match: propose new requirement for NEW_SPECS.md
>
> Goal: No test without a requirement link.

### 7.3 Code Module Analysis (Subagent Loop)

For each source file in `src/elspais/`:

- [ ] Use subagent to analyze module purpose
- [ ] Match to existing requirements
- [ ] For unmatched modules, add proposed requirement to `NEW_SPECS.md`

**Subagent Instructions:**

> Analyze this source module. What requirements does it implement?
>
> 1. List the main functions/classes and their purposes
> 2. Search for matching requirements using `find_by_keywords()`
> 3. If no requirement exists: propose one for NEW_SPECS.md
>
> Goal: No code without a requirement.

### 7.4 Propose New Requirements

- [ ] Review `NEW_SPECS.md` for proposed requirements
- [ ] Group by topic/module
- [ ] Prioritize: Active code > Draft features > Future ideas
- [ ] Format as proper requirement specs with assertions

### 7.5 Implement Coverage Improvements

- [ ] Rename tests to reference assertions (batch by file)
- [ ] Add approved requirements from NEW_SPECS.md to `spec/`
- [ ] Re-run coverage analysis to verify improvement

### 7.6 Final Verification

- [ ] Target: >80% assertion coverage (from current 14%)
- [ ] Target: All active code modules have requirements
- [ ] Document lessons learned in dogfooding report
