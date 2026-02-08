# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**Also read**: `AGENT_DESIGN_PRINCIPLES.md` for architectural directives and mandatory practices.

## Overview

elspais is a minimal-dependency Python requirements validation and traceability tool. It validates requirement formats, checks hierarchy relationships, generates traceability matrices, and supports multi-repository requirement management with configurable ID patterns.

## Full documentation

Full specifications are contained in spec/ and docs/. Don't read more than is necessary for the task.

**IMPORTANT**: there is only ONE main graph data struct. there is only _ONE_ modular system for CRUD opertions.
**IMPORTANT**: **DO NOT** change the structure of Graph or GraphTrace or GraphBuilder. Do not violate the current encapsulation.

**Minimal Dependencies**: Core requires only `tomlkit` (pure Python TOML library). Uses Python 3.9+ stdlib for everything else.
**Hierarchy Rules**: Requirements have levels (PRD=1, OPS=2, DEV=3). Rules define allowed "implements" relationships (e.g., `dev -> ops, prd`).
**Hash-Based Change Detection**: Body content is hashed (SHA-256, 8 chars) for tracking requirement changes. Centralized in `utilities/hasher.py`.
**Configuration System** (`config/__init__.py`) almost all parsible content is configurable.
**Format Validation** (`validation/format.py`)
**Git-Based Change Detection**: The `changed` command uses git to detect uncommitted changes to spec files.
**Git Repository Root Auto-Detection**: The CLI auto-detects the git repository root and runs as if invoked from there. This means `elspais` works identically from any subdirectory. Use `-v` flag to see "Working from repository root: ...". If not in a git repo, continues silently (warns with `-v`). Implementation: `find_git_root()` in `config/__init__.py`.
**Coverage Source Tracking**: `RollupMetrics` tracks where coverage originates via `direct_covered`, `explicit_covered`, `inferred_covered`:
**Multi-Assertion Syntax**: `Implements: REQ-p00001-A-B-C` expands to individual assertion references (`REQ-p00001-A`, `REQ-p00001-B`, `REQ-p00001-C`). Same for `Refines:`.
**Associated Spec Scanning**: The `validate` command supports `--mode core|combined` to include/exclude associated repository specs. Uses `.github/config/sponsors.yml` with local override support via `sponsors.local.yml`.
**Optional Dependencies**: Advanced features are available via pip extras:

- `elspais[trace-view]`: HTML generation with Jinja2
- `elspais[trace-review]`: Flask-based review server
- `elspais[all]`: All optional features
- Missing dependencies produce clear installation instructions.
**NodeKind.REMAINDER**: Unclaimed file content (not requirements).
**File-Based Documentation** (`elspais docs [topic]`): User documentation loaded from `docs/cli/*.md` files:
- **Single Source of Truth**: Markdown files in `docs/cli/` are the canonical docs
**Unified Traceability Graph**: a unified DAG structure representing the full traceability graph. `GraphNode` supports multiple parents (DAG), typed content (requirement, assertion, code, test, result, journey), and mutable metrics for accumulation. `TraceGraphBuilder` constructs graphs from requirements with automatic hierarchy linking.
**Parser Plugin System**: The `parsers/` module provides a `SpecParser` protocol for extracting nodes from various sources. Built-in parsers handle requirements, user journeys, code references (`# Implements:`), test files (REQ-xxx patterns), JUnit XML, and pytest JSON. Custom parsers can be registered via module paths in config.
**Iterator-Only Graph API**: The graph uses an iterator-only API to prevent accidental list materialization:
  - **GraphNode**: Use `iter_children()`, `iter_parents()`, `iter_outgoing_edges()`, `iter_incoming_edges()` for traversal. Use `child_count()`, `parent_count()`, `has_child()`, `has_parent()`, `is_root`, `is_leaf` for checks. Use `get_field()`, `set_field()`, `get_metric()`, `set_metric()` for content/metrics. Convenience properties: `level`, `status`, `hash`. Use `set_id()` for ID mutations.
  - **TraceGraph**: Use `iter_roots()` for traversal. Use `root_count()`, `has_root()` for checks. Internal storage uses `_roots`, `_index` prefixed attributes.
  - **UUID for GUI**: Each node has a stable `uuid` (32-char hex) for DOM IDs and API endpoints.
**Node Mutation API**: TraceGraph provides mutation methods with full undo support
**Assertion Mutation API**: TraceGraph provides assertion-specific mutations
**Edge Mutation API**: TraceGraph provides edge (relationship) mutations
**MCP Tools** (`elspais[mcp]`): The MCP server provides tools to explore and manipulate the graph for a system
**Unified References Configuration** (`[references]`): Configurable reference parsing for all parser types

**Multi-Language Comment Support:**

| Language | Comment Style | Marker Example |
|----------|--------------|----------------|
| Python, Shell, Ruby, YAML | `#` | `# elspais: expected-broken-links 3` |
| JavaScript, TypeScript, Java, C, Go, Rust | `//` | `// elspais: expected-broken-links 3` |
| SQL, Lua, Ada | `--` | `-- elspais: expected-broken-links 3` |
| HTML, XML | `<!-- -->` | `<!-- elspais: expected-broken-links 3 -->` |
| CSS, C-style block | `/* */` | `/* elspais: expected-broken-links 3 */` |

## Workflow

**See `WORKFLOW_STATE.md`** for the complete workflow checklist including documentation steps.

- **ALWAYS** use a sub-agent to write tests
- **ALWAYS** include assertion references in test names (e.g., `test_REQ_p00001_A_validates_input`) so TEST_RESULT nodes automatically link to requirements in the traceability graph

## Master Plan Workflow

**IMPORTANT**: After `/clear` or at the start of a new session, check `WORKFLOW_STATE.md` for queued issues.

**Commit Discipline**: Each phase should result in exactly one commit. This ensures:

- Atomic, reviewable changes
- Easy rollback if issues arise
- Clear progress tracking in git history

This enables iterative implementation of multiple phases across context boundaries.
