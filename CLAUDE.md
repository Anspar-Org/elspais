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
elspais changed            # Show uncommitted changes to spec files
elspais changed --json     # Output changes as JSON

# trace-view enhanced features (requires pip install elspais[trace-view])
elspais trace --view                 # Generate interactive HTML view
elspais trace --view --embed-content # Embed full requirement content
elspais trace --view --edit-mode     # Enable client-side editing
elspais trace --view --review-mode   # Enable collaborative review

# Review server (requires pip install elspais[trace-review])
elspais trace --server               # Start Flask review server on port 8080
elspais trace --server --port 3000   # Start on custom port

# Graph-based traceability (unified Requirements → Assertions → Code → Tests DAG)
elspais trace --graph                     # Generate graph-based traceability matrix
elspais trace --graph --format html       # Generate HTML graph with collapsible hierarchy
elspais trace --graph-json                # Output full graph structure as JSON
elspais trace --graph --report minimal    # Use minimal report (id, title, status only)
elspais trace --graph --report standard   # Use standard report with coverage metrics
elspais trace --graph --report full       # Use full report with all metrics
elspais trace --graph --depth 2           # Limit depth to 2 levels (numeric)
elspais trace --graph --depth requirements # Show requirements hierarchy only (depth=1)
elspais trace --graph --depth assertions  # Include assertions (depth=2)
elspais trace --graph --depth implementation # Include code/tests (depth=3)
elspais trace --graph --depth full        # Show unlimited depth (default)

# AI-assisted requirement reformatting
elspais reformat-with-claude --dry-run              # Preview reformatting
elspais reformat-with-claude --backup               # Create backups before changes
elspais reformat-with-claude --start-req X          # Start from requirement X
elspais reformat-with-claude --mode combined        # Cross-repo hierarchy support
elspais reformat-with-claude --mode local-only      # Only local requirements

# Format examples (learn requirement format)
elspais example                   # Quick format reference
elspais example requirement       # Full requirement template
elspais example journey           # User journey template
elspais example assertion         # Assertion rules and examples
elspais example ids               # ID patterns from current config
elspais example --full            # Display spec/requirements-spec.md

# Project initialization
elspais init                      # Create .elspais.toml configuration
elspais init --template           # Create example requirement file
elspais init --type associated    # Initialize associated repository
```

## Architecture

### Core Package Structure (`src/elspais/`)

- **cli.py**: Entry point, argparse-based CLI dispatcher
- **core/**: Core domain logic
  - **models.py**: Dataclasses (`Requirement` with `refines`/`implements`/`is_conflict`/`conflict_with` fields, `ParsedRequirement`, `RequirementType`, `Assertion`, `ParseResult`, `ParseWarning`, `ContentRule`)
  - **parser.py**: `RequirementParser` - parses Markdown requirement files using regex patterns, extracts `## Assertions` section, returns `ParseResult` with warnings
  - **patterns.py**: `PatternValidator`, `PatternConfig` - configurable ID pattern matching (supports HHT-style `REQ-p00001`, Jira-style `PROJ-123`, named `REQ-UserAuth`, assertion IDs `REQ-p00001-A`, etc.)
  - **rules.py**: `RuleEngine`, `RulesConfig`, `FormatConfig` - validation rules for hierarchy, format, assertions, and traceability
  - **hasher.py**: SHA-256 content hashing for change detection
  - **content_rules.py**: Content rule loading and parsing (AI agent guidance)
  - **git.py**: Git-based change detection (`get_git_changes`, `get_modified_files`, `detect_moved_requirements`) for tracking uncommitted changes and moved requirements
  - **hierarchy.py**: Centralized hierarchy scanning utilities (`find_requirement`, `find_children`, `find_children_ids`, `build_children_index`, `detect_cycles`, `find_roots`, `find_orphans`, `CycleInfo` dataclass) - replaces duplicated logic across analyze, trace, and trace_view modules
  - **loader.py**: Centralized requirement loading (`load_requirements_from_repo`) - moved from validate.py to break circular dependencies
  - **graph.py**: Unified traceability graph (`SourceLocation`, `NodeKind`, `TraceNode`, `TraceGraph`, `CodeReference`, `TestReference`, `TestResult`, `UserJourney`) - represents full Requirements → Assertions → Code → Tests → Results DAG
  - **graph_schema.py**: Schema-driven graph configuration (`NodeTypeSchema`, `RelationshipSchema`, `ParserConfig`, `ValidationConfig`, `GraphSchema`, `RollupMetrics` with coverage source tracking, `MetricsConfig` with `strict_mode`, `ReportSchema`, `CoverageSource` enum) - enables custom node types, relationships, and configurable reports via config
  - **graph_builder.py**: Graph construction (`TraceGraphBuilder`, `ValidationResult`, `build_graph_from_requirements`, `build_graph_from_repo`) - builds DAG with cycle detection, orphan checking, and broken link validation
- **config/**: Configuration handling
  - **loader.py**: TOML parser (zero-dependency), config file discovery, environment variable overrides
  - **defaults.py**: Default configuration values
- **commands/**: CLI command implementations (validate, trace, hash_cmd, index, analyze, changed, init, edit, config_cmd, rules_cmd, reformat_cmd, example_cmd)
- **testing/**: Test mapping and coverage functionality
  - **config.py**: `TestingConfig` - configuration for test scanning with `reference_keyword` (default: "Validates")
  - **scanner.py**: `TestScanner` - scans test files for requirement references using configurable `Validates:` keyword; `build_validates_patterns()` generates patterns from PatternConfig; `create_test_nodes()` converts scan results to TraceNode objects for graph integration
  - **result_parser.py**: `ResultParser` - parses JUnit XML and pytest JSON test results
  - **mapper.py**: `TestMapper` - orchestrates scanning and result mapping for coverage analysis
- **sponsors/**: Sponsor/associated repository configuration loading
  - **\_\_init\_\_.py**: `Sponsor`, `SponsorsConfig` dataclasses, zero-dependency YAML parser, `load_sponsors_config()`, `resolve_sponsor_spec_dir()`, `get_sponsor_spec_directories()` for multi-repo spec scanning
- **mcp/**: Model Context Protocol server (optional, requires `elspais[mcp]`)
  - **server.py**: MCP server with resources and tools
  - **context.py**: `WorkspaceContext`, `GraphState` - context management with graph caching
  - **serializers.py**: JSON serialization helpers for MCP responses
  - **Resources**: Read-only data access
    - `requirements://all`, `requirements://{req_id}`, `requirements://level/{level}`
    - `content-rules://list`, `content-rules://{filename}`
    - `config://current`
    - `graph://status` - staleness and node counts
    - `graph://validation` - warnings/errors from graph build
    - `traceability://{req_id}` - full tree path to tests
    - `coverage://{req_id}` - per-assertion coverage breakdown
    - `hierarchy://{req_id}/ancestors`, `hierarchy://{req_id}/descendants`
  - **Tools**: Callable operations
    - `validate()`, `parse_requirement()`, `search()`, `get_requirement()`, `analyze()`
    - `get_graph_status()`, `refresh_graph()`, `get_hierarchy()`, `get_traceability_path()`
    - `get_coverage_breakdown()`, `list_by_criteria()`, `show_requirement_context()`
- **trace_view/**: Enhanced traceability visualization (optional, requires `elspais[trace-view]`)
  - **models.py**: `TraceViewRequirement` adapter wrapping `core.models.Requirement`, `TestInfo`, `GitChangeInfo`
  - **coverage.py**: Coverage calculation (`calculate_coverage`, `count_by_level`, `find_orphaned_requirements`)
  - **scanning.py**: Implementation file scanning (`scan_implementation_files`)
  - **generators/**: Output format generators
    - **base.py**: `TraceViewGenerator` - abstract base with HTML, CSV, Markdown support
    - **markdown.py**: Markdown matrix generation
    - **csv.py**: CSV export
  - **html/**: HTML generation (requires jinja2)
    - **generator.py**: `HTMLGenerator` with Jinja2 templates
    - **templates/**: Jinja2 template files
    - **static/**: CSS and JavaScript assets
  - **review/**: Collaborative review system (requires flask)
    - **models.py**: `Comment`, `Thread`, `ReviewFlag`, `StatusRequest` dataclasses
    - **storage.py**: JSON-based comment persistence
    - **branches.py**: Git branch management for reviews
    - **server.py**: Flask REST API (`create_app`)
    - **position.py**: Position resolution for diff-based comments
    - **status.py**: Requirement status modification
- **reformat/**: AI-assisted requirement reformatting
  - **detector.py**: `detect_format`, `needs_reformatting`, `FormatAnalysis` - detects old vs new format
  - **transformer.py**: `reformat_requirement`, `assemble_new_format` - Claude CLI integration
  - **prompts.py**: System prompts and JSON schema for Claude
  - **line_breaks.py**: `normalize_line_breaks`, `fix_requirement_line_breaks`
  - **hierarchy.py**: `RequirementNode`, `build_hierarchy`, `traverse_top_down`
- **parsers/**: Parser plugin system for traceability tree
  - **\_\_init\_\_.py**: `SpecParser` protocol, `ParserRegistry`, `get_parser()` for parser discovery
  - **requirement.py**: Requirement parser wrapping core parser
  - **journey.py**: User journey parser for JNY-xxx-NN format
  - **code.py**: Code reference parser for `# Implements:` comments
  - **test.py**: Test file parser for REQ-xxx patterns
  - **junit_xml.py**: JUnit XML test result parser
  - **pytest_json.py**: pytest JSON test result parser

### Key Design Patterns

1. **Zero Dependencies**: Uses only Python 3.9+ stdlib. Custom TOML parser in `config/loader.py`.

2. **Configurable Patterns**: ID patterns defined via template tokens (`{prefix}`, `{type}`, `{associated}`, `{id}`). The `PatternValidator` builds regex dynamically from config.

3. **Hierarchy Rules**: Requirements have levels (PRD=1, OPS=2, DEV=3). Rules define allowed "implements" relationships (e.g., `dev -> ops, prd`).

4. **Hash-Based Change Detection**: Body content is hashed (SHA-256, 8 chars) for tracking requirement changes.

5. **ParseResult API**: Parser returns `ParseResult` containing both requirements and warnings, enabling resilient parsing that continues on non-fatal issues. Warnings include duplicate ID detection (surfaced as `id.duplicate` rule violations during validation).

6. **Dynamic Version Detection**: Uses `importlib.metadata` to read version from installed package metadata, with fallback to "0.0.0+unknown" if not installed.

7. **Git-Based Change Detection**: The `changed` command uses git to detect uncommitted changes to spec files, files changed vs main branch, and moved requirements (by comparing current location to committed state).

8. **Conflict Entry Handling**: When duplicate requirement IDs are found (e.g., same ID in spec/ and spec/roadmap/), both are kept: the original with its ID, and the duplicate with a `__conflict` suffix. Conflict entries have `is_conflict=True`, `conflict_with` set to original ID, and `implements=[]` (orphaned).

9. **Refines vs Implements Relationships**: Two distinct relationship types with different coverage semantics:
   - **`Refines:`** - Adds detail/additional requirements building on parent. NO coverage rollup.
   - **`Implements:`** - In default mode, REQ→REQ implements is treated like refines (safe defaults for backward compatibility). In strict mode (`strict_mode=True`), claims full satisfaction with coverage rollup.
   - Code→REQ and Test→REQ always use implements/validates semantics with coverage rollup.

10. **Coverage Source Tracking**: `RollupMetrics` tracks where coverage originates via `direct_covered`, `explicit_covered`, `inferred_covered`:
    - `direct`: Test directly validates assertion (high confidence)
    - `explicit`: Child implements specific assertion(s) via `Implements: REQ-xxx-A` (high confidence)
    - `inferred`: Child implements parent REQ, claims all assertions (strict mode only, review recommended)

11. **Multi-Assertion Syntax**: `Implements: REQ-p00001-A-B-C` expands to individual assertion references (`REQ-p00001-A`, `REQ-p00001-B`, `REQ-p00001-C`). Same for `Refines:`.

12. **Sponsor Spec Scanning**: The `validate` command supports `--mode core|combined` to include/exclude sponsor repository specs. Uses `.github/config/sponsors.yml` with local override support via `sponsors.local.yml`.

10. **Optional Dependencies**: Advanced features are available via pip extras:
    - `elspais[trace-view]`: HTML generation with Jinja2
    - `elspais[trace-review]`: Flask-based review server
    - `elspais[all]`: All optional features
    Missing dependencies produce clear installation instructions.

11. **TraceViewRequirement Adapter**: `TraceViewRequirement.from_core()` wraps `core.models.Requirement` with trace-view specific fields (git state, test info, implementation files). Dependency injection rather than global state.

12. **AI-Assisted Reformatting**: The `reformat` module uses Claude CLI (`claude -p --output-format json`) to transform legacy "Acceptance Criteria" format to assertion-based format. Includes format detection, validation, and line break normalization.

13. **Unified Traceability Graph**: The `core/graph.py` module provides a unified DAG structure representing the full traceability graph. `TraceNode` supports multiple parents (DAG), typed content (requirement, assertion, code, test, result, journey), and mutable metrics for accumulation. `TraceGraphBuilder` constructs graphs from requirements with automatic hierarchy linking. Schema-driven via `graph_schema.py` for custom node types and relationships.

14. **Configurable Report Schema**: The `ReportSchema` dataclass defines report content and layout (fields, metrics, filters, sorting). Built-in presets (minimal, standard, full) are available, and custom reports can be defined in `[trace.reports.*]` TOML sections. `RollupMetrics` provides typed storage for accumulated metrics (assertions, coverage, test counts). `MetricsConfig` configures exclusions via `[rules.metrics]`.

14. **Parser Plugin System**: The `parsers/` module provides a `SpecParser` protocol for extracting nodes from various sources. Built-in parsers handle requirements, user journeys, code references (`# Implements:`), test files (REQ-xxx patterns), JUnit XML, and pytest JSON. Custom parsers can be registered via module paths in config.

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
- **One-way traceability** - children reference parents via `Implements:` or `Refines:`, never reverse
- **Refines vs Implements** - Use `Refines:` to add detail without claiming to satisfy parent. Use `Implements:` to claim satisfaction (explicit assertion links recommended: `Implements: REQ-p00001-A-B`)
- **Multi-assertion syntax** - `Implements: REQ-p00001-A-B-C` expands to individual assertion refs
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

Uses `.elspais.toml` with sections: `[project]`, `[directories]`, `[patterns]`, `[rules]`, `[testing]`. See `docs/configuration.md` for full reference.

### Test Scanning Configuration

Enable test scanning in `[testing]` section to link tests to requirements for coverage metrics:

```toml
[testing]
enabled = true
test_dirs = ["tests"]
patterns = ["test_*.py", "*_test.py"]
reference_keyword = "Validates"  # Default keyword for test references
```

Tests reference requirements using `Validates:` syntax in docstrings or comments:

```python
def test_password_hashing():
    """Verify bcrypt is used. Validates: REQ-d00001-A."""
    ...

# Validates: REQ-d00001, REQ-d00001-B
def test_password_storage():
    ...
```

When enabled, `elspais trace --graph` scans test files and links tests to assertions for coverage calculation.

#### Expected Broken Links Marker

Test files that intentionally reference mock requirement IDs can suppress broken link warnings using a file-level marker. The marker suppresses warnings for the **next N references** parsed after it.

**Multi-Language Comment Support:**

| Language | Comment Style | Marker Example |
|----------|--------------|----------------|
| Python, Shell, Ruby, YAML | `#` | `# elspais: expected-broken-links 3` |
| JavaScript, TypeScript, Java, C, Go, Rust | `//` | `// elspais: expected-broken-links 3` |
| SQL, Lua, Ada | `--` | `-- elspais: expected-broken-links 3` |
| HTML, XML | `<!-- -->` | `<!-- elspais: expected-broken-links 3 -->` |
| CSS, C-style block | `/* */` | `/* elspais: expected-broken-links 3 */` |

**Example:**

```python
# elspais: expected-broken-links 2
"""Test file that uses mock requirements for unit testing."""

def test_one():
    # Validates: REQ-mock00001  <- suppressed (count: 2 -> 1)
    pass

def test_two():
    # Validates: REQ-mock00002  <- suppressed (count: 1 -> 0)
    pass

def test_three():
    # Validates: REQ-mock00003  <- NOT suppressed, will produce warning
    pass
```

**Rules:**
- **Marker syntax**: Various comment styles followed by `elspais: expected-broken-links N`
- **Case-insensitive**: `Expected-Broken-Links`, `EXPECTED-BROKEN-LINKS` also work
- **Header area only**: Marker must appear in the first 20 lines of the file
- **Sequential suppression**: Suppresses warnings for the **next N references** parsed after the marker
- **Excess references**: References beyond N are NOT suppressed and will produce warnings
- **Info messages**: Suppressed warnings emit info messages instead of warnings in validation output

### Test Fixtures

`tests/fixtures/` contains example repository structures:

- `hht-like/`: HHT-style requirements (`REQ-p00001`)
- `fda-style/`: Strict hierarchy requirements
- `jira-style/`: Jira-like IDs (`PROJ-123`)
- `named-reqs/`: Named requirements (`REQ-UserAuth`)
- `associated-repo/`: Multi-repo with associated prefixes
- `assertions/`: Assertion-based requirements with `## Assertions` section
- `invalid/`: Invalid cases (circular deps, broken links, missing hashes)

`tests/test_trace_view/` contains trace_view integration tests:

- Tests use `pytest.importorskip()` for optional dependencies (jinja2, flask)
- `test_integration.py`: Import tests, model tests, format detection tests

## Workflow

- **ALWAYS** update the version in `pyproject.toml` before pushing to remote
- **ALWAYS** update `CHANGELOG.md` with new features
- **ALWAYS** use a sub-agent to update the `docs/` files
- **ALWAYS** ensure that `CLAUDE.md` is updated with changes for each commit
- **ALWAYS** run `pytest tests/test_doc_sync.py` before committing doc changes to verify documentation matches implementation

## Master Plan Workflow

**IMPORTANT**: After `/clear` or at the start of a new session, check `MASTER_PLAN.md` for queued issues.

The `MASTER_PLAN.md` file contains a prioritized queue of enhancement issues. Follow this workflow:

1. **Read MASTER_PLAN.md** - Find the first issue with `[ ]` (incomplete) status
2. **Refine the plan** - Use sub-agents to:
   - Explore relevant code files
   - Understand the current implementation
   - Create a detailed implementation plan
3. **Implement** - Write the code and tests
4. **Verify** - Run `pytest` to ensure all tests pass
5. **Mark complete** - Change `[ ]` to `[x]` in MASTER_PLAN.md
6. **Commit** - Create a git commit with `[CUR-514]` prefix
7. **Clear context** - Suggest `/clear` to the user to free context
8. **Resume** - After clear, read MASTER_PLAN.md and continue with next issue

This enables iterative implementation of multiple issues across context boundaries.
