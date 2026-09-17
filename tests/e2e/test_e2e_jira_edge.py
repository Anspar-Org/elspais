# Verifies: REQ-p00002, REQ-p00003, REQ-d00080
"""E2E tests for Jira-style IDs and edge-case configurations.

Fixture 4: Jira-style variable-length IDs (PROJ-1, PROJ-2, PROJ-3),
zero-padded numeric assertions, complex directory structures,
JS comment styles, custom test dirs, status roles, and env var overrides.
"""

from __future__ import annotations

import json

import pytest

from .conftest import (
    ensure_fixture_daemon,
    load_fixture,
    run_elspais,
)
from .helpers import resolve_elspais, trace_rows

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        resolve_elspais() is None,
        reason="elspais CLI not found on PATH",
    ),
]


# ---------------------------------------------------------------------------
# Module-scoped fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def project(tmp_path_factory):
    """Copy e2e-jira-edge fixture to /tmp, init git, start daemon."""
    root = tmp_path_factory.mktemp("e2e_jira_edge")
    load_fixture("e2e-jira-edge", root)
    ensure_fixture_daemon(root)
    return root


# ---------------------------------------------------------------------------
# TestVariableLengthIds (from test_e2e_cli_health_summary.py)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestVariableLengthIds:
    """Jira-style variable-length IDs: PROJ-1, PROJ-2, PROJ-3."""

    def test_health_passes(self, project):
        result = run_elspais("checks", "--lenient", cwd=project)
        assert result.returncode == 0, f"health failed: {result.stderr}"

    # Verifies: REQ-d00086-A, REQ-d00281-A, REQ-d00281-B, REQ-d00291-E+F+I
    def test_level_groups_account_for_every_reported_requirement(self, project):
        """The single level this project defines forms one group, and that
        group plus the status disclosure account for all 6 reported.

        `[levels.req]` is the whole vocabulary, so REQ is the only group
        REQ-d00281-A forms. PROJ-1, PROJ-3 and PROJ-6 carry Active; PROJ-2
        (Draft), PROJ-4 (Deprecated) and PROJ-5 (Proposed) carry statuses whose
        roles do not expect implementation.
        """
        result = run_elspais("summary", "--format", "json", cwd=project)
        assert result.returncode == 0, f"summary failed: {result.stderr}"
        data = json.loads(result.stdout)

        groups = {lv["level"]: lv["requirements"] for lv in data["levels"]}
        assert groups == {"REQ": 3}

        # REQ-d00291-I: each withheld status is named with its count.
        assert data["excluded"] == {"Draft": 1, "Deprecated": 1, "Proposed": 1}

        # REQ-d00281-B: 3 counted plus 3 withheld are the 6 reported.
        trace = run_elspais("trace", "--format", "json", cwd=project)
        assert trace.returncode == 0
        reported = len(trace_rows(trace.stdout))
        assert reported == 6
        assert sum(groups.values()) + sum(data["excluded"].values()) == reported


# ---------------------------------------------------------------------------
# TestSkipDirsMultiSegment (from test_e2e_cli_health_summary.py)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestSkipDirsMultiSegment:
    """Config: skip_dirs names spec/active/drafts and spec/approved/archive."""

    # Verifies: REQ-d00212-Q
    def test_health_finds_only_included(self, project):
        """A skipped directory is matched by name beneath either configured
        spec directory: ``drafts`` under spec/active and ``archive`` under
        spec/approved are both excluded."""
        result = run_elspais("summary", "--format", "json", cwd=project)
        assert result.returncode == 0, f"summary failed: {result.stderr}"
        json.loads(result.stdout)  # validate JSON
        # PROJ-99 (in drafts/) and PROJ-98 (in archive/) must be excluded
        # The trace output should NOT contain the excluded IDs
        trace = run_elspais("trace", "--format", "json", cwd=project)
        assert "PROJ-99" not in trace.stdout, "PROJ-99 should be excluded (in drafts/)"
        assert "PROJ-98" not in trace.stdout, "PROJ-98 should be excluded (in archive/)"


# ---------------------------------------------------------------------------
# TestMultipleSpecDirs (from test_e2e_cli_health_summary.py)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestMultipleSpecDirs:
    """Config: spec_dirs = ['spec/active', 'spec/approved'] scans both."""

    def test_health_passes(self, project):
        result = run_elspais("checks", "--lenient", cwd=project)
        assert result.returncode == 0, f"health failed: {result.stderr}"

    def test_summary_counts_both_dirs(self, project):
        result = run_elspais("summary", "--format", "json", cwd=project)
        assert result.returncode == 0, f"summary failed: {result.stderr}"
        # PROJ-6 from spec/approved must be found
        trace = run_elspais("trace", "--format", "json", cwd=project)
        assert result.returncode == 0
        assert "PROJ-6" in trace.stdout, "PROJ-6 from spec/approved should be scanned"


# ---------------------------------------------------------------------------
# TestZeroPaddedNumericAssertions (from test_e2e_additional_coverage.py)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestZeroPaddedNumericAssertions:
    """Config: label_style='numeric', zero_pad=True — assertions labeled 00, 01, 02."""

    def test_zero_padded_labels_health_passes(self, project):
        # PROJ-3 has 3 assertions labeled 00, 01, 02
        result = run_elspais("checks", "--lenient", cwd=project)
        assert result.returncode == 0, (
            f"health failed with zero-padded assertions: {result.stderr}\n{result.stdout}"
        )


# ---------------------------------------------------------------------------
# TestIgnorePatterns (from test_e2e_config_variations.py)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestIgnorePatterns:
    """Ignore patterns: node_modules and skip files."""

    def test_global_ignore_excludes_node_modules(self, project):
        """spec/active/node_modules/ should be ignored."""
        result = run_elspais("checks", "--lenient", cwd=project)
        assert result.returncode == 0, f"health failed: {result.stderr}"
        # node_modules content should not appear in trace
        trace = run_elspais("trace", "--format", "json", cwd=project)
        assert "node_modules" not in trace.stdout

    # Verifies: REQ-d00212-Q, REQ-d00281-B
    def test_spec_skip_dirs_excludes_the_requirements_beneath_them(self, project):
        """``skip_dirs = ["spec/active/drafts", "spec/approved/archive"]`` keeps
        PROJ-99 and PROJ-98 out
        of the report entirely -- not merely out of its counts.

        The counted total cannot show this. PROJ-99 is Draft and PROJ-98 is
        Deprecated, so both are outside the coverage aggregation anyway and the
        total stays 3 either way -- measured by dropping ``skip_dirs``, which
        left the total at 3 while moving the reported set from 6 to 8 and the
        disclosure from {Draft 1, Deprecated 1, Proposed 1} to {Draft 2,
        Deprecated 2, Proposed 1}. Those are the probes, as they are for the
        ``node_modules`` case above.
        """
        trace = run_elspais("trace", "--format", "json", cwd=project)
        assert trace.returncode == 0
        ids = {r["id"] for r in trace_rows(trace.stdout)}
        assert ids == {"PROJ-1", "PROJ-2", "PROJ-3", "PROJ-4", "PROJ-5", "PROJ-6"}

        summary = run_elspais("summary", "--format", "json", cwd=project)
        assert summary.returncode == 0
        data = json.loads(summary.stdout)
        # A leak would add a second Draft (PROJ-99) and a second Deprecated
        # (PROJ-98) here, while leaving the counted total at 3.
        assert data["excluded"] == {"Draft": 1, "Deprecated": 1, "Proposed": 1}
        assert sum(lv["requirements"] for lv in data["levels"]) == 3


# ---------------------------------------------------------------------------
# TestReferencesOverrides (from test_e2e_config_variations.py) — JS comments
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestReferencesOverrides:
    """JS `//` Implements comments are read as references."""

    def test_js_comment_style(self, project):
        # src/feature.js contains "// Implements: PROJ-3" — should parse without error
        result = run_elspais("checks", "--lenient", cwd=project)
        assert result.returncode == 0, f"health failed with JS comments: {result.stderr}"


# ---------------------------------------------------------------------------
# TestLargeHierarchy (from test_e2e_config_variations.py)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestLargeHierarchy:
    """Multiple requirements across spec/active and spec/approved."""

    # Verifies: REQ-d00086-A, REQ-d00281-B
    def test_both_configured_spec_directories_contribute(self, project):
        """`directories = ["spec/active", "spec/approved"]` -- the report counts
        requirements from both, not from whichever is scanned first.

        PROJ-1 and PROJ-3 come from spec/active and PROJ-6 from spec/approved.
        The counted total of 3 is therefore only reachable with both
        directories scanned: either one alone would give 2 or 1.
        """
        health = run_elspais("checks", "--lenient", cwd=project)
        assert health.returncode == 0, f"health failed: {health.stderr}"

        summary = run_elspais("summary", "--format", "json", cwd=project)
        assert summary.returncode == 0, f"summary failed: {summary.stderr}"
        data = json.loads(summary.stdout)
        assert sum(lv["requirements"] for lv in data["levels"]) == 3

        trace = run_elspais("trace", "--format", "json", cwd=project)
        assert trace.returncode == 0
        active = {r["id"] for r in trace_rows(trace.stdout) if r["status"] == "Active"}
        assert active == {"PROJ-1", "PROJ-3", "PROJ-6"}

    def test_large_project_analysis(self, project):
        result = run_elspais("analysis", "--format", "json", "-n", "3", cwd=project)
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

    def test_custom_test_dirs(self, project):
        # verification/verify_feature.py contains "# Verifies: PROJ-3"
        result = run_elspais("checks", "--lenient", cwd=project)
        assert result.returncode == 0, f"health failed with custom test dirs: {result.stderr}"


# ---------------------------------------------------------------------------
# TestComplexDirectoryStructure (from test_e2e_config_variations.py)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestComplexDirectoryStructure:
    """spec/active + spec/approved with drafts/ and archive/ excluded."""

    # Verifies: REQ-d00086-A, REQ-d00291-E+F+I
    def test_nested_structure(self, project):
        """Requirements spread across nested spec directories are counted by
        status role, whichever directory they were found in.

        PROJ-1 and PROJ-3 sit in spec/active and PROJ-6 in spec/approved; all
        three carry Active, so the count is 3 wherever they were read from.
        PROJ-2 (Draft), PROJ-4 (Deprecated) and PROJ-5 (Proposed) carry statuses
        whose roles do not expect implementation, and are disclosed instead.

        This test says nothing about ``skip_dirs``: the requirements that
        setting withholds are non-Active anyway, so this total is invariant to
        it. That axis is covered by
        ``TestSkipDirsMultiSegment::test_health_finds_only_included`` and
        ``TestIgnorePatterns::test_spec_skip_dirs_excludes_the_requirements_beneath_them``,
        both of which probe the reported ID set rather than the count.
        """
        summary = run_elspais("summary", "--format", "json", cwd=project)
        assert summary.returncode == 0, f"summary failed: {summary.stderr}"
        data = json.loads(summary.stdout)
        total = sum(lv["requirements"] for lv in data["levels"])
        assert total == 3, f"Expected 3 active-role reqs, got {total}"
        # REQ-d00291-I: the three withheld statuses are named, not dropped.
        assert data["excluded"] == {"Draft": 1, "Deprecated": 1, "Proposed": 1}


# ---------------------------------------------------------------------------
# TestEnvVarOverrides (from test_e2e_config_variations.py)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# TestAllowStructuralOrphansConfig (from test_e2e_config_variations.py)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestAllowStructuralOrphansConfig:
    """Config: allow_structural_orphans=True suppresses orphan warnings."""

    def test_orphan_warning_suppressed(self, project):
        """PROJ-3 (DEV with no parent) should pass health when allow_structural_orphans=True."""
        result = run_elspais("checks", "--format", "json", "--lenient", cwd=project)
        assert result.returncode == 0, f"health failed: {result.stderr}"
        data = json.loads(result.stdout)
        orphan_check = next(
            (c for c in data["checks"] if c["name"] == "spec.structural_orphans"), None
        )
        if orphan_check:
            assert orphan_check["passed"], (
                f"Orphan check should pass with allow_structural_orphans=True: {orphan_check}"
            )

    def test_orphan_check_runs_when_disallowed(self, tmp_path):
        """When allow_structural_orphans=False, orphan check should run (not be skipped)."""
        from .helpers import Requirement, base_config, build_project

        cfg = base_config(
            name="jira-orphans-denied",
            namespace="PROJ",
            canonical="{namespace}-{component}",
            component_digits=0,
            leading_zeros=False,
            label_style="numeric",
            zero_pad_assertions=True,
            allow_structural_orphans=False,
            status_roles={"active": ["Active"], "provisional": ["Draft"]},
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

    # Verifies: REQ-d00291-E+F
    def test_provisional_excluded_from_summary(self, project):
        """Draft and Proposed (provisional role) should be excluded from summary counts."""
        result = run_elspais("summary", "--format", "json", cwd=project)
        assert result.returncode == 0, f"summary failed: {result.stderr}"
        data = json.loads(result.stdout)
        total = sum(lv["requirements"] for lv in data["levels"])
        # Active only: PROJ-1, PROJ-3, PROJ-6 = 3 (Draft/Proposed/Deprecated excluded)
        assert total == 3, f"Expected 3 active requirements, got {total}"
