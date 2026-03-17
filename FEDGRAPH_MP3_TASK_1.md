# Task 1: MCP Server Federation Support

**Ticket**: CUR-1082
**Branch**: claude/cross-cutting-requirements-2Zd0c
**Baseline**: 2765 passed

## Objective

Update MCP server to leverage FederatedGraph's per-repo config access. Replace global
`_state["config"]` usage with per-repo config where appropriate. Expose federation info
in workspace queries.

## APPLICABLE_ASSERTIONS

- REQ-o00061-A: get_workspace_info returns repo path, project name, config summary
- REQ-o00061-D: Config from unified config system
- REQ-d00200-G: repo_for/config_for per-repo access
- REQ-d00205-A: workspace info includes federation details (repos, paths, errors, git origins)
- REQ-d00205-B: refresh\_graph syncs state config with root repo config
- REQ-d00205-C: node-specific ops use graph.config_for() not global config
- REQ-d00205-D: global ops continue using root repo config

## Scope

### 1. get_workspace_info federation info

Add federation details to workspace info: repo names, paths, error states, git origins
via `graph.iter_repos()`. Available in relevant detail profiles.

### 2. refresh_graph config sync

After rebuilding the graph, sync `_state["config"]` from the federation's root repo
config to prevent config staleness.

### 3. Per-repo config for mutation tools

- `_normalize_assertion_targets()`: use `graph.config_for(target_id)` instead of global config
- `_mutate_add_edge()`: derive config from graph rather than `_state["config"]`

### 4. Config access pattern

Keep `_state["config"]` as root repo config for global operations (workspace info,
agent instructions, project summary). Use `graph.config_for()` for node-specific operations.

## Progress

- [x] Baseline: 2765 passed
- [x] Create TASK_FILE: this file
- [x] Find/create assertions: REQ-d00205-A..D in spec/08-mcp-server.md
- [x] Write failing tests: 5 tests in tests/mcp/test_mcp_federation.py
- [x] Implement: workspace federation info, refresh config sync, per-repo config derivation
- [x] Verify: 2770 passed (5 new), doc sync 68 passed
- [x] Update docs: CHANGELOG.md
- [x] Bump version: 0.104.36
- [ ] Commit
