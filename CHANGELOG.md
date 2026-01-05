# Changelog

All notable changes to elspais will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
