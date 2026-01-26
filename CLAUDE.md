# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

elspais is a zero-dependency Python requirements validation and traceability tool. It validates requirement formats, checks hierarchy relationships, generates traceability matrices, and supports multi-repository requirement management with configurable ID patterns.


**IMPORTANT**: there is only ONE main graph data struct. there is only _ONE_ modular system for CRUD opertions.
**IMPORTANT**: there is ONE config data struct and one modular system for CRUD operations.

1. **Zero Dependencies**: Uses only Python 3.9+ stdlib. Custom TOML parser in `config/loader.py`.

2. **Configurable Patterns**: ID patterns defined via template tokens (`{prefix}`, `{type}`, `{associated}`, `{id}`). The `PatternValidator` builds regex dynamically from config.

3. **Hierarchy Rules**: Requirements have levels (PRD=1, OPS=2, DEV=3). Rules define allowed "implements" relationships (e.g., `dev -> ops, prd`).

4. **Hash-Based Change Detection**: Body content is hashed (SHA-256, 8 chars) for tracking requirement changes.

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

13. **Optional Dependencies**: Advanced features are available via pip extras:
    - `elspais[trace-view]`: HTML generation with Jinja2
    - `elspais[trace-review]`: Flask-based review server
    - `elspais[all]`: All optional features
    Missing dependencies produce clear installation instructions.

14. **AI-Assisted Reformatting**: The `reformat` module uses Claude CLI (`claude -p --output-format json`) to transform legacy "Acceptance Criteria" format to assertion-based format. Includes format detection, validation, and line break normalization.

15. **Unified Traceability Graph**: a unified DAG structure representing the full traceability graph. `GraphNode` supports multiple parents (DAG), typed content (requirement, assertion, code, test, result, journey), and mutable metrics for accumulation. `TraceGraphBuilder` constructs graphs from requirements with automatic hierarchy linking.

16. **Parser Plugin System**: The `parsers/` module provides a `SpecParser` protocol for extracting nodes from various sources. Built-in parsers handle requirements, user journeys, code references (`# Implements:`), test files (REQ-xxx patterns), JUnit XML, and pytest JSON. Custom parsers can be registered via module paths in config.


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
