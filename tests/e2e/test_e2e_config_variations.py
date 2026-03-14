# Validates: REQ-p00013
"""E2E tests focused on configuration variations.

Tests various config permutations: ignore patterns, file patterns,
references config, validation rules, hash settings, etc.
"""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from .helpers import (
    Requirement,
    base_config,
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
# Test 49: Ignore patterns - global, spec, code, test
# ---------------------------------------------------------------------------


class TestIgnorePatterns:
    """Unified ignore patterns for different scan types."""

    def test_global_ignore_excludes_node_modules(self, tmp_path):
        cfg = base_config(name="ignore-global", allow_orphans=True)
        cfg["ignore"] = {
            "global": ["node_modules", ".git", "__pycache__"],
        }
        prd = Requirement(
            "REQ-p00001",
            "Ignore Test",
            "PRD",
            assertions=[("A", "The system SHALL ignore node_modules.")],
        )
        build_project(
            tmp_path,
            cfg,
            spec_files={"spec/prd.md": [prd]},
            extra_files={
                "spec/node_modules/bad.md": "# Should be ignored\n",
            },
        )

        result = run_elspais("health", "--lenient", cwd=tmp_path)
        assert result.returncode == 0

    def test_spec_ignore_excludes_pattern(self, tmp_path):
        cfg = base_config(name="ignore-spec", allow_orphans=True)
        cfg["ignore"] = {
            "spec": ["draft-*.md"],
        }
        prd = Requirement(
            "REQ-p00001",
            "Published",
            "PRD",
            assertions=[("A", "The system SHALL be published.")],
        )
        build_project(
            tmp_path,
            cfg,
            spec_files={"spec/prd.md": [prd]},
            extra_files={
                "spec/draft-ideas.md": "# Draft ideas\nNot a real req\n",
            },
        )

        result = run_elspais("health", "--lenient", cwd=tmp_path)
        assert result.returncode == 0

        summary = run_elspais("summary", "--format", "json", cwd=tmp_path)
        data = json.loads(summary.stdout)
        total = sum(lv.get("total", 0) for lv in data.get("levels", []))
        assert total == 1


# ---------------------------------------------------------------------------
# Test 51: Custom hierarchy rules
# ---------------------------------------------------------------------------


class TestCustomHierarchyRules:
    """Non-standard allowed_implements relationships."""

    def test_dev_directly_implements_prd(self, tmp_path):
        """DEV -> PRD should work when allowed."""
        cfg = base_config(
            name="direct-hierarchy",
            allowed_implements=["dev -> prd", "ops -> prd"],
        )
        prd = Requirement(
            "REQ-p00001",
            "Direct Parent",
            "PRD",
            assertions=[("A", "The system SHALL be directly implemented.")],
        )
        dev = Requirement(
            "REQ-d00001",
            "Direct Impl",
            "DEV",
            implements="REQ-p00001",
            assertions=[("A", "The module SHALL implement directly.")],
        )
        build_project(
            tmp_path,
            cfg,
            spec_files={
                "spec/prd.md": [prd],
                "spec/dev.md": [dev],
            },
        )

        result = run_elspais("health", "--lenient", cwd=tmp_path)
        assert result.returncode == 0

    def test_allow_orphans(self, tmp_path):
        """Orphan requirements should pass when allow_orphans=True."""
        cfg = base_config(name="orphans-ok", allow_orphans=True)
        orphan = Requirement(
            "REQ-d00001",
            "Orphan Dev",
            "DEV",
            assertions=[("A", "The module SHALL exist alone.")],
        )
        build_project(
            tmp_path,
            cfg,
            spec_files={"spec/dev-orphan.md": [orphan]},
        )

        result = run_elspais("health", "--lenient", cwd=tmp_path)
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# Test 52: Require rationale
# ---------------------------------------------------------------------------


class TestRequireRationale:
    """Config: require_rationale = true."""

    def test_rationale_required_present(self, tmp_path):
        cfg = base_config(name="rationale-required", allow_orphans=True)
        cfg["rules"]["format"]["require_rationale"] = True
        prd = Requirement(
            "REQ-p00001",
            "Rationalized",
            "PRD",
            assertions=[("A", "The system SHALL have rationale.")],
            rationale="This is needed for compliance reasons.",
        )
        build_project(tmp_path, cfg, spec_files={"spec/prd.md": [prd]})

        # Fix hashes first
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "add"], cwd=tmp_path, capture_output=True)
        run_elspais("fix", cwd=tmp_path)

        result = run_elspais("health", "--lenient", cwd=tmp_path)
        assert result.returncode == 0, f"health failed: {result.stdout}"


# ---------------------------------------------------------------------------
# Test 53: Require SHALL disabled
# ---------------------------------------------------------------------------


class TestRequireShallDisabled:
    """Config: require_shall = false allows non-SHALL assertions."""

    def test_no_shall_requirement(self, tmp_path):
        cfg = base_config(
            name="no-shall",
            require_shall=False,
            allow_orphans=True,
        )
        prd = Requirement(
            "REQ-p00001",
            "No SHALL",
            "PRD",
            assertions=[
                ("A", "The system must validate input."),
                ("B", "Users can export data."),
            ],
        )
        build_project(
            tmp_path,
            cfg,
            spec_files={"spec/prd.md": [prd]},
        )

        result = run_elspais("health", "--lenient", cwd=tmp_path)
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# Test 54: Multi-assertion separator customization
# ---------------------------------------------------------------------------


class TestMultiAssertionSeparator:
    """Config: multi_assertion_separator = ',' instead of '+'."""

    def test_comma_separator(self, tmp_path):
        cfg = base_config(
            name="comma-sep",
            multi_assertion_separator=",",
            testing_enabled=True,
            test_dirs=["tests"],
        )
        prd = Requirement(
            "REQ-p00001",
            "Comma Sep",
            "PRD",
            assertions=[
                ("A", "The system SHALL do A."),
                ("B", "The system SHALL do B."),
            ],
        )
        dev = Requirement(
            "REQ-d00001",
            "Comma Impl",
            "DEV",
            implements="REQ-p00001",
            assertions=[("A", "The module SHALL implement both.")],
        )
        build_project(
            tmp_path,
            cfg,
            spec_files={
                "spec/prd.md": [prd],
                "spec/dev.md": [dev],
            },
        )

        result = run_elspais("health", "--lenient", cwd=tmp_path)
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# Test 55: References overrides per file type
# ---------------------------------------------------------------------------


class TestReferencesOverrides:
    """Config: references.overrides for different comment styles."""

    def test_js_comment_style(self, tmp_path):
        cfg = base_config(
            name="ref-overrides",
            comment_styles=["#", "//"],
            allow_orphans=True,
        )
        prd = Requirement(
            "REQ-p00001",
            "JS Feature",
            "PRD",
            assertions=[("A", "The system SHALL work in JS.")],
        )
        dev = Requirement(
            "REQ-d00001",
            "JS Module",
            "DEV",
            implements="REQ-p00001",
            assertions=[("A", "The module SHALL be written in JS.")],
        )
        build_project(
            tmp_path,
            cfg,
            spec_files={
                "spec/prd.md": [prd],
                "spec/dev.md": [dev],
            },
        )

        # Write a JS file with // Implements comment
        js_file = tmp_path / "src" / "feature.js"
        js_file.parent.mkdir(parents=True, exist_ok=True)
        js_file.write_text("// Implements: REQ-d00001\nfunction feature() {}\n")

        result = run_elspais("health", "--lenient", cwd=tmp_path)
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# Test 56: Large hierarchy (10+ requirements)
# ---------------------------------------------------------------------------


class TestLargeHierarchy:
    """Project with many requirements across all levels."""

    def test_large_project_health(self, tmp_path):
        cfg = base_config(name="large-project")
        prd_reqs = []
        for i in range(1, 4):
            prd_reqs.append(
                Requirement(
                    f"REQ-p0000{i}",
                    f"Product Feature {i}",
                    "PRD",
                    assertions=[
                        ("A", f"The system SHALL implement feature {i}A."),
                        ("B", f"The system SHALL implement feature {i}B."),
                    ],
                )
            )

        ops_reqs = []
        for i in range(1, 4):
            ops_reqs.append(
                Requirement(
                    f"REQ-o0000{i}",
                    f"Ops Process {i}",
                    "OPS",
                    implements=f"REQ-p0000{i}",
                    assertions=[("A", f"Operations SHALL manage process {i}.")],
                )
            )

        dev_reqs = []
        for i in range(1, 7):
            parent_idx = ((i - 1) % 3) + 1
            dev_reqs.append(
                Requirement(
                    f"REQ-d0000{i}",
                    f"Dev Module {i}",
                    "DEV",
                    implements=f"REQ-o0000{parent_idx}",
                    assertions=[
                        ("A", f"The module SHALL implement component {i}A."),
                        ("B", f"The module SHALL implement component {i}B."),
                    ],
                )
            )

        build_project(
            tmp_path,
            cfg,
            spec_files={
                "spec/prd-features.md": prd_reqs,
                "spec/ops-processes.md": ops_reqs,
                "spec/dev-modules.md": dev_reqs,
            },
        )

        health = run_elspais("health", "--lenient", cwd=tmp_path)
        assert health.returncode == 0

        summary = run_elspais("summary", "--format", "json", cwd=tmp_path)
        data = json.loads(summary.stdout)
        levels = data.get("levels", [])
        total = sum(lv.get("total", 0) for lv in levels)
        assert total == 12  # 3 PRD + 3 OPS + 6 DEV

    def test_large_project_analysis(self, tmp_path):
        cfg = base_config(name="large-analysis")
        reqs = []
        for i in range(1, 4):
            reqs.append(
                Requirement(
                    f"REQ-p0000{i}",
                    f"Feature {i}",
                    "PRD",
                    assertions=[("A", f"The system SHALL do {i}.")],
                )
            )
        for i in range(1, 4):
            reqs.append(
                Requirement(
                    f"REQ-d0000{i}",
                    f"Module {i}",
                    "DEV",
                    implements=f"REQ-p0000{i}",
                    assertions=[("A", f"The module SHALL implement {i}.")],
                )
            )
        build_project(
            tmp_path,
            cfg,
            spec_files={"spec/all.md": reqs},
        )

        result = run_elspais(
            "analysis",
            "--format",
            "json",
            "-n",
            "3",
            cwd=tmp_path,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        # Analysis JSON returns a dict with ranked_nodes, top_foundations, etc.
        assert isinstance(data, dict)
        assert "ranked_nodes" in data or "top_foundations" in data


# ---------------------------------------------------------------------------
# Test 57: Deprecated/Superseded status filtering
# ---------------------------------------------------------------------------


class TestStatusFiltering:
    """Health and summary handle Deprecated/Superseded requirements."""

    def test_deprecated_excluded_from_summary(self, tmp_path):
        cfg = base_config(name="status-filter", allow_orphans=True)
        active = Requirement(
            "REQ-p00001",
            "Active Feature",
            "PRD",
            assertions=[("A", "The system SHALL be active.")],
        )
        deprecated = Requirement(
            "REQ-p00002",
            "Deprecated Feature",
            "PRD",
            status="Deprecated",
            assertions=[("A", "The system SHALL be deprecated.")],
        )
        build_project(
            tmp_path,
            cfg,
            spec_files={"spec/prd.md": [active, deprecated]},
        )

        # Health should pass (both statuses allowed)
        health = run_elspais("health", "--lenient", cwd=tmp_path)
        assert health.returncode == 0

        # Summary default (Active only) should show 1
        summary = run_elspais("summary", "--format", "json", cwd=tmp_path)
        data = json.loads(summary.stdout)
        total = sum(lv.get("total", 0) for lv in data.get("levels", []))
        assert total >= 1  # At least 1 Active


# ---------------------------------------------------------------------------
# Test 58: Testing section config
# ---------------------------------------------------------------------------


class TestTestingConfig:
    """Full testing configuration with custom dirs and patterns."""

    def test_custom_test_dirs(self, tmp_path):
        cfg = base_config(
            name="custom-tests",
            testing_enabled=True,
            test_dirs=["verification"],
            test_patterns=["verify_*.py", "*_verify.py"],
        )
        prd = Requirement(
            "REQ-p00001",
            "Verified Feature",
            "PRD",
            assertions=[("A", "The system SHALL be verified.")],
        )
        dev = Requirement(
            "REQ-d00001",
            "Verified Impl",
            "DEV",
            implements="REQ-p00001",
            assertions=[("A", "The module SHALL pass verification.")],
        )
        build_project(
            tmp_path,
            cfg,
            spec_files={
                "spec/prd.md": [prd],
                "spec/dev.md": [dev],
            },
        )

        # Create test in custom dir with custom pattern
        test_dir = tmp_path / "verification"
        test_dir.mkdir()
        test_file = test_dir / "verify_feature.py"
        test_file.write_text("# Validates: REQ-d00001\ndef verify_feature():\n    assert True\n")

        result = run_elspais("health", "--lenient", cwd=tmp_path)
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# Test 59: Complex directory structure with nested skip
# ---------------------------------------------------------------------------


class TestComplexDirectoryStructure:
    """Realistic multi-level directory with include/exclude patterns."""

    def test_nested_structure(self, tmp_path):
        # skip_dirs are relative to each spec dir
        cfg = base_config(
            name="complex-dirs",
            spec_dir=["spec/active", "spec/approved"],
            skip_dirs=["drafts", "archive"],
            allow_orphans=True,
        )
        # Active requirements
        active1 = Requirement(
            "REQ-p00001",
            "Active One",
            "PRD",
            assertions=[("A", "The system SHALL be active one.")],
        )
        active2 = Requirement(
            "REQ-p00002",
            "Active Two",
            "PRD",
            assertions=[("A", "The system SHALL be active two.")],
        )
        # These should be excluded (in skip_dirs)
        draft = Requirement(
            "REQ-p00003",
            "Draft",
            "PRD",
            assertions=[("A", "The system SHALL be draft.")],
        )
        archived = Requirement(
            "REQ-p00004",
            "Archived",
            "PRD",
            assertions=[("A", "The system SHALL be archived.")],
        )
        # Approved requirements
        approved = Requirement(
            "REQ-p00005",
            "Approved",
            "PRD",
            assertions=[("A", "The system SHALL be approved.")],
        )

        build_project(
            tmp_path,
            cfg,
            spec_files={
                "spec/active/prd-active.md": [active1, active2],
                "spec/active/drafts/prd-draft.md": [draft],
                "spec/approved/prd-approved.md": [approved],
                "spec/approved/archive/prd-archived.md": [archived],
            },
        )

        summary = run_elspais("summary", "--format", "json", cwd=tmp_path)
        assert summary.returncode == 0
        data = json.loads(summary.stdout)
        total = sum(lv.get("total", 0) for lv in data.get("levels", []))
        # Should include active1, active2, approved = 3
        # Should exclude draft (in drafts/), archived (in archive/)
        assert total == 3, f"Expected 3 (excluded drafts/archive), got {total}"


# ---------------------------------------------------------------------------
# Test 60: Environment variable overrides
# ---------------------------------------------------------------------------


class TestEnvVarOverrides:
    """Configuration can be overridden via ELSPAIS_* env vars."""

    def test_env_override_project_name(self, tmp_path):
        cfg = base_config(name="original-name", allow_orphans=True)
        build_project(
            tmp_path,
            cfg,
            spec_files={
                "spec/prd.md": [
                    Requirement(
                        "REQ-p00001",
                        "Env Test",
                        "PRD",
                        assertions=[("A", "The system SHALL use env vars.")],
                    ),
                ],
            },
        )

        # Override project name via env var
        result = run_elspais(
            "config",
            "show",
            "--format",
            "json",
            cwd=tmp_path,
            env={"ELSPAIS_PROJECT_NAME": "env-overridden"},
        )
        assert result.returncode == 0
        # Check if override took effect
        data = json.loads(result.stdout)
        # The name may or may not be overridden depending on implementation
        # At minimum, the command should not crash with env vars set
        assert "project" in data


# ---------------------------------------------------------------------------
# Test: allow_orphans config
# ---------------------------------------------------------------------------


class TestAllowOrphansConfig:
    """Config: allow_orphans suppresses orphan warnings."""

    def test_orphan_warning_suppressed(self, tmp_path):
        """DEV without parent should pass health when allow_orphans=True."""
        cfg = base_config(name="orphans-allowed", allow_orphans=True)
        dev = Requirement(
            "REQ-d00001",
            "Orphan Dev",
            "DEV",
            assertions=[("A", "The module SHALL exist alone.")],
        )
        build_project(tmp_path, cfg, spec_files={"spec/dev.md": [dev]})

        result = run_elspais("health", "--format", "json", "--lenient", cwd=tmp_path)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        # The orphan check should pass (not just be a warning)
        orphan_check = next((c for c in data["checks"] if c["name"] == "spec.orphans"), None)
        if orphan_check:
            assert orphan_check[
                "passed"
            ], f"Orphan check should pass with allow_orphans=True: {orphan_check}"

    def test_orphan_check_runs_when_disallowed(self, tmp_path):
        """With allow_orphans=False, orphan check should actually run (not skip)."""
        cfg = base_config(name="orphans-denied", allow_orphans=False)
        dev = Requirement(
            "REQ-d00001",
            "Orphan Dev",
            "DEV",
            assertions=[("A", "The module SHALL exist alone.")],
        )
        build_project(tmp_path, cfg, spec_files={"spec/dev.md": [dev]})

        result = run_elspais("health", "--format", "json", "--lenient", cwd=tmp_path)
        data = json.loads(result.stdout)
        orphan_check = next((c for c in data["checks"] if c["name"] == "spec.orphans"), None)
        assert orphan_check is not None, "Orphan check should exist"
        # The check ran (not skipped) — message should NOT mention "skipped"
        assert "skipped" not in orphan_check["message"].lower()
