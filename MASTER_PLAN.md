# MASTER PLAN: MCP Server Clean Rewrite

> **Workflow:** Follow `~/.claude/refactor-workflow.md` for each phase (SPEC → TEST → IMPL → DEBUG → COMMIT)

## Overview

**Goal**: Remove the broken MCP implementation and rebuild from scratch using the correct GraphNode iterator-only API. The MCP must be a pure interface layer - no data duplication, no caching, graph as single source of truth.

---

## Phase 0: MCP Specification

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

## Phase 1: Core MCP Server

### 1.1 Remove Existing MCP Code
- [ ] Delete all files in `src/elspais/mcp/`
- [ ] Verify no imports break elsewhere

### 1.2 Create Minimal MCP Server
- [ ] Create `src/elspais/mcp/__init__.py` with MCP_AVAILABLE check
- [ ] Create `src/elspais/mcp/__main__.py` entry point
- [ ] Create `src/elspais/mcp/server.py` with core tools:
  - [ ] `get_graph_status()` - Is graph stale, node counts
  - [ ] `refresh_graph(full)` - Force rebuild
  - [ ] `search(query, field, regex)` - Search requirements
  - [ ] `get_requirement(req_id)` - Single requirement details
  - [ ] `get_hierarchy(req_id)` - Ancestors/children

---

## Phase 2: MCP Docs & Repo Context

### 2.1 Workspace Info Tools
- [ ] Add `get_workspace_info()` - "What repo am I serving?"
  - Returns: repo path, project name, config summary
- [ ] Add `get_project_summary()` - "Serve info about this repo"
  - Returns: requirement counts by level, coverage stats, recent changes

### 2.2 MCP Documentation
- [ ] Add comprehensive help/docs to MCP server instructions
- [ ] Document all available tools and their parameters

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
| 1.1 Remove MCP | [ ] Not Started | |
| 1.2 Core Server | [ ] Not Started | |
| 2.1 Workspace Tools | [ ] Not Started | |
| 2.2 MCP Docs | [ ] Not Started | |
| 3.1 File Mutators | [ ] Not Started | |
| 3.2 In-Memory Mutations | [ ] Not Started | |
| 4.1 Keyword Extractor | [ ] Not Started | |
| 4.2 Trace View Keywords | [ ] Not Started | |
| 4.3 MCP Keywords | [ ] Not Started | |

---

## Current Session Notes

*Add notes here as work progresses*

