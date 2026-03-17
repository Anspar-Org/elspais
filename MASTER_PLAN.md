# Master Plan: FederatedGraph — Config and Multi-Repo Federation

**Branch**: claude/cross-cutting-requirements-2Zd0c
**Ticket**: CUR-1082
**Status**: Not Started
**Depends on**: MASTER_PLAN.md (Core Wrapper) must be complete first

**Background**: With `FederatedGraph` established as the sole graph type (MASTER_PLAN.md), this plan adds the `[associates]` config section to `.elspais.toml`, builds separate `TraceGraph` instances per repo with config isolation, wires cross-graph edges, and detects ID conflicts. After this plan, elspais can build a federated graph from multiple repos with proper config isolation.

**Spec**: `docs/superpowers/specs/2026-03-16-federated-graph-design.md`

## Execution Rules

These rules apply to EVERY task below. Do not skip steps. Do not reorder.
If you find yourself writing implementation code without a TASK_FILE and
failing tests, STOP and return to step 1 of the current task.

Read `AGENT_DESIGN_PRINCIPLES.md` before starting the first task.

## Plan

### Task 1: Add `[associates]` section to config loading

Add `get_associates_config(config: dict) -> dict[str, dict]` that reads `[associates.<name>]` sections from `.elspais.toml` with `path` (required, relative to root repo) and `git` (optional, for clone assistance) fields. Returns empty dict if no `[associates]` section. Config type is `dict` (the existing project convention, not a typed class).

**TASK_FILE**: `FEDGRAPH_MP1_TASK_1.md`

- [x] **Baseline**: 2728 passed
- [x] **Create TASK_FILE**: FEDGRAPH_MP1_TASK_1.md
- [x] **Find assertions**: REQ-d00202-A, B, C
- [x] **Create assertions if missing**: Added REQ-d00202 to spec/07-graph-architecture.md
- [x] **Write failing tests**: 4 tests in tests/core/test_associates_config.py
- [x] **Implement**: `get_associates_config()` in `config/__init__.py`
- [x] **Verify**: 2732 passed, lint clean
- [x] **Update docs**: CHANGELOG.md
- [x] **Bump version**: 0.104.28
- [x] **Commit**: done

---

### Task 2: Detect transitive associates (hard error)

When loading an associate's `.elspais.toml`, check if it has an `[associates]` section. If so, raise `FederationError`: "Associate 'X' declares its own associates — only the root repo may declare associates."

**TASK_FILE**: `FEDGRAPH_MP1_TASK_2.md`

- [x] **Baseline**: 2732 passed
- [x] **Create TASK_FILE**: FEDGRAPH_MP1_TASK_2.md
- [x] **Find assertions**: REQ-d00202-D
- [x] **Create assertions if missing**: D already in REQ-d00202
- [x] **Write failing tests**: 2 tests in TestTransitiveAssociateDetection
- [x] **Implement**: `validate_no_transitive_associates()` + `FederationError`
- [x] **Verify**: 2734 passed, lint clean
- [x] **Update docs**: CHANGELOG.md
- [x] **Bump version**: 0.104.29
- [x] **Commit**: done

---

### Task 3: Build per-repo TraceGraphs and construct FederatedGraph

When `[associates]` config is present in `factory.py`, create a separate `GraphBuilder` per repo, each with its own config-derived resolver and reference resolver. Build each repo's `TraceGraph` independently. Create `RepoEntry` per repo. Construct `FederatedGraph` from all entries. Missing associate path: create error-state `RepoEntry` (soft fail by default). Thread `--strict` flag through `build_graph()` to raise on missing associates instead of soft-failing.

Test fixtures: create temp directory structures with two repos (root + associate), each with its own `.elspais.toml` and spec files using `pytest tmp_path`.

**TASK_FILE**: `FEDGRAPH_MP1_TASK_3.md`

- [x] **Baseline**: 2734 passed
- [x] **Create TASK_FILE**: FEDGRAPH_MP1_TASK_3.md
- [x] **Find assertions**: Created REQ-d00203 (A-E)
- [x] **Create assertions if missing**: Added REQ-d00203 to spec
- [x] **Write failing tests**: 5 tests in TestFederationBuild
- [x] **Implement**: Multi-repo build in `factory.py` with `_build_associates` recursion guard
- [x] **Verify**: 2739 passed, lint clean
- [x] **Update docs**: CHANGELOG.md
- [x] **Bump version**: 0.104.30
- [x] **Commit**: done

---

### Task 4: ID conflict detection and cross-graph edge wiring

During `FederatedGraph.__init__()`, detect duplicate IDs across repos when building `_ownership` — raise `FederationError` on conflict. Add `_wire_cross_graph_edges()` method: collect `broken_references()` from each sub-graph, check if target_id exists in another sub-graph's index, if found call `source_graph.add_edge(source_id, target_id, edge_kind, target_graph=target_graph)` and remove the resolved broken reference. After wiring, remaining broken references are genuinely unresolvable.

Test cross-graph wiring: associate has PRD, root has DEV implementing PRD — edge wires, DEV no longer orphaned. Test ID conflict: two repos define same ID — hard error. Test unresolvable reference: stays as broken ref. Test clone on multi-repo FederatedGraph preserves cross-graph edges.

**TASK_FILE**: `FEDGRAPH_MP1_TASK_4.md`

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

- [ ] Move plan: `mv MASTER_PLAN.md ~/archive/2026-03-16/MASTER_PLAN_CUR-1082_FEDGRAPH_CONFIG.md`
- [ ] Move all TASK_FILEs to the same archive directory
- [ ] Promote next queued plan if one exists: `mv MASTER_PLAN2.md MASTER_PLAN.md`
