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

## Phase 3: Graph Mutation Parity

### 3.1 File Mutators Use Graph Mutators

- [ ] Audit file mutation tools vs graph mutation API
- [ ] Ensure consistency: file mutators delegate to graph mutators
- [ ] Add `change_reference_type()`
- [ ] Add `move_requirement()`
- [ ] Add `transform_with_ai()`

### 3.2 In-Memory Mutations with Undo

- [ ] Node mutations: rename, update_title, change_status, add, delete
- [ ] Assertion mutations: add, update, delete, rename
- [ ] Edge mutations: add, change_kind, delete, fix_broken
- [ ] Undo: undo_last, undo_to, get_mutation_log

---

## Phase 4: Keyword Extraction

### 4.1 Add Keyword Extractor to Parsing

- [ ] Extract keywords from requirement body/title
- [ ] Extract keywords from assertion text
- [ ] Store as field: `node.get_field("keywords")`

### 4.2 Integrate with Trace View

- [ ] Add keyword filtering to `graph --trace`
- [ ] Filter by keywords in HTML trace view

### 4.3 Integrate with MCP

- [ ] Add keyword search to `search()` tool
- [ ] Add `find_by_keywords(keywords)` tool
- [ ] Support keyword-based requirement/assertion discovery
