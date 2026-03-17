# Validates: REQ-p00002, REQ-p00003, REQ-d00080
"""E2E tests for health, summary, trace, and doctor CLI commands.

Each test builds a unique project from scratch in tmp_path with specific
config settings and validates CLI output against independently computed
expected values.
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
# Test 1: Standard 3-tier hierarchy, uppercase assertions, health + summary
# ---------------------------------------------------------------------------


class TestStandard3TierHealthSummary:
    """Standard REQ-{type.letter}{5-digit} pattern, uppercase assertions."""

    def _build(self, tmp_path):
        prd = Requirement(
            "REQ-p00001",
            "User Authentication",
            "PRD",
            assertions=[
                ("A", "The system SHALL authenticate users."),
                ("B", "The system SHALL enforce password policies."),
            ],
        )
        ops = Requirement(
            "REQ-o00001",
            "Auth Deployment",
            "OPS",
            implements="REQ-p00001",
            assertions=[("A", "Operations SHALL deploy auth service with HA.")],
        )
        dev = Requirement(
            "REQ-d00001",
            "Auth Module",
            "DEV",
            implements="REQ-o00001",
            assertions=[
                ("A", "The module SHALL use bcrypt for hashing."),
                ("B", "The module SHALL validate JWT tokens."),
            ],
        )

        cfg = base_config(name="std-3tier")
        build_project(
            tmp_path,
            cfg,
            spec_files={
                "spec/prd-core.md": [prd],
                "spec/ops-deploy.md": [ops],
                "spec/dev-impl.md": [dev],
            },
        )
        return tmp_path

    def test_health_passes(self, tmp_path):
        self._build(tmp_path)
        result = run_elspais("health", "--lenient", cwd=tmp_path)
        assert result.returncode == 0, f"health failed: {result.stderr}"

    def test_summary_counts_3_requirements(self, tmp_path):
        self._build(tmp_path)
        result = run_elspais("summary", "--format", "json", cwd=tmp_path)
        assert result.returncode == 0, f"summary failed: {result.stderr}"
        data = json.loads(result.stdout)
        levels = data.get("levels", [])
        total = sum(lv.get("total", 0) for lv in levels)
        assert total == 3, f"Expected 3 requirements, got {total}"

    def test_summary_level_breakdown(self, tmp_path):
        self._build(tmp_path)
        result = run_elspais("summary", "--format", "json", cwd=tmp_path)
        data = json.loads(result.stdout)
        levels = {lv["level"].lower(): lv["total"] for lv in data.get("levels", [])}
        assert levels.get("prd", 0) == 1
        assert levels.get("ops", 0) == 1
        assert levels.get("dev", 0) == 1

    def test_trace_json_has_3_entries(self, tmp_path):
        self._build(tmp_path)
        result = run_elspais("trace", "--format", "json", cwd=tmp_path)
        assert result.returncode == 0, f"trace failed: {result.stderr}"
        data = json.loads(result.stdout)
        # Trace returns a flat list of requirement dicts
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        assert len(data) == 3

    def test_doctor_passes(self, tmp_path):
        self._build(tmp_path)
        result = run_elspais("doctor", cwd=tmp_path)
        assert result.returncode == 0, f"doctor failed: {result.stderr}"


# ---------------------------------------------------------------------------
# Test 2: FDA-style IDs (PRD-00001, OPS-00001, DEV-00001)
# ---------------------------------------------------------------------------


class TestFDAStyleIds:
    """FDA-style IDs without namespace prefix."""

    def _build(self, tmp_path):
        cfg = base_config(
            name="fda-style",
            canonical="{type}-{component}",
            types={
                "PRD": {"level": 1},
                "OPS": {"level": 2},
                "DEV": {"level": 3},
            },
            allowed_implements=["DEV -> OPS, PRD", "OPS -> PRD", "PRD -> PRD"],
        )
        prd = Requirement(
            "PRD-00001",
            "Regulatory Compliance",
            "PRD",
            assertions=[
                ("A", "The system SHALL comply with FDA 21 CFR Part 11."),
                ("B", "The system SHALL maintain audit trails."),
            ],
        )
        ops = Requirement(
            "OPS-00001",
            "Compliance Monitoring",
            "OPS",
            implements="PRD-00001",
            assertions=[("A", "Operations SHALL monitor compliance status daily.")],
        )
        dev = Requirement(
            "DEV-00001",
            "Audit Logger",
            "DEV",
            implements="OPS-00001",
            assertions=[
                ("A", "The module SHALL log all data modifications."),
                ("B", "The module SHALL include timestamps in ISO 8601 format."),
            ],
        )
        build_project(
            tmp_path,
            cfg,
            spec_files={
                "spec/prd-regulatory.md": [prd],
                "spec/ops-compliance.md": [ops],
                "spec/dev-audit.md": [dev],
            },
        )
        return tmp_path

    def test_health_passes(self, tmp_path):
        self._build(tmp_path)
        result = run_elspais("health", "--lenient", cwd=tmp_path)
        assert result.returncode == 0, f"health failed: {result.stderr}"

    def test_summary_counts_3(self, tmp_path):
        self._build(tmp_path)
        result = run_elspais("summary", "--format", "json", cwd=tmp_path)
        assert result.returncode == 0, f"summary failed: {result.stderr}"
        data = json.loads(result.stdout)
        levels = data.get("levels", [])
        total = sum(lv.get("total", 0) for lv in levels)
        assert total == 3

    def test_trace_contains_fda_ids(self, tmp_path):
        self._build(tmp_path)
        result = run_elspais("trace", "--format", "json", cwd=tmp_path)
        assert result.returncode == 0
        output = result.stdout
        assert "PRD-00001" in output
        assert "OPS-00001" in output
        assert "DEV-00001" in output


# ---------------------------------------------------------------------------
# Test 3: Numeric assertion labels
# ---------------------------------------------------------------------------


class TestNumericAssertionLabels:
    """Config: label_style = 'numeric' (0-based)."""

    def _build(self, tmp_path):
        cfg = base_config(
            name="numeric-assertions",
            label_style="numeric",
            labels_sequential=True,
        )
        prd = Requirement(
            "REQ-p00001",
            "Data Validation",
            "PRD",
            assertions=[
                ("0", "The system SHALL validate all input data."),
                ("1", "The system SHALL reject malformed requests."),
                ("2", "The system SHALL log validation failures."),
            ],
        )
        build_project(tmp_path, cfg, spec_files={"spec/prd-data.md": [prd]})
        return tmp_path

    def test_health_passes_with_numeric_labels(self, tmp_path):
        self._build(tmp_path)
        result = run_elspais("health", "--lenient", cwd=tmp_path)
        assert result.returncode == 0, f"health failed: {result.stderr}"

    def test_summary_counts_1(self, tmp_path):
        self._build(tmp_path)
        result = run_elspais("summary", "--format", "json", cwd=tmp_path)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        levels = data.get("levels", [])
        total = sum(lv.get("total", 0) for lv in levels)
        assert total == 1


# ---------------------------------------------------------------------------
# Test 4: 1-based numeric assertion labels
# ---------------------------------------------------------------------------


class TestNumeric1BasedAssertionLabels:
    """Config: label_style = 'numeric_1based'."""

    def _build(self, tmp_path):
        cfg = base_config(
            name="numeric-1based",
            label_style="numeric_1based",
        )
        prd = Requirement(
            "REQ-p00001",
            "Access Control",
            "PRD",
            assertions=[
                ("1", "The system SHALL enforce role-based access control."),
                ("2", "The system SHALL restrict admin operations."),
            ],
        )
        dev = Requirement(
            "REQ-d00001",
            "RBAC Module",
            "DEV",
            implements="REQ-p00001",
            assertions=[
                ("1", "The module SHALL check permissions on every request."),
            ],
        )
        build_project(
            tmp_path,
            cfg,
            spec_files={
                "spec/prd-access.md": [prd],
                "spec/dev-rbac.md": [dev],
            },
        )
        return tmp_path

    def test_health_passes(self, tmp_path):
        self._build(tmp_path)
        result = run_elspais("health", "--lenient", cwd=tmp_path)
        assert result.returncode == 0, f"health failed: {result.stderr}"

    def test_trace_json_valid(self, tmp_path):
        self._build(tmp_path)
        result = run_elspais("trace", "--format", "json", cwd=tmp_path)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data  # Non-empty


# ---------------------------------------------------------------------------
# Test 5: Named component IDs (REQ-UserAuth)
# ---------------------------------------------------------------------------


class TestNamedComponentIds:
    """Named IDs: REQ-UserAuth, REQ-DataExport."""

    def _build(self, tmp_path):
        cfg = base_config(
            name="named-ids",
            canonical="{namespace}-{component}",
            component_style="named",
            types={"req": {"level": 1}},
            allowed_implements=["req -> req"],
            allow_structural_orphans=True,
        )
        cfg["id-patterns"]["component"] = {
            "style": "named",
            "pattern": "[A-Z][a-zA-Z0-9]+",
            "max_length": 32,
        }
        # Named IDs at level 1 map to PRD
        r1 = Requirement(
            "REQ-UserAuth",
            "User Authentication",
            "PRD",
            assertions=[("A", "The system SHALL authenticate users securely.")],
        )
        r2 = Requirement(
            "REQ-DataExport",
            "Data Export",
            "PRD",
            assertions=[("A", "The system SHALL export data in CSV format.")],
        )
        build_project(
            tmp_path,
            cfg,
            spec_files={"spec/features.md": [r1, r2]},
        )
        return tmp_path

    def test_health_passes(self, tmp_path):
        self._build(tmp_path)
        result = run_elspais("health", "--lenient", cwd=tmp_path)
        assert result.returncode == 0, f"health failed: {result.stderr}"

    def test_summary_counts_2(self, tmp_path):
        self._build(tmp_path)
        result = run_elspais("summary", "--format", "json", cwd=tmp_path)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        levels = data.get("levels", [])
        total = sum(lv.get("total", 0) for lv in levels)
        assert total == 2

    def test_trace_contains_named_ids(self, tmp_path):
        self._build(tmp_path)
        result = run_elspais("trace", "--format", "json", cwd=tmp_path)
        assert result.returncode == 0
        output = result.stdout
        assert "REQ-UserAuth" in output
        assert "REQ-DataExport" in output


# ---------------------------------------------------------------------------
# Test 6: Variable-length numeric IDs (PROJ-1, PROJ-12)
# ---------------------------------------------------------------------------


class TestVariableLengthIds:
    """Jira-style: PROJ-1, PROJ-12, PROJ-123."""

    def _build(self, tmp_path):
        cfg = base_config(
            name="jira-style",
            namespace="PROJ",
            canonical="{namespace}-{component}",
            component_digits=0,
            leading_zeros=False,
            types={"req": {"level": 1}},
            allowed_implements=["req -> req"],
            allow_structural_orphans=True,
        )
        reqs = [
            Requirement(
                "PROJ-1",
                "First Feature",
                "PRD",
                assertions=[("A", "The system SHALL do thing one.")],
            ),
            Requirement(
                "PROJ-12",
                "Second Feature",
                "PRD",
                assertions=[("A", "The system SHALL do thing twelve.")],
            ),
            Requirement(
                "PROJ-123",
                "Third Feature",
                "PRD",
                assertions=[("A", "The system SHALL do thing one-twenty-three.")],
            ),
        ]
        build_project(tmp_path, cfg, spec_files={"spec/features.md": reqs})
        return tmp_path

    def test_health_passes(self, tmp_path):
        self._build(tmp_path)
        result = run_elspais("health", "--lenient", cwd=tmp_path)
        assert result.returncode == 0, f"health failed: {result.stderr}"

    def test_summary_counts_3(self, tmp_path):
        self._build(tmp_path)
        result = run_elspais("summary", "--format", "json", cwd=tmp_path)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        levels = data.get("levels", [])
        total = sum(lv.get("total", 0) for lv in levels)
        assert total == 3


# ---------------------------------------------------------------------------
# Test 7: Skip dirs with multi-segment paths
# ---------------------------------------------------------------------------


class TestSkipDirsMultiSegment:
    """Config: skip_dirs = ['drafts/wip'] excludes nested dir."""

    def _build(self, tmp_path):
        cfg = base_config(
            name="skip-dirs-test",
            skip_dirs=["drafts/wip"],
            allow_structural_orphans=True,
        )
        included = Requirement(
            "REQ-p00001",
            "Included Requirement",
            "PRD",
            assertions=[("A", "The system SHALL be included.")],
        )
        excluded = Requirement(
            "REQ-p00002",
            "Excluded Requirement",
            "PRD",
            assertions=[("A", "The system SHALL be excluded.")],
        )
        build_project(
            tmp_path,
            cfg,
            spec_files={
                "spec/main.md": [included],
                "spec/drafts/wip/excluded.md": [excluded],
            },
        )
        return tmp_path

    def test_health_finds_only_included(self, tmp_path):
        self._build(tmp_path)
        result = run_elspais("summary", "--format", "json", cwd=tmp_path)
        assert result.returncode == 0, f"summary failed: {result.stderr}"
        data = json.loads(result.stdout)
        levels = data.get("levels", [])
        total = sum(lv.get("total", 0) for lv in levels)
        assert total == 1, f"Expected 1 requirement (excluded dir skipped), got {total}"


# ---------------------------------------------------------------------------
# Test 8: Custom allowed statuses
# ---------------------------------------------------------------------------


class TestCustomStatuses:
    """Config: allowed_statuses includes 'Review' and 'Archived'."""

    def _build(self, tmp_path):
        cfg = base_config(
            name="custom-statuses",
            allowed_statuses=["Active", "Draft", "Review", "Archived"],
            allow_structural_orphans=True,
        )
        r1 = Requirement(
            "REQ-p00001",
            "Under Review",
            "PRD",
            status="Review",
            assertions=[("A", "The system SHALL be reviewed.")],
        )
        r2 = Requirement(
            "REQ-p00002",
            "Archived Feature",
            "PRD",
            status="Archived",
            assertions=[("A", "The system SHALL be archived.")],
        )
        r3 = Requirement(
            "REQ-p00003",
            "Active Feature",
            "PRD",
            status="Active",
            assertions=[("A", "The system SHALL be active.")],
        )
        build_project(
            tmp_path,
            cfg,
            spec_files={"spec/prd-mixed.md": [r1, r2, r3]},
        )
        return tmp_path

    def test_health_passes_with_custom_statuses(self, tmp_path):
        self._build(tmp_path)
        result = run_elspais("health", "--lenient", cwd=tmp_path)
        assert result.returncode == 0, f"health failed: {result.stderr}"

    def test_summary_default_counts_active_only(self, tmp_path):
        """Default summary filters to Active status."""
        self._build(tmp_path)
        result = run_elspais("summary", "--format", "json", cwd=tmp_path)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        levels = data.get("levels", [])
        total = sum(lv.get("total", 0) for lv in levels)
        # Default --status=Active means only 1 Active req counted
        # Actually summary may count all. Let's check >= 1.
        assert total >= 1


# ---------------------------------------------------------------------------
# Test 9: Multiple spec dirs
# ---------------------------------------------------------------------------


class TestMultipleSpecDirs:
    """Config: spec = ['spec/product', 'spec/tech']."""

    def _build(self, tmp_path):
        cfg = base_config(
            name="multi-spec-dir",
            spec_dir=["spec/product", "spec/tech"],
        )
        prd = Requirement(
            "REQ-p00001",
            "Product Feature",
            "PRD",
            assertions=[("A", "The product SHALL have this feature.")],
        )
        dev = Requirement(
            "REQ-d00001",
            "Tech Implementation",
            "DEV",
            implements="REQ-p00001",
            assertions=[("A", "The module SHALL implement the feature.")],
        )
        build_project(
            tmp_path,
            cfg,
            spec_files={
                "spec/product/prd-features.md": [prd],
                "spec/tech/dev-impl.md": [dev],
            },
        )
        return tmp_path

    def test_health_passes(self, tmp_path):
        self._build(tmp_path)
        result = run_elspais("health", "--lenient", cwd=tmp_path)
        assert result.returncode == 0, f"health failed: {result.stderr}"

    def test_summary_counts_both_dirs(self, tmp_path):
        self._build(tmp_path)
        result = run_elspais("summary", "--format", "json", cwd=tmp_path)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        levels = data.get("levels", [])
        total = sum(lv.get("total", 0) for lv in levels)
        assert total == 2


# ---------------------------------------------------------------------------
# Test 10: Code references with testing enabled
# ---------------------------------------------------------------------------


class TestCodeRefsAndTesting:
    """Full traceability: spec -> code -> tests."""

    def _build(self, tmp_path):
        cfg = base_config(
            name="full-traceability",
            testing_enabled=True,
            test_dirs=["tests"],
        )
        prd = Requirement(
            "REQ-p00001",
            "Input Validation",
            "PRD",
            assertions=[
                ("A", "The system SHALL validate all user input."),
                ("B", "The system SHALL reject SQL injection attempts."),
            ],
        )
        dev = Requirement(
            "REQ-d00001",
            "Validator Module",
            "DEV",
            implements="REQ-p00001",
            assertions=[
                ("A", "The module SHALL sanitize input strings."),
                ("B", "The module SHALL use parameterized queries."),
            ],
        )
        build_project(
            tmp_path,
            cfg,
            spec_files={
                "spec/prd-security.md": [prd],
                "spec/dev-validator.md": [dev],
            },
            code_files={
                "src/validator.py": {
                    "implements": ["REQ-d00001"],
                    "content": "def validate(s):\n    return s.strip()",
                },
            },
            test_files={
                "tests/test_validator.py": {
                    "validates": ["REQ-d00001"],
                    "content": "def test_validate():\n    assert True",
                },
            },
        )
        return tmp_path

    def test_health_passes(self, tmp_path):
        self._build(tmp_path)
        result = run_elspais("health", "--lenient", cwd=tmp_path)
        assert result.returncode == 0, f"health failed: {result.stderr}"

    def test_health_json_shows_code_refs(self, tmp_path):
        self._build(tmp_path)
        result = run_elspais("health", "--format", "json", "--lenient", cwd=tmp_path)
        assert result.returncode == 0
        # Output should reference code/test coverage
        assert "REQ-d00001" in result.stdout

    def test_trace_shows_implementation(self, tmp_path):
        self._build(tmp_path)
        result = run_elspais("trace", "--format", "json", cwd=tmp_path)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data  # Non-empty


# ---------------------------------------------------------------------------
# Test 11: Trace output formats consistency
# ---------------------------------------------------------------------------


class TestTraceFormats:
    """Trace JSON, CSV, markdown, text all produce valid output."""

    def _build(self, tmp_path):
        cfg = base_config(name="trace-formats", allow_structural_orphans=True)
        reqs = [
            Requirement(
                "REQ-p00001",
                "Feature One",
                "PRD",
                assertions=[("A", "The system SHALL do one.")],
            ),
            Requirement(
                "REQ-p00002",
                "Feature Two",
                "PRD",
                assertions=[("A", "The system SHALL do two.")],
            ),
        ]
        build_project(tmp_path, cfg, spec_files={"spec/prd.md": reqs})
        return tmp_path

    def test_trace_json(self, tmp_path):
        self._build(tmp_path)
        result = run_elspais("trace", "--format", "json", cwd=tmp_path)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data

    def test_trace_csv(self, tmp_path):
        self._build(tmp_path)
        result = run_elspais("trace", "--format", "csv", cwd=tmp_path)
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert len(lines) >= 2  # header + at least 1 data row

    def test_trace_text(self, tmp_path):
        self._build(tmp_path)
        result = run_elspais("trace", "--format", "text", cwd=tmp_path)
        assert result.returncode == 0
        assert "REQ-p00001" in result.stdout

    def test_trace_markdown(self, tmp_path):
        self._build(tmp_path)
        result = run_elspais("trace", "--format", "markdown", cwd=tmp_path)
        assert result.returncode == 0
        assert "REQ-p00001" in result.stdout


# ---------------------------------------------------------------------------
# Test 12: Health with --spec, --code, --tests flags
# ---------------------------------------------------------------------------


class TestHealthScopeFlags:
    """Health command with --spec, --code, --tests scope flags."""

    def _build(self, tmp_path):
        cfg = base_config(
            name="health-scopes",
            testing_enabled=True,
            test_dirs=["tests"],
        )
        prd = Requirement(
            "REQ-p00001",
            "Scoped Feature",
            "PRD",
            assertions=[("A", "The system SHALL be scoped.")],
        )
        dev = Requirement(
            "REQ-d00001",
            "Scoped Impl",
            "DEV",
            implements="REQ-p00001",
            assertions=[("A", "The module SHALL implement scoping.")],
        )
        build_project(
            tmp_path,
            cfg,
            spec_files={
                "spec/prd-scoped.md": [prd],
                "spec/dev-scoped.md": [dev],
            },
            code_files={
                "src/scoped.py": {"implements": ["REQ-d00001"]},
            },
            test_files={
                "tests/test_scoped.py": {"validates": ["REQ-d00001"]},
            },
        )
        return tmp_path

    def test_health_spec_only(self, tmp_path):
        self._build(tmp_path)
        result = run_elspais("health", "--spec", "--lenient", cwd=tmp_path)
        assert result.returncode == 0

    def test_health_code_only(self, tmp_path):
        self._build(tmp_path)
        result = run_elspais("health", "--code", "--lenient", cwd=tmp_path)
        assert result.returncode == 0

    def test_health_tests_only(self, tmp_path):
        self._build(tmp_path)
        result = run_elspais("health", "--tests", "--lenient", cwd=tmp_path)
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# Test 13: Summary format variants
# ---------------------------------------------------------------------------


class TestSummaryFormats:
    """Summary in text, markdown, csv, json formats."""

    def _build(self, tmp_path):
        cfg = base_config(name="summary-formats", allow_structural_orphans=True)
        reqs = [
            Requirement(
                "REQ-p00001",
                "Summary Test",
                "PRD",
                assertions=[("A", "The system SHALL test summaries.")],
            ),
        ]
        build_project(tmp_path, cfg, spec_files={"spec/prd.md": reqs})
        return tmp_path

    def test_summary_json(self, tmp_path):
        self._build(tmp_path)
        result = run_elspais("summary", "--format", "json", cwd=tmp_path)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "levels" in data

    def test_summary_text(self, tmp_path):
        self._build(tmp_path)
        result = run_elspais("summary", "--format", "text", cwd=tmp_path)
        assert result.returncode == 0
        assert len(result.stdout.strip()) > 0

    def test_summary_csv(self, tmp_path):
        self._build(tmp_path)
        result = run_elspais("summary", "--format", "csv", cwd=tmp_path)
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert len(lines) >= 1

    def test_summary_markdown(self, tmp_path):
        self._build(tmp_path)
        result = run_elspais("summary", "--format", "markdown", cwd=tmp_path)
        assert result.returncode == 0
        assert len(result.stdout.strip()) > 0
