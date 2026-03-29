# E2E Fixture Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate ~100 unique e2e test project directories into 6 shared fixtures with daemon reuse, cutting e2e runtime from 189s to ~100s.

**Architecture:** Each fixture is a module-scoped project directory with a pre-started daemon. Tests within a fixture run sequentially as an `@pytest.mark.incremental` chain — read-only tests first, then mutations that persist for subsequent tests. Config dimensions (ID patterns, assertion labels, hierarchy rules) are crossed efficiently so 6 fixtures cover all combinations.

**Tech Stack:** Python 3.10+, pytest (module-scoped fixtures, incremental marker), elspais daemon, subprocess CLI

---

## File Structure

```text
tests/e2e/
  conftest.py                    -- MODIFY: add daemon warm-up, shared project builders
  helpers.py                     -- UNCHANGED
  test_e2e_global.py             -- CREATE: Fixture 0 (REPO_ROOT) tests
  test_e2e_standard.py           -- CREATE: Fixture 1 (standard workhorse) chain
  test_e2e_fda_numeric.py        -- CREATE: Fixture 2 (FDA + numeric-0) chain
  test_e2e_named_custom.py       -- CREATE: Fixture 3 (named + numeric-1 + custom) chain
  test_e2e_jira_edge.py          -- CREATE: Fixture 4 (jira + config edge cases) chain
  test_e2e_associated.py         -- CREATE: Fixture 5 (associated repos) chain
  test_e2e_fixture_health.py     -- KEEP: already uses shared static fixtures
  test_e2e_special.py            -- CREATE: tests that need truly unique setups
  test_scenario_mutations.py     -- KEEP: single large scenario, already efficient
  test_viewer_browser.py         -- KEEP: browser tests, separate concern
  test_viewer_git_sync.py        -- KEEP: needs its own git repo lifecycle
  # DELETE after migration:
  test_cli_commands.py
  test_workflows.py
  test_analysis_cmd.py
  test_self_validation.py
  test_e2e_cli_health_summary.py
  test_e2e_cli_fix_changed_analysis.py
  test_e2e_config_variations.py
  test_e2e_complex_workflows.py
  test_e2e_edge_cases.py
  test_e2e_additional_coverage.py
  test_e2e_associated_repos.py
  test_e2e_mcp_comprehensive.py
  test_mcp_e2e.py
  test_e2e_health_check_names.py
```

## Test Migration Map

Each row shows: source file::class → destination fixture.

### Fixture 0: REPO_ROOT (test_e2e_global.py)

All read-only. No mutations. Uses the elspais repo itself.

| Source | Class | Methods | Notes |
|--------|-------|---------|-------|
| test_cli_commands | TestVersion | 2 | version smoke |
| test_cli_commands | TestDoctor | 2 | doctor smoke |
| test_cli_commands | TestSummary | 3 | summary formats |
| test_cli_commands | TestGraph | 1 | graph export |
| test_cli_commands | TestConfig | 3 | config show/path/get |
| test_cli_commands | TestExample | 2 | example command |
| test_cli_commands | TestDocs | 2 | docs command |
| test_cli_commands | TestChanged | 1 | changed (no changes) |
| test_cli_commands | TestRules | 1 | rules list |
| test_cli_commands | TestHealth | 11 | health all formats |
| test_cli_commands | TestFix | 1 | fix --dry-run |
| test_cli_commands | TestPdf | 2 | PDF gen (tmp_path for output only) |
| test_analysis_cmd | All 3 classes | 16 | analysis command |
| test_self_validation | All 6 classes | 11 | self-validation dogfood |
| test_workflows | TestHealthSummaryConsistency | 1 | consistency |
| test_workflows | TestSummaryIdempotent | 1 | idempotent |
| test_mcp_e2e | All 8 classes | 8 | MCP protocol (already module-scoped) |
| test_e2e_edge_cases | TestDocsCommand | 2 | docs (REPO_ROOT) |
| test_e2e_edge_cases | TestExampleCommand | 2 | example (REPO_ROOT) |
| **Total** | | **~72** | |

### Fixture 1: Standard Workhorse (test_e2e_standard.py)

Standard IDs, uppercase assertions, 3-tier, testing+code enabled. Rich content.

| Source | Class | Methods | Mutates? | Notes |
|--------|-------|---------|----------|-------|
| test_e2e_cli_health_summary | TestStandard3TierHealthSummary | 5 | No | health/summary/trace/doctor |
| test_e2e_cli_health_summary | TestTraceFormats | 4 | No | trace json/csv/text/markdown |
| test_e2e_cli_health_summary | TestSummaryFormats | 4 | No | summary formats |
| test_e2e_cli_health_summary | TestCodeRefsAndTesting | 3 | No | code+test refs |
| test_e2e_cli_health_summary | TestHealthScopeFlags | 3 | No | --spec/--code/--tests |
| test_e2e_complex_workflows | TestTraceWithAssertions | 1 | No | --assertions flag |
| test_e2e_complex_workflows | TestTraceWithBody | 1 | No | --body flag |
| test_e2e_complex_workflows | TestHealthTextOutput | 2 | No | health text/json |
| test_e2e_complex_workflows | TestHealthSARIF | 1 | No | SARIF format |
| test_e2e_complex_workflows | TestHealthJUnit | 1 | No | JUnit format |
| test_e2e_complex_workflows | TestHealthMarkdown | 1 | No | markdown format |
| test_e2e_complex_workflows | TestDoctorAndVersion | 1 | No | doctor --json |
| test_e2e_complex_workflows | TestCrossCommandConsistency | 1 | No | counts match |
| test_e2e_edge_cases | TestSingleAssertion | 2 | No | 1 assertion |
| test_e2e_edge_cases | TestManyAssertions | 1 | No | 26 assertions |
| test_e2e_edge_cases | TestMultipleSpecFilesPerLevel | 1 | No | split files |
| test_e2e_edge_cases | TestTracePresets | 3 | No | presets |
| test_e2e_edge_cases | TestIdempotency | 2 | No | repeat runs |
| test_e2e_edge_cases | TestChangedWithBaseBranch | 1 | No | --base-branch |
| test_e2e_edge_cases | TestConfigShowSection | 2 | No | config sections |
| test_e2e_edge_cases | TestConfigShowToml | 1 | No | TOML output |
| test_e2e_edge_cases | TestSummaryStatusFilter | 1 | No | status filter |
| test_e2e_additional_coverage | TestMultipleReqsSingleFile | 2 | No | 10 reqs |
| test_e2e_additional_coverage | TestRefinesRelationship | 1 | No | refines |
| test_e2e_additional_coverage | TestDraftStatusRequirements | 1 | No | draft filter |
| test_e2e_additional_coverage | TestMultipleCodeFilesForSameReq | 1 | No | multi impl |
| test_e2e_additional_coverage | TestHeadingLevel3 | 1 | No | ### headings |
| test_e2e_additional_coverage | TestSpecFilePreamble | 1 | No | preamble |
| test_e2e_additional_coverage | TestDeepHierarchy | 1 | No | deep chain |
| test_e2e_additional_coverage | TestTwoTierHierarchy | 1 | No | 2-tier |
| test_e2e_additional_coverage | TestHealthOutputToFile | 1 | No | --output |
| test_e2e_cli_fix_changed_analysis | TestAnalysisCommand | 5 | No | analysis |
| test_e2e_cli_fix_changed_analysis | TestGraphExport | 1 | No | graph JSON |
| test_e2e_cli_fix_changed_analysis | TestHealthSkipFiles | 1 | No | skip_files |
| test_e2e_cli_fix_changed_analysis | TestMultiAssertionSyntax | 1 | No | A+B+C |
| test_e2e_health_check_names | TestHealthCheckNames | 2 | No | check names |
| — MUTATION BOUNDARY — | | | | |
| test_e2e_cli_fix_changed_analysis | TestFixCorrectsHash | 2 | Yes | fix + dry-run |
| test_e2e_cli_fix_changed_analysis | TestConfigCommands | 4 | No | config show/get |
| test_e2e_complex_workflows | TestMultipleFixesIdempotent | 1 | Yes | fix×2 |
| test_e2e_complex_workflows | TestConfigSetAffectsHealth | 1 | Yes | config set |
| test_e2e_complex_workflows | TestEditCommand | 1 | Yes | edit status |
| test_e2e_cli_fix_changed_analysis | TestChangedCommand | 2 | Yes | detect changes |
| test_e2e_cli_fix_changed_analysis | TestConfigSetGet | 1 | Yes | set+get |
| test_e2e_additional_coverage | TestConfigArrayOperations | 2 | Yes | add/remove |
| test_e2e_additional_coverage | TestConfigUnset | 1 | Yes | unset key |
| test_e2e_edge_cases | TestFixSpecificRequirement | 1 | Yes | fix specific |
| test_e2e_edge_cases | TestTraceOutputToFile | 1 | Yes | trace to file |
| — MCP SECTION — | | | | |
| test_e2e_mcp_comprehensive | TestMCPSearchAndNavigation | 5 | No | search/nav |
| test_e2e_mcp_comprehensive | TestMCPProjectInfo | 3 | No | project info |
| test_e2e_mcp_comprehensive | TestMCPCursors | 2 | No | cursors |
| test_e2e_mcp_comprehensive | TestMCPSubtree | 4 | No | subtrees |
| test_e2e_mcp_comprehensive | TestMCPTestCoverage | 2 | No | coverage |
| test_e2e_mcp_comprehensive | TestMCPScopedSearch | 2 | No | scoped search |
| test_e2e_mcp_comprehensive | TestMCPKeywordSearch | 3 | No | keywords |
| test_e2e_mcp_comprehensive | TestMCPQueryNodes | 3 | No | query |
| test_e2e_mcp_comprehensive | TestMCPGraphHealth | 2 | No | orphans/broken |
| test_e2e_mcp_comprehensive | TestMCPMutations | 3 | No (undo) | mutations |
| test_e2e_mcp_comprehensive | TestMCPAssertionMutations | 3 | No (undo) | assertions |
| test_e2e_mcp_comprehensive | TestMCPEdgeMutations | 2 | No (undo) | edges |
| test_e2e_mcp_comprehensive | TestMCPComprehensiveWorkflow | 1 | No (undo) | workflow |
| test_e2e_mcp_comprehensive | TestMCPSaveMutations | 1 | Yes | save |
| test_e2e_mcp_comprehensive | TestMCPRefreshGraph | 1 | No | refresh |
| test_e2e_additional_coverage | TestMCPUndoToMutation | 1 | No (undo) | undo_to |
| test_e2e_additional_coverage | TestMCPRenameNode | 1 | No (undo) | rename |
| test_e2e_additional_coverage | TestMCPChangeStatus | 1 | No (undo) | status |
| test_e2e_additional_coverage | TestMCPDeleteRequirement | 1 | No (undo) | delete |
| test_e2e_additional_coverage | TestMCPRenameAssertion | 1 | No (undo) | rename assert |
| test_e2e_additional_coverage | TestMCPWorkspaceInfoProfiles | 4 | No | profiles |
| test_e2e_additional_coverage | TestMCPAgentInstructions | 1 | No | instructions |
| test_e2e_additional_coverage | TestMCPSuggestLinks | 1 | No | suggest |
| test_e2e_additional_coverage | TestMCPChangedRequirements | 1 | No | changed |
| test_e2e_additional_coverage | TestMCPMultiMutationWorkflow | 1 | Yes (save) | multi-mut |
| test_e2e_edge_cases | TestMCPChangeEdgeKind | 1 | No (undo) | edge kind |
| test_e2e_edge_cases | TestMCPFixBrokenReference | 1 | No (undo) | fix ref |
| **Total** | | **~120** | | |

### Fixture 2: FDA + Numeric-0 (test_e2e_fda_numeric.py)

FDA-style IDs, numeric-0 assertions, custom statuses, require_rationale.

| Source | Class | Methods | Notes |
|--------|-------|---------|-------|
| test_e2e_cli_health_summary | TestFDAStyleIds | 3 | FDA health/summary/trace |
| test_e2e_cli_fix_changed_analysis | TestFixFDAStyle | 1 | fix with FDA |
| test_e2e_mcp_comprehensive | TestMCPFDAStyle | 3 | MCP with FDA |
| test_e2e_cli_health_summary | TestNumericAssertionLabels | 2 | numeric-0 health/summary |
| test_e2e_cli_health_summary | TestCustomStatuses | 2 | custom statuses |
| test_e2e_config_variations | TestRequireRationale | 1 | rationale |
| test_e2e_config_variations | TestStatusFiltering | 1 | deprecated filter |
| test_e2e_complex_workflows | TestMCPNumericAssertions | 1 | MCP numeric |
| **Total** | | **~14** | |

### Fixture 3: Named + Numeric-1 + Custom Rules (test_e2e_named_custom.py)

Named-component IDs, numeric-1-based assertions, custom hierarchy, SHALL=false, comma separator.

| Source | Class | Methods | Notes |
|--------|-------|---------|-------|
| test_e2e_cli_health_summary | TestNamedComponentIds | 3 | named IDs |
| test_e2e_cli_health_summary | TestNumeric1BasedAssertionLabels | 2 | numeric-1 |
| test_e2e_config_variations | TestCustomHierarchyRules | 2 | dev→prd |
| test_e2e_config_variations | TestRequireShallDisabled | 1 | SHALL=false |
| test_e2e_config_variations | TestMultiAssertionSeparator | 1 | comma sep |
| test_e2e_edge_cases | TestMCPNumeric1Based | 1 | MCP 1-based |
| test_e2e_edge_cases | TestPlaceholderAssertions | 1 | placeholders |
| test_e2e_additional_coverage | TestEmptyAssertions | 1 | no assertions |
| test_e2e_cli_fix_changed_analysis | TestConfigCommands (dup) | 4 | config with custom ns |
| **Total** | | **~16** | |

### Fixture 4: Jira-Style + Config Edge Cases (test_e2e_jira_edge.py)

Variable-length IDs, zero-padded assertions, orphans, status_roles, complex dirs, env vars.

| Source | Class | Methods | Notes |
|--------|-------|---------|-------|
| test_e2e_cli_health_summary | TestVariableLengthIds | 2 | jira IDs |
| test_e2e_cli_health_summary | TestSkipDirsMultiSegment | 1 | skip_dirs |
| test_e2e_cli_health_summary | TestMultipleSpecDirs | 2 | multi spec |
| test_e2e_additional_coverage | TestZeroPaddedNumericAssertions | 1 | zero-padded |
| test_e2e_config_variations | TestIgnorePatterns | 2 | ignore |
| test_e2e_config_variations | TestReferencesOverrides | 1 | JS comments |
| test_e2e_config_variations | TestLargeHierarchy | 2 | 12 reqs |
| test_e2e_config_variations | TestTestingConfig | 1 | custom test dirs |
| test_e2e_config_variations | TestComplexDirectoryStructure | 1 | nested dirs |
| test_e2e_config_variations | TestEnvVarOverrides | 1 | env vars |
| test_e2e_config_variations | TestAllowStructuralOrphansConfig | 2 | orphans |
| test_e2e_config_variations | TestStatusRolesConfig | 1 | status_roles |
| **Total** | | **~17** | |

### Fixture 5: Associated Repos (test_e2e_associated.py)

Core + associates, cross-repo implements, mixed assertion styles.

| Source | Class | Methods | Notes |
|--------|-------|---------|-------|
| test_e2e_associated_repos | All 8 classes | 12 | all associated tests |
| test_e2e_complex_workflows | TestMCPAssociatedWorkflow | 1 | MCP associates |
| test_e2e_edge_cases | TestAssociateUnlink | 1 | unlink |
| test_e2e_edge_cases | TestMultiAssociateHealth | 1 | 3 associates |
| test_e2e_edge_cases | TestMCPAssociatedSubtree | 1 | subtree |
| **Total** | | **~16** | |

### Special Cases (test_e2e_special.py)

Tests needing truly unique setups that can't share a fixture.

| Source | Class | Methods | Notes |
|--------|-------|---------|-------|
| test_cli_commands | TestInit | 1 | init in empty dir |
| test_workflows | TestInitThenHealth | 1 | init → health |
| test_workflows | TestInitTemplate | 1 | init template |
| test_workflows | TestFixThenHealth | 1 | wrong hash → fix |
| test_workflows | TestTraceFormatConsistency | 1 | trace output files |
| test_e2e_cli_fix_changed_analysis | TestInitCommand | 4 | init variations |
| test_e2e_complex_workflows | TestFullProjectLifecycle | 1 | full lifecycle |
| test_e2e_additional_coverage | TestInitForce | 1 | --force overwrite |
| **Total** | | **~11** | |

---

## Implementation Tasks

### Task 1: Infrastructure — conftest.py and daemon warm-up

**Files:**
- Modify: `tests/e2e/conftest.py`

- [ ] **Step 1: Add session-scoped daemon warm-up fixture**

Add before the existing `_cleanup_daemon` fixture in `tests/e2e/conftest.py`:

```python
@pytest.fixture(autouse=True, scope="session")
def _warm_daemon():
    """Pre-start the daemon for REPO_ROOT so global-scope tests are fast.

    Without this, the first CLI invocation pays ~3s for daemon auto-start.
    With this, the daemon starts once and all subsequent calls hit it in ~0.3s.
    """
    try:
        from elspais.config import find_git_root
        from elspais.mcp.daemon import ensure_daemon

        repo_root = find_git_root()
        if repo_root:
            ensure_daemon(repo_root)
    except Exception:
        pass
    yield
```

- [ ] **Step 2: Add shared project builder function**

Add to `tests/e2e/conftest.py`:

```python
import os


def build_fixture_project(
    root: Path,
    config_overrides: dict | None = None,
    spec_files: dict[str, str] | None = None,
    code_files: dict[str, str] | None = None,
    test_files: dict[str, str] | None = None,
    init_git: bool = True,
) -> Path:
    """Build a project directory for a fixture and optionally start its daemon.

    Args:
        root: Project root directory (e.g., from tmp_path_factory.mktemp).
        config_overrides: Dict merged into base_config() defaults.
        spec_files: {relative_path: content} for spec files.
        code_files: {relative_path: content} for code files.
        test_files: {relative_path: content} for test files.
        init_git: Whether to initialize a git repo and commit.

    Returns:
        The project root path.
    """
    import subprocess

    from tests.e2e.helpers import base_config, write_config

    config = base_config(**(config_overrides or {}))
    write_config(root, config)

    for files, default_dir in [
        (spec_files, "spec"),
        (code_files, "src"),
        (test_files, "tests"),
    ]:
        if files:
            for rel_path, content in files.items():
                fpath = root / rel_path
                fpath.parent.mkdir(parents=True, exist_ok=True)
                fpath.write_text(content)
        else:
            (root / default_dir).mkdir(exist_ok=True)

    if init_git:
        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "t@t",
        }
        subprocess.run(["git", "init"], cwd=root, capture_output=True, env=env)
        subprocess.run(["git", "add", "."], cwd=root, capture_output=True, env=env)
        subprocess.run(
            ["git", "commit", "-m", "init"], cwd=root, capture_output=True, env=env
        )

    return root


def ensure_fixture_daemon(root: Path) -> None:
    """Start a daemon for the fixture project if cli_ttl allows."""
    try:
        from elspais.mcp.daemon import ensure_daemon

        ensure_daemon(root)
    except Exception:
        pass
```

- [ ] **Step 3: Run existing e2e tests to confirm no regression**

```bash
python -m pytest -m "e2e" --tb=short -q 2>&1 | tail -5
```

Expected: 313 passed, 1 failed (pre-existing), 1 skipped.

- [ ] **Step 4: Commit**

```bash
git add tests/e2e/conftest.py
git commit -m "[CUR-1081] test: add e2e daemon warm-up and shared project builder

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Fixture 0 — Global Tests (test_e2e_global.py)

**Files:**
- Create: `tests/e2e/test_e2e_global.py`

Consolidate all REPO_ROOT tests into one file. These are all read-only and
share the session-warmed daemon. No sequencing needed — they can run in any
order. Keep `@pytest.mark.e2e` on the module.

- [ ] **Step 1: Create test_e2e_global.py**

Port all test classes from the migration map (Fixture 0 section above) into a
single file. Each class keeps its original test methods and assertions. The
key change: remove any per-test project setup. All tests use `run_elspais()`
with default CWD (REPO_ROOT).

Structure:
```python
# Verifies: REQ-p00013-A+B+C+D+E+F
"""Global-scope e2e tests — all run against REPO_ROOT with daemon acceleration.

These tests validate CLI commands against the elspais repository itself.
No project setup needed. The session-scoped daemon warm-up ensures fast responses.
"""
import json
import subprocess
from pathlib import Path

import pytest

from tests.e2e.conftest import REPO_ROOT, run_elspais


@pytest.mark.e2e
class TestCLISmoke:
    """Basic CLI command smoke tests."""

    def test_version_returns_zero(self):
        result = run_elspais("--version")
        assert result.returncode == 0

    def test_doctor_returns_zero(self):
        result = run_elspais("doctor")
        assert result.returncode == 0

    # ... (port remaining smoke tests)


@pytest.mark.e2e
class TestHealthFormats:
    """Health command output format tests."""

    def test_health_lenient_returns_zero(self):
        result = run_elspais("health", "--lenient")
        assert result.returncode == 0

    # ... (port all TestHealth methods)


# ... (remaining classes)
```

- [ ] **Step 2: Run the new file in isolation**

```bash
python -m pytest tests/e2e/test_e2e_global.py -v --durations=10 -m "" 2>&1 | tail -20
```

Expected: all pass, first test ~3s (daemon start), rest ~0.3s each.

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/test_e2e_global.py
git commit -m "[CUR-1081] test: create test_e2e_global.py — REPO_ROOT tests consolidated

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Fixture 1 — Standard Workhorse (test_e2e_standard.py)

**Files:**
- Create: `tests/e2e/test_e2e_standard.py`

This is the largest fixture. The project needs:
- Standard IDs (REQ-p/o/d), uppercase assertions
- 3-tier hierarchy (PRD, OPS, DEV)
- Testing enabled, code scanning, test files
- Multiple spec files with varied content
- Active, Draft, Deprecated status requirements
- Multi-assertion syntax (A+B+C)
- Refines edges
- A requirement with wrong hash (for fix testing)
- A `drafts/` dir (for skip_dirs testing)
- A `spec/INDEX.md` and `spec/NOTES.md` (for skip_files testing)
- 26-assertion requirement (for many-assertions test)
- Deep hierarchy (PRD→OPS→DEV→DEV)
- Multiple code files implementing same req
- Git repo initialized

- [ ] **Step 1: Build the fixture project content**

Create `tests/e2e/test_e2e_standard.py` with a module-scoped fixture that
builds a comprehensive project using `build_fixture_project()` and
`Requirement` from helpers.py. The fixture must include ALL the content
needed by every test in the chain.

Use helpers to generate requirements:
```python
from tests.e2e.helpers import Requirement, compute_hash, labels_uppercase

# PRD requirements
prd1 = Requirement("REQ-p00001", "User Authentication", "PRD", "Active",
    assertions=[("A", "The system SHALL authenticate users."),
                ("B", "The system SHALL log failed attempts."),
                ("C", "The system SHALL lock accounts after 5 failures.")],
    body="The system SHALL provide secure user authentication.")

# ... (build all requirements needed by the chain)
```

The fixture function:
```python
@pytest.fixture(scope="module")
def project(tmp_path_factory):
    """Standard workhorse project — shared across all tests in module."""
    root = tmp_path_factory.mktemp("standard")
    # ... build project with all requirements, code, tests
    ensure_fixture_daemon(root)
    return root
```

- [ ] **Step 2: Port read-only tests as the first section of the chain**

Each test method takes the `project` fixture and calls `run_elspais(cmd, cwd=project)`.
Read-only tests go first (no `@pytest.mark.incremental` needed for these — they
don't depend on order). Group them into classes by feature area:

```python
@pytest.mark.e2e
class TestStandardHealth:
    def test_health_passes(self, project):
        result = run_elspais("health", "--lenient", cwd=project)
        assert result.returncode == 0

    def test_health_json_valid(self, project):
        result = run_elspais("health", "--lenient", "--format", "json", cwd=project)
        data = json.loads(result.stdout)
        assert "checks" in data
    # ...
```

- [ ] **Step 3: Port mutation tests as an incremental chain**

After all read-only tests, add an `@pytest.mark.incremental` class for
mutation tests. Order matters here:

```python
@pytest.mark.e2e
@pytest.mark.incremental
class TestStandardMutations:
    """Sequential mutation chain — each test builds on the previous state."""

    def test_fix_corrects_hash(self, project):
        result = run_elspais("fix", cwd=project)
        assert result.returncode == 0

    def test_health_after_fix(self, project):
        result = run_elspais("health", "--lenient", cwd=project)
        assert result.returncode == 0

    def test_config_set(self, project):
        result = run_elspais("config", "set", "project.name", "mutated", cwd=project)
        assert result.returncode == 0

    def test_config_get_after_set(self, project):
        result = run_elspais("config", "get", "project.name", cwd=project)
        assert "mutated" in result.stdout
    # ...
```

- [ ] **Step 4: Port MCP tests using the same project**

Start an MCP server against the project and run MCP tool tests:

```python
@pytest.fixture(scope="module")
def mcp(project):
    """MCP server for the standard project."""
    from tests.e2e.helpers import start_mcp, stop_mcp
    server = start_mcp(cwd=project)
    yield server
    stop_mcp(server)

@pytest.mark.e2e
class TestStandardMCPQueries:
    def test_search(self, mcp):
        result = mcp.call("search", {"query": "Authentication"})
        assert len(result["results"]) > 0
    # ...
```

- [ ] **Step 5: Run and verify**

```bash
python -m pytest tests/e2e/test_e2e_standard.py -v --durations=10 -m "" 2>&1 | tail -30
```

Expected: all pass, ~120 tests, total time ~40s (1 daemon start + ~0.3s per test).

- [ ] **Step 6: Commit**

```bash
git add tests/e2e/test_e2e_standard.py
git commit -m "[CUR-1081] test: create test_e2e_standard.py — standard workhorse fixture

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Fixture 2 — FDA + Numeric-0 (test_e2e_fda_numeric.py)

**Files:**
- Create: `tests/e2e/test_e2e_fda_numeric.py`

**Config:**
- FDA-style IDs: `canonical="{type}-{component}"`, types=PRD/OPS/DEV
- Numeric-0 assertions: `label_style="numeric"`, `labels_sequential=True`
- Custom statuses: `allowed_statuses=["Active", "Draft", "Review", "Archived"]`
- `require_rationale=True`

- [ ] **Step 1: Build fixture and port tests**

Same pattern as Task 3 but with FDA config. ~14 tests total.

- [ ] **Step 2: Run and verify**

```bash
python -m pytest tests/e2e/test_e2e_fda_numeric.py -v -m "" 2>&1 | tail -20
```

- [ ] **Step 3: Commit**

---

### Task 5: Fixture 3 — Named + Custom Rules (test_e2e_named_custom.py)

**Files:**
- Create: `tests/e2e/test_e2e_named_custom.py`

**Config:**
- Named-component IDs: `component_style="named"`
- Numeric-1-based assertions: `label_style="numeric_1based"`
- Custom hierarchy: `allowed_implements=["dev -> prd", "ops -> prd"]`
- `require_shall=False`
- `multi_assertion_separator=","`
- `allow_structural_orphans=True`

- [ ] **Step 1: Build fixture and port tests**

~16 tests. Include requirements that exercise all the config features.

- [ ] **Step 2: Run and verify**

- [ ] **Step 3: Commit**

---

### Task 6: Fixture 4 — Jira-Style + Config Edge Cases (test_e2e_jira_edge.py)

**Files:**
- Create: `tests/e2e/test_e2e_jira_edge.py`

**Config:**
- Jira-style variable-length IDs: `namespace="PROJ"`, `component_digits=0`, `leading_zeros=False`
- Zero-padded assertions: `label_style="numeric"`, `zero_pad_assertions=True`
- `allow_structural_orphans=True`
- `status_roles` configured
- Complex directory: `spec_dir=["spec/active", "spec/approved"]`, `skip_dirs=["drafts", "archive"]`
- Custom comment styles: `comment_styles=["#", "//"]`
- Custom test dirs: `testing_enabled=True`, `test_dirs=["verification"]`

- [ ] **Step 1: Build fixture and port tests**

~17 tests. Include node_modules/ dir for ignore testing, nested spec dirs, etc.

- [ ] **Step 2: Run and verify**

- [ ] **Step 3: Commit**

---

### Task 7: Fixture 5 — Associated Repos (test_e2e_associated.py)

**Files:**
- Create: `tests/e2e/test_e2e_associated.py`

**Structure:**
- Core project: standard IDs, uppercase, 2 PRD + 2 DEV
- Associate "alpha": standard IDs, different namespace
- Associate "beta": FDA-style IDs, numeric assertions

- [ ] **Step 1: Build multi-repo fixture**

The fixture creates 3 separate directories (core, alpha, beta) with their
own `.elspais.toml` and git repos. Core's config includes `[associates]`
sections pointing to ../alpha and ../beta.

- [ ] **Step 2: Port all associated repo tests**

~16 tests including cross-repo implements, associate list, unlink, MCP.

- [ ] **Step 3: Run and verify**

- [ ] **Step 4: Commit**

---

### Task 8: Special Cases (test_e2e_special.py)

**Files:**
- Create: `tests/e2e/test_e2e_special.py`

Tests that need truly unique setups (init in empty dir, lifecycle from
scratch, specific wrong-hash fixtures). These keep per-test tmp_path
isolation. ~11 tests — acceptable overhead since each is unique.

- [ ] **Step 1: Port init and lifecycle tests**

- [ ] **Step 2: Run and verify**

- [ ] **Step 3: Commit**

---

### Task 9: Delete Old Files and Final Verification

**Files:**
- Delete: 14 old test files (see file structure above)

- [ ] **Step 1: Run the full new e2e suite**

```bash
python -m pytest -m "e2e" --tb=short -q --durations=30 2>&1 | tail -40
```

Verify: same test count (~315), same pass/fail ratio, runtime target ~100s.

- [ ] **Step 2: Delete old files**

```bash
git rm tests/e2e/test_cli_commands.py
git rm tests/e2e/test_workflows.py
git rm tests/e2e/test_analysis_cmd.py
git rm tests/e2e/test_self_validation.py
git rm tests/e2e/test_e2e_cli_health_summary.py
git rm tests/e2e/test_e2e_cli_fix_changed_analysis.py
git rm tests/e2e/test_e2e_config_variations.py
git rm tests/e2e/test_e2e_complex_workflows.py
git rm tests/e2e/test_e2e_edge_cases.py
git rm tests/e2e/test_e2e_additional_coverage.py
git rm tests/e2e/test_e2e_associated_repos.py
git rm tests/e2e/test_e2e_mcp_comprehensive.py
git rm tests/e2e/test_mcp_e2e.py
git rm tests/e2e/test_e2e_health_check_names.py
```

- [ ] **Step 3: Run full suite (unit + e2e)**

```bash
python -m pytest -m "" --tb=short -q 2>&1 | tail -10
```

- [ ] **Step 4: Commit**

```bash
git commit -m "[CUR-1081] test: delete old e2e test files after consolidation

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: Update Documentation and Version

**Files:**
- Modify: `CLAUDE.md`
- Modify: `pyproject.toml`

- [ ] **Step 1: Update CLAUDE.md testing section**

Update the e2e test description and add fixture documentation:

```markdown
**E2E fixture structure**: Tests are organized into 6 shared fixtures
(test_e2e_global, test_e2e_standard, test_e2e_fda_numeric, test_e2e_named_custom,
test_e2e_jira_edge, test_e2e_associated) plus test_e2e_special for unique setups.
Each fixture builds one project with a daemon, and tests run sequentially against it.
When adding new e2e tests, add them to the appropriate fixture file rather than
creating a new test file with its own project setup.
```

- [ ] **Step 2: Bump version**

- [ ] **Step 3: Commit**
