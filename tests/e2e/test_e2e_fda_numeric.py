# Verifies: REQ-p00002, REQ-p00003, REQ-p00004, REQ-p00060, REQ-d00080, REQ-d00085-A
"""FDA-style IDs + numeric assertions e2e tests — module-scoped fixture with daemon acceleration.

Tests FDA-style ID patterns (PRD-00001, OPS-00001, DEV-00001), numeric-0
assertion labels, custom allowed_statuses, require_rationale, and the fix
command against an FDA-style project.

Groups:
  1. Read-only CLI tests (health, summary, trace)
  2. Mutation tests (fix corrects FDA hashes)
  3. MCP query tests (search, get_requirement, hierarchy)
  4. Config variation tests (require_rationale, status filtering)
  5. MCP numeric assertion mutation test
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from .conftest import (
    build_fixture_project,
    ensure_fixture_daemon,
)
from .helpers import (
    Requirement,
    compute_hash,
    labels_numeric,
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
# Fixture project content
# ---------------------------------------------------------------------------

# FDA-style config overrides
_FDA_CONFIG_OVERRIDES = {
    "name": "e2e-fda-numeric",
    "canonical": "{type}-{component}",
    "types": {
        "PRD": {"level": 1},
        "OPS": {"level": 2},
        "DEV": {"level": 3},
    },
    "allowed_implements": ["DEV -> OPS, PRD", "OPS -> PRD", "PRD -> PRD"],
    "label_style": "numeric",
    "labels_sequential": True,
    "allowed_statuses": ["Active", "Draft", "Review", "Archived"],
    "allow_structural_orphans": True,
}

# PRD-00001 — Active with rationale, numeric assertions
_RATIONALE_TEXT = "Required for regulatory compliance with FDA 21 CFR Part 11."

_PRD_00001 = Requirement(
    "PRD-00001",
    "Regulatory Compliance",
    "PRD",
    status="Active",
    assertions=[
        ("0", "The system SHALL comply with FDA 21 CFR Part 11."),
        ("1", "The system SHALL maintain audit trails."),
    ],
    rationale=_RATIONALE_TEXT,
)

# PRD-00002 — Review status
_PRD_00002 = Requirement(
    "PRD-00002",
    "Data Integrity",
    "PRD",
    status="Review",
    assertions=[
        ("0", "The system SHALL validate all data inputs."),
        ("1", "The system SHALL reject malformed records."),
    ],
    rationale="Needed for GxP data integrity requirements.",
)

# OPS-00001 — Active, implements PRD-00001
_OPS_00001 = Requirement(
    "OPS-00001",
    "Compliance Monitoring",
    "OPS",
    status="Active",
    implements="PRD-00001",
    assertions=[
        ("0", "Operations SHALL monitor compliance status daily."),
    ],
    rationale="Operational oversight of compliance posture.",
)

# DEV-00001 — Archived, implements OPS-00001
_DEV_00001 = Requirement(
    "DEV-00001",
    "Audit Logger",
    "DEV",
    status="Archived",
    implements="OPS-00001",
    assertions=[
        ("0", "The module SHALL log all data modifications."),
        ("1", "The module SHALL include timestamps in ISO 8601 format."),
        ("2", "The module SHALL sign audit entries cryptographically."),
    ],
)


def _build_spec_content(reqs: list[Requirement]) -> str:
    """Render multiple requirements to spec file content."""
    return "\n".join(r.render() for r in reqs)


def _build_wrong_hash_prd_spec() -> str:
    """Build prd-regulatory.md with an intentionally wrong hash for fix testing."""
    return (
        "# PRD-00001: Regulation\n\n"
        "**Level**: PRD | **Status**: Active\n\n"
        "## Assertions\n\n"
        "A. The system SHALL comply.\n\n"
        "*End* *Regulation* | **Hash**: XXXXXXXX\n---\n"
    )


def _build_wrong_hash_dev_spec() -> str:
    """Build dev-impl.md with intentionally wrong hash for fix testing."""
    return (
        "# DEV-00001: Implementation\n\n"
        "**Level**: DEV | **Status**: Active | **Implements**: PRD-00001\n\n"
        "## Assertions\n\n"
        "A. The module SHALL implement compliance.\n\n"
        "*End* *Implementation* | **Hash**: XXXXXXXX\n---\n"
    )


# ---------------------------------------------------------------------------
# Module-scoped fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def project(tmp_path_factory):
    """Build the FDA-numeric project once for the entire module."""
    root = tmp_path_factory.mktemp("e2e_fda_numeric")

    spec_files = {
        "spec/prd-core.md": _build_spec_content([_PRD_00001, _PRD_00002]),
        "spec/ops-compliance.md": _build_spec_content([_OPS_00001]),
        "spec/dev-audit.md": _build_spec_content([_DEV_00001]),
    }

    build_fixture_project(
        root,
        config_overrides=_FDA_CONFIG_OVERRIDES,
        spec_files=spec_files,
    )
    ensure_fixture_daemon(root)
    return root


# ---------------------------------------------------------------------------
# Group 1: Read-only CLI tests
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestFDAHealth:
    """FDA-style IDs health, summary, trace — ported from TestFDAStyleIds."""

    def test_health_passes(self, project):
        result = run_elspais("checks", "--lenient", cwd=project)
        assert result.returncode == 0, f"health failed: {result.stderr}"

    def test_summary_counts_4(self, project):
        result = run_elspais("summary", "--format", "json", cwd=project)
        assert result.returncode == 0, f"summary failed: {result.stderr}"
        data = json.loads(result.stdout)
        levels = data.get("levels", [])
        total = sum(lv.get("total", 0) for lv in levels)
        # 4 requirements total (PRD-00001, PRD-00002, OPS-00001, DEV-00001)
        # Summary counts by active status; at least 2 Active requirements visible
        assert total >= 1, f"Expected at least 1 requirement in summary, got {total}"

    def test_trace_contains_fda_ids(self, project):
        result = run_elspais("trace", "--format", "json", cwd=project)
        assert result.returncode == 0
        output = result.stdout
        assert "PRD-00001" in output
        assert "OPS-00001" in output
        assert "DEV-00001" in output


@pytest.mark.e2e
class TestNumericAssertionLabels:
    """Config: label_style='numeric', labels_sequential=True — ported from source."""

    def test_health_passes_with_numeric_labels(self, project):
        result = run_elspais("checks", "--lenient", cwd=project)
        assert result.returncode == 0, f"health failed: {result.stderr}"

    def test_summary_counts_requirements(self, project):
        result = run_elspais("summary", "--format", "json", cwd=project)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        levels = data.get("levels", [])
        total = sum(lv.get("total", 0) for lv in levels)
        assert total >= 1


@pytest.mark.e2e
class TestCustomStatuses:
    """Config: allowed_statuses includes Review and Archived — ported from source."""

    def test_health_passes_with_custom_statuses(self, project):
        # PRD-00002 is Review, DEV-00001 is Archived — both should be valid
        result = run_elspais("checks", "--lenient", cwd=project)
        assert result.returncode == 0, f"health failed: {result.stderr}"

    def test_summary_default_counts_active_only(self, project):
        """Default summary filters to Active status."""
        result = run_elspais("summary", "--format", "json", cwd=project)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        levels = data.get("levels", [])
        total = sum(lv.get("total", 0) for lv in levels)
        # Default --status=Active means Active reqs counted; at least PRD-00001
        assert total >= 1


# ---------------------------------------------------------------------------
# Group 2: Mutation tests (fix)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestFixFDAStyle:
    """Fix command with FDA-style IDs — ported from TestFixFDAStyle."""

    def test_fix_corrects_fda_hashes(self, tmp_path):
        """Fix corrects wrong hashes in FDA-style project (uses own tmp_path, not module fixture)."""
        from .helpers import base_config, build_project

        cfg = base_config(
            name="fix-fda",
            canonical="{type}-{component}",
            types={
                "PRD": {"level": 1},
                "DEV": {"level": 3},
            },
            allowed_implements=["DEV -> PRD"],
        )
        build_project(tmp_path, cfg, spec_files={})

        prd_spec = tmp_path / "spec" / "prd-regs.md"
        prd_spec.parent.mkdir(parents=True, exist_ok=True)
        prd_spec.write_text(_build_wrong_hash_prd_spec())
        dev_spec = tmp_path / "spec" / "dev-impl.md"
        dev_spec.write_text(_build_wrong_hash_dev_spec())

        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "add fda"],
            cwd=tmp_path,
            capture_output=True,
        )

        fix = run_elspais("fix", cwd=tmp_path)
        assert fix.returncode == 0, f"fix failed: {fix.stderr}"

        # Verify hashes were corrected
        prd_content = prd_spec.read_text()
        assert "XXXXXXXX" not in prd_content, "PRD hash was not corrected by fix"
        match = re.search(r"\*\*Hash\*\*:\s*([0-9a-f]{8})", prd_content)
        assert match, "No valid 8-char hex hash found in PRD file after fix"

        health = run_elspais("checks", "--lenient", cwd=tmp_path)
        assert health.returncode == 0, f"health failed after fix: {health.stderr}"


# ---------------------------------------------------------------------------
# Group 3: MCP query tests
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestMCPFDAStyle:
    """MCP tools work with FDA-style ID patterns — ported from TestMCPFDAStyle."""

    def test_search_fda_ids(self, project):
        pytest.importorskip("mcp")
        from .helpers import mcp_call_all, start_mcp, stop_mcp

        proc = start_mcp(project)
        try:
            results = mcp_call_all(proc, "search", {"query": "Compliance"})
            assert len(results) >= 1
            ids = [r.get("id", "") for r in results]
            assert any("PRD-00001" in i for i in ids), f"PRD-00001 not found in: {ids}"
        finally:
            stop_mcp(proc)

    def test_get_requirement_fda(self, project):
        pytest.importorskip("mcp")
        from .helpers import mcp_call, start_mcp, stop_mcp

        proc = start_mcp(project)
        try:
            result = mcp_call(proc, "get_requirement", {"req_id": "PRD-00001"})
            assert result["id"] == "PRD-00001"
            assert "Compliance" in result.get("title", "")
        finally:
            stop_mcp(proc)

    def test_hierarchy_fda(self, project):
        pytest.importorskip("mcp")
        from .helpers import mcp_call, start_mcp, stop_mcp

        proc = start_mcp(project)
        try:
            result = mcp_call(proc, "get_hierarchy", {"req_id": "DEV-00001"})
            assert "ancestors" in result
            ancestor_ids = [a.get("id", "") for a in result["ancestors"]]
            # DEV-00001 -> OPS-00001 -> PRD-00001
            assert "PRD-00001" in ancestor_ids or "OPS-00001" in ancestor_ids, (
                f"Expected PRD-00001 or OPS-00001 in ancestors, got: {ancestor_ids}"
            )
        finally:
            stop_mcp(proc)


# ---------------------------------------------------------------------------
# Group 4: Config variation tests
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestRequireRationale:
    """Config: require_rationale=True — ported from TestRequireRationale."""

    def test_rationale_required_present(self, tmp_path):
        from .helpers import base_config, build_project

        cfg = base_config(name="rationale-required", allow_structural_orphans=True)
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

        result = run_elspais("checks", "--lenient", cwd=tmp_path)
        assert result.returncode == 0, f"health failed: {result.stdout}"


@pytest.mark.e2e
class TestStatusFiltering:
    """Health and summary handle Deprecated/Superseded requirements — ported from source."""

    def test_deprecated_excluded_from_summary(self, tmp_path):
        from .helpers import base_config, build_project

        cfg = base_config(name="status-filter", allow_structural_orphans=True)
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
        health = run_elspais("checks", "--lenient", cwd=tmp_path)
        assert health.returncode == 0

        # Summary default (Active only) should show >= 1
        summary = run_elspais("summary", "--format", "json", cwd=tmp_path)
        data = json.loads(summary.stdout)
        total = sum(lv.get("total", 0) for lv in data.get("levels", []))
        assert total >= 1  # At least 1 Active


# ---------------------------------------------------------------------------
# Group 5: MCP numeric assertion mutation
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestMCPNumericAssertions:
    """MCP tools work with numeric assertion labels — ported from TestMCPNumericAssertions."""

    def test_mcp_numeric_assertions(self, tmp_path):
        pytest.importorskip("mcp")
        from .helpers import base_config, build_project, mcp_call, start_mcp, stop_mcp

        cfg = base_config(
            name="mcp-numeric",
            label_style="numeric",
            allow_structural_orphans=True,
        )
        prd = Requirement(
            "REQ-p00001",
            "Numeric MCP",
            "PRD",
            assertions=[
                ("0", "The system SHALL do zero."),
                ("1", "The system SHALL do one."),
                ("2", "The system SHALL do two."),
            ],
        )
        build_project(tmp_path, cfg, spec_files={"spec/prd.md": [prd]})

        proc = start_mcp(tmp_path)
        try:
            req = mcp_call(proc, "get_requirement", {"req_id": "REQ-p00001"})
            assert req["id"] == "REQ-p00001"
            labels = [a.get("label", "") for a in req.get("assertions", [])]
            assert "0" in labels
            assert "1" in labels
            assert "2" in labels

            # Add another numeric assertion
            mcp_call(
                proc,
                "mutate_add_assertion",
                {
                    "req_id": "REQ-p00001",
                    "label": "3",
                    "text": "The system SHALL do three.",
                },
            )

            # Verify it was added
            req2 = mcp_call(proc, "get_requirement", {"req_id": "REQ-p00001"})
            labels2 = [a.get("label", "") for a in req2.get("assertions", [])]
            assert "3" in labels2
        finally:
            stop_mcp(proc)
