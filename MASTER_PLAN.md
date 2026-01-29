# MASTER PLAN: MCP Server Implementation

> **Workflow:** Follow `~/.claude/refactor-workflow.md` for each phase (SPEC → TEST → IMPL → DEBUG → COMMIT)
> **Principles:** Follow `AGENT_DESIGN_PRINCIPLES.md` for architectural directives

## Overview

**Goal**: Build an MCP server using the correct GraphNode iterator-only API. The MCP must be a pure interface layer - no data duplication, no caching, graph as single source of truth.

---

## Workflow Checklist (Required for Each Phase)

When adding or completing a phase in this file, verify ALL steps are followed:

| Step | Action | Required |
|------|--------|----------|
| **SPEC** | Verify or create requirement in `spec/` | ✅ For code features |
| **TEST** | Write tests BEFORE implementation (TDD) | ✅ For code features |
| **IMPL** | Implement the feature | ✅ Always |
| **DEBUG** | Run tests, verify all pass | ✅ Always |
| **LINT** | Fix ALL lint errors (Python + Markdown) | ✅ Always |
| **COMMIT** | Git commit with `[TICKET]` prefix | ✅ Always |

> ⚠️ **DO NOT use `--no-verify`** to skip pre-commit hooks. Fix markdown lint errors
> (blank lines around headings/lists, etc.) before committing. The hooks exist to
> maintain code quality.

**Sub-Agent Delegation:** The following chores should be delegated to sub-agents
(can be passed as a group of parallel tasks when appropriate):

- Update CHANGELOG.md with new version entry
- Bump version in pyproject.toml
- Update CLAUDE.md if architecture changed
- Fix markdown lint errors in modified files
- Update MASTER_PLAN.md progress tracking table

This keeps the main agent focused on core implementation while sub-agents handle
mechanical documentation tasks.

**Phase Completion Checklist** (copy into each phase when completing):

```markdown
- [ ] Spec requirement exists or verified
- [ ] Tests written/updated and passing
- [ ] Implementation complete
- [ ] All related tests pass (`pytest tests/relevant/`)
- [ ] CHANGELOG.md updated
- [ ] Version bumped in pyproject.toml
- [ ] All lint errors fixed (ruff, black, markdownlint)
- [ ] Committed with ticket prefix (no --no-verify)
```

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

**Completion Checklist:**

- [x] Spec requirement exists or verified (docs only, no spec needed)
- [x] Tests written/updated and passing (64 doc sync tests)
- [x] Implementation complete (docs/cli/mcp.md, server instructions)
- [x] All related tests pass (93 total MCP + doc tests)
- [x] CHANGELOG.md updated (v0.37.0)
- [x] Version bumped in pyproject.toml (0.37.0)
- [x] Committed with ticket prefix ([CUR-514])

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

---

## Progress Tracking

| Phase | Status | Notes |
|-------|--------|-------|
| 0.1 Create MCP Spec | [x] Complete | spec/08-mcp-server.md created |
| 0.2 Core Tool Reqs | [x] Complete | REQ-o00060 defines core tools |
| 0.3 New Feature Reqs | [x] Complete | REQ-o00061 workspace, keywords deferred to Phase 4 |
| 0.4 Update INDEX | [x] Complete | 12 new requirements indexed |
| 1 Core Server | [x] Complete | 5 core tools, 19 passing tests |
| 2.1 Workspace Tools | [x] Complete | get_workspace_info(), get_project_summary(), 10 tests |
| 2.2 MCP Docs | [x] Complete | docs/cli/mcp.md, server instructions |
| 3.1 File Mutators | [ ] Not Started | |
| 3.2 In-Memory Mutations | [ ] Not Started | |
| 4.1 Keyword Extractor | [ ] Not Started | |
| 4.2 Trace View Keywords | [ ] Not Started | |
| 4.3 MCP Keywords | [ ] Not Started | |

---

## Current Session Notes

*Add notes here as work progresses*
