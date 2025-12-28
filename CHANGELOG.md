# Changelog

All notable changes to elspais will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
- Multi-repository support (core/sponsor model)
- Traceability matrix generation (Markdown, HTML, CSV)
- Hash-based change detection for requirements
- Zero external dependencies (Python 3.8+ standard library only)
- Core requirement parsing and validation
- Pattern matching for multiple ID formats
- Rule engine for hierarchy validation
- Configuration system with sensible defaults
- Test fixtures for multiple requirement formats
- Comprehensive documentation
