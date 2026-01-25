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

### [x] 2.1 Add TrackedFile Registry

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
  - [x] TrackedFile records which nodes from each file
  - [x] is_stale() returns list of changed files
- **Resolution**: Added `TrackedFile` dataclass with `path`, `mtime`, and `node_ids` fields. Updated `GraphState` to use `tracked_files: Dict[Path, TrackedFile]` with backward-compatible `file_mtimes` property. Added `_build_tracked_files()` to populate node_ids during graph build. Added helper methods: `get_tracked_files()`, `get_nodes_for_file()`, `get_stale_tracked_files()`. 18 new tests added.

---

### [x] 2.2 Implement Partial Graph Refresh

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
  - [x] Only changed files re-parsed
  - [x] Graph structure correct after partial refresh
  - [x] Metrics updated correctly
- **Resolution**: Added `partial_refresh(changed_files)` method to `WorkspaceContext` that identifies stale files (modified, deleted, new), removes requirements from stale files, re-parses only affected files, merges with cached requirements, and rebuilds the graph. Added helper methods `_get_requirement_ids_for_files()` and `_is_assertion_id()` to support incremental updates. 16 new tests added covering all scenarios: no graph, no changes, modified/deleted/new files, explicit changed_files, tracked file updates, cross-file relationships, and metrics updates.

---

## Phase 3: Write Operations

### [x] 3.1 Create GraphMutator Class

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
  - [x] Can read spec file and track lines
  - [x] Can write spec file preserving format
  - [x] Can locate requirement by ID in file
- **Resolution**: Added `GraphMutator` class with `FileContent` and `RequirementLocation` dataclasses. Implemented `_read_spec_file()` with path security checks, `_write_spec_file()` with parent directory creation, `_find_requirement_lines()` with 1-indexed line tracking supporting both end-marker and next-header detection, plus helper methods `get_requirement_text()` and `replace_requirement_text()` for read-modify-write workflows. 25 new tests added.

---

### [x] 3.2 Implement Reference Type Change

- **Priority**: P2 - Key UC2 capability
- **Description**: Change Implements ↔ Refines in spec files.
- **Files**:
  - `src/elspais/mcp/mutator.py`
  - `src/elspais/mcp/server.py`
  - `src/elspais/mcp/serializers.py`
- **Tasks**:
  - Implement `change_reference_type(source_id, target_id, new_type)` in mutator
  - Parse requirement header to find Implements:/Refines: line
  - Replace reference type while preserving other references
  - Add MCP tool `change_reference_type()`
- **Tests**: `tests/test_mcp/test_reference_change.py`
- **Acceptance criteria**:
  - [x] Can change Implements to Refines
  - [x] Can change Refines to Implements
  - [x] Preserves other references on same line
  - [x] Graph updates after change
- **Resolution**: Added `ReferenceType` enum and `ReferenceChange` dataclass to mutator. Implemented `change_reference_type()` with helper methods `_find_metadata_line()`, `_parse_reference_list()`, `_find_reference_in_line()`, `_build_refs_string()`, and `_update_metadata_line()`. Added MCP tool `change_reference_type()` that invalidates cache after changes. Added `refines` field to serializers. 21 new tests added.

---

### [x] 3.2.5 Add Graph Manipulation Foundation

- **Priority**: P1 - Foundation for all write operations
- **Description**: Add foundational primitives for graph manipulation including node serialization, AI transformation, and session annotations.
- **Files**:
  - `src/elspais/mcp/serializers.py` - Added serialize_node_full()
  - `src/elspais/mcp/transforms.py` (new) - AITransformer class
  - `src/elspais/mcp/annotations.py` (new) - Session-scoped storage
  - `src/elspais/mcp/git_safety.py` (new) - Branch management
  - `src/elspais/mcp/server.py` - Added new tools
- **Tasks**:
  - Implement `get_node_as_json(node_id)` for full node serialization
  - Implement `transform_with_ai(node_id, prompt, output_mode, save_branch, dry_run)`
  - Add git safety utilities (create safety branch, restore)
  - Implement session annotation system (add_annotation, add_tag, etc.)
- **Tests**: `tests/test_mcp/test_transforms.py`, `tests/test_mcp/test_annotations.py`, `tests/test_mcp/test_git_safety.py`
- **Acceptance criteria**:
  - [x] get_node_as_json returns complete node data including text, metrics, relationships
  - [x] transform_with_ai successfully calls claude -p and applies changes
  - [x] Git safety branch is created before modifications
  - [x] Annotations persist within session but not to files
  - [x] dry_run mode previews without applying
- **Resolution**: Added 4 new modules:
  - `git_safety.py`: `GitSafetyManager` with `create_safety_branch()`, `restore_from_branch()`, `list_safety_branches()`, `delete_safety_branch()`
  - `annotations.py`: `AnnotationStore` with add/get/remove annotation/tag methods, tags index for fast lookup
  - `transforms.py`: `AITransformer` with `transform()` method supporting replace/operations output modes, `ClaudeInvoker` for subprocess calls
  - `serializers.py`: Added `serialize_node_full()` with full text, metrics, relationships, coverage info
  - Added 14 new MCP tools: `get_node_as_json`, `transform_with_ai`, `restore_from_safety_branch`, `list_safety_branches`, `add_annotation`, `get_annotations`, `add_tag`, `remove_tag`, `list_tagged`, `list_all_tags`, `nodes_with_annotation`, `clear_annotations`, `annotation_stats`
  - 59 new tests added covering all modules.

---

### [x] 3.3 Implement Reference Specialization

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
  - [x] Can specialize REQ ref to assertion ref
  - [x] Multi-assertion syntax works (A-B-C)
  - [x] Graph edges update correctly (cache invalidated after change)
- **Resolution**: Added `ReferenceSpecialization` dataclass and `specialize_reference()` method to mutator with `_build_multi_assertion_ref()` and `_update_reference_in_line()` helpers. Added MCP tool `specialize_reference()` that invalidates cache on success. 16 new tests added.

---

## Phase 4: Interface Consolidation

### [x] 4.1 Consolidate All Interface Libraries

- **Priority**: P2 - Code quality and maintainability
- **Description**: Audit all interfaces (file I/O, user input, API, command line, MCP) and ensure each uses a single shared library. No duplicating of logic across modules.
- **Files**: Various - determined by audit
- **Tasks**:
  - Audit file I/O operations across codebase - ensure single library for spec file loading (loader.py now consolidated)
  - Audit configuration loading - ensure single config loader
  - Audit pattern validation - ensure single PatternValidator usage
  - Audit graph building - ensure single TraceGraphBuilder usage
  - Audit CLI argument parsing - ensure consistent patterns
  - Audit MCP tool implementations - ensure consistent patterns and shared helpers
  - Create shared helper modules where duplication exists
  - Document interface patterns in CLAUDE.md
- **Tests**: Existing tests should continue to pass
- **Acceptance criteria**:
  - [x] File I/O: Single library for reading/writing spec files
  - [x] Config: Single loader used everywhere
  - [x] Patterns: Single validator instance pattern
  - [x] Graph: Single builder pattern
  - [x] CLI: Consistent argument handling
  - [x] MCP: Shared helpers for common operations
- **Resolution**: Completed comprehensive interface consolidation:
  - **File I/O**: All 9 files creating `RequirementParser` directly now use `load_requirements_from_directories()` or `create_parser()` from `core/loader.py`. Updated: `trace.py`, `hash_cmd.py`, `analyze.py`, `index.py`, `reformat_cmd.py`, `trace_view/generators/base.py`, `reformat/hierarchy.py`, `mcp/server.py`
  - **Config Loading**: Added `get_config()` helper to `config/loader.py`. Updated `validate.py` and `changed.py` to use it (eliminates duplicate `load_configuration()` functions)
  - **Patterns**: `PatternConfig` creation is now centralized through `create_parser()` in `core/loader.py`
  - **Graph Building**: Already well consolidated via `TraceGraphBuilder` (no changes needed)
  - **CLI Parsing**: Already well consolidated in `cli.py` (no changes needed)
  - **MCP Tools**: `WorkspaceContext` pattern is consistent (no changes needed). 974 tests pass

---

### [x] 4.2 Library Function and Class Naming Audit

- **Priority**: P2 - Code quality and maintainability
- **Description**: Rename classes/functions with misleading names to accurately reflect their functionality.
- **Files**:
  - `src/elspais/mcp/mutator.py` - Rename `GraphMutator` → `SpecFileMutator`
  - `src/elspais/mcp/transforms.py` - Update import
  - `src/elspais/parsers/requirement.py` - Rename `RequirementNodeParser` → `RequirementTextParser`
  - `src/elspais/parsers/__init__.py` - Update registration
  - `src/elspais/testing/mapper.py` - Rename `TestMapper` → `TestCoverageMapper`
  - `src/elspais/commands/validate.py` - Update import
  - `CLAUDE.md` - Update documentation
- **Tasks**:
  - Rename `GraphMutator` → `SpecFileMutator` (mutates spec files, not graphs)
  - Rename `RequirementNodeParser` → `RequirementTextParser` (parses text, creates nodes)
  - Rename `TestMapper` → `TestCoverageMapper` (maps test→requirement coverage)
  - Update all imports and usages
  - Document `parse_*` vs `load_*` distinction in CLAUDE.md
  - Note that all parsers in `parsers/` module output `TraceNode` objects
- **Tests**: All existing tests should pass after renames
- **Acceptance criteria**:
  - [x] GraphMutator renamed to SpecFileMutator
  - [x] RequirementNodeParser renamed to RequirementTextParser
  - [x] TestMapper renamed to TestCoverageMapper
  - [x] All imports updated
  - [x] CLAUDE.md documentation updated
  - [x] All 974 tests pass

---

## Phase 5: Extended Write Operations

### [x] 5.1 Implement Requirement Move

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
  - [x] Requirement removed from source file
  - [x] Requirement added to target file
  - [x] Position options work (start/end/after)
  - [x] References remain valid
- **Resolution**: Added `RequirementMove` dataclass and `move_requirement()` method to SpecFileMutator with helper methods `_find_insertion_point()`, `_normalize_requirement_for_insertion()`, and `_remove_requirement_from_content()`. Added MCP tool `move_requirement()` that invalidates cache on success. Supports "start", "end", and "after" positions. Creates target file if it doesn't exist. 35 new tests added.

---

### [x] 5.2 Implement File Deletion Workflow

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
  - [x] Detects remaining requirements
  - [x] Extracts non-requirement content
  - [x] Refuses to delete file with remaining requirements
  - [x] Deletes empty file successfully
- **Resolution**: Added `FileDeletionAnalysis` and `FileDeletionResult` dataclasses. Added `_find_all_requirements()` and `_extract_non_requirement_content()` helper methods. Implemented `analyze_file_for_deletion()` for pre-deletion analysis and `delete_spec_file()` with force flag and content extraction options. Added MCP tools `prepare_file_deletion()` and `delete_spec_file()` with cache invalidation. 24 new tests added.

---

### [x] 5.3 Validate Recursive Subdirectory Parsing

- **Priority**: P2 - Spec organization flexibility
- **Description**: Ensure spec file discovery and parsing works correctly for nested subdirectories (e.g., `spec/regulations/fda/`, `spec/sub/sub/`).
- **Files**:
  - `src/elspais/core/loader.py`
  - `src/elspais/mcp/context.py`
- **Tasks**:
  - Audit spec file discovery to ensure recursive directory traversal
  - Validate file pattern matching (`prd-*.md`, etc.) works at any nesting depth
  - Ensure `skip_dirs` config works for nested paths (e.g., `regulations/fda/reference`)
  - Verify TrackedFile registry handles subdirectory paths correctly
  - Test graph refresh with files in nested subdirectories
- **Tests**: `tests/test_mcp/test_subdirectory_parsing.py`
- **Acceptance criteria**:
  - [x] Files in `spec/sub/` discovered and parsed
  - [x] Files in `spec/sub/sub/` discovered and parsed
  - [x] File type patterns match at any depth
  - [x] `skip_dirs` excludes nested paths correctly
  - [x] Incremental refresh works for nested file changes
  - [x] Requirement IDs from nested files appear in graph
- **Resolution**: Validated that existing recursive parsing implementation using `rglob()` works correctly for nested subdirectories. The `RequirementParser.parse_directory()` method with `recursive=True` correctly handles files at any nesting depth, tracks subdirectory paths in the `subdir` attribute, and applies `skip_files` at all levels. The `WorkspaceContext.from_directory()` correctly loads config files and enables MCP graph operations on nested files. 17 new tests added validating: recursive discovery, file pattern matching at depth, skip_files at multiple depths, MCP context with nested files including graph refresh, tracked files, new file detection, and deleted file detection.

---

### [ ] 5.4 Implement Lossless Graph-to-File Reconstruction

- **Priority**: P3 - Full round-trip fidelity
- **Description**: Enable reconstructing the original spec files character-for-character from graph data alone. This requires the graph to preserve all content, including non-requirement sections (prose, comments, headers between requirements).
- **Files**:
  - `src/elspais/core/graph.py`
  - `src/elspais/core/graph_builder.py`
  - `src/elspais/core/loader.py`
  - `src/elspais/mcp/reconstructor.py` (new)
- **Tasks**:
  - Design `FileNode` concept to represent spec files in the graph
    - Careful: avoid circular deps (file → reqs, reqs → file for location)
    - Consider: file as container node, reqs as children with ordering
  - Design `UnparsedContent` node type for non-requirement content
    - Preserves text between/around requirements
    - Tracks position relative to adjacent requirements
  - Extend parser to capture unparsed regions during file load
  - Implement `reconstruct_file(file_path)` that reassembles content
  - Add MCP tool `reconstruct_spec_file(path, dry_run)` for validation
  - Add MCP tool `verify_reconstruction(path)` to diff original vs reconstructed
- **Tests**: `tests/test_mcp/test_file_reconstruction.py`
- **Acceptance criteria**:
  - [ ] UnparsedContent nodes capture prose/headers between requirements
  - [ ] FileNode or equivalent tracks content ordering
  - [ ] `reconstruct_file()` produces character-identical output (whitespace may differ)
  - [ ] Round-trip test: load → graph → reconstruct → compare passes
  - [ ] No circular dependency issues in graph structure
  - [ ] Incremental refresh preserves unparsed content correctly

---

## Completion Checklist

- [x] All Phase 1 items complete
- [x] All Phase 2 items complete
- [x] All Phase 3 items complete
- [x] All Phase 4 items complete
- [ ] All Phase 5 items complete
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
- Phase 4 can run in parallel with Phase 5
- Phase 5 depends on Phase 3 completion
- Run full test suite before marking complete
- Update CHANGELOG.md for user-visible changes
- Update CLAUDE.md if architecture changes significantly
- Commit with `[CUR-514]` prefix
- Use `/clear` between issues to manage context
