# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

elspais is a zero-dependency Python requirements validation and traceability tool. It validates requirement formats, checks hierarchy relationships, generates traceability matrices, and supports multi-repository requirement management with configurable ID patterns.

## Commands

```bash
# Install in development mode
pip install -e ".[dev]"

# Run all tests
pytest

# Run a single test file
pytest tests/test_parser.py

# Run a specific test
pytest tests/test_parser.py::test_function_name -v

# Run with coverage
pytest --cov=elspais

# Type checking
mypy src/elspais

# Linting
ruff check src/elspais
black --check src/elspais

# CLI usage
elspais validate           # Validate requirements
elspais trace --format html  # Generate traceability matrix
elspais hash update         # Update requirement hashes
```

## Architecture

### Core Package Structure (`src/elspais/`)

- **cli.py**: Entry point, argparse-based CLI dispatcher
- **core/**: Core domain logic
  - **models.py**: Dataclasses (`Requirement`, `ParsedRequirement`, `RequirementType`, `Assertion`, `ParseResult`, `ParseWarning`, `ContentRule`)
  - **parser.py**: `RequirementParser` - parses Markdown requirement files using regex patterns, extracts `## Assertions` section, returns `ParseResult` with warnings
  - **patterns.py**: `PatternValidator`, `PatternConfig` - configurable ID pattern matching (supports HHT-style `REQ-p00001`, Jira-style `PROJ-123`, named `REQ-UserAuth`, assertion IDs `REQ-p00001-A`, etc.)
  - **rules.py**: `RuleEngine`, `RulesConfig`, `FormatConfig` - validation rules for hierarchy, format, assertions, and traceability
  - **hasher.py**: SHA-256 content hashing for change detection
  - **content_rules.py**: Content rule loading and parsing (AI agent guidance)
- **config/**: Configuration handling
  - **loader.py**: TOML parser (zero-dependency), config file discovery, environment variable overrides
  - **defaults.py**: Default configuration values
- **commands/**: CLI command implementations (validate, trace, hash_cmd, index, analyze, init, edit, config_cmd, rules_cmd)
- **testing/**: Test mapping and coverage functionality
  - **config.py**: `TestingConfig` - configuration for test scanning
  - **scanner.py**: `TestScanner` - scans test files for requirement references (REQ-xxxxx patterns)
  - **result_parser.py**: `ResultParser` - parses JUnit XML and pytest JSON test results
  - **mapper.py**: `TestMapper` - orchestrates scanning and result mapping for coverage analysis
- **mcp/**: Model Context Protocol server (optional, requires `elspais[mcp]`)
  - **server.py**: MCP server implementation
  - **context.py**: Context management for MCP resources
  - **serializers.py**: Serialization helpers for MCP responses

### Key Design Patterns

1. **Zero Dependencies**: Uses only Python 3.9+ stdlib. Custom TOML parser in `config/loader.py`.

2. **Configurable Patterns**: ID patterns defined via template tokens (`{prefix}`, `{type}`, `{associated}`, `{id}`). The `PatternValidator` builds regex dynamically from config.

3. **Hierarchy Rules**: Requirements have levels (PRD=1, OPS=2, DEV=3). Rules define allowed "implements" relationships (e.g., `dev -> ops, prd`).

4. **Hash-Based Change Detection**: Body content is hashed (SHA-256, 8 chars) for tracking requirement changes.

5. **ParseResult API**: Parser returns `ParseResult` containing both requirements and warnings, enabling resilient parsing that continues on non-fatal issues.

### Requirement Format (Updated)

Requirements use Markdown with assertions as the unit of verification:

```markdown
# REQ-d00001: Requirement Title

**Level**: Dev | **Status**: Active | **Implements**: REQ-p00001

## Assertions

A. The system SHALL do something specific.
B. The system SHALL do another thing.

## Rationale

<optional non-normative explanation>

*End* *Requirement Title* | **Hash**: a1b2c3d4
```

Key format rules:
- **Assertions replace Acceptance Criteria** - labeled A-Z, each uses SHALL
- **Assertion IDs** - tests can reference `REQ-d00001` or `REQ-d00001-A`
- **One-way traceability** - children reference parents via `Implements:`, never reverse
- **Associated-scoped IDs** - format `TTN-REQ-p00001` for associated repositories
- **Hash scope** - calculated from lines between header and footer
- **Placeholder assertions** - removed assertions can use placeholder text ("Removed", "obsolete", etc.) to maintain sequential labels

### Assertion Configuration

Assertions are configured via `[patterns.assertions]` and `[rules.format]`:

```toml
[patterns.assertions]
label_style = "uppercase"  # "uppercase" [A-Z], "numeric" [00-99], "alphanumeric" [0-Z], "numeric_1based" [1-99]
max_count = 26             # Maximum assertions per requirement
zero_pad = false           # For numeric styles: true = "01", false = "1"

[rules.format]
require_assertions = true       # Require ## Assertions section
acceptance_criteria = "warn"    # "allow" | "warn" | "error" for old Acceptance Criteria format
require_shall = true            # Require SHALL in assertion text
labels_sequential = true        # Labels must be sequential (A, B, C... not A, C, D)
labels_unique = true            # No duplicate labels
placeholder_values = ["obsolete", "removed", "deprecated", "N/A", "n/a", "-", "reserved", "Removed"]
```

See `docs/configuration.md` for full configuration options.

### Configuration

Uses `.elspais.toml` with sections: `[project]`, `[directories]`, `[patterns]`, `[rules]`. See `docs/configuration.md` for full reference.

### Test Fixtures

`tests/fixtures/` contains example repository structures:
- `hht-like/`: HHT-style requirements (`REQ-p00001`)
- `fda-style/`: Strict hierarchy requirements
- `jira-style/`: Jira-like IDs (`PROJ-123`)
- `named-reqs/`: Named requirements (`REQ-UserAuth`)
- `associated-repo/`: Multi-repo with associated prefixes
- `assertions/`: Assertion-based requirements with `## Assertions` section
- `invalid/`: Invalid cases (circular deps, broken links, missing hashes)

## Workflow

- **ALWAYS** update the version in `pyproject.toml` before pushing to remote
- **ALWAYS** update `CHANGELOG.md` with new features
- **ALWAYS** use a sub-agent to update the `docs/` files
- **ALWAYS** ensure that `CLAUDE.md` is updated with changes for each commit
