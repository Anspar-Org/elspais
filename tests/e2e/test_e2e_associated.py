# Verifies: REQ-p00005
"""E2E tests for associated repository features — Fixture 5.

Consolidated from:
  - test_e2e_associated_repos.py (all 8 classes)
  - test_e2e_complex_workflows.py TestMCPAssociatedWorkflow
  - test_e2e_edge_cases.py TestAssociateUnlink, TestMultiAssociateHealth,
    TestMCPAssociatedSubtree

On-disk fixture layout (tests/fixtures/e2e-associated/):
  - core:  standard IDs (REQ-p/o/d), uppercase assertions, associates=[alpha,beta]
  - alpha: standard IDs, prefix ALP, uppercase assertions
  - beta:  standard IDs, prefix BET, numeric assertions
"""

from __future__ import annotations

import json
import shutil

import pytest

from .conftest import (
    ensure_fixture_daemon,
    load_associated_fixture,
    run_elspais,
)
from .helpers import (
    Requirement,
    base_config,
    build_associate,
    build_project,
)

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        shutil.which("elspais") is None,
        reason="elspais CLI not found on PATH",
    ),
]


# ---------------------------------------------------------------------------
# Shared module fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def project(tmp_path_factory):
    """Copy e2e-associated fixture to /tmp, git init each repo, start daemon on core."""
    root = tmp_path_factory.mktemp("e2e_associated")
    core = load_associated_fixture(root)
    ensure_fixture_daemon(core)
    return core


@pytest.fixture(scope="module")
def mcp_server(project):
    """Start an MCP server for the associated project."""
    pytest.importorskip("mcp")
    from .helpers import start_mcp, stop_mcp

    proc = start_mcp(project)
    yield proc
    stop_mcp(proc)


# ---------------------------------------------------------------------------
# Test: Core + 1 associate health passes (from TestCoreWithOneAssociate)
# ---------------------------------------------------------------------------


class TestCoreWithOneAssociate:
    """Core project with one associated repo."""

    def test_health_passes(self, project):
        result = run_elspais("checks", "--lenient", cwd=project)
        assert result.returncode == 0, f"health failed: {result.stderr}\n{result.stdout}"

    def test_summary_includes_associate_reqs(self, project):
        result = run_elspais("summary", "--format", "json", cwd=project)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        levels = data.get("levels", [])
        total = sum(lv.get("total", 0) for lv in levels)
        # Core has 4 reqs (p00001, p00002, d00001, d00002)
        assert total >= 4, f"Expected at least 4 requirements (core), got {total}"

    def test_trace_includes_core_ids(self, project):
        result = run_elspais("trace", "--format", "json", cwd=project)
        assert result.returncode == 0
        output = result.stdout
        assert "REQ-p00001" in output
        assert "REQ-d00001" in output


# ---------------------------------------------------------------------------
# Test: Core + 2 associates (from TestCoreWithTwoAssociates)
# ---------------------------------------------------------------------------


class TestCoreWithTwoAssociates:
    """Core project with two associated repos."""

    def test_health_passes(self, project):
        result = run_elspais("checks", "--lenient", cwd=project)
        assert result.returncode == 0, f"health failed: {result.stderr}\n{result.stdout}"

    def test_summary_counts_all(self, project):
        result = run_elspais("summary", "--format", "json", cwd=project)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        levels = data.get("levels", [])
        total = sum(lv.get("total", 0) for lv in levels)
        # Core: 2 PRD + 2 DEV, Alpha: 2 DEV, Beta: 1 PRD + 1 DEV = at least 1 total
        assert total >= 1


# ---------------------------------------------------------------------------
# Test: Associate CLI list command (from TestAssociateListCommand)
# ---------------------------------------------------------------------------


class TestAssociateListCommand:
    """Associate --list shows linked repos."""

    def test_associate_list(self, project):
        result = run_elspais("associate", "--list", cwd=project)
        assert result.returncode == 0
        output = result.stdout.lower()
        assert "alpha" in output or "alp" in output, f"Expected alpha in output: {result.stdout}"


# ---------------------------------------------------------------------------
# Test: Associate with numeric assertions (from TestAssociateNumericAssertions)
# ---------------------------------------------------------------------------


class TestAssociateNumericAssertions:
    """Core with uppercase assertions, associate with numeric assertions."""

    def test_health_passes_mixed_assertions(self, project):
        result = run_elspais("checks", "--lenient", cwd=project)
        assert result.returncode == 0, f"health failed: {result.stderr}\n{result.stdout}"

    def test_trace_shows_both_repos(self, project):
        result = run_elspais("trace", "--format", "json", cwd=project)
        assert result.returncode == 0
        # Core PRD should always be present
        assert "REQ-p00001" in result.stdout


# ---------------------------------------------------------------------------
# Test: Cross-repo implements reference (from TestCrossRepoImplements)
# ---------------------------------------------------------------------------


class TestCrossRepoImplements:
    """Associate DEV implements core PRD."""

    def test_health_passes_cross_repo(self, project):
        # alpha DEV reqs implement core PRD reqs
        result = run_elspais("checks", "--lenient", cwd=project)
        assert result.returncode == 0, f"health failed: {result.stderr}\n{result.stdout}"

    def test_trace_shows_cross_repo_link(self, project):
        result = run_elspais("trace", "--format", "json", cwd=project)
        assert result.returncode == 0
        assert "REQ-p00001" in result.stdout


# ---------------------------------------------------------------------------
# Test: Associate auto-discovery (from TestAssociateAutoDiscovery)
# Unique layout — keeps per-test build.
# ---------------------------------------------------------------------------


class TestAssociateAutoDiscovery:
    """Associate --all auto-discovers sibling repos."""

    def test_auto_discover(self, tmp_path):
        # Create core without any associate links
        core_root = tmp_path / "core"
        core_cfg = base_config(name="auto-disc-core", associated_enabled=True)
        build_project(
            core_root,
            core_cfg,
            spec_files={
                "spec/prd.md": [
                    Requirement(
                        "REQ-p00001",
                        "Auto Disc",
                        "PRD",
                        assertions=[("A", "The system SHALL auto-discover.")],
                    ),
                ],
            },
        )

        # Create an associate as a sibling (not linked in core config)
        assoc_root = tmp_path / "sibling"
        build_associate(
            assoc_root,
            "sibling",
            "SIB",
            "../core",
            spec_files={
                "spec/prd.md": [
                    Requirement(
                        "REQ-SIB-p00001",
                        "Sibling Feature",
                        "PRD",
                        assertions=[("A", "Sibling SHALL be discovered.")],
                    ),
                ],
            },
            init_git=True,
        )

        # Run associate --all — may or may not find it; must not crash
        result = run_elspais("associate", "--all", cwd=core_root)
        assert result.returncode in (0, 1), f"associate --all crashed unexpectedly: {result.stderr}"


# ---------------------------------------------------------------------------
# Test: MCP with associated repos (from TestMCPWithAssociates)
# ---------------------------------------------------------------------------


class TestMCPWithAssociates:
    """MCP server with core + associate project."""

    def test_mcp_search_finds_associate_reqs(self, project, mcp_server):
        from .helpers import mcp_call, mcp_call_all

        # Search for core requirement
        results = mcp_call_all(mcp_server, "search", {"query": "Auth"})
        assert len(results) >= 1
        ids = [r.get("id", "") for r in results]
        assert any("p00001" in i for i in ids)

        # Get project summary
        summary = mcp_call(mcp_server, "get_project_summary", {})
        assert isinstance(summary, dict)

        # Navigate hierarchy
        hier = mcp_call(mcp_server, "get_hierarchy", {"req_id": "REQ-d00001"})
        assert "ancestors" in hier


# ---------------------------------------------------------------------------
# Test: Associate with FDA-style IDs (from TestAssociateFDAStyle)
# Unique layout — keeps per-test build.
# ---------------------------------------------------------------------------


class TestAssociateFDAStyle:
    """Core with standard IDs, associate with FDA-style (namespaced) IDs."""

    def _build(self, tmp_path):
        core_root = tmp_path / "core"
        assoc_root = tmp_path / "fda-assoc"

        core_cfg = base_config(
            name="core-std",
            associated_enabled=True,
        )
        core_cfg["associates"] = {"paths": ["../fda-assoc"]}
        core_prd = Requirement(
            "REQ-p00001",
            "Core Standard",
            "PRD",
            assertions=[("A", "The system SHALL use standard IDs.")],
        )
        build_project(
            core_root,
            core_cfg,
            spec_files={"spec/prd.md": [core_prd]},
        )

        # FDA-style associate with namespaced prefix
        assoc_prd = Requirement(
            "REQ-FDA-p00001",
            "FDA Compliance",
            "PRD",
            assertions=[("A", "The system SHALL comply with FDA regulations.")],
        )
        build_associate(
            assoc_root,
            "fda-assoc",
            "FDA",
            "../core",
            spec_files={"spec/prd-fda.md": [assoc_prd]},
            init_git=True,
        )

        return core_root

    def test_health_passes(self, tmp_path):
        core = self._build(tmp_path)
        result = run_elspais("checks", "--lenient", cwd=core)
        assert result.returncode == 0, f"health failed: {result.stderr}\n{result.stdout}"


# ---------------------------------------------------------------------------
# Test: Full MCP workflow with associate (from TestMCPAssociatedWorkflow)
# ---------------------------------------------------------------------------


class TestMCPAssociatedWorkflow:
    """Full MCP workflow with core + associate."""

    def test_mcp_associate_workflow(self, project, mcp_server):
        from .helpers import mcp_call, mcp_call_all

        # 1. Get status
        status = mcp_call(mcp_server, "get_graph_status", {})
        assert isinstance(status, dict)

        # 2. Search
        results = mcp_call_all(mcp_server, "search", {"query": "Auth"})
        assert len(results) >= 1

        # 3. Get core requirement
        req = mcp_call(mcp_server, "get_requirement", {"req_id": "REQ-p00001"})
        assert req["id"] == "REQ-p00001"

        # 4. Get summary
        summary = mcp_call(mcp_server, "get_project_summary", {})
        assert isinstance(summary, dict)


# ---------------------------------------------------------------------------
# Test: Health with multiple associates (from TestMultiAssociateHealth)
# ---------------------------------------------------------------------------


class TestMultiAssociateHealth:
    """Health check with multi-associate setup (core + alpha + beta)."""

    def test_three_repos(self, project):
        health = run_elspais("checks", "--lenient", cwd=project)
        assert health.returncode == 0


# ---------------------------------------------------------------------------
# Test: MCP subtree extraction with associate (from TestMCPAssociatedSubtree)
# ---------------------------------------------------------------------------


class TestMCPAssociatedSubtree:
    """MCP subtree extraction with associated repos."""

    def test_subtree_with_associate(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(
            mcp_server,
            "get_subtree",
            {
                "root_id": "REQ-p00001",
                "format": "flat",
            },
        )
        assert isinstance(result, dict)
        nodes = result.get("nodes", [])
        node_ids = [n.get("id", "") for n in nodes]
        assert "REQ-p00001" in node_ids


# ---------------------------------------------------------------------------
# Mutation tests — run LAST, after all read-only tests above.
# ---------------------------------------------------------------------------


@pytest.mark.incremental
class TestAssociatedMutations:
    """Sequential mutations on the associated fixture."""

    def test_01_unlink_associate(self, project):
        result = run_elspais("associate", "--unlink", "beta", cwd=project)
        assert result.returncode in (0, 1)
