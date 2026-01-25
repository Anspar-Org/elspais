# Master Plan: MCP Graph Integration

This file tracks a queue of enhancement issues for MCP graph integration. After each `/clear`, Claude should read this file and continue with the next incomplete issue.

**Branch:** feature/CUR-514-viewtrace-port
**Reference:** `.claude/future-mcp-graph-integration.md`

## Workflow

1. **Pick next issue**: Find the first `[ ]` (incomplete) issue below
2. **Refine into plan**: Use sub-agents to analyze the codebase and create a detailed implementation plan
3. **Implement**: Execute the plan, writing code and tests
4. **Verify**: Run tests, ensure the feature works
5. **Mark complete**: Change `[ ]` to `[x]` for the issue
6. **Commit**: Create a git commit for the changes
7. **Clear context**: Run `/clear` to free up context
8. **Resume**: After clear, read this file and continue with next issue

---

## Phase 1: Read-Only Graph with Lazy Refresh

### [x] 1.1 Add GraphState to MCP Context

- **Priority**: P1 - Foundation for all graph features
- **Description**: Add `TraceGraph` caching with staleness tracking to `WorkspaceContext`.
- **Files**:
  - `src/elspais/mcp/context.py`
- **Tasks**:
  - Add `GraphState` dataclass with `graph`, `validation`, `file_mtimes`
  - Add `_graph_state: Optional[GraphState]` to `WorkspaceContext`
  - Implement `get_graph(force_refresh=False)` method
  - Implement `_build_graph()` using `TraceGraphBuilder`
  - Implement `is_stale()` checking file mtimes
- **Tests**: `tests/test_mcp/test_context_graph.py`
- **Acceptance criteria**:
  - [x] GraphState dataclass defined
  - [x] get_graph() returns cached graph on repeated calls
  - [x] is_stale() returns True when spec files change
  - [x] force_refresh=True rebuilds graph
- **Resolution**: Added `GraphState` dataclass with graph, validation, file_mtimes, and built_at fields. Implemented `get_graph()`, `is_graph_stale()`, `get_stale_files()`, `get_graph_built_at()`, `_build_graph()`, and `_get_spec_file_mtimes()` methods. Graph auto-refreshes when stale files detected. 16 new tests added.

---

### [x] 1.2 Add Graph Status MCP Tool

- **Priority**: P1 - Enables graph introspection
- **Description**: Expose graph state information via MCP tool.
- **Files**:
  - `src/elspais/mcp/server.py`
- **Tasks**:
  - Add `get_graph_status()` tool returning:
    - `is_stale`: bool
    - `stale_files`: List of changed files
    - `node_counts`: Dict by NodeKind
    - `last_built`: timestamp
  - Add `refresh_graph(full=False)` tool
- **Tests**: `tests/test_mcp/test_graph_tools.py`
- **Acceptance criteria**:
  - [x] get_graph_status returns correct staleness
  - [x] Node counts match actual graph
  - [x] refresh_graph triggers rebuild
- **Resolution**: Added `get_graph_status()` and `refresh_graph()` MCP tools. Renamed `tests/mcp/` to `tests/test_mcp/` to avoid namespace collision with the `mcp` package. 8 new tests added.

---

### [x] 1.3 Add Hierarchy Navigation Tools

- **Priority**: P1 - Core auditor review capability
- **Description**: MCP tools for traversing requirement hierarchy.
- **Files**:
  - `src/elspais/mcp/server.py`
- **Tasks**:
  - Add `get_hierarchy(req_id)` tool:
    - `ancestors`: List of parent IDs
    - `children`: List of child IDs
    - `depth`: Node depth in graph
  - Add `get_traceability_path(req_id)` tool:
    - Returns tree structure: REQ → Assertions → Code → Tests → Results
- **Tests**: `tests/test_mcp/test_hierarchy_tools.py`
- **Acceptance criteria**:
  - [x] get_hierarchy returns correct ancestors
  - [x] get_hierarchy returns correct children
  - [x] get_traceability_path shows full path to tests
- **Resolution**: Added `get_hierarchy()` returning ancestors, children (by kind), depth, and source location. Added `get_traceability_path()` returning recursive tree with children organized by kind, summary metrics, and max_depth limiting. 12 new tests added.

---

### [x] 1.4 Add Coverage Query Tools

- **Priority**: P2 - Key auditor review capability
- **Description**: MCP tools for coverage analysis (auditor review use case).
- **Files**:
  - `src/elspais/mcp/server.py`
- **Tasks**:
  - Add `get_coverage_breakdown(req_id)` tool:
    - Per-assertion coverage status
    - Coverage sources (direct/explicit/inferred)
    - Implementing code references
    - Validating tests with pass/fail
    - Gaps (uncovered assertions)
  - Add `list_by_criteria(level, status, coverage_below, has_gaps)` tool
- **Tests**: `tests/test_mcp/test_coverage_tools.py`
- **Acceptance criteria**:
  - [x] get_coverage_breakdown shows assertion-level detail
  - [x] Coverage sources correctly identified
  - [x] list_by_criteria filters correctly
- **Resolution**: Added `get_coverage_breakdown()` with per-assertion detail including coverage source type, implementing code, validating tests, and gap detection. Added `list_by_criteria()` with level, status, coverage_below, and has_gaps filters. 14 new tests added.

---

### [x] 1.5 Add Requirement Context Tool

- **Priority**: P2 - Auditor review UX
- **Description**: Display requirement with full context for auditor review.
- **Files**:
  - `src/elspais/mcp/server.py`
  - `src/elspais/mcp/serializers.py`
- **Tasks**:
  - Add `show_requirement_context(req_id, include_assertions, include_implementers)` tool:
    - Full requirement text
    - Assertion labels and text
    - Source file and line range
    - Coverage metrics summary
  - Add serialization helpers for rich output
- **Tests**: `tests/test_mcp/test_context_tools.py`
- **Acceptance criteria**:
  - [x] Returns full requirement text
  - [x] Shows assertions when requested
  - [x] Shows implementers when requested
  - [x] Includes file path and line numbers
- **Resolution**: Added `show_requirement_context()` with full requirement text, assertions (toggleable), source location, coverage metrics, and implementers (toggleable). 11 new tests added.

---

### [x] 1.6 Add Graph MCP Resources

- **Priority**: P3 - Alternative access pattern
- **Description**: Expose graph data via MCP resources.
- **Files**:
  - `src/elspais/mcp/server.py`
- **Tasks**:
  - Add resource `graph://status` - staleness and statistics
  - Add resource `graph://validation` - current warnings/errors
  - Add resource `traceability://{id}` - full path for requirement
  - Add resource `coverage://{id}` - coverage breakdown
  - Add resource `hierarchy://{id}/ancestors` and `hierarchy://{id}/descendants`
- **Tests**: `tests/test_mcp/test_graph_resources.py`
- **Acceptance criteria**:
  - [x] All resources return valid data
  - [x] ID-based resources handle invalid IDs gracefully
- **Resolution**: Added 7 MCP resources for graph data access: `graph://status` (staleness and statistics), `graph://validation` (warnings/errors), `traceability://{req_id}` (full tree path), `coverage://{req_id}` (assertion-level coverage), `hierarchy://{req_id}/ancestors` (parent chain), and `hierarchy://{req_id}/descendants` (all descendants). 17 new tests added.

---

## Phase 2: Incremental Refresh

### [ ] 2.1 Add TrackedFile Registry

- **Priority**: P2 - Performance optimization foundation
- **Description**: Track which nodes come from which files for incremental updates.
- **Files**:
  - `src/elspais/mcp/context.py`
- **Tasks**:
  - Add `TrackedFile` dataclass: `path`, `mtime`, `node_ids`
  - Add file → node_ids mapping during graph build
  - Update `is_stale()` to identify specific stale files
- **Tests**: `tests/test_mcp/test_tracked_files.py`
- **Acceptance criteria**:
  - [ ] TrackedFile records which nodes from each file
  - [ ] is_stale() returns list of changed files

---

### [ ] 2.2 Implement Partial Graph Refresh

- **Priority**: P3 - Performance optimization
- **Description**: Re-parse only changed files, update affected subgraph.
- **Files**:
  - `src/elspais/mcp/context.py`
  - `src/elspais/core/graph_builder.py` (if needed)
- **Tasks**:
  - Implement `partial_refresh(changed_files)` method
  - Remove nodes from changed files
  - Re-parse changed files
  - Re-add nodes to graph
  - Recompute affected metrics only
- **Tests**: `tests/test_mcp/test_incremental_refresh.py`
- **Acceptance criteria**:
  - [ ] Only changed files re-parsed
  - [ ] Graph structure correct after partial refresh
  - [ ] Metrics updated correctly

---

## Phase 3: Write Operations

### [ ] 3.1 Create GraphMutator Class

- **Priority**: P2 - Foundation for write operations
- **Description**: Encapsulate graph-to-filesystem sync operations.
- **Files**:
  - `src/elspais/mcp/mutator.py` (new file)
- **Tasks**:
  - Create `GraphMutator` class
  - Implement `_read_spec_file(path)` with line tracking
  - Implement `_write_spec_file(path, content)` preserving format
  - Implement `_find_requirement_lines(content, req_id)` to locate requirement in file
- **Tests**: `tests/test_mcp/test_mutator_base.py`
- **Acceptance criteria**:
  - [ ] Can read spec file and track lines
  - [ ] Can write spec file preserving format
  - [ ] Can locate requirement by ID in file

---

### [ ] 3.2 Implement Reference Type Change

- **Priority**: P2 - Key UC2 capability
- **Description**: Change Implements ↔ Refines in spec files.
- **Files**:
  - `src/elspais/mcp/mutator.py`
  - `src/elspais/mcp/server.py`
- **Tasks**:
  - Implement `change_reference_type(source_id, target_id, new_type)` in mutator
  - Parse requirement header to find Implements:/Refines: line
  - Replace reference type while preserving other references
  - Add MCP tool `change_reference_type()`
- **Tests**: `tests/test_mcp/test_reference_change.py`
- **Acceptance criteria**:
  - [ ] Can change Implements to Refines
  - [ ] Can change Refines to Implements
  - [ ] Preserves other references on same line
  - [ ] Graph updates after change

---

### [ ] 3.3 Implement Reference Specialization

- **Priority**: P2 - Key UC1 capability
- **Description**: Convert REQ→REQ to REQ→Assertion references.
- **Files**:
  - `src/elspais/mcp/mutator.py`
  - `src/elspais/mcp/server.py`
- **Tasks**:
  - Implement `specialize_reference(source_id, target_id, assertions)` in mutator
  - Convert `Implements: REQ-p00001` to `Implements: REQ-p00001-A-B`
  - Handle multi-assertion syntax
  - Add MCP tool `specialize_reference()`
- **Tests**: `tests/test_mcp/test_reference_specialize.py`
- **Acceptance criteria**:
  - [ ] Can specialize REQ ref to assertion ref
  - [ ] Multi-assertion syntax works (A-B-C)
  - [ ] Graph edges update correctly

---

### [ ] 3.4 Implement Requirement Move

- **Priority**: P3 - UC3 capability
- **Description**: Move requirements between spec files.
- **Files**:
  - `src/elspais/mcp/mutator.py`
  - `src/elspais/mcp/server.py`
- **Tasks**:
  - Implement `move_requirement(req_id, target_file, position, after_id)` in mutator
  - Extract requirement text from source file
  - Insert at target file with proper positioning
  - Remove from source file
  - Add MCP tool `move_requirement()`
- **Tests**: `tests/test_mcp/test_requirement_move.py`
- **Acceptance criteria**:
  - [ ] Requirement removed from source file
  - [ ] Requirement added to target file
  - [ ] Position options work (start/end/after)
  - [ ] References remain valid

---

### [ ] 3.5 Implement File Deletion Workflow

- **Priority**: P3 - UC4 capability
- **Description**: Prepare and execute spec file deletion.
- **Files**:
  - `src/elspais/mcp/mutator.py`
  - `src/elspais/mcp/server.py`
- **Tasks**:
  - Implement `analyze_file_for_deletion(source_file)`:
    - Find remaining REQ/JNY entries
    - Extract non-requirement content
    - Return deletion readiness status
  - Implement `extract_and_delete(source_file, content_target)`:
    - Extract content to target file
    - Delete source file
  - Add MCP tools `prepare_file_deletion()` and `extract_and_delete()`
- **Tests**: `tests/test_mcp/test_file_deletion.py`
- **Acceptance criteria**:
  - [ ] Detects remaining requirements
  - [ ] Extracts non-requirement content
  - [ ] Refuses to delete file with remaining requirements
  - [ ] Deletes empty file successfully

---

## Completion Checklist

- [x] All Phase 1 items complete
- [ ] All Phase 2 items complete
- [ ] All Phase 3 items complete
- [ ] All tests passing
- [ ] Documentation updated in CLAUDE.md
- [ ] Version bumped in pyproject.toml
- [ ] CHANGELOG.md updated

---

## Priority Legend

| Priority | Meaning |
|----------|---------|
| P1 | Foundation, critical path - do first |
| P2 | Key feature capability |
| P3 | Enhancement, optimization |

---

## Notes

- Each issue should result in a single commit or small commit series
- Phase 2 depends on Phase 1 completion
- Phase 3 depends on Phase 2 completion (except 3.1 which can start after 1.1)
- Run full test suite before marking complete
- Update CHANGELOG.md for user-visible changes
- Update CLAUDE.md if architecture changes significantly
- Commit with `[CUR-514]` prefix
- Use `/clear` between issues to manage context
