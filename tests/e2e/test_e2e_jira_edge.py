# Verifies: REQ-p00002, REQ-p00003, REQ-d00080
"""E2E tests for Jira-style IDs and edge-case configurations.

Fixture 4: Jira-style variable-length IDs (PROJ-1, PROJ-2, PROJ-3),
zero-padded numeric assertions, complex directory structures,
JS comment styles, custom test dirs, status roles, and env var overrides.
"""

from __future__ import annotations

import json
import shutil

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
# Shared fixture builder
# ---------------------------------------------------------------------------


def _build_jira_project(tmp_path):
    """Build the shared Jira-style fixture project.

    Config:
    - Jira-style IDs: namespace=PROJ, component_digits=0, leading_zeros=False
    - Zero-padded numeric assertions: label_style=numeric, zero_pad_assertions=True
    - allow_structural_orphans=True
    - status_roles: active=[Active], provisional=[Draft,Proposed], retired=[Deprecated]
    - spec_dirs: spec/active, spec/approved (skip: drafts, archive)
    - comment_styles: ["#", "//"]
    - testing: enabled, test_dirs=["verification"], patterns=[verify_*.py, *_verify.py]
    - Git repo initialized
    """
    cfg = base_config(
        name="jira-edge",
        namespace="PROJ",
        canonical="{namespace}-{component}",
        component_digits=0,
        leading_zeros=False,
        label_style="numeric",
        zero_pad_assertions=True,
        allow_structural_orphans=True,
        spec_dir=["spec/active", "spec/approved"],
        skip_dirs=["drafts", "archive"],
        comment_styles=["#", "//"],
        testing_enabled=True,
        test_dirs=["verification"],
        test_patterns=["verify_*.py", "*_verify.py"],
        # Broader allowed statuses to cover Active, Draft, Proposed, Deprecated
        allowed_statuses=["Active", "Draft", "Proposed", "Deprecated"],
        types={"req": {"level": 1}},
    )
    # Add status_roles
    cfg["rules"]["format"]["status_roles"] = {
        "active": ["Active"],
        "provisional": ["Draft", "Proposed"],
        "retired": ["Deprecated"],
    }

    # PROJ-1: Active PRD requirement
    proj1 = Requirement(
        "PROJ-1",
        "First Feature",
        "PRD",
        status="Active",
        assertions=[
            ("00", "The system SHALL implement the first feature."),
            ("01", "The system SHALL validate inputs for the first feature."),
        ],
    )
    # PROJ-2: Draft (provisional) PRD requirement
    proj2 = Requirement(
        "PROJ-2",
        "Second Feature",
        "PRD",
        status="Draft",
        assertions=[
            ("00", "The system SHALL implement the second feature."),
        ],
    )
    # PROJ-3: Active DEV requirement (structural orphan — no parent)
    proj3 = Requirement(
        "PROJ-3",
        "Implementation Module",
        "DEV",
        status="Active",
        assertions=[
            ("00", "The module SHALL process requests."),
            ("01", "The module SHALL handle errors gracefully."),
            ("02", "The module SHALL log all operations."),
        ],
    )
    # PROJ-4: Deprecated requirement
    proj4 = Requirement(
        "PROJ-4",
        "Deprecated Feature",
        "PRD",
        status="Deprecated",
        assertions=[
            ("00", "The system SHALL be deprecated."),
        ],
    )
    # PROJ-5: Proposed (provisional)
    proj5 = Requirement(
        "PROJ-5",
        "Proposed Feature",
        "PRD",
        status="Proposed",
        assertions=[
            ("00", "The system SHALL be proposed."),
        ],
    )
    # Approved-section requirement
    proj6 = Requirement(
        "PROJ-6",
        "Approved Feature",
        "PRD",
        status="Active",
        assertions=[
            ("00", "The system SHALL be formally approved."),
        ],
    )
    # Draft spec (in skip dir — should be excluded)
    draft_excluded = Requirement(
        "PROJ-99",
        "Draft Excluded",
        "PRD",
        status="Draft",
        assertions=[
            ("00", "The system SHALL be excluded by skip_dirs."),
        ],
    )
    # Archived spec (in skip dir — should be excluded)
    archived_excluded = Requirement(
        "PROJ-98",
        "Archived Excluded",
        "PRD",
        status="Deprecated",
        assertions=[
            ("00", "The system SHALL be archived and excluded."),
        ],
    )

    build_project(
        tmp_path,
        cfg,
        spec_files={
            "spec/active/prd-features.md": [proj1, proj2, proj4, proj5],
            "spec/active/dev-impl.md": [proj3],
            "spec/active/drafts/prd-draft.md": [draft_excluded],
            "spec/approved/prd-approved.md": [proj6],
            "spec/approved/archive/prd-archived.md": [archived_excluded],
        },
        extra_files={
            # JS code file with // Implements comment
            "src/feature.js": "// Implements: PROJ-3\nfunction feature() {}\n",
            # node_modules dir (for ignore testing)
            "spec/active/node_modules/bad.md": "# Should be ignored\n",
        },
    )

    # Python code file with # Implements comment
    py_code = tmp_path / "src" / "impl.py"
    py_code.parent.mkdir(parents=True, exist_ok=True)
    py_code.write_text("# Implements: PROJ-3\ndef impl():\n    pass\n")

    # Test file in verification/ dir with verify_*.py pattern
    verification_dir = tmp_path / "verification"
    verification_dir.mkdir()
    (verification_dir / "verify_feature.py").write_text(
        "# Verifies: PROJ-3\ndef verify_feature():\n    assert True\n"
    )

    return tmp_path


# ---------------------------------------------------------------------------
# TestVariableLengthIds (from test_e2e_cli_health_summary.py)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestVariableLengthIds:
    """Jira-style variable-length IDs: PROJ-1, PROJ-2, PROJ-3."""

    def test_health_passes(self, tmp_path):
        _build_jira_project(tmp_path)
        result = run_elspais("checks", "--lenient", cwd=tmp_path)
        assert result.returncode == 0, f"health failed: {result.stderr}"

    def test_summary_counts_active_requirements(self, tmp_path):
        _build_jira_project(tmp_path)
        result = run_elspais("summary", "--format", "json", cwd=tmp_path)
        assert result.returncode == 0, f"summary failed: {result.stderr}"
        data = json.loads(result.stdout)
        levels = data.get("levels", [])
        total = sum(lv.get("total", 0) for lv in levels)
        # Active requirements: PROJ-1, PROJ-3, PROJ-6 = 3
        assert total >= 1, f"Expected at least 1 active requirement, got {total}"


# ---------------------------------------------------------------------------
# TestSkipDirsMultiSegment (from test_e2e_cli_health_summary.py)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestSkipDirsMultiSegment:
    """Config: skip_dirs = ['drafts', 'archive'] excludes nested dirs."""

    def test_health_finds_only_included(self, tmp_path):
        _build_jira_project(tmp_path)
        result = run_elspais("summary", "--format", "json", cwd=tmp_path)
        assert result.returncode == 0, f"summary failed: {result.stderr}"
        json.loads(result.stdout)  # validate JSON
        # PROJ-99 (in drafts/) and PROJ-98 (in archive/) must be excluded
        # The trace output should NOT contain the excluded IDs
        trace = run_elspais("trace", "--format", "json", cwd=tmp_path)
        assert "PROJ-99" not in trace.stdout, "PROJ-99 should be excluded (in drafts/)"
        assert "PROJ-98" not in trace.stdout, "PROJ-98 should be excluded (in archive/)"


# ---------------------------------------------------------------------------
# TestMultipleSpecDirs (from test_e2e_cli_health_summary.py)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestMultipleSpecDirs:
    """Config: spec_dirs = ['spec/active', 'spec/approved'] scans both."""

    def test_health_passes(self, tmp_path):
        _build_jira_project(tmp_path)
        result = run_elspais("checks", "--lenient", cwd=tmp_path)
        assert result.returncode == 0, f"health failed: {result.stderr}"

    def test_summary_counts_both_dirs(self, tmp_path):
        _build_jira_project(tmp_path)
        result = run_elspais("summary", "--format", "json", cwd=tmp_path)
        assert result.returncode == 0, f"summary failed: {result.stderr}"
        # PROJ-6 from spec/approved must be found
        trace = run_elspais("trace", "--format", "json", cwd=tmp_path)
        assert result.returncode == 0
        assert "PROJ-6" in trace.stdout, "PROJ-6 from spec/approved should be scanned"


# ---------------------------------------------------------------------------
# TestZeroPaddedNumericAssertions (from test_e2e_additional_coverage.py)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestZeroPaddedNumericAssertions:
    """Config: label_style='numeric', zero_pad=True — assertions labeled 00, 01, 02."""

    def test_zero_padded_labels_health_passes(self, tmp_path):
        _build_jira_project(tmp_path)
        # PROJ-3 has 3 assertions labeled 00, 01, 02
        result = run_elspais("checks", "--lenient", cwd=tmp_path)
        assert (
            result.returncode == 0
        ), f"health failed with zero-padded assertions: {result.stderr}\n{result.stdout}"


# ---------------------------------------------------------------------------
# TestIgnorePatterns (from test_e2e_config_variations.py)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestIgnorePatterns:
    """Ignore patterns: node_modules and skip files."""

    def test_global_ignore_excludes_node_modules(self, tmp_path):
        """spec/active/node_modules/ should be ignored."""
        _build_jira_project(tmp_path)
        result = run_elspais("checks", "--lenient", cwd=tmp_path)
        assert result.returncode == 0, f"health failed: {result.stderr}"
        # node_modules content should not appear in trace
        trace = run_elspais("trace", "--format", "json", cwd=tmp_path)
        assert "node_modules" not in trace.stdout

    def test_spec_skip_dirs_excludes_pattern(self, tmp_path):
        """drafts/ and archive/ subdirs should be excluded from scan."""
        _build_jira_project(tmp_path)
        summary = run_elspais("summary", "--format", "json", cwd=tmp_path)
        assert summary.returncode == 0
        data = json.loads(summary.stdout)
        total = sum(lv.get("total", 0) for lv in data.get("levels", []))
        # PROJ-1,2,3,4,5 (active dir) + PROJ-6 (approved dir) = 6 scanned
        # PROJ-99 (drafts) and PROJ-98 (archive) must be excluded
        assert total <= 6, f"Expected at most 6 (excluded skipped dirs), got {total}"


# ---------------------------------------------------------------------------
# TestReferencesOverrides (from test_e2e_config_variations.py) — JS comments
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestReferencesOverrides:
    """Config: comment_styles=['#', '//'] — JS // Implements comments work."""

    def test_js_comment_style(self, tmp_path):
        _build_jira_project(tmp_path)
        # src/feature.js contains "// Implements: PROJ-3" — should parse without error
        result = run_elspais("checks", "--lenient", cwd=tmp_path)
        assert result.returncode == 0, f"health failed with JS comments: {result.stderr}"


# ---------------------------------------------------------------------------
# TestLargeHierarchy (from test_e2e_config_variations.py)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestLargeHierarchy:
    """Multiple requirements across spec/active and spec/approved."""

    def test_large_project_health(self, tmp_path):
        _build_jira_project(tmp_path)
        health = run_elspais("checks", "--lenient", cwd=tmp_path)
        assert health.returncode == 0, f"health failed: {health.stderr}"

        summary = run_elspais("summary", "--format", "json", cwd=tmp_path)
        data = json.loads(summary.stdout)
        levels = data.get("levels", [])
        total = sum(lv.get("total", 0) for lv in levels)
        assert total >= 1

    def test_large_project_analysis(self, tmp_path):
        _build_jira_project(tmp_path)
        result = run_elspais("analysis", "--format", "json", "-n", "3", cwd=tmp_path)
        assert result.returncode == 0, f"analysis failed: {result.stderr}"
        data = json.loads(result.stdout)
        assert isinstance(data, dict)
        assert "ranked_nodes" in data or "top_foundations" in data


# ---------------------------------------------------------------------------
# TestTestingConfig (from test_e2e_config_variations.py) — custom test dirs
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestTestingConfig:
    """Custom testing config: verification dir, verify_*.py patterns."""

    def test_custom_test_dirs(self, tmp_path):
        _build_jira_project(tmp_path)
        # verification/verify_feature.py contains "# Verifies: PROJ-3"
        result = run_elspais("checks", "--lenient", cwd=tmp_path)
        assert result.returncode == 0, f"health failed with custom test dirs: {result.stderr}"


# ---------------------------------------------------------------------------
# TestComplexDirectoryStructure (from test_e2e_config_variations.py)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestComplexDirectoryStructure:
    """spec/active + spec/approved with drafts/ and archive/ excluded."""

    def test_nested_structure(self, tmp_path):
        _build_jira_project(tmp_path)
        summary = run_elspais("summary", "--format", "json", cwd=tmp_path)
        assert summary.returncode == 0, f"summary failed: {summary.stderr}"
        data = json.loads(summary.stdout)
        total = sum(lv.get("total", 0) for lv in data.get("levels", []))
        # Summary counts Active-status requirements only:
        #   PROJ-1 (Active, spec/active), PROJ-3 (Active, spec/active),
        #   PROJ-6 (Active, spec/approved) = 3
        # PROJ-2 (Draft), PROJ-4 (Deprecated), PROJ-5 (Proposed) excluded by status_roles
        # PROJ-99 (drafts/), PROJ-98 (archive/) excluded by skip_dirs
        assert total == 3, f"Expected 3 active reqs (skip_dirs + non-active excluded), got {total}"


# ---------------------------------------------------------------------------
# TestEnvVarOverrides (from test_e2e_config_variations.py)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestEnvVarOverrides:
    """Configuration can be overridden via ELSPAIS_* env vars."""

    def test_env_override_project_name(self, tmp_path):
        _build_jira_project(tmp_path)
        result = run_elspais(
            "config",
            "show",
            "--format",
            "json",
            cwd=tmp_path,
            env={"ELSPAIS_PROJECT_NAME": "env-overridden"},
        )
        assert result.returncode == 0, f"config show failed: {result.stderr}"
        data = json.loads(result.stdout)
        assert "project" in data


# ---------------------------------------------------------------------------
# TestAllowStructuralOrphansConfig (from test_e2e_config_variations.py)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestAllowStructuralOrphansConfig:
    """Config: allow_structural_orphans=True suppresses orphan warnings."""

    def test_orphan_warning_suppressed(self, tmp_path):
        """PROJ-3 (DEV with no parent) should pass health when allow_structural_orphans=True."""
        _build_jira_project(tmp_path)
        result = run_elspais("checks", "--format", "json", "--lenient", cwd=tmp_path)
        assert result.returncode == 0, f"health failed: {result.stderr}"
        data = json.loads(result.stdout)
        orphan_check = next(
            (c for c in data["checks"] if c["name"] == "spec.structural_orphans"), None
        )
        if orphan_check:
            assert orphan_check[
                "passed"
            ], f"Orphan check should pass with allow_structural_orphans=True: {orphan_check}"

    def test_orphan_check_runs_when_disallowed(self, tmp_path):
        """When allow_structural_orphans=False, orphan check should run (not be skipped)."""
        cfg = base_config(
            name="jira-orphans-denied",
            namespace="PROJ",
            canonical="{namespace}-{component}",
            component_digits=0,
            leading_zeros=False,
            label_style="numeric",
            zero_pad_assertions=True,
            allow_structural_orphans=False,
            allowed_statuses=["Active", "Draft"],
            types={"req": {"level": 1}},
        )
        orphan = Requirement(
            "PROJ-1",
            "Orphan Dev",
            "DEV",
            status="Active",
            assertions=[("00", "The module SHALL exist alone.")],
        )
        build_project(tmp_path, cfg, spec_files={"spec/dev.md": [orphan]})

        result = run_elspais("checks", "--format", "json", "--lenient", cwd=tmp_path)
        data = json.loads(result.stdout)
        orphan_check = next(
            (c for c in data["checks"] if c["name"] == "spec.structural_orphans"), None
        )
        assert orphan_check is not None, "Orphan check should exist"
        assert "skipped" not in orphan_check["message"].lower()


# ---------------------------------------------------------------------------
# TestStatusRolesConfig (from test_e2e_config_variations.py)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestStatusRolesConfig:
    """Config: status_roles controls coverage exclusion."""

    def test_provisional_excluded_from_summary(self, tmp_path):
        """Draft and Proposed (provisional role) should be excluded from summary counts."""
        _build_jira_project(tmp_path)
        result = run_elspais("summary", "--format", "json", cwd=tmp_path)
        assert result.returncode == 0, f"summary failed: {result.stderr}"
        data = json.loads(result.stdout)
        total = sum(lv.get("total", 0) for lv in data.get("levels", []))
        # Active only: PROJ-1, PROJ-3, PROJ-6 = 3 (Draft/Proposed/Deprecated excluded)
        assert total == 3, f"Expected 3 active requirements, got {total}"
