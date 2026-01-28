# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

elspais is a zero-dependency Python requirements validation and traceability tool. It validates requirement formats, checks hierarchy relationships, generates traceability matrices, and supports multi-repository requirement management with configurable ID patterns.


**IMPORTANT**: there is only ONE main graph data struct. there is only _ONE_ modular system for CRUD opertions.
**IMPORTANT**: there is ONE config data struct and one modular system for CRUD operations.
**IMPORTANT**: **DO NOT** change the structure of Graph or GraphTrace or GraphBuilder. Do not violate the current encapsulation.
**IMPORTANT**: **DO NOT** consult git history for context. It will only give you bad ideas.

1. **Zero Dependencies**: Uses only Python 3.9+ stdlib. Custom TOML parser in `config/loader.py`.

2. **Configurable Patterns**: ID patterns defined via template tokens (`{prefix}`, `{type}`, `{associated}`, `{id}`). The `PatternValidator` builds regex dynamically from config.

3. **Hierarchy Rules**: Requirements have levels (PRD=1, OPS=2, DEV=3). Rules define allowed "implements" relationships (e.g., `dev -> ops, prd`).

4. **Hash-Based Change Detection**: Body content is hashed (SHA-256, 8 chars) for tracking requirement changes.

7. **Git-Based Change Detection**: The `changed` command uses git to detect uncommitted changes to spec files, files changed vs main branch, and moved requirements (by comparing current location to committed state).

7b. **Git Repository Root Auto-Detection**: The CLI auto-detects the git repository root and runs as if invoked from there. This means `elspais` works identically from any subdirectory. Use `-v` flag to see "Working from repository root: ...". If not in a git repo, continues silently (warns with `-v`). Implementation: `find_git_root()` in `config/__init__.py`.

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

13. **Optional Dependencies**: Advanced features are available via pip extras:
    - `elspais[trace-view]`: HTML generation with Jinja2
    - `elspais[trace-review]`: Flask-based review server
    - `elspais[all]`: All optional features
    Missing dependencies produce clear installation instructions.

17. **Interactive Trace View** (`trace --view`): Generates rich interactive HTML with Jinja2 templates:
    - **Hierarchical Tree**: Requirements displayed as collapsible tree with expand/collapse
    - **View Modes**: Flat view or hierarchical view toggle
    - **Git Filters**: "Uncommitted" and "Changed vs Main" filters using git detection
    - **Content Filters**: Leaf only, include deprecated, include roadmap, show code refs
    - **Column Filters**: Text search for ID/title, dropdowns for level/status/coverage/topic
    - **Coverage Indicators**: ○ (none), ◐ (partial), ● (full) based on CODE node references
    - **Assertion Letters**: `[A][B]` badges show which parent assertions a child implements
    - **Change Indicator**: ◆ diamond shows nodes changed vs main branch
    - **Lightning Bolt**: ⚡ indicates test failures from TEST_RESULT nodes
    - **Legend Modal**: Explains all icons and indicators
    - **DAG as Tree**: Nodes can appear under multiple parents for complete traceability
    - **User Journeys Tab**: Separate tab with rich journey cards showing Actor/Goal metadata, searchable

18. **NodeKind.REMAINDER**: Unclaimed file content (not requirements). Previously named TODO, renamed for clarity.

19. **File-Based Documentation** (`elspais docs [topic]`): User documentation loaded from `docs/cli/*.md` files:
    - **Single Source of Truth**: Markdown files in `docs/cli/` are the canonical docs
    - **Markdown Renderer**: `utilities/md_renderer.py` converts markdown to ANSI terminal output
    - **Docs Loader**: `utilities/docs_loader.py` locates and loads topic files
    - **Topics**: quickstart, format, hierarchy, assertions, traceability, validation, git, config
    - **Package Inclusion**: `docs/cli/` bundled in wheel via `pyproject.toml` force-include
    - **TTY Detection**: Colors enabled for terminals, `--plain` for piped output

14. **Unified Traceability Graph**: a unified DAG structure representing the full traceability graph. `GraphNode` supports multiple parents (DAG), typed content (requirement, assertion, code, test, result, journey), and mutable metrics for accumulation. `TraceGraphBuilder` constructs graphs from requirements with automatic hierarchy linking.

15. **Parser Plugin System**: The `parsers/` module provides a `SpecParser` protocol for extracting nodes from various sources. Built-in parsers handle requirements, user journeys, code references (`# Implements:`), test files (REQ-xxx patterns), JUnit XML, and pytest JSON. Custom parsers can be registered via module paths in config.

16. **Iterator-Only Graph API**: The graph uses an iterator-only API to prevent accidental list materialization:
    - **GraphNode**: Use `iter_children()`, `iter_parents()`, `iter_outgoing_edges()`, `iter_incoming_edges()` for traversal. Use `child_count()`, `parent_count()`, `has_child()`, `has_parent()`, `is_root`, `is_leaf` for checks. Use `get_field()`, `set_field()`, `get_metric()`, `set_metric()` for content/metrics. Convenience properties: `level`, `status`, `hash`.
    - **TraceGraph**: Use `iter_roots()` for traversal. Use `root_count()`, `has_root()` for checks. Internal storage uses `_roots`, `_index` prefixed attributes.
    - **UUID for GUI**: Each node has a stable `uuid` (32-char hex) for DOM IDs and API endpoints.


**Multi-Language Comment Support:**

| Language | Comment Style | Marker Example |
|----------|--------------|----------------|
| Python, Shell, Ruby, YAML | `#` | `# elspais: expected-broken-links 3` |
| JavaScript, TypeScript, Java, C, Go, Rust | `//` | `// elspais: expected-broken-links 3` |
| SQL, Lua, Ada | `--` | `-- elspais: expected-broken-links 3` |
| HTML, XML | `<!-- -->` | `<!-- elspais: expected-broken-links 3 -->` |
| CSS, C-style block | `/* */` | `/* elspais: expected-broken-links 3 */` |

## Workflow

- **ALWAYS** update the version in `pyproject.toml` before pushing to remote
- **ALWAYS** update `CHANGELOG.md` with new features
- **ALWAYS** use a sub-agent to update the `docs/` files and --help cli commands
- **ALWAYS** ensure that `CLAUDE.md` is updated with changes for each commit
- **ALWAYS** run `pytest tests/test_doc_sync.py` before committing doc changes to verify documentation matches implementation

## Master Plan Workflow

**IMPORTANT**: After `/clear` or at the start of a new session, check `MASTER_PLAN.md` for queued issues.

The `MASTER_PLAN.md` file contains a prioritized queue of enhancement issues. Follow this workflow:

1. **Read MASTER_PLAN.md** - Find the first phase with `[ ]` (incomplete) status
2. **Refine the plan** - Use sub-agents to:
   - Explore relevant code files
   - Understand the current implementation
   - Create a detailed implementation plan
3. **Implement** - Write the code and tests
4. **Verify** - Run `pytest` to ensure all tests pass
5. **Mark complete** - Change `[ ]` to `[x]` in MASTER_PLAN.md
6. **Commit after each phase** - Create a git commit with `[CUR-514]` prefix immediately after completing each phase. Do not batch multiple phases into one commit.
7. **Clear context** - Suggest `/clear` to the user to free context
8. **Resume** - After clear, read MASTER_PLAN.md and continue with next phase

**Commit Discipline**: Each phase should result in exactly one commit. This ensures:
- Atomic, reviewable changes
- Easy rollback if issues arise
- Clear progress tracking in git history

This enables iterative implementation of multiple phases across context boundaries.
