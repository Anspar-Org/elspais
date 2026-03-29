# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**Also read**: `AGENT_DESIGN_PRINCIPLES.md` for architectural directives and mandatory practices.

## Overview

elspais is a minimal-dependency Python requirements validation and traceability tool. It validates requirement formats, checks hierarchy relationships, generates traceability matrices, and supports multi-repository requirement management with configurable ID patterns.

## Full documentation

Full specifications are contained in spec/ and docs/. Don't read more than is necessary for the task.

**IMPORTANT**: there is only ONE main graph data struct. there is only _ONE_ modular system for CRUD opertions.
**IMPORTANT**: **DO NOT** change the structure of Graph or GraphTrace or GraphBuilder. Do not violate the current encapsulation.
**No Duplicate Library Functions**: Do NOT create duplicate implementations of core functionality across modules:
- Hierarchy traversal: only in TraceGraph (roots, children, parents, find_by_id)
- Coverage calculation: only in GraphBuilder (computed during build)
- Requirement loading: only in core/loader.py (create_parser, parse_requirements_from_directories)
- Git state detection: only in core/git.py (get_git_changes, GitChangeInfo)
- Pattern validation: only in core/patterns.py (PatternValidator)
- Hash computation: only in `utilities/hasher.py` (`compute_normalized_hash`, `calculate_hash`). Do NOT create alternative hash functions elsewhere.
- Do NOT create hierarchy.py files in multiple locations

**Minimal Dependencies**: Core requires `tomlkit` (pure Python TOML library), `pydantic>=2.0` (config schema validation), and `tyro>=0.9` (CLI generation). Uses Python 3.10+ stdlib for everything else.
**Hierarchy Rules**: Requirements have levels defined in `[levels]` (e.g., prd rank=1, ops rank=2, dev rank=3). Each level declares its `implements` list (e.g., `dev.implements = ["dev", "ops", "prd"]`).
**Hash-Based Change Detection**: Body content is hashed (SHA-256, 8 chars) for tracking requirement changes. Centralized in `utilities/hasher.py`.
**Configuration System** (`config/__init__.py`, `config/schema.py`) almost all parsible content is configurable. `load_config()` returns a plain `dict[str, Any]`; defaults come from the `ElspaisConfig` Pydantic model via `config_defaults()`. Config version is 3. Top-level fields: `project`, `levels`, `id_patterns` (alias `id-patterns`), `scanning`, `rules`, `keywords`, `validation`, `changelog`, `output`, `associates`. There is no `ConfigLoader` class or `DEFAULT_CONFIG` dict.
**Format Validation** (`validation/format.py`)
**Git-Based Change Detection**: The `changed` command uses git to detect uncommitted changes to spec files.
**Git Repository Root Auto-Detection**: The CLI auto-detects the git repository root and runs as if invoked from there. This means `elspais` works identically from any subdirectory. Use `-v` flag to see "Working from repository root: ...". If not in a git repo, continues silently (warns with `-v`). Implementation: `find_git_root()` in `config/__init__.py`.
**No Canonical Root**: Associate paths resolve from `repo_root` (git root or CWD). There is no special worktree handling. If working in a git worktree with relative associate paths, use absolute paths in `.elspais.local.toml`. The `find_canonical_root()` function exists but is not used by the main code paths.
**Coverage Source Tracking**: `RollupMetrics` tracks where coverage originates via `direct_covered`, `explicit_covered`, `inferred_covered`:
**Multi-Assertion Syntax**: `Implements: REQ-p00001-A+B+C` expands to individual assertion references (`REQ-p00001-A`, `REQ-p00001-B`, `REQ-p00001-C`). Same for `Refines:`. The separator (`+` by default) is configured via `multi_separator` in `[id-patterns.assertions]`.
**Satisfies Relationship**: `Satisfies:` metadata declares compliance with a template requirement (e.g., a cross-cutting PRD). When a requirement declares `Satisfies: X`, the graph builder clones the template's REQ subtree with composite IDs (`declaring_id::original_id`), creating INSTANCE nodes. A `Stereotype` enum (`CONCRETE`, `TEMPLATE`, `INSTANCE`) classifies nodes, and `EdgeKind.INSTANCE` connects each clone to its original. Coverage uses the standard mechanism on cloned nodes. File-based attribution redirects `Implements:` refs targeting template assertions to the correct instance by finding a sibling concrete ref in the same source file. Template hash changes flag declaring requirements for review. DEFINES edges connect the declaring requirement's FILE node to each INSTANCE node (virtual provenance). INSTANCE nodes have no CONTAINS edges. `file_node()` returns None for INSTANCE nodes; navigate via INSTANCE edge to the original node to find the source file.
**Associated Spec Scanning**: Multi-repo federation is configured via `[associates.<name>]` sections in `.elspais.toml`, each with `path` and `namespace` fields. The legacy `sponsors.yml`/`sponsors.local.yml` YAML system has been removed. Use `build_graph()` which automatically builds per-repo TraceGraphs when `[associates]` config is present.
**Optional Dependencies**: Advanced features are available via pip extras:

- `elspais[trace-view]`: HTML generation with Jinja2
- `elspais[trace-review]`: Flask-based review server
- `elspais[all]`: All optional features
- Missing dependencies produce clear installation instructions.
**NodeKind.FILE**: Represents a source file as a first-class graph node. ID format: `file:<repo-relative-path>`. Content fields include `file_type` (FileType enum), `absolute_path`, `relative_path`, `repo`, `git_branch`, `git_commit`.
**FileType Enum**: Classifies source files by domain role: `SPEC`, `JOURNEY`, `CODE`, `TEST`, `RESULT`. Lives in `graph/GraphNode.py` alongside `NodeKind`.
**NodeKind.REMAINDER**: Unclaimed file content (not requirements).
**File Path Access Pattern**: File paths are accessed via `node.file_node().get_field("relative_path")`. Line numbers via `node.get_field("parse_line")`. The `SourceLocation` class and `GraphNode.source` field have been removed. `file_node()` returns None for INSTANCE nodes and unlinked nodes -- always check for None.
**FILE Node Build Pipeline**: `factory.py` creates FILE nodes (`file:<repo-relative-path>`) for every scanned file before parsing. `GraphBuilder` receives FILE nodes and wires CONTAINS edges to top-level content nodes (REQUIREMENT, USER_JOURNEY, CODE, TEST, file-level REMAINDER). CONTAINS edge metadata: `start_line`, `end_line`, `render_order` (float, sequential from 0.0). ASSERTIONs and requirement-level REMAINDER sections are reached via STRUCTURES from their parent REQUIREMENT, not CONTAINS from FILE. RemainderParser is mandatory for SPEC/JOURNEY/CODE/TEST files but NOT for RESULT files. `git_branch` and `git_commit` are captured once per repo.
**File-Based Documentation** (`elspais docs [topic]`): User documentation loaded from `docs/cli/*.md` files:
- **Single Source of Truth**: Markdown files in `docs/cli/` are the canonical docs
**Edge Kind Classification** (`graph/builder.py`): `_STRUCTURAL_EDGE_KINDS` (CONTAINS, STRUCTURES) represent physical file structure; `_TRACEABILITY_EDGE_KINDS` (IMPLEMENTS, REFINES, SATISFIES, VERIFIES, VALIDATES, INSTANCE, DEFINES) represent requirement traceability. IMPLEMENTS: code → assertion (direct satisfaction). REFINES: requirement → requirement/assertion only (adds detail, splits assertions; cumulative; NOT valid in code/test files). VERIFIES: produces pass/fail output (test → assertion, or code that generates results). VALIDATES: JNY → REQ/assertion (UAT coverage). Keyword validity: test files accept only `Verifies`; code files accept `Implements` and `Verifies`; spec files accept `Implements`, `Refines`, and `Satisfies`; journey files accept `Validates`. Used by reachability queries (`is_reachable_to_requirement()`) and health checks to distinguish structural orphans from unlinked nodes.
**Unified Traceability Graph**: a unified DAG structure representing the full traceability graph. `GraphNode` supports multiple parents (DAG), typed content (requirement, assertion, code, test, result, journey), and mutable metrics for accumulation. `TraceGraphBuilder` constructs graphs from requirements with automatic hierarchy linking.
**Test Pre-Scan Strategy**: Python test files use `ast.parse()` for 100% accurate class/function context (immune to multiline strings). Non-Python files use text-based indent tracking. An external command can be configured via `[scanning.test].prescan_command` for any language -- it receives file paths on stdin and outputs JSON `[{file, function, class, line}]` on stdout.
**Parser Plugin System**: The `parsers/` module provides a `SpecParser` protocol for extracting nodes from various sources. Built-in parsers handle requirements, user journeys, code references (`# Implements:`), test files (REQ-xxx patterns), JUnit XML, and pytest JSON. Custom parsers can be registered via module paths in config.
**Iterator-Only Graph API**: The graph uses an iterator-only API to prevent accidental list materialization:
  - **GraphNode**: Use `iter_children()`, `iter_parents()`, `iter_outgoing_edges()`, `iter_incoming_edges()` for traversal. These accept optional `edge_kinds` parameter for filtered traversal (e.g., `iter_children(edge_kinds={EdgeKind.STRUCTURES})`). Use `walk(edge_kinds=...)` and `ancestors(edge_kinds=...)` for filtered recursive traversal. Use `child_count()`, `parent_count()`, `has_child()`, `has_parent()`, `is_root`, `is_leaf` for checks. Use `get_field()`, `set_field()`, `get_metric()`, `set_metric()` for content/metrics. Convenience properties: `level`, `status`, `hash`. Use `set_id()` for ID mutations. Use `file_node()` to find nearest FILE ancestor (returns None if not found). Use `link(child, EdgeKind)` for all relationships and `unlink(child)` to sever. **DO NOT** use `add_child()` or `remove_child()` -- they no longer exist.
  - **TraceGraph**: Use `iter_roots()` for traversal (accepts optional `NodeKind` filter: `iter_roots(NodeKind.FILE)` for FILE nodes, `iter_roots(NodeKind.REQUIREMENT)` for REQ roots only; default returns REQ+JOURNEY roots excluding FILE). Use `iter_by_kind(kind)` for general kind-based index queries. Use `root_count()`, `has_root()` for checks. Internal storage uses `_roots`, `_index` prefixed attributes. Use `is_reachable_to_requirement(node)` to check if a node can reach a REQUIREMENT ancestor via traceability edges. Use `iter_unlinked(kind?)` to iterate CODE/TEST nodes not linked to any requirement. Use `iter_structural_orphans()` to iterate nodes without a FILE ancestor.
  - **UUID for GUI**: Each node has a stable `uuid` (32-char hex) for DOM IDs and API endpoints.
**Graph Analysis** (`graph/analysis.py`): Read-only analytical functions that rank requirements by foundational importance. Computes PageRank centrality, fan-in branch count, and uncovered dependents. Does not modify the graph.
**Render Protocol & Save** (`graph/render.py`): Each NodeKind has a `render_node()` function that produces its text representation. `render_file()` walks a FILE node's CONTAINS children sorted by `render_order` and concatenates their output to produce file content. REQUIREMENT renders full block (header, metadata, body, assertions, sections, `*End*` marker with hash). REMAINDER renders raw text verbatim. USER_JOURNEY renders stored body. CODE/TEST render stored `raw_text`. ASSERTION and RESULT raise `ValueError` (rendered by parent or read-only). `compute_requirement_hash()` uses order-independent assertion hashing (sort individual hashes before combining). `render_save()` persists dirty FILE nodes to disk — it identifies files with pending mutations, renders their content, and writes to disk. Implements/Refines references are derived from live graph edges. Supports optional consistency check (rebuild + compare) via `consistency_check=True` with a `rebuild_fn` callback. `persistence.py` is deleted; all save operations use `render_save()`.
**Node Mutation API**: TraceGraph provides mutation methods with full undo support
**Assertion Mutation API**: TraceGraph provides assertion-specific mutations
**Edge Mutation API**: TraceGraph provides edge (relationship) mutations: `mutate_add_edge()`, `mutate_delete_edge()`, `mutate_change_edge_kind()`, `change_edge_targets(source_id, target_id, assertion_targets)` (modifies assertion targets on IMPLEMENTS/REFINES edges without delete+add)
**File Mutation API**: TraceGraph provides file-level mutations: `move_node_to_file(node_id, target_file_id)` (re-wires CONTAINS edge), `rename_file(file_id, new_relative_path)` (updates ID, index, paths; render_save handles disk rename). Both support full undo.
**MCP Tools** (`elspais[mcp]`): The MCP server provides tools to explore and manipulate the graph for a system. Includes `get_subtree()` for scoped subgraph extraction (markdown/flat/nested formats), a cursor protocol (`open_cursor`/`cursor_next`/`cursor_info`) for incremental iteration over any read query, multi-term search with relevance scoring (`search()`, `scoped_search()`, `discover_requirements()`), and `get_unlinked_nodes(kind?)` to list CODE/TEST nodes not linked to any requirement.
**Multi-Term Search** (`mcp/search.py`): Query parser and scorer engine supporting AND/OR operators, parenthesized grouping, quoted phrases, `-exclusion`, `=exact` keyword matching, and field-weighted relevance scoring (ID=100, title=50, keyword-exact=40, keyword-substring=25, body=10). Used by MCP search tools, Flask `/api/search`, and the GUI tree filter.
**Comment/Review System**: An annotation layer stored as append-only JSONL files in `.elspais/comments/`. `CommentEvent` (frozen dataclass) represents comment/reply/resolve/promote events; `CommentThread` groups a root comment with its replies. `CommentIndex` (in-memory) provides iterator-only query API. `TraceGraph` delegates to `_comment_index` via public methods (`iter_comments`, `comment_count`, `has_comments`, `iter_orphaned_comments`, `find_comment_thread`, `remove_comment_thread`, `iter_comments_for_card`, `add_comment_thread`, `comment_source_file`). `FederatedGraph` routes comment queries to the owning repo using anchor-based ownership lookup (`parse_anchor()` extracts node_id). `FederatedGraph.load_comments()` loads per-repo indexes at viewer startup/refresh. Comment storage: only in `graph/comment_store.py` (parse_anchor, generate_comment_id, append_event, load_events, assemble_threads, load_comment_index, comment_file_for, validate_anchor, promote_orphaned_comments, update_anchors_on_rename, compact_file). Comment data models: only in `graph/comments.py`. Rename hooks in `TraceGraph.rename_node()`/`rename_assertion()` call `update_anchors_on_rename()` automatically. API endpoints: POST `/api/comment/add`, `/api/comment/reply`, `/api/comment/resolve`; GET `/api/comments`, `/api/comments/card`, `/api/comments/orphaned`. Author resolved server-side via `get_author_info()`. CLI: `elspais comments compact` strips resolved threads and collapses promote chains.
**Multi-Language Comment Support:**

| Language | Comment Style | Marker Example |
|----------|--------------|----------------|
| Python, Shell, Ruby, YAML | `#` | `# elspais: expected-broken-links 3` |
| JavaScript, TypeScript, Java, C, Go, Rust | `//` | `// elspais: expected-broken-links 3` |
| SQL, Lua, Ada | `--` | `-- elspais: expected-broken-links 3` |
| HTML, XML | `<!-- -->` | `<!-- elspais: expected-broken-links 3 -->` |
| CSS, C-style block | `/* */` | `/* elspais: expected-broken-links 3 */` |

## Workflow

**See `TASK_PROTOCOL.md`** for the complete workflow checklist including documentation steps.

- **ALWAYS** use a sub-agent to write tests (unless you are the sub-agent)
- **ALWAYS** update user-facing surfaces when adding/modifying CLI features: `docs/cli/*.md`, `docs/configuration.md`, `src/elspais/commands/init.py` templates, CLI help/epilog text, and shell completion

## Testing

**Test tiers** (configured in `pyproject.toml`):

- `pytest` — runs unit/integration tests only (~26s). This is the default during development.
- `pytest -m e2e` — runs e2e subprocess tests only (~143s). CLI commands, MCP protocol, CI workflows.
- `pytest -m "e2e or browser"` — runs all slow tests.
- `pytest -m ""` — runs everything (unit + e2e + browser, ~182s). **Run before `git push`.**

**Marking tests**: Use `@pytest.mark.e2e` on tests that spawn external processes (elspais CLI, claude CLI, act, MCP subprocess). Use `@pytest.mark.browser` on Playwright tests.
**Claude Code caveat**: The `test_e2e_install_and_uninstall` test (claude MCP install) is auto-skipped inside Claude Code sessions (`CLAUDECODE=1`) because the claude CLI hijacks pytest's file descriptors.

### Test-Writing Conventions

**Prefer the canonical graph**: Use the `canonical_graph` session fixture for read-only assertions instead of building ad-hoc graphs with `build_graph()` or `make_requirement()`. Use `canonical_federated_graph` when you need the FederatedGraph (e.g., trace rendering). Only create custom graphs when testing features not in the hht-like fixture (invalid inputs, specific config variations).

**Use incremental classes for mutation tests**: Mark with `@pytest.mark.incremental`, use the `mutable_graph` fixture. Assert after each mutation step. The fixture undoes all mutations on teardown via the undo log — no disk I/O for reset.

**No tautology tests**: Don't assert constants, factory return values, or type-system guarantees. Tests must exercise behavior — if the test can't fail due to a code change, it's not testing anything.

**Parametrize variants, don't duplicate**: If testing the same behavior across formats/configs, use `@pytest.mark.parametrize` with the shared fixture. Don't write separate test methods for each format.

**E2E fixture structure**: E2E tests are organized into 6 shared fixture files (test_e2e_global, test_e2e_standard, test_e2e_fda_numeric, test_e2e_named_custom, test_e2e_jira_edge, test_e2e_associated) plus test_e2e_special for unique setups. Each fixture builds one project with a daemon, and tests run sequentially against it. When adding new e2e tests, add them to the appropriate fixture file rather than creating a new file with its own project setup. Config dimensions (ID patterns, assertion labels, hierarchy rules) are crossed efficiently across fixtures.

**E2E: reuse MCP servers**: The `mcp` fixture in `test_mcp_e2e.py` is module-scoped. Don't start a new server per test class unless the project config differs.

## Master Plan Workflow

**IMPORTANT**: After `/clear` or at the start of a new session, check `MASTER_PLAN.md` for queued issues.

**Commit Discipline**: Each phase should result in exactly one commit. This ensures:

- Atomic, reviewable changes
- Easy rollback if issues arise
- Clear progress tracking in git history

This enables iterative implementation of multiple phases across context boundaries.
