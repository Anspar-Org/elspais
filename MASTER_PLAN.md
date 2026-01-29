# MASTER PLAN

> **Principles:** Read `AGENT_DESIGN_PRINCIPLES.md` for architectural directives

## Overview

**Goal**: Build an MCP server using the correct GraphNode iterator-only API. The MCP must be a pure interface layer - no data duplication, no caching, graph as single source of truth.

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

## Phase 0: MCP Specification ✅

### 0.1 Create MCP Spec File

- [x] Create `spec/08-mcp-server.md` with:
  - PRD-level requirement: MCP Server for AI-Driven Requirements Management
  - OPS-level requirements: Core tools, workspace context, mutations
  - DEV-level requirements: Specific tool implementations
  - Assertions enforcing "graph as source of truth" principle
  - Reference to REQ-p00050-B (consume graph directly)

### 0.2 Define Core Tool Requirements

- [x] `get_graph_status()` - Graph state and statistics
- [x] `refresh_graph()` - Force rebuild
- [x] `search()` - Search requirements
- [x] `get_requirement()` - Single requirement details
- [x] `get_hierarchy()` - Ancestors/children navigation

### 0.3 Define New Feature Requirements

- [x] `get_workspace_info()` - Repo path, project name, config
- [x] `get_project_summary()` - Counts by level, coverage stats
- [ ] Keyword extraction from requirements/assertions (deferred to Phase 4)
- [ ] Keyword-based search and filtering (deferred to Phase 4)

### 0.4 Update INDEX.md

- [x] Add new MCP requirements to spec/INDEX.md

---

## Phase 1: Core MCP Server ✅

- [x] Create `src/elspais/mcp/__init__.py` with MCP_AVAILABLE check
- [x] Create `src/elspais/mcp/__main__.py` entry point
- [x] Create `src/elspais/mcp/server.py` with core tools:
  - [x] `get_graph_status()` - Is graph stale, node counts
  - [x] `refresh_graph(full)` - Force rebuild
  - [x] `search(query, field, regex)` - Search requirements
  - [x] `get_requirement(req_id)` - Single requirement details
  - [x] `get_hierarchy(req_id)` - Ancestors/children

---

## Phase 2: MCP Docs & Repo Context ✅

### 2.1 Workspace Info Tools

- [x] Add `get_workspace_info()` - "What repo am I serving?"
  - Returns: repo path, project name, config summary
- [x] Add `get_project_summary()` - "Serve info about this repo"
  - Returns: requirement counts by level, coverage stats, recent changes

### 2.2 MCP Documentation

- [x] Add comprehensive help/docs to MCP server instructions
- [x] Document all available tools and their parameters

---

## Phase 3: Graph Mutation Parity ✅

### 3.1 File Mutators Use Graph Mutators ✅

- [x] Audit file mutation tools vs graph mutation API
- [x] Add git safety branch utilities for file mutation rollback
- [x] Add `change_reference_type()` - Modify Implements/Refines in spec files
- [x] Add `move_requirement()` - Relocate requirements between spec files
- [x] Add `restore_from_safety_branch()` - Revert file changes
- [x] Add `list_safety_branches()` - List available safety branches
- [x] Auto-refresh graph after file mutations (REQ-o00063-F)
- [ ] Add `transform_with_ai()` (deferred - requires AI integration)

### 3.2 In-Memory Mutations with Undo ✅

- [x] Node mutations: rename, update_title, change_status, add, delete
- [x] Assertion mutations: add, update, delete, rename
- [x] Edge mutations: add, change_kind, delete, fix_broken
- [x] Undo: undo_last, undo_to, get_mutation_log

---

## Phase 4: Keyword Extraction ✅

### 4.1 Add Keyword Extractor to Parsing ✅

- [x] Extract keywords from requirement body/title
- [x] Extract keywords from assertion text
- [x] Store as field: `node.get_field("keywords")`
- [x] Filter stopwords and common terms
- [x] Normalize to lowercase, deduplicate

### 4.2 Integrate with Trace View

- [ ] Add keyword filtering to `graph --trace` (deferred)
- [ ] Filter by keywords in HTML trace view (deferred)

### 4.3 Integrate with MCP ✅

- [x] Add keyword search to `search()` tool (field="keywords")
- [x] Add `find_by_keywords(keywords)` tool
- [x] Add `get_all_keywords()` tool for keyword discovery

---

## Phase 5: MCP Dogfooding ✅

**Goal**: Validate the MCP server's utility by using it to improve test traceability in this codebase.

### 5.1 Improve Test Traceability

- [x] Tests that validate requirements should reference assertion IDs in their names
- [x] Test names should follow pattern: `test_REQ_xxx_A_describes_behavior`
- [x] TEST_RESULT nodes should link to requirements in trace view

### 5.2 Document MCP Gaps

- [x] Identify any missing tools needed during the dogfooding process
- [x] Note any API ergonomic issues or confusing tool behaviors
- [x] Create issues for MCP enhancements discovered

### 5.3 Verify Traceability Improvement

- [x] Trace view shows test coverage for requirements
- [x] Coverage metrics reflect test validation
- [x] Documentation captures lessons learned

**Report**: See `docs/phase5-dogfooding-report.md` for detailed findings.

---

## Phase 6: Test Coverage Tools

**Goal**: Add MCP tools for analyzing test-requirement relationships, discovered as high-priority gaps during dogfooding.

### 6.1 Specification

- [ ] Add requirements to `spec/08-mcp-server.md` for coverage tools
- [ ] Define tool signatures and return types

### 6.2 Implement `get_test_coverage()`

- [ ] Create tool: `get_test_coverage(req_id: str) -> dict`
- [ ] Returns TEST nodes that reference the requirement
- [ ] Returns TEST_RESULT nodes for those tests
- [ ] Identifies assertion coverage gaps (assertions with no tests)
- [ ] Add tests with REQ-assertion naming pattern

### 6.3 Implement `get_uncovered_assertions()`

- [ ] Create tool: `get_uncovered_assertions(req_id: str = None) -> list`
- [ ] When `req_id` is None, scan all requirements
- [ ] Return assertions that have no TEST node references
- [ ] Include parent requirement context in results
- [ ] Add tests with REQ-assertion naming pattern

### 6.4 Implement `find_assertions_by_keywords()`

- [ ] Create tool: `find_assertions_by_keywords(keywords: list[str], match_all: bool = True) -> list`
- [ ] Search assertion text for matching keywords
- [ ] Return assertion id, text, label, and parent requirement context
- [ ] Complement to existing `find_by_keywords()` which finds requirements
- [ ] Add tests with REQ-assertion naming pattern

### 6.5 Documentation

- [ ] Update MCP server help/instructions
- [ ] Add usage examples to dogfooding report

---

## Phase 7: Comprehensive Assertion Coverage

**Goal**: Achieve full test-requirement traceability. Every test should reference an assertion. Every code module should trace to a requirement. Use Phase 6 tools to systematically close coverage gaps.

### 7.1 Analyze Current State

- [ ] Run `get_uncovered_assertions()` to get full gap list
- [ ] Generate initial coverage report: assertions covered vs total
- [ ] Create `docs/NEW_SPECS.md` to track proposed requirements

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
