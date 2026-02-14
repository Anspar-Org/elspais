# Changelog

All notable changes to elspais will be documented in this file.

## [0.70.0] - 2026-02-14

### Added

- **Cursor support for `scoped_search`**: Register `scoped_search` as a cursor query type, enabling paginated iteration through scoped search results via `open_cursor("scoped_search", {...})` (REQ-o00068-F, REQ-d00076-B)

## [0.69.0] - 2026-02-14

### Added

- **`scoped_search` MCP tool**: Restricts keyword search to descendants or ancestors of a scope node, preventing over-matching across unrelated parts of the graph. Supports assertion text matching via `include_assertions` parameter (REQ-o00070, REQ-d00078)

## [0.68.0] - 2026-02-14

### Added

- **`minimize_requirement_set` MCP tool**: Prunes a set of requirement IDs to most-specific members by removing ancestors covered by more-specific descendants. Returns minimal set, pruned items with `superseded_by` metadata, and stats (REQ-o00069, REQ-d00077)

## [0.67.0] - 2026-02-14

### Changed

- **Extract `_matches_query()` helper**: Refactored per-node matching logic out of `_search()` into a reusable `_matches_query()` function for shared use by `search()` and future `scoped_search()` (REQ-d00061-B, REQ-d00061-C, REQ-p00050-D)

## [0.65.0] - 2026-02-13

### Added

- **CLI-based associate registration**: Register associate repositories via `elspais config add associates.paths /path/to/repo` instead of manually editing config files. Auto-discovers associate identity (name, prefix, spec path) from the target repo's `.elspais.toml` (REQ-p00005-C, REQ-p00005-D)
- **Structured error reporting for associate paths**: Invalid associate paths return error messages instead of silently skipping, enabling CI pipelines to detect misconfigured associates (REQ-p00005-E)
- **Subtree extraction MCP tool**: `get_subtree(root_id, depth, include_kinds, format)` extracts a subgraph rooted at any node with three output formats (markdown, flat JSON, nested JSON). Supports depth limiting, kind filtering, DAG deduplication, and includes coverage summary stats (REQ-o00067, REQ-d00075)
- **Cursor protocol for incremental iteration**: Three new MCP tools (`open_cursor`, `cursor_next`, `cursor_info`) enable LLMs to iterate query results one item at a time. Supports 6 query types (subtree, search, hierarchy, query_nodes, test_coverage, uncovered_assertions) and 3 batch_size modes for controlling item granularity (REQ-o00068, REQ-d00076)

## [0.63.3] - 2026-02-12

### Changed

- **Cleanup and file renames**: Renamed `_header-edit.css.j2` to `_header.css.j2` and `_file-viewer-edit.css.j2` to `_file-viewer.css.j2` since they now serve both modes. Deleted dead `_tabs.html.j2` (REQ-p00006-A)

## [0.63.2] - 2026-02-12

### Changed

- **Unified cookie persistence**: Single `elspais_trace_state` cookie shared between view and edit modes, replacing mode-specific `elspais_trace_edit_state`/`elspais_trace_view_state`. State (theme, font size, open cards, filters, panel widths) now seamlessly transfers between modes (REQ-p00006-A)
- Added `clearState()` function for programmatic cookie reset
- Cookie version bumped to v9

## [0.63.1] - 2026-02-12

### Added

- **Search in view mode**: Extracted search into shared `_search.js.j2` partial, enabling search in both static HTML and edit mode. `Ctrl+K` shortcut works in both modes (REQ-p00006-A, REQ-p00006-B)
- **New toolbar filter toggles**: Added Hide Deprecated, Hide Roadmap, Code Refs, and Indirect Coverage toggle checkboxes to the unified filter toolbar
- Cookie version bumped to v8 for new filter state keys

## [0.63.0] - 2026-02-12

### Changed

- **Unified 3-panel layout for both view and edit modes**: Replaced the view-mode table layout with the 3-panel layout (nav tree + card stack + file viewer) already used by edit mode. Both modes now share the same interactive layout, state management (`editState`), and cookie persistence (REQ-p00006-A, REQ-d00010-A)
- **Unified file viewer**: Single implementation using `apiFetch()` for both modes with vscode:// link interception, markdown rendering toggle, and syntax highlighting
- **Unified header and toolbar**: Edit-mode header (with dynamic stats via JS) and toolbar (git filters, status/coverage dropdowns) now serve both modes, with edit-specific buttons wrapped in mode conditionals
- **Dark theme support in view mode**: Added `pygments_css_dark` generation to HTMLGenerator for syntax highlighting in dark theme

### Removed

- View-mode table layout, flat/hierarchical view toggle, table column filters
- Dead CSS: `_table.css.j2`, `_tree-structure.css.j2`, `_code-test-rows.css.j2`, `_responsive.css.j2`, `_tabs.css.j2`, `_header.css.j2`, `_file-viewer.css.j2`
- Dead JS: `_filter-engine.js.j2`, `_journey-engine.js.j2`

## [0.62.0] - 2026-02-12

### Added

- **Embedded data layer for unified trace viewer**: View-mode static HTML now embeds node index, coverage index, and status data as JSON script tags, enabling a unified `apiFetch()` adapter that routes to embedded data in view mode and live API in edit mode (REQ-p00006-A, REQ-p00006-B, REQ-p00006-C)

## [0.61.0] - 2026-02-11

### Added

- **`elspais install local`**: Install local source as editable pipx/uv install, replacing the global PyPI version for dev testing
- **`elspais uninstall local`**: Revert to PyPI release version with optional `--version` pinning
- Auto-detects pipx/uv, source root via `pyproject.toml`, and currently installed extras

## [0.54.1] - 2026-02-10

### Changed

- **Python 3.10+ support**: Lowered minimum Python version from 3.12 to 3.10, added 3.10/3.11 to CI test matrix
- **Auto version bump**: PRs automatically get a version bump based on changed files — patch for docs/tests/specs, minor for source changes
- **Auto release**: Merging to main with a version change automatically creates a GitHub release, triggering PyPI publish and Homebrew tap update

## [0.54.0] - 2026-02-10

### Added

- **Trace-edit interactive server**: Interactive spec editing via Flask with `spec_writer` mutations (REQ-d00010-A, REQ-o00063-G/H/I)
- **Agent-assisted link suggestion engine**: Heuristic-based link suggestions for unlinked test nodes (REQ-o00065, REQ-d00072/73/74)
- **CI/CD pipelines**: CI and PR validation workflows, PyPI publish and Homebrew tap update automation (REQ-o00066)

### Changed

- **Replaced gitleaks with TruffleHog**: Secret scanning now uses TruffleHog (REQ-o00066-D)
- **Fixed code directory scanning**: `build_graph()` now correctly scans `[directories].code` config (REQ-d00054-A)

## [0.51.0] - 2026-02-07

### Changed

- **Consolidated spec file I/O**: All spec-file mutation helpers (`modify_implements`, `modify_status`, `move_requirement`, `change_reference_type`, `update_hash_in_file`) now live in `utilities/spec_writer.py`. Both CLI (`edit.py`, `hash_cmd.py`) and MCP (`server.py`) import from this single module.
- **Fixed encoding bug**: 4 spec-file writes in `edit.py` were missing `encoding="utf-8"` — now all writes go through `spec_writer` which uses explicit UTF-8 encoding.
- **Relocated `mcp/file_mutations.py`**: Core file I/O moved to `utilities/spec_writer.py`; `mcp/file_mutations.py` is now a backward-compatible re-export shim.

## [0.50.0] - 2026-02-07

### Added

- **MCP round-trip fidelity**: `get_requirement()` now returns enough data to reconstruct the original requirement from the graph. Parser computes line numbers on assertions and sections, builder creates `SourceLocation` on all child nodes with document-order insertion, and MCP serializer returns a flat `children` list with `kind`/`line` tags and `edge_kind` on parent entries.
- **Linking convention documentation**: New `docs/cli/linking.md` topic for `elspais docs linking` — authoritative reference for all requirement linking patterns (code comments, test names, multi-assertion syntax, direct vs indirect linking).

## [0.49.0] - 2026-02-07

### Added

- **Configurable satellite kinds**: `[graph].satellite_kinds` in `.elspais.toml` controls which node kinds are treated as satellite (don't count as meaningful children for root/orphan classification). Defaults to `["assertion", "result"]`.

## [0.48.0] - 2026-02-07

### Changed

- **Unified root vs orphan classification**: Parentless nodes are now classified as roots only when they have at least one meaningful (non-satellite) child. Nodes with only ASSERTION or TEST_RESULT children are classified as orphans. USER_JOURNEY nodes follow the same rule. This replaces the previous logic where all parentless REQUIREMENTs and all USER_JOURNEYs were unconditionally treated as roots.
- **Simplified orphan detection in CLI**: Removed domain-level REQUIREMENT orphan loops from `analyze.py` and `health.py` — the unified graph-level classification now handles all node kinds.

### Added

- **REQ-d00071** specification: Formal requirement for unified root vs orphan classification with 4 assertions (A-D).
- **`_SATELLITE_KINDS` constant**: Defines ASSERTION and TEST_RESULT as satellite kinds that don't count as meaningful children.

## [0.47.0] - 2026-02-06

### Added

- **Indirect coverage toggle** for trace view: whole-requirement tests (tests targeting a requirement without assertion suffixes) can now count as covering all assertions. A new "Indirect coverage" toggle in the toolbar switches between strict traceability view and a progress-indicator view.
- **`CoverageSource.INDIRECT`**: New coverage source type for whole-requirement test contributions, alongside existing DIRECT, EXPLICIT, and INFERRED sources.
- **Dual coverage metrics**: `RollupMetrics` now tracks both `coverage_pct` (strict, excludes indirect) and `indirect_coverage_pct` (includes indirect). `validated_with_indirect` counts assertions validated when including whole-req passing tests.
- **`data-coverage-indirect` attribute**: Tree rows carry both strict and indirect coverage data for client-side toggle without page reload.
- **JNY→REQ linking via `Addresses:` field**: User journeys can now reference the requirements they address using `Addresses: REQ-xxx, REQ-yyy` in the journey block. Parsed into `EdgeKind.ADDRESSES` edges in the traceability graph.
- **Trace view journey cards show linked REQs**: Addressed requirements appear as clickable pill badges on journey cards. Clicking navigates to the requirement in the requirements tab with a flash highlight.
- **Journey search includes addresses**: The journey tab search bar now matches against referenced requirement IDs.
- **Index regenerate includes Addresses column**: `elspais index regenerate` now includes an Addresses column in the User Journeys section.
- **Index validate checks JNY IDs**: `elspais index validate` now verifies that all JNY IDs in the graph appear in INDEX.md and vice versa.

## [0.46.0] - 2026-02-07

### Added

- **Inline file viewer panel** for `elspais trace --view --embed-content`: clicking file links now opens source files in a right-side panel with syntax-highlighted content and stable line numbers, instead of opening VS Code externally. Supports 500+ languages via Pygments.
- **Syntax highlighting** powered by Pygments (new optional dependency under `trace-view` extra). Highlighting runs at generation time — no client-side JS library needed.
- **Resizable split-pane layout**: drag the divider between the trace table and file viewer. Panel width persists via cookies.
- **Markdown rendered view**: `.md` files show a toggle between "Rendered" and "Source" views.
- **Graceful fallback**: without `--embed-content`, file links open in VS Code as before.

### Changed

- **Optional dependency**: Added `pygments>=2.0` to `trace-view`, `trace-review`, and `all` extras.

## [0.45.0] - 2026-02-06

### Fixed

- **TOML parser: multi-line arrays corrupted during `config add` round-trips** — replaced custom TOML parser/serializer with `tomlkit` library for full TOML 1.0 compliance. Multi-line arrays and arrays containing comma-delimited strings are now handled correctly. Comments and formatting are preserved during config modifications.

### Changed

- **Core dependency**: Added `tomlkit>=0.12` as the sole core dependency (pure Python, no transitive deps). The custom TOML parser has been removed.

## [0.44.0] - 2026-02-04

### Added

- **Configurable hash mode** (`[validation].hash_mode` in `.elspais.toml`):
  - `full-text`: Hash every line between header and footer, no normalization.
  - `normalized-text` (default): Hash assertion text only with cosmetic normalization. Invariant over trailing whitespace, line wrapping, multiple spaces, and non-assertion body text changes.
  - Documented in `spec/requirements-spec.md` Hash Definition section.

## [0.43.5] - 2026-01-29

### Changed

- **Generalized keyword search API for all node kinds** (`graph/annotators.py`):
  - `annotate_keywords()` now annotates ALL node kinds with text content:
    - REQUIREMENT: title + child assertion text
    - ASSERTION: SHALL statement (label)
    - USER_JOURNEY: title + actor + goal + description
    - REMAINDER: label + raw_text
    - CODE, TEST, TEST_RESULT: label only
  - `find_by_keywords()` accepts optional `kind: NodeKind | None` parameter
    - `kind=None` (default) searches all nodes
    - `kind=NodeKind.ASSERTION` searches only assertions
  - `collect_all_keywords()` accepts optional `kind` parameter similarly
  - 12 new tests in `tests/graph/test_keyword_extraction_generalized.py`

- **MCP server refactored to use public graph API**:
  - `_find_assertions_by_keywords()` now uses `find_by_keywords(..., kind=NodeKind.ASSERTION)`
  - `_get_uncovered_assertions()` uses `nodes_by_kind(NodeKind.ASSERTION)`
  - Removed direct `_index.values()` access (encapsulation violation)

## [0.43.4] - 2026-01-29

### Changed

- **TestParser, JUnitXMLParser, PytestJSONParser refactored** to use shared reference config:
  - All three parsers now accept optional `PatternConfig` and `ReferenceResolver`
  - Removed hardcoded regex patterns from all parsers
  - TestParser: Custom comment pattern for `# Tests REQ-xxx` syntax (no colon)
  - Result parsers: Use `extract_ids_from_text()` from reference_config.py
  - Backward compatible - all work without explicit config

### Fixed

- **Assertion matching negative lookahead**: Added `(?![a-z])` in `build_id_pattern()` to prevent
  matching lowercase letters as assertion suffixes (e.g., `test_REQ_p00001_login` no longer
  captures "l" as an assertion)

## [0.43.3] - 2026-01-29

### Changed

- **CodeParser refactored to use shared reference config** (`graph/parsers/code.py`):
  - Now accepts optional `PatternConfig` and `ReferenceResolver` in constructor
  - Patterns built dynamically per-file using `reference_config.py` infrastructure
  - Removed hardcoded class-level regex patterns (`IMPLEMENTS_PATTERN`, `VALIDATES_PATTERN`, etc.)
  - Preserves full multi-line block parsing capability
  - Backward compatible - works without config (uses defaults)
  - 20 new tests covering custom configs, separators, case sensitivity, and block styles

## [0.43.2] - 2026-01-29

### Added

- **Reference Pattern Builder Module** (`utilities/reference_config.py`): New module for unified pattern building
  - `ReferenceConfig` dataclass: Configuration for reference pattern matching (separators, case sensitivity, etc.)
  - `ReferenceOverride` dataclass: File-type/directory-based override rules with glob matching
  - `ReferenceResolver` class: Single entry point for parsers to get merged configuration
  - Pattern builder functions:
    - `build_id_pattern()`: Build regex for requirement IDs with configurable separators
    - `build_comment_pattern()`: Build regex for `# Implements:` style comments
    - `build_block_header_pattern()`: Build regex for multi-line block headers
    - `build_block_ref_pattern()`: Build regex for block reference lines
    - `extract_ids_from_text()`: Extract all requirement IDs from text
    - `normalize_extracted_id()`: Normalize IDs to canonical format
  - 40 comprehensive unit tests in `tests/core/test_reference_config.py`

## [0.43.1] - 2026-01-29

### Added

- **Unified `[references]` configuration**: New config section for configurable reference parsing
  - `references.defaults.separators`: Separator characters for requirement IDs (default: `["-", "_"]`)
  - `references.defaults.case_sensitive`: Case sensitivity for matching (default: `false`)
  - `references.defaults.prefix_optional`: Whether REQ prefix is required (default: `false`)
  - `references.defaults.comment_styles`: Recognized comment markers (default: `["#", "//", "--"]`)
  - `references.defaults.keywords`: Keywords for implements/validates/refines references
  - `references.overrides`: File-type specific override patterns (empty by default)

## [0.43.0] - 2026-01-29

### Fixed

- **TestParser regex bug**: Fixed assertion-level test references not being captured.
  - Tests named `test_REQ_d00060_A_description` now correctly validate assertion `REQ-d00060-A`
  - Supports multi-assertion syntax: `test_REQ_d00060_A_B_description` → validates `REQ-d00060-A-B`
  - Coverage percentage now correctly reflects assertion-level test coverage

### Added

- New tests for assertion-level reference parsing in `test_test_parser.py`
- Created `docs/NEW_SPECS.md` for tracking proposed requirements during coverage analysis

## [0.42.0] - 2026-01-29

### Added

- **MCP Test Coverage Tools (Phase 6)**: New tools for analyzing test-requirement relationships:
  - `get_test_coverage(req_id)` - Returns TEST nodes that reference a requirement:
    - Lists test_nodes with their file and name
    - Lists result_nodes with pass/fail status
    - Identifies covered and uncovered assertions
    - Calculates coverage percentage
  - `get_uncovered_assertions(req_id=None)` - Finds assertions lacking test coverage:
    - When req_id is None, scans all requirements
    - Returns assertion id, text, label, and parent requirement context
    - Results sorted by parent requirement ID
  - `find_assertions_by_keywords(keywords, match_all=True)` - Searches assertion text:
    - Complements `find_by_keywords()` which searches requirement titles
    - Supports AND (match_all=True) and OR (match_all=False) logic
    - Case-insensitive matching

### Specification

- Added requirements to `spec/08-mcp-server.md`:
  - REQ-o00064: MCP Test Coverage Analysis Tools (OPS level)
  - REQ-d00066: Test Coverage Tool Implementation
  - REQ-d00067: Uncovered Assertions Tool Implementation
  - REQ-d00068: Assertion Keyword Search Tool Implementation

### Technical

- 14 new tests in `tests/mcp/test_mcp_coverage.py` with REQ-assertion naming pattern
- All coverage tools use iterator-only graph API per REQ-p00050-B

## [0.41.0] - 2026-01-29

### Added

- **MCP Dogfooding (Phase 5)**: Validated MCP server utility by improving test traceability:
  - Added 5 new tests with REQ-assertion naming pattern (e.g., `test_REQ_d00050_E_idempotent`)
  - Tests for REQ-d00050-E (annotator idempotency) and REQ-d00051-F (no duplicate iteration)
  - TEST nodes now automatically link to requirements via name pattern matching

### Documentation

- `docs/phase5-dogfooding-report.md`: Comprehensive dogfooding analysis with:
  - Test-requirement mapping table for `tests/core/test_annotators.py`
  - MCP tool ergonomic issues and suggested improvements
  - Before/after traceability metrics verification

### Technical

- Graph node count increased from 346 to 398 after test improvements
- TEST nodes: 36 → 75, TEST_RESULT nodes: 17 → 30

## [0.40.0] - 2026-01-29

### Added

- **Keyword Extraction & Search (Phase 4)**: Automatic keyword extraction and search for requirements:
  - `extract_keywords(text)` - Extract meaningful keywords from text, filtering stopwords
  - `annotate_keywords(graph)` - Annotate all requirements with keywords from title and assertions
  - `find_by_keywords(graph, keywords)` - Find requirements matching keywords (AND/OR logic)
  - `collect_all_keywords(graph)` - Get all unique keywords in the graph
  - Keywords stored in `node.get_field("keywords")` as list of lowercase strings

- **MCP Keyword Search Tools**: New MCP tools for keyword-based requirement discovery:
  - `find_by_keywords(keywords, match_all)` - Search by keywords with AND/OR matching
  - `get_all_keywords()` - List all available keywords for discovery
  - Enhanced `search()` to support `field="keywords"` for keyword searches

### Technical

- 29 new keyword tests (19 annotator + 10 MCP)
- STOPWORDS constant with 100+ common words filtered from keywords

## [0.39.0] - 2026-01-29

### Added

- **MCP File Mutation Tools (Phase 3.1)**: File-based mutation API for AI agents to modify spec files on disk:
  - `change_reference_type(req_id, target_id, new_type, save_branch)` - Change Implements/Refines relationships
  - `move_requirement(req_id, target_file, save_branch)` - Relocate requirements between spec files
  - `restore_from_safety_branch(branch_name)` - Revert file changes from safety branch
  - `list_safety_branches()` - List available safety branches for rollback
  - Auto-refresh graph after file mutations (REQ-o00063-F)
  - Optional `save_branch=True` creates timestamped safety branch before modification

- **Git Safety Branch Utilities**: New utilities in `utilities/git.py` for file mutation safety:
  - `create_safety_branch(repo_root, req_id)` - Create timestamped safety branch
  - `list_safety_branches(repo_root)` - List all `safety/*` branches
  - `get_current_branch(repo_root)` - Get current branch name
  - `restore_from_safety_branch(repo_root, branch_name)` - Restore spec/ from branch
  - `delete_safety_branch(repo_root, branch_name)` - Remove safety branch

### Technical

- Implements REQ-o00063: MCP File Mutation Tools (4 new tools)
- 14 new file mutation tests, 82 total MCP tests

## [0.38.0] - 2026-01-28

### Added

- **MCP Graph Mutation Tools (Phase 3.2)**: Complete in-memory graph mutation API for AI agents:
  - **Node mutations**: `mutate_rename_node()`, `mutate_update_title()`, `mutate_change_status()`, `mutate_add_requirement()`, `mutate_delete_requirement()`
  - **Assertion mutations**: `mutate_add_assertion()`, `mutate_update_assertion()`, `mutate_delete_assertion()`, `mutate_rename_assertion()`
  - **Edge mutations**: `mutate_add_edge()`, `mutate_change_edge_kind()`, `mutate_delete_edge()`, `mutate_fix_broken_reference()`
  - **Undo operations**: `undo_last_mutation()`, `undo_to_mutation()`, `get_mutation_log()`
  - **Inspection tools**: `get_orphaned_nodes()`, `get_broken_references()`
  - All destructive operations require `confirm=True` for safety (REQ-o00062-F)
  - All mutations return `MutationEntry` for audit trail (REQ-o00062-E)
  - Pure delegation pattern - MCP layer only validates params and calls TraceGraph methods (REQ-d00065)

### Technical

- Implements REQ-o00062: MCP Graph Mutation Tools (17 new tools)
- Implements REQ-d00065: Mutation Tool Delegation pattern
- 39 new mutation tests, 68 total MCP tests

## [0.37.0] - 2026-01-28

### Added

- **MCP Server Documentation (Phase 2.2)**: Comprehensive documentation for AI agents and users:
  - `docs/cli/mcp.md` - User-facing documentation for the MCP server with all tool descriptions
  - MCP server `instructions` parameter for AI agents with quick start guide and usage patterns
  - New `elspais docs mcp` command to view MCP documentation from CLI
  - Updated docs topic list to include mcp topic (11 topics total)

### Technical

- 4 new documentation tests (64 total doc sync tests, 93 total MCP + doc tests)

## [0.36.0] - 2026-01-28

### Added

- **MCP Workspace Context Tools (Phase 2.1)**: New tools for workspace and project information:
  - `get_workspace_info()` - Returns repo path, project name, and configuration summary
  - `get_project_summary()` - Returns requirement counts by level, coverage statistics, and change metrics
  - Uses `count_by_level()` from annotators module per REQ-o00061-C
  - Reads config from unified config system per REQ-o00061-D
  - 10 new tests for workspace tools (29 total MCP tests)

### Technical

- Implements REQ-o00061: MCP Workspace Context Tools

## [0.35.0] - 2026-01-28

### Added

- **MCP Server Core Tools (Phase 1)**: Minimal MCP server implementation with graph-as-single-source-of-truth:
  - `get_graph_status()` - Node counts, root count, detection flags
  - `refresh_graph(full)` - Force graph rebuild from spec files
  - `search(query, field, regex)` - Search requirements by ID, title, or content
  - `get_requirement(req_id)` - Full requirement details with assertions
  - `get_hierarchy(req_id)` - Ancestors and children navigation
  - All tools consume TraceGraph directly via iterator-only API (REQ-p00060-B)
  - Serializers read from `node.get_field()` and `node.get_label()`
  - 19 tests verifying proper graph API usage

### Technical

- Implements REQ-o00060: MCP Core Query Tools
- Implements REQ-d00060-65: Tool implementations and serializers

## [0.34.1] - 2026-01-28

### Added

- **MCP Server Specification**: Created `spec/08-mcp-server.md` defining the MCP server architecture:
  - PRD-level: REQ-p00060 - MCP Server for AI-Driven Requirements Management
  - OPS-level: REQ-o00060 (Core Query), REQ-o00061 (Workspace Context), REQ-o00062 (Graph Mutations), REQ-o00063 (File Mutations)
  - DEV-level: REQ-d00060-65 (Tool implementations, serializers, mutation delegation)
- **Graph-as-Source-of-Truth**: MCP spec enforces REQ-p00050-B - all tools consume TraceGraph directly without intermediate data structures
- **Architecture Diagram**: Spec includes diagram showing MCP server layer consuming TraceGraph via iterator and mutation APIs

## [0.31.0] - 2026-01-28

### Added

- **MCP Mutator Tools**: The MCP server now exposes TraceGraph mutation methods for AI-driven requirement management:
  - **Node Mutations**: `mutate_rename_node()`, `mutate_update_title()`, `mutate_change_status()`, `mutate_add_requirement()`, `mutate_delete_requirement(confirm=True)`
  - **Assertion Mutations**: `mutate_add_assertion()`, `mutate_update_assertion()`, `mutate_delete_assertion(confirm=True)`, `mutate_rename_assertion()`
  - **Edge Mutations**: `mutate_add_edge()`, `mutate_change_edge_kind()`, `mutate_delete_edge(confirm=True)`, `mutate_fix_broken_reference()`
  - **Undo Operations**: `undo_last_mutation()` and `undo_to_mutation(mutation_id)` for reverting graph changes
  - **Inspection Tools**: `get_mutation_log(limit)`, `get_orphaned_nodes()`, `get_broken_references()` for graph state inspection
- **Safety Checks**: Destructive mutation operations (`mutate_delete_*`) require explicit `confirm=True` parameter to prevent accidental data loss
- **Mutation Serialization**: New `serialize_mutation_entry()` and `serialize_broken_reference()` functions in MCP serializers

## [0.30.0] - 2026-01-28

### Added

- **Edge Mutation API**: TraceGraph now supports edge (relationship) mutations:
  - `add_edge(source_id, target_id, edge_kind, assertion_targets)` - Adds new edge, creates BrokenReference if target doesn't exist
  - `change_edge_kind(source_id, target_id, new_kind)` - Changes edge type (IMPLEMENTS -> REFINES)
  - `delete_edge(source_id, target_id)` - Removes edge, marks source as orphan if no other parents
  - `fix_broken_reference(source_id, old_target_id, new_target_id)` - Redirects broken reference to new target
- **Orphan Management**: Edge mutations automatically update `_orphaned_ids` set when parent relationships change
- **Broken Reference Tracking**: `add_edge` to non-existent target creates BrokenReference; `fix_broken_reference` can redirect these

## [0.29.0] - 2026-01-28

### Added

- **Assertion Mutation API**: TraceGraph now supports assertion-specific mutations:
  - `rename_assertion(old_id, new_label)` - Renames assertion label (e.g., A -> D), updates edges
  - `update_assertion(assertion_id, new_text)` - Updates assertion text
  - `add_assertion(req_id, label, text)` - Adds new assertion to requirement
  - `delete_assertion(assertion_id, compact=True)` - Deletes assertion with optional compaction
- **Assertion Compaction**: When deleting middle assertion (e.g., B from [A,B,C,D]), subsequent labels shift down (C->B, D->C) and all edge references update automatically
- **Hash Recomputation**: All assertion mutations recompute parent requirement hash via `_recompute_requirement_hash()`

## [0.28.0] - 2026-01-28

### Added

- **Node Mutation API**: TraceGraph now supports CRUD operations with full undo:
  - `rename_node(old_id, new_id)` - Renames node and its assertion children
  - `update_title(node_id, new_title)` - Updates requirement title
  - `change_status(node_id, new_status)` - Changes requirement status
  - `add_requirement(...)` - Creates new requirement with optional parent link
  - `delete_requirement(node_id)` - Deletes requirement, tracks in `_deleted_nodes`
- **Mutation Logging**: All mutations log `MutationEntry` to `graph.mutation_log` for audit
- **Undo Support**: `graph.undo_last()` and `graph.undo_to(mutation_id)` for reverting changes
- **GraphNode.set_id()**: Mutable node IDs for rename operations
- **GraphNode.remove_child()**: Removes child node with bidirectional link cleanup

## [0.27.0] - 2026-01-27

### Fixed

- **trace --view**: Fixed Assoc (Associated) toggle - now uses HIDE semantic consistent with PRD/OPS/DEV badges
- **trace --view**: Fixed Core toggle - clicking now hides core (non-associated) requirements with proper styling
- **trace --view**: Added tree collapse/expand state persistence via cookies - tree state now survives page refresh
- **trace --view**: Children implementing multiple assertions now show single row with combined badges `[A][B][C]`
- **trace --report**: Implemented report presets that were previously ignored

### Changed

- **CLI**: Removed 19 dead arguments that were defined but never implemented:
  - `validate`: --fix, --core-repo, --tests, --no-tests, --mode
  - `trace`: --port, --mode, --sponsor, --graph, --depth
  - `reformat-with-claude`: Simplified to placeholder stub (entire command not yet implemented)
- **CLI**: `trace --report` now uses `choices` for tab completion - shows `{minimal,standard,full}` in help
  - `--report minimal`: ID, Title, Status only (quick overview)
  - `--report standard`: ID, Title, Level, Status, Implements (default)
  - `--report full`: All fields including Body, Assertions, Hash, Code/Test refs

- **trace --view**: Version badge now shows actual elspais version (e.g., "v0.27.0") instead of hardcoded "v1"

- **trace --view**: Replaced confusing "Files" filter with "Tests" filter
  - Shows TEST nodes in tree hierarchy (with 🧪 icon)
  - Badge displays count of test nodes instead of file count
  - Clicking badge shows test rows that validate requirements

## [0.26.0] - Previous

- Multiline block comment support for code/test references
- Various bug fixes and improvements
