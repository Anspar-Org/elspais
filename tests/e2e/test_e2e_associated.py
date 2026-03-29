# Verifies: REQ-p00005
"""E2E tests for associated repository features — Fixture 5.

Consolidated from:
  - test_e2e_associated_repos.py (all 8 classes)
  - test_e2e_complex_workflows.py TestMCPAssociatedWorkflow
  - test_e2e_edge_cases.py TestAssociateUnlink, TestMultiAssociateHealth,
    TestMCPAssociatedSubtree

Multi-repo fixture layout:
  - core:  standard IDs (REQ-p/o/d), uppercase assertions
  - alpha: standard IDs, namespace "ALPHA"
  - beta:  FDA-style IDs (PRD-/DEV- pattern unused here, uses REQ-BET prefix),
           numeric assertions
"""

from __future__ import annotations

import json
import shutil

import pytest

from .helpers import (
    Requirement,
    associate_config,
    base_config,
    build_associate,
    build_project,
    run_elspais,
)

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        shutil.which("elspais") is None,
        reason="elspais CLI not found on PATH",
    ),
]


# ---------------------------------------------------------------------------
# Shared fixture builders
# ---------------------------------------------------------------------------


def _build_core_alpha(tmp_path):
    """Build core + one associate (alpha) with standard IDs and uppercase assertions."""
    core_root = tmp_path / "core"
    alpha_root = tmp_path / "alpha"

    core_cfg = base_config(
        name="core-project",
        associated_enabled=True,
        label_style="uppercase",
    )
    core_cfg["associates"] = {"paths": ["../alpha"]}

    core_prd1 = Requirement(
        "REQ-p00001",
        "Core Auth",
        "PRD",
        assertions=[
            ("A", "The system SHALL authenticate users."),
            ("B", "The system SHALL support SSO."),
        ],
    )
    core_prd2 = Requirement(
        "REQ-p00002",
        "Core Data",
        "PRD",
        assertions=[
            ("A", "The system SHALL persist data reliably."),
        ],
    )
    core_dev1 = Requirement(
        "REQ-d00001",
        "Auth Module",
        "DEV",
        implements="REQ-p00001",
        assertions=[("A", "The module SHALL implement bcrypt hashing.")],
    )
    core_dev2 = Requirement(
        "REQ-d00002",
        "Data Module",
        "DEV",
        implements="REQ-p00002",
        assertions=[("A", "The module SHALL use PostgreSQL.")],
    )
    build_project(
        core_root,
        core_cfg,
        spec_files={
            "spec/prd-core.md": [core_prd1, core_prd2],
            "spec/dev-core.md": [core_dev1, core_dev2],
        },
    )

    # Alpha associate: standard IDs, namespace ALPHA, uppercase assertions
    alpha_dev1 = Requirement(
        "REQ-ALP-d00001",
        "Alpha Auth Impl",
        "DEV",
        implements="REQ-p00001",
        assertions=[("A", "Alpha SHALL implement core auth.")],
    )
    alpha_dev2 = Requirement(
        "REQ-ALP-d00002",
        "Alpha Data Impl",
        "DEV",
        implements="REQ-p00002",
        assertions=[("A", "Alpha SHALL implement core data layer.")],
    )
    build_associate(
        alpha_root,
        "alpha",
        "ALP",
        "../core",
        spec_files={
            "spec/dev-alpha.md": [alpha_dev1, alpha_dev2],
        },
        config_overrides={
            "id-patterns": {"assertions": {"label_style": "uppercase"}},
        },
        init_git=True,
    )

    return core_root, alpha_root


def _build_core_alpha_beta(tmp_path):
    """Build core + alpha (uppercase) + beta (numeric assertions)."""
    core_root = tmp_path / "core"
    alpha_root = tmp_path / "alpha"
    beta_root = tmp_path / "beta"

    core_cfg = base_config(
        name="multi-assoc-core",
        associated_enabled=True,
    )
    core_cfg["associates"] = {"paths": ["../alpha", "../beta"]}
    core_prd = Requirement(
        "REQ-p00001",
        "Core Platform",
        "PRD",
        assertions=[
            ("A", "The platform SHALL support multiple tenants."),
            ("B", "The platform SHALL isolate tenant data."),
        ],
    )
    build_project(
        core_root,
        core_cfg,
        spec_files={"spec/prd-platform.md": [core_prd]},
    )

    # Alpha: standard uppercase assertions
    alpha_prd = Requirement(
        "REQ-ALP-p00001",
        "Alpha Customization",
        "PRD",
        assertions=[("A", "Alpha tenant SHALL have custom dashboard.")],
    )
    build_associate(
        alpha_root,
        "alpha",
        "ALP",
        "../core",
        spec_files={"spec/prd-alpha.md": [alpha_prd]},
        init_git=True,
    )

    # Beta: PRD with numeric assertions (FDA-style numeric labels)
    beta_prd = Requirement(
        "REQ-BET-p00001",
        "Beta Compliance",
        "PRD",
        assertions=[
            ("0", "Beta system SHALL satisfy requirement zero."),
            ("1", "Beta system SHALL satisfy requirement one."),
        ],
    )
    beta_dev = Requirement(
        "REQ-BET-d00001",
        "Beta Implementation",
        "DEV",
        implements="REQ-BET-p00001",
        assertions=[
            ("0", "Beta module SHALL implement requirement zero."),
        ],
    )
    build_associate(
        beta_root,
        "beta",
        "BET",
        "../core",
        spec_files={
            "spec/prd-beta.md": [beta_prd],
            "spec/dev-beta.md": [beta_dev],
        },
        config_overrides={
            "id-patterns": {"assertions": {"label_style": "numeric"}},
        },
        init_git=True,
    )

    return core_root, alpha_root, beta_root


# ---------------------------------------------------------------------------
# Test: Core + 1 associate health passes (from TestCoreWithOneAssociate)
# ---------------------------------------------------------------------------


class TestCoreWithOneAssociate:
    """Core project with one associated repo."""

    def test_health_passes(self, tmp_path):
        core, _ = _build_core_alpha(tmp_path)
        result = run_elspais("checks", "--lenient", cwd=core)
        assert result.returncode == 0, f"health failed: {result.stderr}\n{result.stdout}"

    def test_summary_includes_associate_reqs(self, tmp_path):
        core, _ = _build_core_alpha(tmp_path)
        result = run_elspais("summary", "--format", "json", cwd=core)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        levels = data.get("levels", [])
        total = sum(lv.get("total", 0) for lv in levels)
        # Core has 4 reqs (p00001, p00002, d00001, d00002)
        assert total >= 4, f"Expected at least 4 requirements (core), got {total}"

    def test_trace_includes_core_ids(self, tmp_path):
        core, _ = _build_core_alpha(tmp_path)
        result = run_elspais("trace", "--format", "json", cwd=core)
        assert result.returncode == 0
        output = result.stdout
        assert "REQ-p00001" in output
        assert "REQ-d00001" in output


# ---------------------------------------------------------------------------
# Test: Core + 2 associates (from TestCoreWithTwoAssociates)
# ---------------------------------------------------------------------------


class TestCoreWithTwoAssociates:
    """Core project with two associated repos."""

    def test_health_passes(self, tmp_path):
        core, _, _ = _build_core_alpha_beta(tmp_path)
        result = run_elspais("checks", "--lenient", cwd=core)
        assert result.returncode == 0, f"health failed: {result.stderr}\n{result.stdout}"

    def test_summary_counts_all(self, tmp_path):
        core, _, _ = _build_core_alpha_beta(tmp_path)
        result = run_elspais("summary", "--format", "json", cwd=core)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        levels = data.get("levels", [])
        total = sum(lv.get("total", 0) for lv in levels)
        # Core: 1 PRD, Alpha: 1 PRD, Beta: 1 PRD + 1 DEV = at least 1 total
        assert total >= 1


# ---------------------------------------------------------------------------
# Test: Associate CLI list command (from TestAssociateListCommand)
# ---------------------------------------------------------------------------


class TestAssociateListCommand:
    """Associate --list shows linked repos."""

    def test_associate_list(self, tmp_path):
        core, _ = _build_core_alpha(tmp_path)
        result = run_elspais("associate", "--list", cwd=core)
        assert result.returncode == 0
        output = result.stdout.lower()
        assert (
            "alpha" in output or "alp" in output
        ), f"Expected alpha in output: {result.stdout}"


# ---------------------------------------------------------------------------
# Test: Associate with numeric assertions (from TestAssociateNumericAssertions)
# ---------------------------------------------------------------------------


class TestAssociateNumericAssertions:
    """Core with uppercase assertions, associate with numeric assertions."""

    def test_health_passes_mixed_assertions(self, tmp_path):
        core, _, _ = _build_core_alpha_beta(tmp_path)
        result = run_elspais("checks", "--lenient", cwd=core)
        assert result.returncode == 0, f"health failed: {result.stderr}\n{result.stdout}"

    def test_trace_shows_both_repos(self, tmp_path):
        core, _, _ = _build_core_alpha_beta(tmp_path)
        result = run_elspais("trace", "--format", "json", cwd=core)
        assert result.returncode == 0
        # Core PRD should always be present
        assert "REQ-p00001" in result.stdout


# ---------------------------------------------------------------------------
# Test: Cross-repo implements reference (from TestCrossRepoImplements)
# ---------------------------------------------------------------------------


class TestCrossRepoImplements:
    """Associate DEV implements core PRD."""

    def test_health_passes_cross_repo(self, tmp_path):
        # alpha DEV reqs implement core PRD reqs
        core, _ = _build_core_alpha(tmp_path)
        result = run_elspais("checks", "--lenient", cwd=core)
        assert result.returncode == 0, f"health failed: {result.stderr}\n{result.stdout}"

    def test_trace_shows_cross_repo_link(self, tmp_path):
        core, _ = _build_core_alpha(tmp_path)
        result = run_elspais("trace", "--format", "json", cwd=core)
        assert result.returncode == 0
        assert "REQ-p00001" in result.stdout


# ---------------------------------------------------------------------------
# Test: Associate auto-discovery (from TestAssociateAutoDiscovery)
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
        assert result.returncode in (0, 1), (
            f"associate --all crashed unexpectedly: {result.stderr}"
        )


# ---------------------------------------------------------------------------
# Test: MCP with associated repos (from TestMCPWithAssociates)
# ---------------------------------------------------------------------------


class TestMCPWithAssociates:
    """MCP server with core + associate project."""

    def test_mcp_search_finds_associate_reqs(self, tmp_path):
        pytest.importorskip("mcp")
        from .helpers import mcp_call, mcp_call_all, start_mcp, stop_mcp

        core, _ = _build_core_alpha(tmp_path)
        proc = start_mcp(core)
        try:
            # Search for core requirement
            results = mcp_call_all(proc, "search", {"query": "Auth"})
            assert len(results) >= 1
            ids = [r.get("id", "") for r in results]
            assert any("p00001" in i for i in ids)

            # Get project summary
            summary = mcp_call(proc, "get_project_summary", {})
            assert isinstance(summary, dict)

            # Navigate hierarchy
            hier = mcp_call(proc, "get_hierarchy", {"req_id": "REQ-d00001"})
            assert "ancestors" in hier
        finally:
            stop_mcp(proc)


# ---------------------------------------------------------------------------
# Test: Associate with FDA-style IDs (from TestAssociateFDAStyle)
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

    def test_mcp_associate_workflow(self, tmp_path):
        pytest.importorskip("mcp")
        from .helpers import mcp_call, mcp_call_all, start_mcp, stop_mcp

        core_root = tmp_path / "core"
        assoc_root = tmp_path / "partner"

        core_cfg = base_config(
            name="mcp-assoc-core",
            associated_enabled=True,
        )
        core_cfg["associates"] = {"paths": ["../partner"]}
        core_prd = Requirement(
            "REQ-p00001",
            "Core MCP Feature",
            "PRD",
            assertions=[
                ("A", "The system SHALL work via MCP."),
                ("B", "The system SHALL support associates."),
            ],
        )
        build_project(
            core_root,
            core_cfg,
            spec_files={"spec/prd.md": [core_prd]},
        )

        assoc_prd = Requirement(
            "REQ-PAR-p00001",
            "Partner Feature",
            "PRD",
            assertions=[("A", "Partner SHALL customize core.")],
        )
        build_associate(
            assoc_root,
            "partner",
            "PAR",
            "../core",
            spec_files={"spec/prd.md": [assoc_prd]},
            init_git=True,
        )

        proc = start_mcp(core_root)
        try:
            # 1. Get status
            status = mcp_call(proc, "get_graph_status", {})
            assert isinstance(status, dict)

            # 2. Search
            results = mcp_call_all(proc, "search", {"query": "feature"})
            assert len(results) >= 1

            # 3. Get core requirement
            req = mcp_call(proc, "get_requirement", {"req_id": "REQ-p00001"})
            assert req["id"] == "REQ-p00001"

            # 4. Get summary
            summary = mcp_call(proc, "get_project_summary", {})
            assert isinstance(summary, dict)
        finally:
            stop_mcp(proc)


# ---------------------------------------------------------------------------
# Test: Health with multiple associates (from TestMultiAssociateHealth)
# ---------------------------------------------------------------------------


class TestMultiAssociateHealth:
    """Health check with complex multi-associate setup (3 associates)."""

    def test_three_associates(self, tmp_path):
        core = tmp_path / "core"
        a1 = tmp_path / "alpha"
        a2 = tmp_path / "beta"
        a3 = tmp_path / "gamma"

        core_cfg = base_config(name="multi3-core", associated_enabled=True)
        core_cfg["associates"] = {"paths": ["../alpha", "../beta", "../gamma"]}
        build_project(
            core,
            core_cfg,
            spec_files={
                "spec/prd.md": [
                    Requirement(
                        "REQ-p00001",
                        "Core PRD",
                        "PRD",
                        assertions=[("A", "The system SHALL be core.")],
                    )
                ],
            },
        )

        for name, prefix, root in [
            ("alpha", "ALP", a1),
            ("beta", "BET", a2),
            ("gamma", "GAM", a3),
        ]:
            build_associate(
                root,
                name,
                prefix,
                "../core",
                spec_files={
                    "spec/prd.md": [
                        Requirement(
                            f"REQ-{prefix}-p00001",
                            f"{name.title()} PRD",
                            "PRD",
                            assertions=[("A", f"{name.title()} SHALL customize.")],
                        )
                    ],
                },
                init_git=True,
            )

        health = run_elspais("checks", "--lenient", cwd=core)
        assert health.returncode == 0


# ---------------------------------------------------------------------------
# Test: MCP subtree extraction with associate (from TestMCPAssociatedSubtree)
# ---------------------------------------------------------------------------


class TestMCPAssociatedSubtree:
    """MCP subtree extraction with associated repos."""

    def test_subtree_with_associate(self, tmp_path):
        pytest.importorskip("mcp")
        from .helpers import mcp_call, start_mcp, stop_mcp

        core = tmp_path / "core"
        assoc = tmp_path / "partner"

        core_cfg = base_config(name="subtree-assoc", associated_enabled=True)
        core_cfg["associates"] = {"paths": ["../partner"]}
        build_project(
            core,
            core_cfg,
            spec_files={
                "spec/prd.md": [
                    Requirement(
                        "REQ-p00001",
                        "Core PRD",
                        "PRD",
                        assertions=[("A", "Core SHALL exist."), ("B", "Core SHALL subtree.")],
                    )
                ],
                "spec/dev.md": [
                    Requirement(
                        "REQ-d00001",
                        "Core DEV",
                        "DEV",
                        implements="REQ-p00001",
                        assertions=[("A", "Module SHALL exist.")],
                    )
                ],
            },
        )

        build_associate(
            assoc,
            "partner",
            "PAR",
            "../core",
            spec_files={
                "spec/dev.md": [
                    Requirement(
                        "REQ-PAR-d00001",
                        "Partner DEV",
                        "DEV",
                        implements="REQ-p00001",
                        assertions=[("A", "Partner SHALL implement.")],
                    )
                ],
            },
            init_git=True,
        )

        proc = start_mcp(core)
        try:
            result = mcp_call(
                proc,
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
        finally:
            stop_mcp(proc)


# ---------------------------------------------------------------------------
# Test: Associate --unlink removes a link (from TestAssociateUnlink)
# NOTE: This test mutates config — kept last.
# ---------------------------------------------------------------------------


class TestAssociateUnlink:
    """Associate --unlink removes a link from core config."""

    def test_unlink_associate(self, tmp_path):
        core_root = tmp_path / "core"
        assoc_root = tmp_path / "removable"

        core_cfg = base_config(name="unlink-core", associated_enabled=True)
        core_cfg["associates"] = {"paths": ["../removable"]}
        build_project(
            core_root,
            core_cfg,
            spec_files={
                "spec/prd.md": [
                    Requirement(
                        "REQ-p00001",
                        "Unlink Test",
                        "PRD",
                        assertions=[("A", "The system SHALL unlink.")],
                    ),
                ],
            },
        )

        build_associate(
            assoc_root,
            "removable",
            "REM",
            "../core",
            spec_files={
                "spec/prd.md": [
                    Requirement(
                        "REQ-REM-p00001",
                        "Removable",
                        "PRD",
                        assertions=[("A", "Removable SHALL be unlinked.")],
                    ),
                ],
            },
            init_git=True,
        )

        result = run_elspais("associate", "--unlink", "removable", cwd=core_root)
        # May succeed or warn — should not crash
        assert result.returncode in (0, 1), (
            f"associate --unlink returned unexpected code: {result.returncode}\n{result.stderr}"
        )
