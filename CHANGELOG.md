# Changelog

All notable changes to elspais will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
  - `TestMapper`: Orchestrates scanning and result mapping
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
