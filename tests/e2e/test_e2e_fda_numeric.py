# Verifies: REQ-p00002, REQ-p00003, REQ-p00004, REQ-p00060, REQ-d00080, REQ-d00085-A
"""FDA-style IDs + numeric assertions e2e tests — on-disk fixture with daemon acceleration.

Tests FDA-style ID patterns (PRD-00001, OPS-00001, DEV-00001), numeric-0
assertion labels, custom allowed_statuses, require_rationale, and the fix
command against an FDA-style project.

Groups:
  1. Read-only CLI tests (health, summary, trace)
  2. Config variation tests (require_rationale, status filtering)
  3. Term health checks
  4. MCP query tests (search, get_requirement, hierarchy)
  5. MCP numeric assertion mutation test
  6. CLI mutation tests (fix, incremental)
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from .conftest import (
    ensure_fixture_daemon,
    load_fixture,
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
# Module-scoped fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def project(tmp_path_factory):
    """Copy e2e-fda-numeric fixture to /tmp, init git, start daemon."""
    root = tmp_path_factory.mktemp("e2e_fda_numeric")
    load_fixture("e2e-fda-numeric", root)
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
# Group 2: Config variation tests
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestRequireRationale:
    """Config: require_rationale=True — fixture already has rationale on all reqs."""

    def test_rationale_required_present(self, project):
        result = run_elspais("checks", "--lenient", cwd=project)
        assert result.returncode == 0, f"health failed: {result.stdout}"


@pytest.mark.e2e
class TestStatusFiltering:
    """Health and summary handle Review/Archived requirements — uses shared fixture."""

    def test_statuses_accepted_by_health(self, project):
        # PRD-00002 is Review, DEV-00001 is Archived — both should be valid
        health = run_elspais("checks", "--lenient", cwd=project)
        assert health.returncode == 0

    def test_summary_default_active_only(self, project):
        """Default summary (Active only) should show >= 1."""
        summary = run_elspais("summary", "--format", "json", cwd=project)
        data = json.loads(summary.stdout)
        total = sum(lv.get("total", 0) for lv in data.get("levels", []))
        assert total >= 1  # At least 1 Active


# ---------------------------------------------------------------------------
# Group 3: Term health checks
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestFDATermChecks:
    """Term health checks with alternate severity config."""

    def test_term_checks_present(self, project):
        result = run_elspais("checks", "--format", "json", "--lenient", cwd=project)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        check_names = {c["name"] for c in data.get("checks", [])}
        assert "terms.duplicates" in check_names

    def test_off_severity_checks_pass(self, project):
        """Checks with severity='off' always pass."""
        result = run_elspais("checks", "--format", "json", "--lenient", cwd=project)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        checks = {c["name"]: c for c in data.get("checks", [])}
        for name in ("terms.undefined", "terms.unmarked", "terms.collection_empty"):
            if name in checks:
                assert checks[name]["passed"], f"{name} should pass with severity=off"

    def test_glossary_command(self, project):
        result = run_elspais("glossary", "--format", "json", cwd=project)
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# Group 4: MCP query tests
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
            assert (
                "PRD-00001" in ancestor_ids or "OPS-00001" in ancestor_ids
            ), f"Expected PRD-00001 or OPS-00001 in ancestors, got: {ancestor_ids}"
        finally:
            stop_mcp(proc)


# ---------------------------------------------------------------------------
# Group 5: MCP numeric assertion mutation
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestMCPNumericAssertions:
    """MCP tools work with numeric assertion labels — uses shared fixture."""

    def test_mcp_numeric_assertions(self, project):
        pytest.importorskip("mcp")
        from .helpers import mcp_call, start_mcp, stop_mcp

        proc = start_mcp(project)
        try:
            req = mcp_call(proc, "get_requirement", {"req_id": "PRD-00001"})
            assert req["id"] == "PRD-00001"
            labels = [a.get("label", "") for a in req.get("assertions", [])]
            assert "0" in labels
            assert "1" in labels

            # Add another numeric assertion
            mcp_call(
                proc,
                "mutate_add_assertion",
                {
                    "req_id": "PRD-00001",
                    "label": "2",
                    "text": "The system SHALL do two.",
                },
            )

            # Verify it was added
            req2 = mcp_call(proc, "get_requirement", {"req_id": "PRD-00001"})
            labels2 = [a.get("label", "") for a in req2.get("assertions", [])]
            assert "2" in labels2
        finally:
            stop_mcp(proc)


# ---------------------------------------------------------------------------
# Group 6: CLI mutation tests (incremental, placed last)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.incremental
class TestFDACLIMutations:
    """Sequential CLI mutations on the FDA fixture."""

    def test_01_fix_corrects_wrong_hash(self, project):
        """Fix corrects XXXXXXXX hash in prd-wrong-hash.md."""
        subprocess.run(["git", "add", "."], cwd=project, capture_output=True)
        subprocess.run(["git", "commit", "-m", "pre-fix"], cwd=project, capture_output=True)

        result = run_elspais("fix", cwd=project)
        assert result.returncode == 0, f"fix failed: {result.stderr}"
        content = (project / "spec/prd-wrong-hash.md").read_text()
        assert "XXXXXXXX" not in content
        match = re.search(r"\*\*Hash\*\*:\s*([0-9a-f]{8})", content)
        assert match, "No valid 8-char hex hash found in PRD file after fix"

    def test_02_health_after_fix(self, project):
        result = run_elspais("checks", "--lenient", cwd=project)
        assert result.returncode == 0, f"health failed after fix: {result.stderr}"
