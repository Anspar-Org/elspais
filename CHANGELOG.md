# Changelog

<!-- markdownlint-disable MD022 MD032 -->
<!-- Compact changelog format: no blank lines around headings/lists -->

All notable changes to elspais will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.20.0] - 2026-01-25
### Added
- **FILE Node Support** - Unified graph approach for lossless file reconstruction
  - New `--graph-file` CLI flag for `elspais trace --graph`
  - `NodeKind.FILE` and `NodeKind.FILE_REGION` in TraceGraph
  - `FileInfo` dataclass with file_path and requirements (node-data refs)
  - `TraceNode.source_file` for REQ→FILE bidirectional linking
  - Graph-based reconstruction in FileReconstructor
  - Node-data references (not edges) prevent coverage algorithm interference
  - Schema entries for FILE (is_root=True) and FILE_REGION node types
- **Cookie State Persistence** for `--view` mode
  - Filter state persists across page refreshes (hiddenLevels, hiddenRepos, hideFiles, viewMode)
  - SameSite=Lax cookies with 30-day expiration
  - Graceful fallback when cookies disabled
  - Clear Filters button resets all saved state
- **Requirement Move** - Move requirements between spec files via MCP
  - `move_requirement()` in mutator for moving requirements to different files
  - Position control: `start`, `end`, or `after` a specific requirement
  - Creates target file if it doesn't exist
  - Properly handles whitespace and separators
  - MCP tool `move_requirement()` with cache invalidation on success
  - 35 new tests in `test_requirement_move.py`
- **File Deletion Workflow** - Safely delete spec files via MCP
  - `analyze_file_for_deletion()` checks for remaining requirements and non-req content
  - `delete_spec_file()` with force flag and content extraction options
  - MCP tools `prepare_file_deletion()` and `delete_spec_file()`
  - Refuses deletion when requirements exist (unless force=True)
  - 24 new tests in `test_file_deletion.py`
- **Recursive Subdirectory Parsing Validation** - Comprehensive test coverage for nested specs
  - Validates `RequirementParser.parse_directory(recursive=True)` works at any nesting depth
  - Tests file pattern matching (`prd-*.md`, `ops-*.md`) at multiple depths
  - Tests `skip_files` configuration at all nesting levels
  - Tests MCP context with nested files: graph building, incremental refresh, tracked files
  - Tests new file detection and deleted file detection in nested directories
  - 17 new tests in `test_subdirectory_parsing.py`

## [0.19.0] - 2026-01-25
### Added
- **Reference Specialization** - Convert REQ→REQ references to REQ→Assertion
  - `specialize_reference()` in mutator for converting `Implements: REQ-p00001` to `Implements: REQ-p00001-A-B-C`
  - Multi-assertion syntax support (combines assertion labels with hyphens)
  - MCP tool `specialize_reference()` with cache invalidation on success
  - 16 new tests in `test_reference_specialize.py`
- **Recursive Parsing** - Fix for files in subdirectories not being parsed
  - Added `recursive` parameter to `parse_directory()` and `parse_directories()`
  - Files in `spec/regulations/fda/` now properly included in graph
  - Context.py mtime tracking now matches actual parsing behavior
### Changed
- **Loader Consolidation** - Single source of truth for spec file loading
  - `loader.py` now provides `create_parser()`, `parse_requirements_from_directories()`, `load_requirements_from_directories()`
  - `context.py` and `validate.py` use shared loader instead of duplicating parsing logic
  - Removed duplicate `load_requirements_from_repo()` from `validate.py`

## [0.18.0] - 2026-01-25
### Added
- **Graph Manipulation Foundation** - Foundation for AI-assisted graph operations via MCP
  - `git_safety.py`: `GitSafetyManager` for creating safety branches before risky operations
    - `create_safety_branch()`, `restore_from_branch()`, `list_safety_branches()`, `delete_safety_branch()`
    - Automatic stash handling when repo has uncommitted changes
  - `annotations.py`: `AnnotationStore` for session-scoped annotations and tags
    - In-memory storage that doesn't modify spec files
    - `add_annotation()`, `get_annotations()`, `add_tag()`, `remove_tag()`, `list_tagged()`
    - Tags index for fast node lookup by tag
  - `transforms.py`: `AITransformer` for AI-assisted requirement transformations
    - `transform()` method with replace/operations output modes
    - `ClaudeInvoker` for subprocess calls to `claude -p`
    - Git safety branch creation before changes
    - dry_run mode for previewing transformations
  - `serializers.py`: Added `serialize_node_full()` for complete node serialization
    - Full requirement text from file
    - All assertions with coverage info
    - Metrics, relationships, source location
- **14 new MCP tools** for graph manipulation and annotations:
  - `get_node_as_json()` - Full node serialization for AI processing
  - `transform_with_ai()` - AI-assisted requirement transformation
  - `restore_from_safety_branch()`, `list_safety_branches()` - Git branch management
  - `add_annotation()`, `get_annotations()`, `add_tag()`, `remove_tag()`, `list_tagged()`, `list_all_tags()`, `nodes_with_annotation()`, `clear_annotations()`, `annotation_stats()` - Session annotations
- 59 new tests in `test_annotations.py`, `test_transforms.py`, `test_git_safety.py`, `test_serializers.py`

## [0.17.0] - 2026-01-25
### Added
- **Partial graph refresh** in MCP context - Performance optimization for incremental updates
  - `partial_refresh(changed_files)` method only re-parses modified/deleted/new files
  - Preserves requirements from unchanged files in cache
  - Supports explicit file list or automatic stale detection
  - Helper methods `_get_requirement_ids_for_files()` and `_is_assertion_id()`
- 16 new tests in `tests/test_mcp/test_incremental_refresh.py`
- **TrackedFile registry** in MCP context - Foundation for incremental graph updates
  - `TrackedFile` dataclass tracks which nodes originate from each spec file
  - `GraphState.tracked_files` maps file paths to TrackedFile with node_ids
  - `get_tracked_files()`, `get_nodes_for_file()`, `get_stale_tracked_files()` helper methods
  - Backward-compatible `file_mtimes` property on GraphState
- 18 new tests in `tests/test_mcp/test_tracked_files.py`

## [0.16.0] - 2026-01-25
### Added
- **MCP Graph Resources** - Alternative read-only access pattern for graph data
  - `graph://status` - Staleness and node count statistics
  - `graph://validation` - Current warnings/errors from graph build
  - `traceability://{req_id}` - Full tree path from requirement to tests
  - `coverage://{req_id}` - Per-assertion coverage breakdown with sources
  - `hierarchy://{req_id}/ancestors` - Parent chain to root
  - `hierarchy://{req_id}/descendants` - All child nodes recursively
- 17 new tests in `tests/test_mcp/test_graph_resources.py`
- **Phase 1 Complete** - All read-only graph MCP tools and resources are now available

## [0.15.0] - 2026-01-25
### Added
- **`--depth` flag** for trace command - Control graph output depth
  - Numeric values: `--depth 0` (roots only), `--depth 1`, `--depth 2`, etc.
  - Named levels: `--depth requirements` (1), `--depth assertions` (2), `--depth implementation` (3), `--depth full` (unlimited)
  - Can be combined with `--report` to override preset's max_depth
- **Coverage breakdown in reports** - Standard/full reports now show direct_covered, explicit_covered, inferred_covered metrics
- **Diff viewer infrastructure** for `--view` mode
  - New `trace_view/diff.py` module with difflib-based diff generation
  - Diff modal HTML/CSS/JS in base.html and styles.css
  - `showDiffModal()` and `closeDiffModal()` JavaScript functions
- **Standalone mode banner** - Info banner when using `--view` without `--embed-content` explaining file link limitations
- **INDEX.md markdownlint compliance** - Generated INDEX files now end with trailing newline (MD047)
- New test classes: `TestCLIDepthFlag`, `TestDepthMapping`, `TestGenerateIndex`

### Fixed
- **Assertion-level references in scanning.py** - Pattern now matches `REQ-d00001-A` style assertion refs
- **Summary metrics table** - Shows coverage breakdown with Direct/Explicit (high confidence) combined count

## [0.14.0] - 2026-01-25
### Added
- **Refines relationship** - New `Refines:` field for requirements that add detail without claiming coverage
  - NO coverage rollup for refines relationships
  - Safe for decomposition without strong satisfaction claims
- **Coverage source tracking** in `RollupMetrics`
  - `direct_covered`: Assertions with direct test coverage (Test → Assertion)
  - `explicit_covered`: Assertions covered via explicit implements (REQ → Assertion)
  - `inferred_covered`: Assertions covered via REQ → REQ implements (strict mode only)
- **Multi-assertion syntax** - `Implements: REQ-p00001-A-B-C` expands to individual assertion refs
- **CoverageSource enum** in `graph_schema.py` with values: `direct`, `explicit`, `inferred`
- **Strict mode** for metrics calculation
  - `MetricsConfig.strict_mode` (default: False)
  - In strict mode, REQ→REQ implements rolls up coverage (flagged as inferred)
  - Default mode treats REQ→REQ implements like refines (no assertion rollup)
- New test classes: `TestRefinesParsing`, `TestMultiAssertionSyntax`, `TestCoverageSourceTracking`, `TestRefinesRelationship`

### Changed
- **Implements targets assertions** - `Implements: REQ-xxx-A` now creates valid explicit coverage links
- `graph_schema.py` implements relationship now allows `to_kind=["requirement", "assertion"]`
- `RollupMetrics` dataclass updated with `direct_covered`, `explicit_covered`, `inferred_covered` fields
- Test metrics now properly roll up from assertions to parent requirements

## [0.13.0] - 2026-01-25
### Added
- **Unified test parsing** via enhanced `parsers/test.py`
  - Context-aware patterns: only matches `Validates:`, `IMPLEMENTS:`, and test function names
  - Eliminates false positives from fixture data and bare REQ mentions
  - Expected-broken-links marker support with multi-language comment styles
- **Relationship type validation** in `TraceGraphBuilder`
  - Validates `from_kind`/`to_kind` constraints from schema
  - Warns when tests try to "implement" requirements or validate invalid targets
- New test classes: `TestTestParserContextAware`, `TestTestParserExpectedBrokenLinks`, `TestRelationshipTypeValidation`

### Changed
- `commands/trace.py` now uses `TestParser` from parser registry instead of `TestScanner`
- `graph_builder._find_node()` suffix matching now only matches REQUIREMENT/ASSERTION nodes

### Fixed
- Fixed `_find_node` returning test nodes when looking for requirement IDs

## [0.12.0] - 2026-01-24
### Added
- **Centralized hierarchy scanning** via new `core/hierarchy.py` module
  - `find_requirement()`, `resolve_id()`, `normalize_req_id()` for flexible ID matching
  - `find_children()`, `find_children_ids()` for parent/child discovery
  - `build_children_index()` for efficient hierarchy traversal
  - `detect_cycles()` with `CycleInfo` dataclass for pure cycle detection
  - `find_roots()`, `find_orphans()` for hierarchy analysis
- New `core/loader.py` with `load_requirements_from_repo()` for centralized requirement loading

### Changed
- `commands/analyze.py` now uses centralized hierarchy functions from `core/hierarchy.py`
- `commands/trace.py` now uses `find_children_ids()` instead of local `find_implementers()`
- `trace_view/generators/base.py` now uses centralized `detect_cycles()` from `core/hierarchy`
- `reformat/hierarchy.py` now imports `load_requirements_from_repo` from `core/loader`

## [0.11.2] - 2026-01-21

### Fixed

- Fixed `elspais trace --view` crash caused by missing `is_cycle` and `cycle_path` properties in `TraceViewRequirement`

### Added

- Comprehensive git hooks (pre-commit, pre-push, commit-msg) with branch protection, linting, secret detection, and commit message format validation
- Commit message format validation requiring `[TICKET-NUMBER]` prefix (e.g., `[CUR-514]`)
- Markdownlint configuration (`.markdownlint.json`) disabling line length and duplicate heading rules

### Changed

- Applied ruff and black formatting fixes across the codebase

## [0.11.1] - 2026-01-15

### Changed
- Improved CLI `--help` output with examples, subcommand hints, and clearer descriptions

## [0.11.0] - 2026-01-15

### Added
- **Cross-repo hierarchy support** for `reformat-with-claude` command
  - Resolves parent requirements from associated/sponsor repositories
  - New `--core-repo` flag to specify core repository path
  - Builds complete hierarchy graph across repository boundaries

### Changed
- **Performance optimization** for reformat command: Uses validation to filter requirements before reformatting instead of processing all files
- Reformat module now uses core modules directly for consistent behavior

### Fixed
- Hash update robustness improved with better error handling and INFO logging
- `normalize_req_id()` now uses config-based `PatternValidator` for consistent ID normalization
- Associated prefix case is now preserved in normalized requirement IDs

## [0.10.0] - 2026-01-10

### Added
- **trace-view integration**: Enhanced traceability visualization with optional dependencies
  - Interactive HTML generation with Jinja2 templates (`elspais[trace-view]`)
  - Collaborative review server with Flask REST API (`elspais[trace-review]`)
  - New CLI flags: `--view`, `--embed-content`, `--edit-mode`, `--review-mode`, `--server`, `--port`
- **New `trace_view` package** (`src/elspais/trace_view/`)
  - `TraceViewRequirement` adapter wrapping core `Requirement` model
  - Coverage calculation and orphan detection
  - Implementation file scanning
  - Generators for HTML, Markdown, and CSV output
- **Review system** for collaborative requirement feedback
  - Comment threads with nested replies
  - Review flags and status change requests
  - Git branch management for review workflows
  - JSON-based persistence in `.elspais/reviews/`
- **AI-assisted requirement reformatting** with `reformat-with-claude` command
  - Transforms legacy "Acceptance Criteria" format to assertion-based format
  - Format detection and validation
  - Line break normalization
  - Claude CLI integration with structured JSON output
- **New `reformat` module** (`src/elspais/reformat/`)
  - `detect_format()`, `needs_reformatting()` - format analysis
  - `reformat_requirement()`, `assemble_new_format()` - AI transformation
  - `normalize_line_breaks()`, `fix_requirement_line_breaks()` - cleanup
  - `RequirementNode`, `build_hierarchy()` - requirement traversal
- New optional dependency extras in pyproject.toml:
  - `elspais[trace-view]`: jinja2 for HTML generation
  - `elspais[trace-review]`: flask, flask-cors for review server
  - `elspais[all]`: all optional features
- New documentation: `docs/trace-view.md` user guide
- 18 new integration tests for trace-view features

### Changed
- `elspais trace` command now delegates to trace-view when enhanced features requested
- CLAUDE.md updated with trace-view architecture documentation

## [0.9.4] - 2026-01-08

### Added
- **Roadmap conflict entries**: When duplicate requirement IDs exist (e.g., same ID in spec/ and spec/roadmap/), both requirements are now visible in output
  - Duplicate entries stored with `__conflict` suffix key (e.g., `REQ-p00001__conflict`)
  - New `is_conflict` and `conflict_with` fields on Requirement model
  - Conflict entries treated as orphaned (`implements=[]`) for clear visibility
  - Warning generated for each duplicate (surfaced as `id.duplicate` rule)
- **Sponsor/associated repository spec scanning**: New `--mode` flag and sponsor configuration support
  - `elspais validate --mode core`: Scan only core spec directories
  - `elspais validate --mode combined`: Include sponsor specs (default)
  - New `sponsors` module with zero-dependency YAML parser
  - Configuration via `.github/config/sponsors.yml` with local override support
  - `traceability.include_associated` config option (default: true)
- 29 new tests for conflict entries and sponsor scanning

### Changed
- Parser now keeps both requirements when duplicates found (instead of ignoring second)
- JSON output includes conflict metadata for both original and conflict entries

## [0.9.3] - 2026-01-05

### Added
- Git-based change detection with new `changed` command
  - `elspais changed`: Show uncommitted changes to spec files
  - `elspais changed --json`: JSON output for programmatic use
  - `elspais changed --all`: Include all changed files, not just spec/
  - `elspais changed --base-branch`: Compare vs different branch
- New `src/elspais/core/git.py` module with functions:
  - `get_git_changes()`: Main entry point for git change detection
  - `get_modified_files()`: Detect modified/untracked files via git status
  - `get_changed_vs_branch()`: Files changed vs main/master branch
  - `detect_moved_requirements()`: Detect requirements moved between files
- 23 new tests for git functionality

## [0.9.2] - 2026-01-05

### Added
- `id.duplicate` rule documentation in `docs/rules.md`
- Dynamic version detection using `importlib.metadata`

### Changed
- Enhanced ParseResult API documentation in CLAUDE.md to explain warning handling
- Updated CLAUDE.md with git.py module description

## [0.9.1] - 2026-01-03

### Changed
- Updated CLAUDE.md with complete architecture documentation
- Added testing/, mcp/, and content_rules modules to CLAUDE.md
- Added ParseResult API design pattern documentation
- Added Workflow section with contribution guidelines
- Updated Python version reference from 3.8+ to 3.9+

## [0.9.0] - 2026-01-03

### Added
- Test mapping and coverage functionality (`elspais.testing` module)
  - `TestScanner`: Scans test files for requirement references
  - `ResultParser`: Parses JUnit XML and pytest JSON test results
  - `TestCoverageMapper`: Orchestrates scanning and result mapping for test→requirement coverage
- Parser resilience with `ParseResult` API and warning system
  - Parser now returns `ParseResult` containing both requirements and warnings
  - Non-fatal issues generate warnings instead of failing parsing

## [0.2.1] - 2025-12-28

### Changed
- Renamed "sponsor" to "associated" throughout the codebase
  - Config: `[sponsor]` → `[associated]`, `[patterns.sponsor]` → `[patterns.associated]`
  - CLI: `--sponsor-prefix` → `--associated-prefix`, `--type sponsor` → `--type associated`
  - ID template: `{sponsor}` → `{associated}`
- Made the tool generic by removing standards-specific references
- Updated documentation to use neutral terminology

## [0.2.0] - 2025-12-28

### Added
- Multi-directory spec support: `spec = ["spec", "spec/roadmap"]`
- Generic `get_directories()` function for any config key
- Recursive directory scanning for code directories
- `get_code_directories()` convenience function with auto-recursion
- `ignore` config for excluding directories (node_modules, .git, etc.)
- Configurable `no_reference_values` for Implements field (-, null, none, N/A)
- `parse_directories()` method for parsing multiple spec directories
- `skip_files` config support across all commands

### Fixed
- Body extraction now matches hht-diary behavior (includes Rationale/Acceptance)
- Hash calculation strips trailing whitespace for consistency
- skip_files config now properly passed to parser in all commands

## [0.1.0] - 2025-12-27

### Added
- Initial release of elspais requirements validation tools
- Configurable requirement ID patterns (REQ-p00001, PRD-00001, PROJ-123, etc.)
- Configurable validation rules with hierarchy enforcement
- TOML-based per-repository configuration (.elspais.toml)
- CLI commands: validate, trace, hash, index, analyze, init
- Multi-repository support (core/associated model)
- Traceability matrix generation (Markdown, HTML, CSV)
- Hash-based change detection for requirements
- Zero external dependencies (Python 3.8+ standard library only)
- Core requirement parsing and validation
- Pattern matching for multiple ID formats
- Rule engine for hierarchy validation
- Configuration system with sensible defaults
- Test fixtures for multiple requirement formats
- Comprehensive documentation
