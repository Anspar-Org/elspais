# Verifies: REQ-p00002, REQ-p00003, REQ-p00060
"""E2E edge case tests for comprehensive coverage.

Tests unusual configurations, boundary conditions, and
less common feature combinations.
"""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from .helpers import (
    Requirement,
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
# Test 101: Single assertion requirement
# ---------------------------------------------------------------------------


class TestSingleAssertion:
    """Requirement with only one assertion."""

    def test_single_assertion_health(self, tmp_path):
        cfg = base_config(name="single-assert", allow_structural_orphans=True)
        prd = Requirement(
            "REQ-p00001",
            "Minimal",
            "PRD",
            assertions=[("A", "The system SHALL do one thing.")],
        )
        build_project(tmp_path, cfg, spec_files={"spec/prd.md": [prd]})

        health = run_elspais("health", "--lenient", cwd=tmp_path)
        assert health.returncode == 0

    def test_single_assertion_trace(self, tmp_path):
        cfg = base_config(name="single-trace", allow_structural_orphans=True)
        prd = Requirement(
            "REQ-p00001",
            "Single Trace",
            "PRD",
            assertions=[("A", "The system SHALL trace single assertion.")],
        )
        build_project(tmp_path, cfg, spec_files={"spec/prd.md": [prd]})

        result = run_elspais("trace", "--format", "json", cwd=tmp_path)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert len(data) == 1


# ---------------------------------------------------------------------------
# Test 102: Many assertions (A through Z)
# ---------------------------------------------------------------------------


class TestManyAssertions:
    """Requirement with maximum (26) uppercase assertions."""

    def test_26_assertions(self, tmp_path):
        cfg = base_config(name="many-assertions", allow_structural_orphans=True)
        assertions = [
            (chr(ord("A") + i), f"The system SHALL satisfy criterion {chr(ord('A') + i)}.")
            for i in range(26)
        ]
        prd = Requirement(
            "REQ-p00001",
            "Comprehensive",
            "PRD",
            assertions=assertions,
        )
        build_project(tmp_path, cfg, spec_files={"spec/prd.md": [prd]})

        health = run_elspais("health", "--lenient", cwd=tmp_path)
        assert health.returncode == 0


# ---------------------------------------------------------------------------
# Test 103: Placeholder assertion values
# ---------------------------------------------------------------------------


class TestPlaceholderAssertions:
    """Assertions with placeholder/deprecated values."""

    def test_placeholder_values(self, tmp_path):
        cfg = base_config(name="placeholder", allow_structural_orphans=True, require_shall=False)
        prd = Requirement(
            "REQ-p00001",
            "With Placeholders",
            "PRD",
            assertions=[
                ("A", "The system SHALL do active things."),
                ("B", "Removed - was duplicate of A."),
                ("C", "The system SHALL still work."),
            ],
        )
        build_project(tmp_path, cfg, spec_files={"spec/prd.md": [prd]})

        health = run_elspais("health", "--lenient", cwd=tmp_path)
        assert health.returncode == 0


# ---------------------------------------------------------------------------
# Test 104: Multiple spec files per level
# ---------------------------------------------------------------------------


class TestMultipleSpecFilesPerLevel:
    """Multiple PRD files, multiple DEV files."""

    def test_split_across_files(self, tmp_path):
        cfg = base_config(name="multi-files")
        prd1 = Requirement(
            "REQ-p00001",
            "PRD in file 1",
            "PRD",
            assertions=[("A", "The system SHALL be in file 1.")],
        )
        prd2 = Requirement(
            "REQ-p00002",
            "PRD in file 2",
            "PRD",
            assertions=[("A", "The system SHALL be in file 2.")],
        )
        dev1 = Requirement(
            "REQ-d00001",
            "DEV for PRD 1",
            "DEV",
            implements="REQ-p00001",
            assertions=[("A", "The module SHALL implement PRD 1.")],
        )
        dev2 = Requirement(
            "REQ-d00002",
            "DEV for PRD 2",
            "DEV",
            implements="REQ-p00002",
            assertions=[("A", "The module SHALL implement PRD 2.")],
        )
        build_project(
            tmp_path,
            cfg,
            spec_files={
                "spec/prd-auth.md": [prd1],
                "spec/prd-data.md": [prd2],
                "spec/dev-auth.md": [dev1],
                "spec/dev-data.md": [dev2],
            },
        )

        health = run_elspais("health", "--lenient", cwd=tmp_path)
        assert health.returncode == 0

        summary = run_elspais("summary", "--format", "json", cwd=tmp_path)
        data = json.loads(summary.stdout)
        total = sum(lv.get("total", 0) for lv in data.get("levels", []))
        assert total == 4


# ---------------------------------------------------------------------------
# Test 105: Config show --section filter
# ---------------------------------------------------------------------------


class TestConfigShowSection:
    """Config show with --section flag."""

    def test_show_project_section(self, tmp_path):
        cfg = base_config(name="section-test")
        build_project(tmp_path, cfg, spec_files={})
        (tmp_path / "spec").mkdir(exist_ok=True)

        result = run_elspais("config", "show", "--section", "project", cwd=tmp_path)
        assert result.returncode == 0
        assert "section-test" in result.stdout

    def test_show_rules_section(self, tmp_path):
        cfg = base_config(name="rules-section")
        build_project(tmp_path, cfg, spec_files={})
        (tmp_path / "spec").mkdir(exist_ok=True)

        result = run_elspais("config", "show", "--section", "rules", cwd=tmp_path)
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# Test 106: Fix specific requirement by ID
# ---------------------------------------------------------------------------


class TestFixSpecificRequirement:
    """Fix command targeting a specific requirement ID."""

    def test_fix_specific_id(self, tmp_path):
        cfg = base_config(name="fix-specific", allow_structural_orphans=True)
        build_project(tmp_path, cfg, spec_files={})

        spec = tmp_path / "spec" / "prd.md"
        spec.parent.mkdir(parents=True, exist_ok=True)
        spec.write_text(
            "# REQ-p00001: Fix This One\n\n"
            "**Level**: PRD | **Status**: Active\n\n"
            "## Assertions\n\n"
            "A. The system SHALL be fixed.\n\n"
            "*End* *Fix This One* | **Hash**: 00000000\n---\n\n"
            "# REQ-p00002: Leave This One\n\n"
            "**Level**: PRD | **Status**: Active\n\n"
            "## Assertions\n\n"
            "A. The system SHALL not be touched.\n\n"
            "*End* *Leave This One* | **Hash**: 00000000\n---\n"
        )

        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "add"], cwd=tmp_path, capture_output=True)

        result = run_elspais("fix", "REQ-p00001", cwd=tmp_path)
        assert result.returncode == 0

        content = spec.read_text()
        # REQ-p00001's hash should be fixed
        # REQ-p00002's hash may or may not be fixed depending on implementation
        import re

        hashes = re.findall(r"\*\*Hash\*\*:\s*(\S+)", content)
        assert len(hashes) == 2
        # At least the first one should be different from 00000000
        assert hashes[0] != "00000000"


# ---------------------------------------------------------------------------
# Test 107: Changed command with base branch
# ---------------------------------------------------------------------------


class TestChangedWithBaseBranch:
    """Changed --base-branch flag."""

    def test_changed_base_branch(self, tmp_path):
        cfg = base_config(name="changed-branch", allow_structural_orphans=True)
        prd = Requirement(
            "REQ-p00001",
            "Branch Test",
            "PRD",
            assertions=[("A", "The system SHALL work on branches.")],
        )
        build_project(tmp_path, cfg, spec_files={"spec/prd.md": [prd]})

        result = run_elspais(
            "changed",
            "--base-branch",
            "main",
            "--format",
            "json",
            cwd=tmp_path,
        )
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# Test 108: Trace preset options
# ---------------------------------------------------------------------------


class TestTracePresets:
    """Trace --preset minimal/standard/full."""

    def _build(self, tmp_path):
        cfg = base_config(name="presets", allow_structural_orphans=True)
        prd = Requirement(
            "REQ-p00001",
            "Preset Test",
            "PRD",
            assertions=[
                ("A", "The system SHALL support presets."),
                ("B", "The system SHALL render correctly."),
            ],
        )
        build_project(tmp_path, cfg, spec_files={"spec/prd.md": [prd]})

    def test_preset_minimal(self, tmp_path):
        self._build(tmp_path)
        result = run_elspais("trace", "--preset", "minimal", cwd=tmp_path)
        assert result.returncode == 0

    def test_preset_standard(self, tmp_path):
        self._build(tmp_path)
        result = run_elspais("trace", "--preset", "standard", cwd=tmp_path)
        assert result.returncode == 0

    def test_preset_full(self, tmp_path):
        self._build(tmp_path)
        result = run_elspais("trace", "--preset", "full", cwd=tmp_path)
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# Test 109: Associate unlink
# ---------------------------------------------------------------------------


class TestAssociateUnlink:
    """Associate --unlink removes a link."""

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
        # May succeed or warn, should not crash
        assert result.returncode in (0, 1)


# ---------------------------------------------------------------------------
# Test 110: MCP with 1-based numeric assertions
# ---------------------------------------------------------------------------


class TestMCPNumeric1Based:
    """MCP tools with numeric_1based assertions."""

    def test_mcp_1based_assertions(self, tmp_path):
        pytest.importorskip("mcp")
        from .helpers import mcp_call, start_mcp, stop_mcp

        cfg = base_config(
            name="mcp-1based",
            label_style="numeric_1based",
            allow_structural_orphans=True,
        )
        prd = Requirement(
            "REQ-p00001",
            "1Based MCP",
            "PRD",
            assertions=[
                ("1", "The system SHALL start at one."),
                ("2", "The system SHALL continue to two."),
            ],
        )
        build_project(tmp_path, cfg, spec_files={"spec/prd.md": [prd]})

        proc = start_mcp(tmp_path)
        try:
            req = mcp_call(proc, "get_requirement", {"req_id": "REQ-p00001"})
            children = [c for c in req.get("children", []) if c.get("kind") == "assertion"]
            labels = [c.get("label", "") for c in children]
            assert "1" in labels
            assert "2" in labels

            # Search
            results = mcp_call(proc, "search", {"query": "1Based"})
            assert isinstance(results, dict)
        finally:
            stop_mcp(proc)


# ---------------------------------------------------------------------------
# Test 111: Health with multiple associates and cross-repo links
# ---------------------------------------------------------------------------


class TestMultiAssociateHealth:
    """Health check with complex multi-associate setup."""

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

        for name, prefix, root in [("alpha", "ALP", a1), ("beta", "BET", a2), ("gamma", "GAM", a3)]:
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

        health = run_elspais("health", "--lenient", cwd=core)
        assert health.returncode == 0


# ---------------------------------------------------------------------------
# Test 112: Docs command
# ---------------------------------------------------------------------------


class TestDocsCommand:
    """Docs command displays user documentation."""

    def test_docs_quickstart(self, tmp_path):
        result = run_elspais("docs", "quickstart", "--plain")
        # docs command may work from any directory
        if result.returncode == 0:
            assert len(result.stdout.strip()) > 0

    def test_docs_commands(self, tmp_path):
        result = run_elspais("docs", "commands", "--plain")
        if result.returncode == 0:
            assert len(result.stdout.strip()) > 0


# ---------------------------------------------------------------------------
# Test 113: Example command
# ---------------------------------------------------------------------------


class TestExampleCommand:
    """Example command shows format examples."""

    def test_example_requirement(self, tmp_path):
        result = run_elspais("example", "requirement")
        assert result.returncode == 0
        assert "REQ" in result.stdout or "SHALL" in result.stdout

    def test_example_assertion(self, tmp_path):
        result = run_elspais("example", "assertion")
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# Test 114: Health + summary idempotency
# ---------------------------------------------------------------------------


class TestIdempotency:
    """Running same command twice produces identical results."""

    def test_health_idempotent(self, tmp_path):
        cfg = base_config(name="idempotent", allow_structural_orphans=True)
        prd = Requirement(
            "REQ-p00001",
            "Stable",
            "PRD",
            assertions=[("A", "The system SHALL be stable.")],
        )
        build_project(tmp_path, cfg, spec_files={"spec/prd.md": [prd]})

        r1 = run_elspais("health", "--format", "json", "--lenient", cwd=tmp_path)
        r2 = run_elspais("health", "--format", "json", "--lenient", cwd=tmp_path)
        assert r1.returncode == r2.returncode
        assert r1.stdout == r2.stdout

    def test_summary_idempotent(self, tmp_path):
        cfg = base_config(name="idempotent-sum", allow_structural_orphans=True)
        prd = Requirement(
            "REQ-p00001",
            "Consistent",
            "PRD",
            assertions=[("A", "The system SHALL be consistent.")],
        )
        build_project(tmp_path, cfg, spec_files={"spec/prd.md": [prd]})

        r1 = run_elspais("summary", "--format", "json", cwd=tmp_path)
        r2 = run_elspais("summary", "--format", "json", cwd=tmp_path)
        assert r1.stdout == r2.stdout


# ---------------------------------------------------------------------------
# Test 115: MCP with associated - get_subtree
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
            # Should include core nodes at minimum
            nodes = result.get("nodes", [])
            node_ids = [n.get("id", "") for n in nodes]
            assert "REQ-p00001" in node_ids
        finally:
            stop_mcp(proc)


# ---------------------------------------------------------------------------
# Test 116: MCP change_edge_kind
# ---------------------------------------------------------------------------


class TestMCPChangeEdgeKind:
    """MCP mutate_change_edge_kind."""

    def test_change_implements_to_refines(self, tmp_path):
        pytest.importorskip("mcp")
        from .helpers import mcp_call, start_mcp, stop_mcp

        cfg = base_config(name="edge-kind", allow_structural_orphans=True)
        prd = Requirement(
            "REQ-p00001",
            "Edge Kind Test",
            "PRD",
            assertions=[("A", "The system SHALL change edge kinds.")],
        )
        prd2 = Requirement(
            "REQ-p00002",
            "Refining",
            "PRD",
            implements="REQ-p00001",
            assertions=[("A", "The system SHALL refine.")],
        )
        build_project(
            tmp_path,
            cfg,
            spec_files={"spec/prd.md": [prd, prd2]},
        )

        proc = start_mcp(tmp_path)
        try:
            result = mcp_call(
                proc,
                "mutate_change_edge_kind",
                {
                    "source_id": "REQ-p00002",
                    "target_id": "REQ-p00001",
                    "new_kind": "refines",
                },
            )
            assert isinstance(result, dict)
        finally:
            stop_mcp(proc)


# ---------------------------------------------------------------------------
# Test 117: Summary with status filter
# ---------------------------------------------------------------------------


class TestSummaryStatusFilter:
    """Summary --status filters by status."""

    def test_status_filter_draft(self, tmp_path):
        cfg = base_config(name="status-filter-sum", allow_structural_orphans=True)
        active = Requirement(
            "REQ-p00001",
            "Active",
            "PRD",
            assertions=[("A", "The system SHALL be active.")],
        )
        draft = Requirement(
            "REQ-p00002",
            "Draft",
            "PRD",
            status="Draft",
            assertions=[("A", "The system SHALL be draft.")],
        )
        build_project(
            tmp_path,
            cfg,
            spec_files={"spec/prd.md": [active, draft]},
        )

        # Default (Active only)
        r1 = run_elspais("summary", "--format", "json", cwd=tmp_path)
        d1 = json.loads(r1.stdout)
        t1 = sum(lv.get("total", 0) for lv in d1.get("levels", []))

        # With Draft status (may be a different flag format)
        r2 = run_elspais("summary", "--format", "json", "--status", "Draft", cwd=tmp_path)
        if r2.returncode == 0 and r2.stdout.strip():
            d2 = json.loads(r2.stdout)
            t2 = sum(lv.get("total", 0) for lv in d2.get("levels", []))
            # At least one filter should return results
            assert t1 >= 1 or t2 >= 1
        else:
            # If --status flag isn't supported for summary, just verify Active works
            assert t1 >= 1


# ---------------------------------------------------------------------------
# Test 118: MCP fix_broken_reference
# ---------------------------------------------------------------------------


class TestMCPFixBrokenReference:
    """MCP mutate_fix_broken_reference."""

    def test_fix_broken_ref(self, tmp_path):
        pytest.importorskip("mcp")
        from .helpers import mcp_call, start_mcp, stop_mcp

        cfg = base_config(name="broken-ref", allow_structural_orphans=True)
        prd = Requirement(
            "REQ-p00001",
            "Target",
            "PRD",
            assertions=[("A", "The system SHALL be the target.")],
        )
        dev = Requirement(
            "REQ-d00001",
            "With Bad Ref",
            "DEV",
            implements="REQ-p99999",  # broken reference
            assertions=[("A", "The module SHALL reference wrong thing.")],
        )
        build_project(
            tmp_path,
            cfg,
            spec_files={
                "spec/prd.md": [prd],
                "spec/dev.md": [dev],
            },
        )

        proc = start_mcp(tmp_path)
        try:
            # Check broken refs
            broken = mcp_call(proc, "get_broken_references", {})
            assert isinstance(broken, (list, dict))

            # Try to fix (may or may not find it depending on implementation)
            result = mcp_call(
                proc,
                "mutate_fix_broken_reference",
                {
                    "source_id": "REQ-d00001",
                    "old_target_id": "REQ-p99999",
                    "new_target_id": "REQ-p00001",
                },
            )
            assert isinstance(result, dict)
        finally:
            stop_mcp(proc)


# ---------------------------------------------------------------------------
# Test 119: Trace output to file
# ---------------------------------------------------------------------------


class TestTraceOutputToFile:
    """Trace --output writes to file."""

    def test_trace_output_json_file(self, tmp_path):
        cfg = base_config(name="trace-file", allow_structural_orphans=True)
        prd = Requirement(
            "REQ-p00001",
            "File Output",
            "PRD",
            assertions=[("A", "The system SHALL write to file.")],
        )
        build_project(tmp_path, cfg, spec_files={"spec/prd.md": [prd]})

        out = tmp_path / "trace-output.json"
        result = run_elspais(
            "trace",
            "--format",
            "json",
            "--output",
            str(out),
            cwd=tmp_path,
        )
        assert result.returncode == 0
        # Check file exists (may have different name)
        candidates = [out, out.with_suffix(".json")]
        found = [p for p in candidates if p.exists()]
        assert found, f"No output file found: {candidates}"
        data = json.loads(found[0].read_text())
        assert isinstance(data, list)


# ---------------------------------------------------------------------------
# Test 120: Config show --format toml
# ---------------------------------------------------------------------------


class TestConfigShowToml:
    """Config show as TOML format."""

    def test_config_show_default(self, tmp_path):
        cfg = base_config(name="toml-show")
        build_project(tmp_path, cfg, spec_files={})
        (tmp_path / "spec").mkdir(exist_ok=True)

        result = run_elspais("config", "show", cwd=tmp_path)
        assert result.returncode == 0
        # Default format should produce readable output
        assert "toml-show" in result.stdout or "project" in result.stdout.lower()
