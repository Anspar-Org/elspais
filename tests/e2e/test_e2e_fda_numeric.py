# Verifies: REQ-p00002, REQ-p00003, REQ-p00004, REQ-p00060, REQ-d00080, REQ-d00085-A
"""FDA-style IDs + numeric assertions e2e tests — on-disk fixture with daemon acceleration.

Tests FDA-style ID patterns (PRD-00001, OPS-00001, DEV-00001), numeric-0
assertion labels, custom status roles, require_rationale, and the fix
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
import subprocess

import pytest

from .conftest import (
    ensure_fixture_daemon,
    load_fixture,
    run_elspais,
)
from .helpers import resolve_elspais

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        resolve_elspais() is None,
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

    # Verifies: REQ-d00086-A, REQ-d00281-A, REQ-d00281-B, REQ-d00291-E+F+I
    def test_level_groups_account_for_every_reported_requirement(self, project):
        """Every level the reported requirements carry forms one group, and the
        groups plus the status disclosure account for all 5 of them.

        This project's `[rules.format.status_roles]` gives Review the
        provisional role and Archived the retired role. Neither expects
        implementation, so PRD-00002 (Review) and DEV-00001 (Archived) are
        reported but not counted, which is why the DEV group is a true zero:
        the one requirement carrying that level is one the coverage gate holds
        back, not an absent value.
        """
        result = run_elspais("summary", "--format", "json", cwd=project)
        assert result.returncode == 0, f"summary failed: {result.stderr}"
        data = json.loads(result.stdout)

        # REQ-d00281-A / REQ-d00086-A: the groups and the counts they produce.
        groups = {lv["level"]: lv["requirements"] for lv in data["levels"]}
        assert groups == {"PRD": 2, "OPS": 1, "DEV": 0}

        # REQ-d00291-I: the two statuses whose roles do not expect
        # implementation are named rather than silently dropped.
        assert data["excluded"] == {"Review": 1, "Archived": 1}

        # REQ-d00281-B: exactly one group per reported requirement -- 3 counted
        # plus the 2 withheld are the 5 the report is over.
        trace = run_elspais("trace", "--format", "json", cwd=project)
        assert trace.returncode == 0
        reported = len(json.loads(trace.stdout))
        assert reported == 5
        assert sum(groups.values()) + sum(data["excluded"].values()) == reported

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

    # Verifies: REQ-d00251-H, REQ-d00282-B
    def test_numeric_labelled_assertions_are_counted(self, project):
        """A numeric *Assertion* label series is read as assertions, so the
        report's per-level assertion population counts them.

        REQ-d00251-H makes a label series one of the alphabets a repository may
        configure; this project configures the numeric one (zero-padded), so its
        labels have to be admitted as *Assertion* labels like any other. The
        figure they land in is the population REQ-d00282-B obliges a report to
        offer. The requirement counts are pinned by
        ``TestFDAHealth::test_level_groups_account_for_every_reported_requirement``;
        this is the *Assertion* side, which is the axis this class exists for.
        """
        result = run_elspais("summary", "--format", "json", cwd=project)
        assert result.returncode == 0, f"summary failed: {result.stderr}"
        data = json.loads(result.stdout)
        assert {lv["level"]: lv["assertions"] for lv in data["levels"]} == {
            "PRD": 3,
            "OPS": 1,
            "DEV": 0,
        }


@pytest.mark.e2e
class TestCustomStatuses:
    """Config: status_roles names Review provisional and Archived retired."""

    def test_health_passes_with_custom_statuses(self, project):
        # PRD-00002 is Review, DEV-00001 is Archived — both should be valid
        result = run_elspais("checks", "--lenient", cwd=project)
        assert result.returncode == 0, f"health failed: {result.stderr}"

    # Verifies: REQ-d00278-B, REQ-d00278-G, REQ-p00084-B, REQ-p00084-D
    def test_status_role_scope_selects_exactly_the_counted_requirements(self, project):
        """Naming Active as a role selects the three requirements the coverage
        gate counts, and nothing that gate withholds.

        With ``--match-status-roles`` the name Active stands for every status
        this project gives the active role (REQ-d00278-G) -- here just Active.
        Selecting on it therefore narrows emission down to the population the
        default report counts, so the `excluded` disclosure goes empty while
        the level counts do not move: a requirement that leaked across the role
        boundary in either direction shows up in one of the two.
        """
        scoped = run_elspais(
            "summary",
            "--format",
            "json",
            "--status",
            "Active",
            "--match-status-roles",
            cwd=project,
        )
        assert scoped.returncode == 0, f"summary failed: {scoped.stderr}"
        data = json.loads(scoped.stdout)

        # REQ-p00084-D: the report discloses the scope it was produced under.
        disclosure = " ".join(data["scope"])
        assert "status Active" in disclosure
        assert "a named status stands for its role" in disclosure
        # REQ-p00084-B: 3 of the 5 requirements selected and emitted.
        assert "3 of 5" in disclosure

        # Everything emitted is counted, so nothing remains to disclose.
        assert data["excluded"] == {}
        assert {lv["level"]: lv["requirements"] for lv in data["levels"]} == {
            "PRD": 2,
            "OPS": 1,
            "DEV": 0,
        }

    # Verifies: REQ-d00278-B, REQ-d00291-E+F+I, REQ-p00084-B, REQ-p00084-E
    def test_provisional_status_scope_emits_what_it_does_not_count(self, project):
        """A Review scope selects PRD-00002 and still counts nothing.

        Review carries the provisional role, so REQ-d00291-E+F keeps the
        requirement out of the coverage aggregation -- and asking for it by
        name does not move that line (REQ-p00084-E). Emission selected it;
        measurement did not.
        """
        result = run_elspais("summary", "--format", "json", "--status", "Review", cwd=project)
        assert result.returncode == 0, f"summary failed: {result.stderr}"
        data = json.loads(result.stdout)

        disclosure = " ".join(data["scope"])
        assert "status Review" in disclosure
        assert "1 of 5" in disclosure

        assert data["excluded"] == {"Review": 1}
        assert sum(lv["requirements"] for lv in data["levels"]) == 0


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

    # Verifies: REQ-p00084-E, REQ-d00278-C
    def test_widening_the_scope_does_not_move_a_single_figure(self, project):
        """A scope naming all three statuses emits all 5 requirements and
        states exactly the figures the unscoped report states.

        Widening emission is the other direction from the narrowing
        TestCustomStatuses covers, and REQ-p00084-E binds both: the coverage
        gate of REQ-d00291-F decides what is measured, and no scope may move
        it. The disclosure is also where a scanning leak would surface -- "5 of
        5" is the size of the reported estate, not of the counted population.
        """
        scoped = run_elspais(
            "summary",
            "--format",
            "json",
            "--status",
            "Active",
            "Review",
            "Archived",
            cwd=project,
        )
        assert scoped.returncode == 0, f"summary failed: {scoped.stderr}"
        scoped_data = json.loads(scoped.stdout)

        disclosure = " ".join(scoped_data["scope"])
        assert "status Active or Review or Archived" in disclosure
        assert "5 of 5" in disclosure

        unscoped = run_elspais("summary", "--format", "json", cwd=project)
        assert unscoped.returncode == 0
        unscoped_data = json.loads(unscoped.stdout)
        assert unscoped_data["scope"] == []

        # REQ-p00084-E: same levels, same counts, same disclosure.
        assert scoped_data["levels"] == unscoped_data["levels"]
        assert (
            scoped_data["excluded"]
            == unscoped_data["excluded"]
            == {
                "Review": 1,
                "Archived": 1,
            }
        )


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
            assert "PRD-00001" in ancestor_ids or "OPS-00001" in ancestor_ids, (
                f"Expected PRD-00001 or OPS-00001 in ancestors, got: {ancestor_ids}"
            )
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

            # Add another numeric assertion, guarded by the version token from
            # the read above (REQ-o00062 optimistic concurrency).
            version = req.get("version")
            assert version, f"get_requirement reported no version token: {req}"
            result = mcp_call(
                proc,
                "mutate_add_assertion",
                {
                    "req_id": "PRD-00001",
                    "text": "The system SHALL do two.",
                    "if_version": version,
                },
            )
            assert result.get("success") is True, f"mutate_add_assertion failed: {result}"

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
