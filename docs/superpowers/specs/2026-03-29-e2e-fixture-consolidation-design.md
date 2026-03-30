# E2E Fixture Consolidation Design

## Problem

E2E tests take 189s. Each of ~100 test classes creates its own tmp_path project,
triggering a fresh daemon start (~3s) or cold graph build (~2.7s) per project.
Most projects use identical or near-identical configs. The subprocess overhead
per CLI call is ~0.3s when a daemon is running, but ~2.7s cold.

## Goal

Reduce e2e runtime to ~90-110s by consolidating ~100 unique project directories
into 5 shared fixtures + REPO_ROOT, each with a pre-started daemon.

## Design

### Principle: Sequential Test Chains

Each fixture is a sequential test chain. Tests run in order. If test N mutates
(fix, edit, config set, MCP save), test N+1 expects the mutated state. This
means:

1. Read-only tests run first (health, summary, trace, analysis, graph)
2. Mutation tests run next (fix, edit, config set)
3. Post-mutation verification tests run last (health again, changed detection)
4. MCP tests run at the end (mutations + save + refresh)

Tests within a fixture use `@pytest.mark.incremental` so failures cascade
correctly.

### Config Dimension Analysis

Config options are independent axes that can be freely combined:

| Dimension | Variants |
|-----------|----------|
| ID pattern | standard, FDA, jira/variable, named |
| Assertion labels | uppercase, numeric-0, numeric-1, zero-padded |
| Hierarchy | standard 3-tier, custom allowed_implements |
| Statuses | standard, custom (Review/Archived), status_roles |
| Format rules | require_rationale, require_shall, allow_orphans |
| Testing/code | enabled/disabled, custom dirs/patterns |
| Spec structure | single-dir, multi-dir, skip_dirs |
| Multi-assertion sep | + (default), , (comma) |
| Associated repos | none, 1, 2+ (separate dir structure) |

Tests verify one specific feature at a time. FDA tests check ID format in
output; numeric tests check label format. Neither checks the other. So a
fixture with FDA IDs + numeric assertions satisfies both test sets.

### Fixture Allocation

#### Fixture 0: REPO_ROOT (free, already exists)

The elspais repo itself. Pre-warmed daemon via session-scoped fixture.

**Config**: whatever `.elspais.toml` is in the repo (standard IDs, uppercase).

**Tests assigned**:
- Self-validation: health, doctor, summary, trace, graph on own repo
- CLI smoke: version, doctor, config show/path/get, example, docs, rules
- Basic commands: health (all formats), summary (all formats), analysis
- MCP protocol: search, get_requirement, hierarchy, cursors, mutations
- Viewer browser tests
- Subdir detection

**Chain order**: all read-only, no sequencing needed. But pre-warming the
daemon before any test runs saves ~3s on the first call.

#### Fixture 1: Standard Workhorse

**Config**:
- Standard IDs (`REQ-{level.letter}{component}`), uppercase assertions
- 3-tier hierarchy (PRD, OPS, DEV)
- Testing enabled, code scanning enabled
- Multiple spec dirs (`spec/product`, `spec/technical`)
- skip_dirs: `["drafts"]` (with a drafts/ dir containing ignored files)
- Statuses: Active, Draft, Deprecated (at least one req per status)
- Multi-assertion syntax: `Implements: REQ-p00001-A+B+C`
- Refines edges between requirements
- Enough requirements for meaningful health/coverage output

**Content**:
- 3 PRD requirements (1 Active with 3 assertions, 1 Draft, 1 Deprecated)
- 2 OPS requirements implementing PRD (Active)
- 3 DEV requirements implementing OPS (Active, with Refines edges)
- 1 code file with `# Implements:` markers
- 1 test file with `# Verifies:` markers
- 1 requirement with intentionally wrong hash (for fix testing)
- A `drafts/` dir with a spec file (for skip_dirs testing)
- Git repo initialized and committed

**Chain order**:
1. health (text, json, csv, markdown, junit, sarif) — read-only
2. summary (text, json, csv, markdown) — read-only
3. trace (text, json, csv, markdown, --preset, --body, --assertions) — read-only
4. analysis (table, json, --top, --show, --level) — read-only
5. graph --json — read-only
6. config show, config get, config path — read-only
7. health --spec, health --code, health --tests scope flags — read-only
8. fix (corrects wrong hash) — MUTATES
9. health again (should still pass) — verifies fix
10. fix --dry-run — read-only after fix
11. edit a requirement — MUTATES
12. changed (detects the edit) — read-only
13. config set (change an option) — MUTATES
14. health (verify config set effect) — read-only
15. MCP queries: search, get_requirement, hierarchy, project_summary
16. MCP mutations: add_requirement, rename, update_title, add_assertion
17. MCP save_mutations — MUTATES disk
18. MCP refresh, verify saved state
19. MCP undo tests

**Covers**: ~70% of current e2e tests (the majority)

#### Fixture 2: FDA + Numeric-0 + Custom Statuses

**Config**:
- FDA-style IDs (`{type}-{component}`, types: PRD/OPS/DEV)
- Numeric-0 assertion labels
- Custom statuses: Active, Draft, Review, Archived
- require_rationale=true
- Sequential labels enforced

**Content**:
- 2 PRD requirements (Active + Review status)
- 1 OPS requirement (Active)
- 1 DEV requirement (Archived)
- 1 requirement with wrong hash (for fix testing)

**Chain order**:
1. health — verify FDA IDs in output, custom statuses accepted
2. summary — verify numeric assertion labels
3. trace — format consistency
4. fix — corrects hash with FDA IDs
5. health again — rationale enforcement
6. MCP queries with numeric assertions

**Covers**: FDA ID tests, numeric assertion tests, custom status tests,
rationale tests

#### Fixture 3: Named IDs + Numeric-1 + Custom Hierarchy

**Config**:
- Named-component IDs (`REQ-{level.letter}{component}`, component_style=named)
- Numeric-1-based assertions
- Custom hierarchy: DEV can implement PRD directly (skip OPS)
- require_shall=false
- multi_assertion_separator=","
- zero_pad_assertions=true

**Content**:
- 2 PRD requirements (named: UserAuth, DataPrivacy)
- 2 DEV requirements implementing PRD directly (skipping OPS)
- Assertions using comma separator

**Chain order**:
1. health — verify named IDs, custom hierarchy
2. summary — verify 1-based labels, zero-padded
3. trace — comma-separated multi-assertions
4. health — verify SHALL not required

**Covers**: named ID tests, numeric-1 tests, zero-padded tests, custom
hierarchy tests, SHALL tests, separator tests

#### Fixture 4: Jira-Style + Config Edge Cases

**Config**:
- Jira-style variable-length IDs (PROJ-1, PROJ-12, no leading zeros)
- Uppercase assertions (default)
- allow_structural_orphans=true
- status_roles: active=[Active], provisional=[Draft,Proposed], retired=[Deprecated]
- Complex directory structure: `spec/active`, `spec/approved`, skip `drafts`, `archive`
- Custom comment styles: `["#", "//"]`
- Env var overrides tested against this fixture

**Content**:
- 3 requirements with Jira-style IDs
- 1 structural orphan (deliberately, testing allow_orphans)
- Files in spec/active and spec/approved
- Ignored files in drafts/ and archive/

**Chain order**:
1. health — verify variable-length IDs
2. summary — verify status_roles filtering
3. health with env var overrides
4. config show --section filter
5. Multi-file split testing

**Covers**: Jira-style tests, orphan tests, status_roles tests, env var
tests, complex dir tests, comment style tests

#### Fixture 5: Associated Repos

**Config**:
- Core: standard IDs, uppercase
- Associate "alpha": standard IDs, different namespace
- Associate "beta": FDA-style IDs, numeric assertions

**Content**:
- Core: 2 PRD, 2 DEV requirements
- Alpha: 2 DEV requirements implementing core PRD
- Beta: 1 DEV requirement implementing core PRD (cross-repo, FDA-style)

**Chain order**:
1. health — cross-repo validation
2. summary — counts from all repos
3. associate --list
4. MCP search across repos
5. MCP hierarchy across repos
6. associate --unlink (MUTATES config)
7. health after unlink — associate removed
8. associate --all auto-discovery

**Covers**: all associated repo tests, cross-repo implements, mixed assertion
styles across repos

### Implementation Strategy

**File structure**: One test file per fixture (plus REPO_ROOT tests stay in
their current files).

```
tests/e2e/
  conftest.py              -- session daemon warm-up, fixture builders
  test_e2e_global.py       -- Fixture 0: REPO_ROOT tests (merged from current files)
  test_e2e_standard.py     -- Fixture 1: standard workhorse chain
  test_e2e_fda_numeric.py  -- Fixture 2: FDA + numeric-0 chain
  test_e2e_named_custom.py -- Fixture 3: named + numeric-1 chain
  test_e2e_jira_edge.py    -- Fixture 4: jira + config edge cases chain
  test_e2e_associated.py   -- Fixture 5: associated repos chain
  helpers.py               -- unchanged (build_project, Requirement, etc.)
```

**Migration**: Each new file is a single `@pytest.mark.incremental` class (or
a few classes sharing a module-scoped fixture). Tests are ported from existing
files, adapted to assert against the fixture's specific config, and ordered
into the sequential chain.

**Daemon lifecycle**: Each fixture's `conftest.py` or module-level fixture
builds the project, initializes git, and calls `ensure_daemon()`. The daemon
stays alive for the module. Cleanup happens on module teardown.

**Backward compatibility**: Old test files are deleted after their tests are
ported. No parallel existence — clean cutover per fixture.

### Expected Timing

| Component | Time |
|-----------|------|
| 6 daemon starts (REPO_ROOT + 5 fixtures) | ~18s |
| ~300 CLI calls at ~0.3s daemon-served | ~90s |
| **Total** | **~108s** |

Target: under 120s (vs current 189s, baseline 217s).

### Out of Scope

- Changing what the tests assert (only restructuring, not rewriting logic)
- Adding new test coverage
- Modifying the daemon or engine code
- Browser/Playwright tests (already isolated, fast enough)
