# FederatedGraph Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace single-graph multi-repo merging with a `FederatedGraph` that wraps per-repo `TraceGraph+Config` pairs, providing config isolation and cross-graph edge wiring.

**Architecture:** `FederatedGraph` wraps `dict[str, RepoEntry]` where each `RepoEntry` pairs a `TraceGraph` with its config. All 37 TraceGraph public methods are explicitly implemented on `FederatedGraph` with documented federation strategies. `TraceGraph` becomes internal to `graph/` package. Cross-graph edges use direct object references wired via `add_edge(target_graph=...)`.

**Tech Stack:** Python 3.10+, existing TraceGraph/GraphBuilder, tomlkit for config.

**Spec:** `docs/superpowers/specs/2026-03-16-federated-graph-design.md`

---

## Chunk 1: Core FederatedGraph Class and Single-Repo Path

This chunk creates the `FederatedGraph` class with all methods, makes `build_graph()` return it, and updates the test helper. After this chunk, the system works identically to today but through the `FederatedGraph` wrapper (federation of one).

### Task 1: Create RepoEntry and FederatedGraph with read-only methods

**Files:**
- Create: `src/elspais/graph/federated.py`
- Test: `tests/core/test_federated.py`

- [ ] **Step 1: Write failing tests for FederatedGraph read-only API**

Test that a `FederatedGraph` wrapping a single `TraceGraph` correctly delegates all read-only methods: `find_by_id`, `iter_roots`, `all_nodes`, `node_count`, `root_count`, `has_root`, `nodes_by_kind`/`iter_by_kind`, `all_connected_nodes`, `orphaned_nodes`, `has_orphans`, `orphan_count`, `broken_references`, `has_broken_references`, `is_reachable_to_requirement`, `iter_unlinked`, `iter_structural_orphans`, `deleted_nodes`, `has_deletions`.

Also test `repo_for(node_id)` and `config_for(node_id)`.

Use the existing `build_graph()` test helper to create a `TraceGraph`, then wrap it in `FederatedGraph`.

```python
from elspais.graph.federated import FederatedGraph, RepoEntry

def test_find_by_id_delegates():
    trace = helpers.build_graph(make_requirement("REQ-p00001"))
    fg = FederatedGraph.from_single(trace, config={}, repo_root=Path("."))
    assert fg.find_by_id("REQ-p00001") is not None
    assert fg.find_by_id("NONEXISTENT") is None

def test_iter_roots_aggregates():
    trace = helpers.build_graph(make_requirement("REQ-p00001"))
    fg = FederatedGraph.from_single(trace, config={}, repo_root=Path("."))
    roots = list(fg.iter_roots())
    assert len(roots) == 1

def test_repo_for_returns_entry():
    trace = helpers.build_graph(make_requirement("REQ-p00001"))
    fg = FederatedGraph.from_single(trace, config={}, repo_root=Path("."))
    entry = fg.repo_for("REQ-p00001")
    assert entry.name == "root"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/core/test_federated.py -v`
Expected: ImportError — `federated` module doesn't exist yet

- [ ] **Step 3: Implement RepoEntry and FederatedGraph with read-only methods**

Create `src/elspais/graph/federated.py` with:
- `RepoEntry` dataclass: `name`, `graph: TraceGraph | None`, `config: dict | None`, `repo_root: Path`, `git_origin: str | None`, `error: str | None`
- `FederatedGraph` class with:
  - `__init__(repos: dict[str, RepoEntry], root_repo: str)`
  - `from_single(graph, config, repo_root)` classmethod — convenience for federation of one
  - `_ownership: dict[str, str]` built from all sub-graph indexes
  - `_repo_for(node_id)` internal lookup returning `RepoEntry`
  - `repo_for(node_id)` and `config_for(node_id)` public API
  - `iter_repos()` yielding `RepoEntry` objects
  - All read-only methods listed above, each with a comment noting its strategy (`# Strategy: by_id`, `# Strategy: aggregate`, etc.)
  - Aggregate methods skip repos with `graph is None`

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/core/test_federated.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```
[CUR-1082] feat: add FederatedGraph with read-only delegation
```

### Task 2: Add mutation methods to FederatedGraph

**Files:**
- Modify: `src/elspais/graph/federated.py`
- Modify: `src/elspais/graph/builder.py` (add `target_graph` param to `add_edge`)
- Test: `tests/core/test_federated.py` (extend)

- [ ] **Step 1: Write failing tests for mutation delegation**

Test all mutation methods through `FederatedGraph`: `rename_node`, `update_title`, `change_status`, `delete_requirement`, `add_requirement` (with target_repo param), `add_assertion`, `delete_assertion`, `update_assertion`, `rename_assertion`, `add_edge`, `delete_edge`, `change_edge_kind`, `change_edge_targets`, `move_node_to_file`, `rename_file`, `fix_broken_reference`.

Test that the federated mutation log records entries with repo name. Test `undo_last()` delegates to correct sub-graph.

```python
def test_rename_node_delegates_and_updates_ownership():
    trace = helpers.build_graph(make_requirement("REQ-p00001"))
    fg = FederatedGraph.from_single(trace, config={}, repo_root=Path("."))
    fg.rename_node("REQ-p00001", "REQ-p00002")
    assert fg.find_by_id("REQ-p00002") is not None
    assert fg.find_by_id("REQ-p00001") is None
    assert fg.repo_for("REQ-p00002").name == "root"

def test_mutation_log_tags_repo():
    trace = helpers.build_graph(make_requirement("REQ-p00001"))
    fg = FederatedGraph.from_single(trace, config={}, repo_root=Path("."))
    fg.update_title("REQ-p00001", "New Title")
    log = fg.mutation_log
    assert len(log) == 1
    assert log[0].repo == "root"

def test_undo_last_delegates_to_subgraph():
    trace = helpers.build_graph(make_requirement("REQ-p00001"))
    fg = FederatedGraph.from_single(trace, config={}, repo_root=Path("."))
    fg.update_title("REQ-p00001", "New Title")
    fg.undo_last()
    node = fg.find_by_id("REQ-p00001")
    assert node.get_field("title") != "New Title"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/core/test_federated.py -v -k mutation`
Expected: AttributeError — mutation methods don't exist yet

- [ ] **Step 3: Add `target_graph` parameter to `TraceGraph.add_edge()`**

In `builder.py`, modify `add_edge` to accept optional `target_graph` parameter. When provided, resolve target from `target_graph._index` instead of `self._index`. All existing behavior unchanged when `target_graph is None`.

- [ ] **Step 4: Implement mutation methods on FederatedGraph**

Each by_id mutation:
1. Look up owning repo via `_ownership`
2. Delegate to sub-graph's method
3. Read the resulting `MutationEntry` from sub-graph's log
4. Tag with `repo=name`, append to federated log
5. Update `_ownership` if IDs changed (rename, add, delete)

Cross-graph mutations (`add_edge`, `delete_edge`, `change_edge_kind`, `change_edge_targets`, `move_node_to_file`):
1. Look up source and target repos
2. If same repo: delegate directly
3. If different repos: use `target_graph` parameter for `add_edge`; for `move_node_to_file`, handle cross-repo move

`add_requirement`: requires `target_repo` parameter (name of repo to add to).

`clone`: deep copy all sub-graphs, then re-wire cross-graph edges.

`undo_last()` / `undo_to()`: read federated log, delegate to correct sub-graph's undo.

`mutation_log` property: return the federated log.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/core/test_federated.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```
[CUR-1082] feat: add mutation methods to FederatedGraph
```

### Task 3: Make `build_graph()` return FederatedGraph

**Files:**
- Modify: `src/elspais/graph/factory.py`
- Modify: `src/elspais/graph/__init__.py` (export FederatedGraph)
- Test: `tests/core/test_factory.py` (verify return type)

- [ ] **Step 1: Write failing test that `build_graph()` returns FederatedGraph**

```python
from elspais.graph.federated import FederatedGraph

def test_build_graph_returns_federated():
    graph = build_graph(config=config, spec_dirs=[spec_dir])
    assert isinstance(graph, FederatedGraph)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_factory.py::test_build_graph_returns_federated -v`
Expected: AssertionError — returns TraceGraph, not FederatedGraph

- [ ] **Step 3: Modify `build_graph()` to wrap result in FederatedGraph**

At the end of `build_graph()` in `factory.py`, wrap the `TraceGraph` in `FederatedGraph.from_single()` with the config and repo_root used during build. Return the `FederatedGraph`.

Update `graph/__init__.py` to export `FederatedGraph` in `__all__` and update the module docstring.

- [ ] **Step 4: Run full test suite**

Run: `pytest`
Expected: Many failures — tests that access `TraceGraph`-specific internals (like `graph._index`) will break. This is expected; the next task fixes them.

- [ ] **Step 5: Commit (even with known test failures)**

```
[CUR-1082] feat: build_graph() returns FederatedGraph
```

### Task 4: Update test helper and fix test suite

**Files:**
- Modify: `tests/core/graph_test_helpers.py`
- Modify: `tests/core/conftest.py`
- Modify: Various test files that access `TraceGraph` internals

- [ ] **Step 1: Update test helper `build_graph()` to return FederatedGraph**

In `tests/core/graph_test_helpers.py`, wrap the `GraphBuilder.build()` result in `FederatedGraph.from_single()`. Update type hints from `TraceGraph` to `FederatedGraph`.

Update `graph_roots_string()` and `graph_node_ids_string()` signatures.

- [ ] **Step 2: Update `wire_file_parent()` helper**

This function accesses `graph._index` directly. Add a method to `FederatedGraph` that provides this capability (e.g., `_register_node(node_id, repo_name)` for test use), or have `wire_file_parent` accept a `TraceGraph` internally via `graph.repo_for(...)`.

- [ ] **Step 3: Fix tests that directly access `_index` or `TraceGraph` internals**

Search for patterns like `graph._index`, `graph._roots`, `graph._orphaned_ids`, `graph._broken_references`, `graph._mutation_log`, `graph.repo_root`, `graph.hash_mode`, `graph.satellite_kinds` in test files. These need to go through `FederatedGraph` public API or use the root repo's sub-graph for internal assertions.

For tests that need internal access (e.g., asserting `_index` contents), provide a `FederatedGraph._root_graph()` escape hatch or access through `repo_for(node_id).graph`.

- [ ] **Step 4: Run full test suite and iterate until green**

Run: `pytest`
Expected: All PASS. This may take several iterations — work through failures one file at a time.

- [ ] **Step 5: Commit**

```
[CUR-1082] refactor: update test suite for FederatedGraph
```

### Task 5: Update consumer type hints (src/)

**Files:**
- Modify: All source files that import or reference `TraceGraph` (see list below)

This is a mechanical find-and-replace task. For each file:
1. Change `from elspais.graph.builder import TraceGraph` to `from elspais.graph.federated import FederatedGraph`
2. Change `TraceGraph` type hints to `FederatedGraph`
3. Change `TYPE_CHECKING` imports similarly

**Files to update (source, not tests):**

Graph module (TYPE_CHECKING imports):
- `src/elspais/graph/analysis.py`
- `src/elspais/graph/annotators.py`
- `src/elspais/graph/link_suggest.py`
- `src/elspais/graph/test_code_linker.py`
- `src/elspais/graph/render.py`
- `src/elspais/graph/serialize.py`

Commands:
- `src/elspais/commands/summary.py`
- `src/elspais/commands/trace.py`
- `src/elspais/commands/index.py`
- `src/elspais/commands/health.py`
- `src/elspais/commands/validate.py`

Server/UI:
- `src/elspais/server/app.py`
- `src/elspais/mcp/server.py`
- `src/elspais/html/generator.py`
- `src/elspais/pdf/assembler.py`

- [ ] **Step 1: Update all imports and type hints**

Mechanical replacement across all listed files.

- [ ] **Step 2: Run full test suite**

Run: `pytest`
Expected: All PASS — behavioral change is zero; only type hints changed.

- [ ] **Step 3: Commit**

```
[CUR-1082] refactor: replace TraceGraph type hints with FederatedGraph across consumers
```

---

## Chunk 2: Configuration and Multi-Repo Federation

This chunk adds `[associates]` config support, builds separate `TraceGraph` per repo, wires cross-graph edges, and detects ID conflicts.

### Task 6: Add `[associates]` section to config loading

**Files:**
- Modify: `src/elspais/config/__init__.py`
- Test: `tests/core/test_config.py` (or appropriate config test file)

- [ ] **Step 1: Write failing tests for associates config loading**

Test that `[associates.<name>]` sections are parsed from `.elspais.toml` with `path` and optional `git` fields. Test that an empty `[associates]` section is valid (no associates). Test that missing `.elspais.toml` path returns empty associates.

```python
def test_load_associates_from_config():
    toml = """
    [associates.core]
    path = "../core"
    git = "git@github.com:org/core.git"

    [associates.module-a]
    path = "../module-a"
    """
    config = load_config_from_string(toml)
    assocs = get_associates_config(config)
    assert len(assocs) == 2
    assert assocs["core"]["path"] == "../core"
    assert assocs["core"]["git"] == "git@github.com:org/core.git"
    assert assocs["module-a"]["path"] == "../module-a"
    assert assocs["module-a"].get("git") is None
```

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Implement associates config loading**

Add a `get_associates_config(config: dict) -> dict[str, dict]` function that reads `config["associates"]` and returns a dict of name -> {path, git}. Returns empty dict if no `[associates]` section exists.

- [ ] **Step 4: Run tests to verify they pass**

- [ ] **Step 5: Commit**

```
[CUR-1082] feat: add [associates] config section parsing
```

### Task 7: Detect transitive associates (hard error)

**Files:**
- Modify: `src/elspais/graph/factory.py` (or new `src/elspais/graph/federation_builder.py`)
- Test: appropriate test file

- [ ] **Step 1: Write failing test**

Test that building a federated graph from a repo whose associate also declares `[associates]` raises a hard error with a clear message.

- [ ] **Step 2: Run test to verify it fails**

- [ ] **Step 3: Implement transitive associate detection**

When loading an associate's `.elspais.toml`, check if it has an `[associates]` section. If so, raise an error: "Associate 'X' declares its own associates — only the root repo may declare associates."

- [ ] **Step 4: Run tests to verify they pass**

- [ ] **Step 5: Commit**

```
[CUR-1082] feat: detect and reject transitive associates
```

### Task 8: Build per-repo TraceGraphs and construct FederatedGraph

**Files:**
- Modify: `src/elspais/graph/factory.py`
- Test: `tests/core/test_federation_build.py` (new)

- [ ] **Step 1: Write failing tests for multi-repo federation build**

Create a temp directory structure with two repos (root + associate), each with its own `.elspais.toml` and spec files. Test that `build_graph()` produces a `FederatedGraph` with two `RepoEntry` objects, each with its own `TraceGraph`.

Test missing associate path produces error-state `RepoEntry` with `graph=None` and `error` message.

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Implement multi-repo build pipeline**

In `factory.py`, when `[associates]` config is present:
1. For each associate, resolve path, load its config, build its `TraceGraph` independently using its own config
2. Build root repo's `TraceGraph` with root config
3. Create `RepoEntry` for each repo
4. Construct `FederatedGraph` from all entries

When associate path is missing, create error-state `RepoEntry`. With `--strict`, raise instead.

- [ ] **Step 4: Run tests to verify they pass**

- [ ] **Step 5: Commit**

```
[CUR-1082] feat: build per-repo TraceGraphs in federated pipeline
```

### Task 9: ID conflict detection and cross-graph edge wiring

**Files:**
- Modify: `src/elspais/graph/federated.py` (add wiring method)
- Test: `tests/core/test_federation_build.py` (extend)

- [ ] **Step 1: Write failing tests for ID conflicts and cross-graph wiring**

Test 1: Two repos with the same requirement ID → hard error.
Test 2: Root repo has a DEV requirement that `Implements: PRD-001` where `PRD-001` is in the associate → after federation, the edge is wired and the DEV requirement is no longer orphaned.
Test 3: Root repo references a non-existent ID not in any repo → stays as broken reference.

```python
def test_id_conflict_raises():
    # Both repos define REQ-p00001
    ...
    with pytest.raises(FederationError, match="ID conflict"):
        build_graph(...)

def test_cross_graph_edge_wired():
    # associate has PRD-001, root has DEV-001 implementing PRD-001
    ...
    fg = build_graph(...)
    dev = fg.find_by_id("DEV-001")
    parents = list(dev.iter_parents(edge_kinds={EdgeKind.IMPLEMENTS}))
    assert any(p.id == "PRD-001" for p in parents)
    assert not fg.has_orphans()  # DEV-001 no longer orphaned
```

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Implement ID conflict detection**

During `FederatedGraph.__init__()`, when building `_ownership`, detect duplicate IDs across repos and raise `FederationError`.

- [ ] **Step 4: Implement cross-graph edge wiring**

Add a `_wire_cross_graph_edges()` method on `FederatedGraph`:
1. Collect `broken_references()` from each sub-graph
2. For each broken ref, check if `target_id` exists in another sub-graph's index
3. If found: call `source_graph.add_edge(source_id, target_id, edge_kind, target_graph=target_graph)`
4. Remove the resolved broken reference from the source graph's list

Call this method at the end of `__init__()` (or from factory after construction).

- [ ] **Step 5: Run tests to verify they pass**

- [ ] **Step 6: Run full test suite**

Run: `pytest`
Expected: All PASS

- [ ] **Step 7: Commit**

```
[CUR-1082] feat: ID conflict detection and cross-graph edge wiring
```

---

## Chunk 3: Remove Legacy Associate System

This chunk removes the `sponsors.yml` / legacy associate handling and replaces all usage with the new `[associates]` config.

### Task 10: Migrate associates.py to new config format

**Files:**
- Modify: `src/elspais/associates.py`
- Modify: `src/elspais/graph/factory.py` (stop calling old associate functions)
- Modify: `src/elspais/commands/health.py` (if it references sponsors directly)
- Test: Update/remove relevant tests

- [ ] **Step 1: Identify all call sites for legacy associate functions**

Grep for `load_associates_config`, `get_associate_spec_directories`, `sponsors`, `SponsorsConfig` across `src/` and `tests/`.

- [ ] **Step 2: Remove or redirect each call site**

The new multi-repo build pipeline (Task 8) replaces `get_associate_spec_directories()`. Remove calls to the old function from `factory.py`. Remove sponsor-specific config from `health.py` and other commands.

- [ ] **Step 3: Clean up associates.py**

Remove legacy YAML loading, `Sponsor`/`SponsorsConfig` aliases, and `sponsors.yml` handling. Keep only what's needed for the new `[associates]` config (or move that into config module).

- [ ] **Step 4: Run full test suite**

Run: `pytest`
Expected: All PASS. Some existing associate/sponsor tests may need updating or removal.

- [ ] **Step 5: Commit**

```
[CUR-1082] refactor: remove legacy sponsors.yml associate system
```

---

## Chunk 4: Health Check Federation

This chunk ensures health checks run per-repo with the correct config.

### Task 11: Per-repo health check delegation

**Files:**
- Modify: `src/elspais/commands/health.py`
- Test: Extend health check tests

- [ ] **Step 1: Write failing test for per-repo health checks**

Create a multi-repo federation where the two repos have different `[rules.hierarchy]` or `[rules.format]` configs. Assert that health checks apply the correct config to each repo's nodes.

- [ ] **Step 2: Run test to verify it fails**

- [ ] **Step 3: Implement per-repo health check dispatch**

Modify health check functions to accept `FederatedGraph` and iterate `fg.iter_repos()`, running config-sensitive checks per-repo with `entry.config`. Merge results.

Cross-repo checks (broken references that span repos) run at the federation level.

- [ ] **Step 4: Run full test suite**

Run: `pytest`
Expected: All PASS

- [ ] **Step 5: Commit**

```
[CUR-1082] feat: per-repo health check delegation with config isolation
```

---

## Chunk 5: MCP Server and Viewer Updates

This chunk updates the MCP server and viewer to work with `FederatedGraph` and expose repo-level information.

### Task 12: MCP server federation support

**Files:**
- Modify: `src/elspais/mcp/server.py`
- Test: Extend MCP tests

- [ ] **Step 1: Update MCP state to hold FederatedGraph**

Replace `_state["graph"]` type from `TraceGraph` to `FederatedGraph`. Replace `_state["config"]` with per-repo config access via `fg.config_for()` / `fg.repo_for()`.

- [ ] **Step 2: Update `get_workspace_info` to include repo federation info**

Expose `iter_repos()` data: repo names, paths, error states, git origins.

- [ ] **Step 3: Update `refresh_graph` to rebuild federation**

When refreshing, rebuild the entire federation (all repos), not just a single graph.

- [ ] **Step 4: Run MCP tests**

Run: `pytest tests/mcp/ -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```
[CUR-1082] feat: MCP server federation support
```

### Task 13: Viewer/server repo staleness info

**Files:**
- Modify: `src/elspais/server/app.py`
- Modify: `src/elspais/mcp/server.py` (repo info endpoint)

- [ ] **Step 1: Add repo info API that includes staleness**

For repos with `git_origin` configured, check if local is behind remote. Include this in the workspace/repo info response. This is informational only.

- [ ] **Step 2: Update Flask app to pass FederatedGraph**

Update `create_app()` signature and internal state to use `FederatedGraph`.

- [ ] **Step 3: Run server tests**

Run: `pytest tests/test_server_app.py -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```
[CUR-1082] feat: viewer repo info with staleness detection
```

---

## Implementation Notes

**Test strategy for multi-repo tests:** Create temporary directory structures with multiple repos, each with their own `.elspais.toml` and spec files. Use `pytest tmp_path` fixture for isolation. The key scenarios to test:

1. Single repo (federation of one) — everything works as before
2. Two repos with cross-references — edges wire correctly
3. Missing associate — error-state RepoEntry, broken refs preserved
4. ID conflict — hard error
5. Transitive associates — hard error
6. Per-repo config isolation — different hierarchy rules applied correctly

**Migration risk mitigation:** Chunk 1 is the highest-risk chunk because it changes the return type of `build_graph()`, affecting 127 files. The `FederatedGraph.from_single()` constructor ensures zero behavioral change for single-repo users. Run the full test suite after every task in Chunk 1.

**Ordering rationale:** Chunk 1 must complete first (changes the foundational type). Chunks 2-5 can be done in order or partially parallelized. Chunk 2 depends on Chunk 1. Chunk 3 depends on Chunk 2. Chunks 4 and 5 depend on Chunk 1 but can proceed in parallel with Chunks 2-3.
