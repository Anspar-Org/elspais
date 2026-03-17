# Master Plan: FederatedGraph — Core Wrapper and Single-Repo Path

**Branch**: claude/cross-cutting-requirements-2Zd0c
**Ticket**: CUR-1082
**Status**: Not Started

**Background**: The current architecture merges all repos into a single `TraceGraph` with one config. Post-parse operations (health checks, validation, render/save) silently apply the root repo's config to all nodes. This plan introduces `FederatedGraph` — a wrapper that pairs each repo's `TraceGraph` with its own config. This first plan establishes the core class, makes `build_graph()` always return `FederatedGraph`, and migrates all consumers. After this plan, the system works identically to today but through the `FederatedGraph` wrapper (federation of one).

**Spec**: `docs/superpowers/specs/2026-03-16-federated-graph-design.md`
**Full plan**: `docs/superpowers/plans/2026-03-16-federated-graph.md`

## Execution Rules

These rules apply to EVERY task below. Do not skip steps. Do not reorder.
If you find yourself writing implementation code without a TASK_FILE and
failing tests, STOP and return to step 1 of the current task.

Read `AGENT_DESIGN_PRINCIPLES.md` before starting the first task.

## Plan

### Task 1: Create RepoEntry and FederatedGraph with read-only methods

Create `src/elspais/graph/federated.py` with `RepoEntry` dataclass and `FederatedGraph` class implementing all read-only TraceGraph methods: `find_by_id`, `iter_roots`, `all_nodes`, `node_count`, `root_count`, `has_root`, `nodes_by_kind`/`iter_by_kind`, `all_connected_nodes`, `orphaned_nodes`, `has_orphans`, `orphan_count`, `broken_references`, `has_broken_references`, `is_reachable_to_requirement`, `iter_unlinked`, `iter_structural_orphans`, `deleted_nodes`, `has_deletions`. Also `repo_for()`, `config_for()`, `iter_repos()`. Include `from_single()` classmethod for federation-of-one. Each method has a strategy comment (`# Strategy: by_id`, `# Strategy: aggregate`). Aggregate methods skip repos with `graph is None`. Include test for error-state repo being skipped.

**TASK_FILE**: `FEDGRAPH_TASK_1.md`

- [x] **Baseline**: confirm tests pass before any changes
- [x] **Create TASK_FILE**: write the task description into it
- [x] **Find assertions**: `discover_requirements("[relevant query]")` — record
      `APPLICABLE_ASSERTIONS: ...` in TASK_FILE
- [x] **Create assertions if missing**: add to appropriate spec file, note in TASK_FILE
- [x] **Write failing tests** (use sub-agent):
  - Test names MUST include assertion IDs (e.g. `test_REQ_p00004_A_validates_hash`)
  - Test classes MUST include `Validates REQ-xxx-Y:` in docstring
  - Confirm tests fail for the right reason (not syntax errors)
  - Append test summary to TASK_FILE
- [x] **Implement**:
  - Use existing code patterns and APIs — search before creating
  - Add `# Implements: REQ-xxx` comments to new/modified source
  - Append implementation summary to TASK_FILE
- [x] **Verify**:
  - All tests pass (no workarounds)
  - Lint clean
  - Append results to TASK_FILE
- [x] **Update docs** (use sub-agent): CHANGELOG.md, docs/cli/, --help text, CLAUDE.md if architectural
- [x] **Bump version** in pyproject.toml
- [x] **Commit** with ticket prefix in subject; append commit summary to TASK_FILE

---

### Task 2: Add mutation methods and `target_graph` parameter

Add `target_graph` parameter to `TraceGraph.add_edge()` (internal API) for cross-graph resolution. Implement all mutation methods on `FederatedGraph`: by_id mutations (`rename_node`, `update_title`, `change_status`, `delete_requirement`, `add_assertion`, `delete_assertion`, `update_assertion`, `rename_assertion`, `rename_file`, `fix_broken_reference`), cross-graph mutations (`add_edge`, `delete_edge`, `change_edge_kind`, `change_edge_targets`, `move_node_to_file`), and special mutations (`add_requirement` with `target_repo` param, `clone` with federation-aware deep copy that rebuilds cross-graph edges). Implement unified mutation log: sub-graph records full entry, federated log records lightweight pointer with repo name. `undo_last()`/`undo_to()` read federated log and delegate to correct sub-graph. Each mutation updates `_ownership` when IDs change.

**TASK_FILE**: `FEDGRAPH_TASK_2.md`

- [x] **Baseline**: confirm tests pass before any changes
- [x] **Create TASK_FILE**: write the task description into it
- [x] **Find assertions**: `discover_requirements("[relevant query]")` — record
      `APPLICABLE_ASSERTIONS: ...` in TASK_FILE
- [x] **Create assertions if missing**: add to appropriate spec file, note in TASK_FILE
- [x] **Write failing tests** (use sub-agent):
  - Test names MUST include assertion IDs (e.g. `test_REQ_p00004_A_validates_hash`)
  - Test classes MUST include `Validates REQ-xxx-Y:` in docstring
  - Confirm tests fail for the right reason (not syntax errors)
  - Append test summary to TASK_FILE
- [x] **Implement**:
  - Use existing code patterns and APIs — search before creating
  - Add `# Implements: REQ-xxx` comments to new/modified source
  - Append implementation summary to TASK_FILE
- [x] **Verify**:
  - All tests pass (no workarounds)
  - Lint clean
  - Append results to TASK_FILE
- [x] **Update docs** (use sub-agent): CHANGELOG.md, docs/cli/, --help text, CLAUDE.md if architectural
- [x] **Bump version** in pyproject.toml
- [x] **Commit** with ticket prefix in subject; append commit summary to TASK_FILE

---

### Task 3: Make `build_graph()` return FederatedGraph and fix all consumers

Modify `build_graph()` in `factory.py` to wrap its result in `FederatedGraph.from_single()`. Export `FederatedGraph` from `graph/__init__.py`. Update the test helper (`tests/core/graph_test_helpers.py`) `build_graph()` to return `FederatedGraph`. For `wire_file_parent()`, access the sub-graph via `graph.repo_for(...).graph` to get `_index` access. For tests that assert on internals (`_index`, `_roots`, `_orphaned_ids`, etc.), access through `repo_for(node_id).graph` — this is the standard escape hatch (not `_root_graph()`). Update all source type hints from `TraceGraph` to `FederatedGraph` across: `graph/analysis.py`, `graph/annotators.py`, `graph/link_suggest.py`, `graph/test_code_linker.py`, `graph/render.py`, `graph/serialize.py`, `commands/summary.py`, `commands/trace.py`, `commands/index.py`, `commands/health.py`, `commands/validate.py`, `server/app.py`, `mcp/server.py`, `html/generator.py`, `pdf/assembler.py`. Tests must be green before committing — do NOT commit with known failures.

**TASK_FILE**: `FEDGRAPH_TASK_3.md`

- [x] **Baseline**: confirm tests pass before any changes
- [x] **Create TASK_FILE**: write the task description into it
- [x] **Find assertions**: existing REQ-d00200 assertions cover this (consumer migration)
- [x] **Create assertions if missing**: N/A — covered by existing assertions
- [x] **Write failing tests** (use sub-agent): N/A — refactoring; verified via existing test suite
- [x] **Implement**:
  - Modified factory.py build_graph() to wrap in FederatedGraph.from_single()
  - Updated 14 source files: type hints TraceGraph -> FederatedGraph
  - Added FederatedGraph.empty() for error fallbacks
  - Exported FederatedGraph from `graph/__init__.py`
  - Fixed 1 test using _orphaned_ids to use public API
- [x] **Verify**:
  - All 2728 tests pass (no workarounds)
  - Lint clean
- [x] **Update docs** (use sub-agent): CHANGELOG.md updated
- [x] **Bump version** in pyproject.toml
- [x] **Commit** with ticket prefix in subject; append commit summary to TASK_FILE

---

### Task 4: Make `render_save()` federation-aware

`render_save()` is a free function in `graph/render.py`, not a TraceGraph method. Update it to accept `FederatedGraph` and iterate `fg.iter_repos()`, calling render per sub-graph with each repo's own `repo_root`. Only sub-graphs with pending mutations get written. Cross-repo references are persisted in the downstream repo's spec files (the repo whose node declares `Implements:`, `Refines:`, etc.).

**TASK_FILE**: `FEDGRAPH_TASK_4.md`

- [ ] **Baseline**: confirm tests pass before any changes
- [ ] **Create TASK_FILE**: write the task description into it
- [ ] **Find assertions**: `discover_requirements("[relevant query]")` — record
      `APPLICABLE_ASSERTIONS: ...` in TASK_FILE
- [ ] **Create assertions if missing**: add to appropriate spec file, note in TASK_FILE
- [ ] **Write failing tests** (use sub-agent):
  - Test names MUST include assertion IDs (e.g. `test_REQ_p00004_A_validates_hash`)
  - Test classes MUST include `Validates REQ-xxx-Y:` in docstring
  - Confirm tests fail for the right reason (not syntax errors)
  - Append test summary to TASK_FILE
- [ ] **Implement**:
  - Use existing code patterns and APIs — search before creating
  - Add `# Implements: REQ-xxx` comments to new/modified source
  - Append implementation summary to TASK_FILE
- [ ] **Verify**:
  - All tests pass (no workarounds)
  - Lint clean
  - Append results to TASK_FILE
- [ ] **Update docs** (use sub-agent): CHANGELOG.md, docs/cli/, --help text, CLAUDE.md if architectural
- [ ] **Bump version** in pyproject.toml
- [ ] **Commit** with ticket prefix in subject; append commit summary to TASK_FILE

---

## Recovery

After `/clear` or context compaction:
1. Read this file (`MASTER_PLAN.md`)
2. Read `AGENT_DESIGN_PRINCIPLES.md`
3. Find the first unchecked box — that is where you resume
4. Read the corresponding TASK_FILE for context on work already done

## Archive

When ALL tasks are complete:

- [ ] Move plan: `mv MASTER_PLAN.md ~/archive/2026-03-16/MASTER_PLAN_CUR-1082_FEDGRAPH_CORE.md`
- [ ] Move all TASK_FILEs to the same archive directory
- [ ] Promote next queued plan if one exists: `mv MASTER_PLAN1.md MASTER_PLAN.md`
