# Master Plan: FederatedGraph — MCP Server and Viewer Updates

**Branch**: claude/cross-cutting-requirements-2Zd0c
**Ticket**: CUR-1082
**Status**: Not Started
**Depends on**: MASTER_PLAN.md (Core Wrapper) must be complete. MASTER_PLAN1.md (Config + Multi-Repo) should be complete for full federation features but is not strictly required — MCP can work with federation-of-one from MASTER_PLAN.md.

**Background**: With the core FederatedGraph in place and multi-repo federation working, this plan updates the MCP server and viewer to fully leverage federation: per-repo config access, federation info in workspace queries, and repo staleness indicators in the viewer/server.

**Spec**: `docs/superpowers/specs/2026-03-16-federated-graph-design.md`

## Execution Rules

These rules apply to EVERY task below. Do not skip steps. Do not reorder.
If you find yourself writing implementation code without a TASK_FILE and
failing tests, STOP and return to step 1 of the current task.

Read `AGENT_DESIGN_PRINCIPLES.md` before starting the first task.

## Plan

### Task 1: MCP server federation support

Update `_state["graph"]` to hold `FederatedGraph`. Replace `_state["config"]` with per-repo config access: tools that currently read `_state["config"]` should use `fg.config_for(node_id)` or `fg.repo_for(repo_name).config` where appropriate. Key config accesses to update: `get_status_roles()` calls, workspace info hierarchy rules, coverage stat computation. Update `get_workspace_info` to expose federation info: repo names, paths, error states, git origins via `fg.iter_repos()`. Update `refresh_graph()` to rebuild the entire federation (all repos). Run MCP test suite.

**TASK_FILE**: `FEDGRAPH_MP3_TASK_1.md`

- [x] **Baseline**: 2765 passed
- [x] **Create TASK_FILE**: FEDGRAPH_MP3_TASK_1.md
- [x] **Find assertions**: Created REQ-d00205-A..D in spec/08-mcp-server.md
- [x] **Write failing tests**: 5 tests in tests/mcp/test_mcp_federation.py
- [x] **Implement**: workspace federation info, refresh config sync, config derivation
- [x] **Verify**: 2770 passed (5 new), doc sync 68 passed
- [x] **Update docs**: CHANGELOG.md
- [x] **Bump version**: 0.104.36
- [ ] **Commit**: pending

---

### Task 2: Viewer/server repo staleness and Flask app update

Update `create_app()` in `server/app.py` to accept `FederatedGraph`. Add repo info API endpoint that includes staleness: for repos with `git_origin` configured, check if local is behind remote (mock the git remote check in tests). Staleness is informational only — not a build error. Include staleness info in workspace/repo info API responses.

**TASK_FILE**: `FEDGRAPH_MP3_TASK_2.md`

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

- [ ] Move plan: `mv MASTER_PLAN.md ~/archive/2026-03-16/MASTER_PLAN_CUR-1082_FEDGRAPH_MCP.md`
- [ ] Move all TASK_FILEs to the same archive directory
- [ ] Promote next queued plan if one exists: check for any remaining MASTER_PLANx.md files
