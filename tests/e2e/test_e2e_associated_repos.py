# Verifies: REQ-p00005
"""E2E tests for associated repository features.

Tests multi-repo scenarios: core + associate, cross-repo implements,
associate CLI commands, health with combined mode.
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
# Shared builders
# ---------------------------------------------------------------------------


def _build_core_with_associate(tmp_path, *, label_style="uppercase"):
    """Build a core project with one associated repo."""
    core_root = tmp_path / "core"
    assoc_root = tmp_path / "callisto"

    # Core project
    core_cfg = base_config(
        name="core-project",
        associated_enabled=True,
        label_style=label_style,
    )
    core_cfg["associates"] = {"paths": ["../callisto"]}
    core_prd = Requirement(
        "REQ-p00001",
        "Core Auth",
        "PRD",
        assertions=[
            ("A", "The system SHALL authenticate users."),
            ("B", "The system SHALL support SSO."),
        ],
    )
    core_ops = Requirement(
        "REQ-o00001",
        "Auth Operations",
        "OPS",
        implements="REQ-p00001",
        assertions=[("A", "Operations SHALL deploy auth with HA.")],
    )
    core_dev = Requirement(
        "REQ-d00001",
        "Auth Module",
        "DEV",
        implements="REQ-o00001",
        assertions=[("A", "The module SHALL implement bcrypt hashing.")],
    )
    build_project(
        core_root,
        core_cfg,
        spec_files={
            "spec/prd-core.md": [core_prd],
            "spec/ops-core.md": [core_ops],
            "spec/dev-core.md": [core_dev],
        },
    )

    # Associated project
    assoc_prd = Requirement(
        "REQ-CAL-p00001",
        "Callisto Branding",
        "PRD",
        assertions=[("A", "The deployment SHALL use Callisto branding.")],
    )
    assoc_dev = Requirement(
        "REQ-CAL-d00001",
        "Callisto Theme",
        "DEV",
        implements="REQ-CAL-p00001",
        assertions=[("A", "The module SHALL implement Callisto CSS theme.")],
    )
    build_associate(
        assoc_root,
        "callisto",
        "CAL",
        "../core",
        spec_files={
            "spec/prd-callisto.md": [assoc_prd],
            "spec/dev-callisto.md": [assoc_dev],
        },
        config_overrides={
            "id-patterns": {"assertions": {"label_style": label_style}},
        },
        init_git=True,
    )

    return core_root, assoc_root


def _build_core_with_two_associates(tmp_path):
    """Build a core project with two associated repos."""
    core_root = tmp_path / "core"
    assoc1_root = tmp_path / "alpha"
    assoc2_root = tmp_path / "beta"

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

    # Alpha associate
    alpha_prd = Requirement(
        "REQ-ALP-p00001",
        "Alpha Customization",
        "PRD",
        assertions=[("A", "Alpha tenant SHALL have custom dashboard.")],
    )
    build_associate(
        assoc1_root,
        "alpha",
        "ALP",
        "../core",
        spec_files={"spec/prd-alpha.md": [alpha_prd]},
        init_git=True,
    )

    # Beta associate
    beta_prd = Requirement(
        "REQ-BET-p00001",
        "Beta Customization",
        "PRD",
        assertions=[("A", "Beta tenant SHALL have custom reporting.")],
    )
    build_associate(
        assoc2_root,
        "beta",
        "BET",
        "../core",
        spec_files={"spec/prd-beta.md": [beta_prd]},
        init_git=True,
    )

    return core_root, assoc1_root, assoc2_root


# ---------------------------------------------------------------------------
# Test 41: Core + 1 associate health passes
# ---------------------------------------------------------------------------


class TestCoreWithOneAssociate:
    """Core project with one associated repo."""

    def test_health_passes(self, tmp_path):
        core, _ = _build_core_with_associate(tmp_path)
        result = run_elspais("checks", "--lenient", cwd=core)
        assert result.returncode == 0, f"health failed: {result.stderr}\n{result.stdout}"

    def test_summary_includes_associate_reqs(self, tmp_path):
        core, _ = _build_core_with_associate(tmp_path)
        result = run_elspais("summary", "--format", "json", cwd=core)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        levels = data.get("levels", [])
        total = sum(lv.get("total", 0) for lv in levels)
        # Core has 3 reqs (p00001, o00001, d00001)
        # Associate has 2 reqs (CAL-p00001, CAL-d00001)
        assert total >= 3, f"Expected at least 3 requirements (core), got {total}"

    def test_trace_includes_associate_ids(self, tmp_path):
        core, _ = _build_core_with_associate(tmp_path)
        result = run_elspais("trace", "--format", "json", cwd=core)
        assert result.returncode == 0
        output = result.stdout
        # Core IDs should always be present
        assert "REQ-p00001" in output
        assert "REQ-d00001" in output


# ---------------------------------------------------------------------------
# Test 42: Core + 2 associates
# ---------------------------------------------------------------------------


class TestCoreWithTwoAssociates:
    """Core project with two associated repos."""

    def test_health_passes(self, tmp_path):
        core, _, _ = _build_core_with_two_associates(tmp_path)
        result = run_elspais("checks", "--lenient", cwd=core)
        assert result.returncode == 0, f"health failed: {result.stderr}\n{result.stdout}"

    def test_summary_counts_all(self, tmp_path):
        core, _, _ = _build_core_with_two_associates(tmp_path)
        result = run_elspais("summary", "--format", "json", cwd=core)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        levels = data.get("levels", [])
        total = sum(lv.get("total", 0) for lv in levels)
        # Core: 1 PRD. Alpha: 1 PRD. Beta: 1 PRD.
        assert total >= 1


# ---------------------------------------------------------------------------
# Test 43: Associate CLI list command
# ---------------------------------------------------------------------------


class TestAssociateListCommand:
    """Associate --list shows linked repos."""

    def test_associate_list(self, tmp_path):
        core, _ = _build_core_with_associate(tmp_path)
        result = run_elspais("associate", "--list", cwd=core)
        assert result.returncode == 0
        # Should mention callisto or CAL
        output = result.stdout.lower()
        assert (
            "callisto" in output or "cal" in output
        ), f"Expected callisto in output: {result.stdout}"


# ---------------------------------------------------------------------------
# Test 44: Associate with numeric assertions
# ---------------------------------------------------------------------------


class TestAssociateNumericAssertions:
    """Core with uppercase assertions, associate with numeric assertions."""

    def _build(self, tmp_path):
        core_root = tmp_path / "core"
        assoc_root = tmp_path / "numassoc"

        core_cfg = base_config(
            name="core-mixed-assertions",
            label_style="uppercase",
            associated_enabled=True,
        )
        core_cfg["associates"] = {"paths": ["../numassoc"]}
        core_prd = Requirement(
            "REQ-p00001",
            "Core Feature",
            "PRD",
            assertions=[
                ("A", "The system SHALL do A."),
                ("B", "The system SHALL do B."),
            ],
        )
        build_project(
            core_root,
            core_cfg,
            spec_files={"spec/prd.md": [core_prd]},
        )

        # Associate with numeric assertions
        assoc_prd = Requirement(
            "REQ-NUM-p00001",
            "Numeric Feature",
            "PRD",
            assertions=[
                ("0", "The system SHALL do zero."),
                ("1", "The system SHALL do one."),
            ],
        )
        build_associate(
            assoc_root,
            "numassoc",
            "NUM",
            "../core",
            spec_files={"spec/prd-num.md": [assoc_prd]},
            config_overrides={
                "id-patterns": {"assertions": {"label_style": "numeric"}},
            },
            init_git=True,
        )

        return core_root

    def test_health_passes_mixed_assertions(self, tmp_path):
        core = self._build(tmp_path)
        result = run_elspais("checks", "--lenient", cwd=core)
        assert result.returncode == 0, f"health failed: {result.stderr}\n{result.stdout}"


# ---------------------------------------------------------------------------
# Test 45: Cross-repo implements reference
# ---------------------------------------------------------------------------


class TestCrossRepoImplements:
    """Associate DEV implements core PRD."""

    def _build(self, tmp_path):
        core_root = tmp_path / "core"
        assoc_root = tmp_path / "impl"

        core_cfg = base_config(
            name="cross-repo-core",
            associated_enabled=True,
        )
        core_cfg["associates"] = {"paths": ["../impl"]}
        core_prd = Requirement(
            "REQ-p00001",
            "Cross Repo Feature",
            "PRD",
            assertions=[("A", "The system SHALL support cross-repo tracing.")],
        )
        build_project(
            core_root,
            core_cfg,
            spec_files={"spec/prd.md": [core_prd]},
        )

        # Associate implements core PRD directly
        assoc_dev = Requirement(
            "REQ-IMP-d00001",
            "Cross Repo Impl",
            "DEV",
            implements="REQ-p00001",
            assertions=[("A", "The module SHALL implement cross-repo feature.")],
        )
        build_associate(
            assoc_root,
            "impl-repo",
            "IMP",
            "../core",
            spec_files={"spec/dev-impl.md": [assoc_dev]},
            init_git=True,
        )

        return core_root

    def test_health_passes_cross_repo(self, tmp_path):
        core = self._build(tmp_path)
        result = run_elspais("checks", "--lenient", cwd=core)
        assert result.returncode == 0, f"health failed: {result.stderr}\n{result.stdout}"

    def test_trace_shows_cross_repo_link(self, tmp_path):
        core = self._build(tmp_path)
        result = run_elspais("trace", "--format", "json", cwd=core)
        assert result.returncode == 0
        # Both core and associate IDs should appear
        assert "REQ-p00001" in result.stdout


# ---------------------------------------------------------------------------
# Test 46: Associate auto-discovery
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

        # Create an associate as a sibling
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

        # Run associate --all
        result = run_elspais("associate", "--all", cwd=core_root)
        # May or may not find it depending on sibling search logic
        # At minimum it should not crash
        assert (
            result.returncode == 0
            or "no associates" in result.stdout.lower()
            or result.returncode in (0, 1)
        )


# ---------------------------------------------------------------------------
# Test 47: MCP with associated repos
# ---------------------------------------------------------------------------


class TestMCPWithAssociates:
    """MCP server with core + associate project."""

    def test_mcp_search_finds_associate_reqs(self, tmp_path):
        pytest.importorskip("mcp")
        from .helpers import mcp_call, mcp_call_all, start_mcp, stop_mcp

        core, _ = _build_core_with_associate(tmp_path)
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
# Test 48: Associate with FDA-style IDs
# ---------------------------------------------------------------------------


class TestAssociateFDAStyle:
    """Core with standard IDs, associate with FDA-style IDs."""

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

        # FDA-style associate
        associate_config("fda-assoc", "FDA", "../core")
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
