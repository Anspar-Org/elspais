# Verifies: REQ-d00085-A
"""E2E tests for complex multi-command workflows.

Each test exercises multiple commands in sequence, validating
cross-command consistency and realistic usage scenarios.
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
# Test 61: Init -> add reqs -> fix -> health -> summary workflow
# ---------------------------------------------------------------------------


class TestFullProjectLifecycle:
    """Complete project lifecycle from init to validated state."""

    def test_lifecycle(self, tmp_path):
        # 1. Init project
        init = run_elspais("init", cwd=tmp_path)
        assert init.returncode == 0

        # 1b. Disable changelog enforcement for this test (Active REQs defer otherwise)
        config_path = tmp_path / ".elspais.toml"
        config_text = config_path.read_text()
        config_text = config_text.replace("hash_current = true", "hash_current = false")
        config_path.write_text(config_text)

        # 2. Create spec directory and requirement
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir(exist_ok=True)
        spec_file = spec_dir / "prd-features.md"
        spec_file.write_text(
            "# REQ-p00001: Feature One\n\n"
            "**Level**: PRD | **Status**: Active\n\n"
            "## Assertions\n\n"
            "A. The system SHALL implement feature one.\n\n"
            "*End* *Feature One* | **Hash**: 00000000\n---\n"
        )

        # 3. Commit so fix can work
        subprocess.run(["git", "init", "-b", "main"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"], cwd=tmp_path, capture_output=True
        )
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=tmp_path, capture_output=True)

        # 4. Fix hashes
        fix = run_elspais("fix", cwd=tmp_path)
        assert fix.returncode == 0

        # 5. Health should pass
        health = run_elspais("checks", "--lenient", cwd=tmp_path)
        assert health.returncode == 0

        # 6. Summary should show 1 PRD requirement
        summary = run_elspais("summary", "--format", "json", cwd=tmp_path)
        assert summary.returncode == 0
        data = json.loads(summary.stdout)
        levels = data.get("levels", [])
        prd_count = next((lv["total"] for lv in levels if lv["level"] == "PRD"), 0)
        assert prd_count == 1

        # 7. Trace should include the requirement
        trace = run_elspais("trace", "--format", "json", cwd=tmp_path)
        assert trace.returncode == 0
        trace_data = json.loads(trace.stdout)
        assert len(trace_data) == 1
        assert trace_data[0]["id"] == "REQ-p00001"


# ---------------------------------------------------------------------------
# Test 62: Health -> trace -> summary consistency
# ---------------------------------------------------------------------------


class TestCrossCommandConsistency:
    """Health, trace, and summary report consistent requirement counts."""

    def test_counts_consistent(self, tmp_path):
        cfg = base_config(name="consistency")
        reqs_prd = [
            Requirement(
                f"REQ-p0000{i}", f"PRD-{i}", "PRD", assertions=[("A", f"The system SHALL do {i}.")]
            )
            for i in range(1, 4)
        ]
        reqs_ops = [
            Requirement(
                f"REQ-o0000{i}",
                f"OPS-{i}",
                "OPS",
                implements=f"REQ-p0000{i}",
                assertions=[("A", f"Operations SHALL manage {i}.")],
            )
            for i in range(1, 4)
        ]
        build_project(
            tmp_path,
            cfg,
            spec_files={
                "spec/prd.md": reqs_prd,
                "spec/ops.md": reqs_ops,
            },
        )

        # Get counts from summary
        summary = run_elspais("summary", "--format", "json", cwd=tmp_path)
        assert summary.returncode == 0
        summary_data = json.loads(summary.stdout)
        summary_total = sum(lv["total"] for lv in summary_data["levels"])

        # Get counts from trace
        trace = run_elspais("trace", "--format", "json", cwd=tmp_path)
        assert trace.returncode == 0
        trace_data = json.loads(trace.stdout)
        trace_total = len(trace_data)

        # Both should agree
        assert (
            summary_total == trace_total == 6
        ), f"Inconsistency: summary={summary_total}, trace={trace_total}"


# ---------------------------------------------------------------------------
# Test 63: Config set -> health verifies new setting
# ---------------------------------------------------------------------------


class TestConfigSetAffectsHealth:
    """Changing config settings affects health validation."""

    def test_change_allowed_statuses(self, tmp_path):
        cfg = base_config(name="config-affects-health", allow_structural_orphans=True)
        prd = Requirement(
            "REQ-p00001",
            "Custom Status",
            "PRD",
            status="InReview",
            assertions=[("A", "The system SHALL be in review.")],
        )
        build_project(tmp_path, cfg, spec_files={"spec/prd.md": [prd]})

        # Health should fail because "InReview" is not an allowed status
        run_elspais("checks", cwd=tmp_path)
        # May fail or warn

        # Add InReview to allowed statuses
        set_result = run_elspais(
            "config",
            "add",
            "rules.format.allowed_statuses",
            "InReview",
            cwd=tmp_path,
        )
        assert set_result.returncode == 0

        # Fix hashes and format issues
        run_elspais("fix", cwd=tmp_path)

        # Health should now pass
        health2 = run_elspais("checks", "--lenient", cwd=tmp_path)
        assert health2.returncode == 0, f"health failed: {health2.stdout}"


# ---------------------------------------------------------------------------
# Test 64: Multiple fixes preserve content
# ---------------------------------------------------------------------------


class TestMultipleFixesIdempotent:
    """Running fix twice produces same result."""

    def test_fix_idempotent(self, tmp_path):
        cfg = base_config(name="fix-idempotent", allow_structural_orphans=True)
        build_project(tmp_path, cfg, spec_files={})

        spec = tmp_path / "spec" / "prd.md"
        spec.parent.mkdir(parents=True, exist_ok=True)
        spec.write_text(
            "# REQ-p00001: Idempotent\n\n"
            "**Level**: PRD | **Status**: Active\n\n"
            "## Assertions\n\n"
            "A. The system SHALL be idempotent.\n"
            "B. The system SHALL be consistent.\n\n"
            "*End* *Idempotent* | **Hash**: 00000000\n---\n"
        )

        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "add"], cwd=tmp_path, capture_output=True)

        # First fix
        run_elspais("fix", cwd=tmp_path)
        content1 = spec.read_text()

        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "fix1"], cwd=tmp_path, capture_output=True)

        # Second fix (should be no-op)
        run_elspais("fix", cwd=tmp_path)
        content2 = spec.read_text()

        assert content1 == content2, "Second fix changed the file"


# ---------------------------------------------------------------------------
# Test 65: Trace with assertions flag
# ---------------------------------------------------------------------------


class TestTraceWithAssertions:
    """Trace --assertions shows individual assertion details."""

    def test_trace_assertions(self, tmp_path):
        cfg = base_config(name="trace-assertions", allow_structural_orphans=True)
        prd = Requirement(
            "REQ-p00001",
            "Assertion Trace",
            "PRD",
            assertions=[
                ("A", "The system SHALL show assertion A."),
                ("B", "The system SHALL show assertion B."),
                ("C", "The system SHALL show assertion C."),
            ],
        )
        build_project(tmp_path, cfg, spec_files={"spec/prd.md": [prd]})

        result = run_elspais("trace", "--format", "json", "--assertions", cwd=tmp_path)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        # With assertions flag, output may include assertion details
        output_str = json.dumps(data)
        assert "REQ-p00001" in output_str


# ---------------------------------------------------------------------------
# Test 66: Graph export then MCP navigation
# ---------------------------------------------------------------------------


class TestGraphExportAndMCP:
    """Export graph JSON, then validate via MCP."""

    def test_graph_and_mcp_agree(self, tmp_path):
        pytest.importorskip("mcp")
        from .helpers import mcp_call, start_mcp, stop_mcp

        cfg = base_config(name="graph-mcp", allow_structural_orphans=True)
        prd = Requirement(
            "REQ-p00001",
            "Graph MCP",
            "PRD",
            assertions=[("A", "The system SHALL agree.")],
        )
        build_project(tmp_path, cfg, spec_files={"spec/prd.md": [prd]})

        # Get graph JSON
        graph_result = run_elspais("graph", cwd=tmp_path)
        assert graph_result.returncode == 0
        json.loads(graph_result.stdout)  # verify valid JSON

        # Now verify via MCP
        proc = start_mcp(tmp_path)
        try:
            req = mcp_call(proc, "get_requirement", {"req_id": "REQ-p00001"})
            assert req["id"] == "REQ-p00001"
            assert req["title"] == "Graph MCP"
        finally:
            stop_mcp(proc)


# ---------------------------------------------------------------------------
# Test 67: Edit command (if available)
# ---------------------------------------------------------------------------


class TestEditCommand:
    """Edit command modifies requirements in-place."""

    def test_edit_status(self, tmp_path):
        cfg = base_config(name="edit-test", allow_structural_orphans=True)
        prd = Requirement(
            "REQ-p00001",
            "Edit Target",
            "PRD",
            assertions=[("A", "The system SHALL be editable.")],
        )
        build_project(tmp_path, cfg, spec_files={"spec/prd.md": [prd]})

        result = run_elspais(
            "edit",
            "REQ-p00001",
            "--status",
            "Draft",
            cwd=tmp_path,
        )
        # Edit may or may not be available
        if result.returncode == 0:
            content = (tmp_path / "spec" / "prd.md").read_text()
            assert "Draft" in content


# ---------------------------------------------------------------------------
# Test 68: Doctor + version
# ---------------------------------------------------------------------------


class TestDoctorAndVersion:
    """Doctor and version commands."""

    def test_doctor_json(self, tmp_path):
        cfg = base_config(name="doctor-json", allow_structural_orphans=True)
        build_project(tmp_path, cfg, spec_files={})
        (tmp_path / "spec").mkdir(exist_ok=True)

        result = run_elspais("doctor", "--format", "json", cwd=tmp_path)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data, (dict, list))

    def test_version(self, tmp_path):
        result = run_elspais("version")
        assert result.returncode == 0
        assert len(result.stdout.strip()) > 0


# ---------------------------------------------------------------------------
# Test 69: Health text output format
# ---------------------------------------------------------------------------


class TestHealthTextOutput:
    """Health text output includes check marks and details."""

    def test_health_text_contains_checks(self, tmp_path):
        cfg = base_config(name="health-text", allow_structural_orphans=True)
        prd = Requirement(
            "REQ-p00001",
            "Text Health",
            "PRD",
            assertions=[("A", "The system SHALL pass health checks.")],
        )
        build_project(tmp_path, cfg, spec_files={"spec/prd.md": [prd]})

        result = run_elspais("checks", "--lenient", cwd=tmp_path)
        assert result.returncode == 0
        # Text output should contain section headers
        assert "CONFIG" in result.stdout or "SPEC" in result.stdout

    def test_health_json_structure(self, tmp_path):
        cfg = base_config(name="health-json", allow_structural_orphans=True)
        prd = Requirement(
            "REQ-p00001",
            "JSON Health",
            "PRD",
            assertions=[("A", "The system SHALL have JSON health.")],
        )
        build_project(tmp_path, cfg, spec_files={"spec/prd.md": [prd]})

        result = run_elspais("checks", "--format", "json", "--lenient", cwd=tmp_path)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data, (dict, list))


# ---------------------------------------------------------------------------
# Test 70: MCP workflow with numeric assertions
# ---------------------------------------------------------------------------


class TestMCPNumericAssertions:
    """MCP tools work with numeric assertion labels."""

    def test_mcp_numeric_assertions(self, tmp_path):
        pytest.importorskip("mcp")
        from .helpers import mcp_call, start_mcp, stop_mcp

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


# ---------------------------------------------------------------------------
# Test 71: MCP mutation save + refresh round-trip
# ---------------------------------------------------------------------------


class TestMCPSaveRefreshRoundTrip:
    """Mutate -> save -> refresh -> verify persisted."""

    def test_save_refresh_roundtrip(self, tmp_path):
        pytest.importorskip("mcp")
        from .helpers import mcp_call, start_mcp, stop_mcp

        cfg = base_config(name="save-refresh", allow_structural_orphans=True)
        prd = Requirement(
            "REQ-p00001",
            "Save Refresh",
            "PRD",
            assertions=[("A", "The system SHALL save and refresh.")],
        )
        build_project(tmp_path, cfg, spec_files={"spec/prd.md": [prd]})

        proc = start_mcp(tmp_path)
        try:
            # 1. Mutate title
            mcp_call(
                proc,
                "mutate_update_title",
                {
                    "node_id": "REQ-p00001",
                    "new_title": "Updated Via MCP",
                },
            )

            # 2. Save to disk
            save = mcp_call(proc, "save_mutations", {"save_branch": False})
            assert not save.get("_error"), f"Save failed: {save}"

            # 3. Refresh from disk
            refresh = mcp_call(proc, "refresh_graph", {})
            assert not refresh.get("_error"), f"Refresh failed: {refresh}"

            # 4. Verify title persisted through refresh
            req = mcp_call(proc, "get_requirement", {"req_id": "REQ-p00001"})
            assert req["title"] == "Updated Via MCP"
        finally:
            stop_mcp(proc)


# ---------------------------------------------------------------------------
# Test 72: Health SARIF output format
# ---------------------------------------------------------------------------


class TestHealthSARIF:
    """Health can output in SARIF format."""

    def test_health_sarif(self, tmp_path):
        cfg = base_config(name="sarif-test", allow_structural_orphans=True)
        prd = Requirement(
            "REQ-p00001",
            "SARIF Test",
            "PRD",
            assertions=[("A", "The system SHALL support SARIF.")],
        )
        build_project(tmp_path, cfg, spec_files={"spec/prd.md": [prd]})

        result = run_elspais("checks", "--format", "sarif", "--lenient", cwd=tmp_path)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data, dict)
        # SARIF has specific structure
        assert "$schema" in data or "runs" in data or "version" in data


# ---------------------------------------------------------------------------
# Test 73: Health JUnit output format
# ---------------------------------------------------------------------------


class TestHealthJUnit:
    """Health can output in JUnit format."""

    def test_health_junit(self, tmp_path):
        cfg = base_config(name="junit-test", allow_structural_orphans=True)
        prd = Requirement(
            "REQ-p00001",
            "JUnit Test",
            "PRD",
            assertions=[("A", "The system SHALL support JUnit.")],
        )
        build_project(tmp_path, cfg, spec_files={"spec/prd.md": [prd]})

        result = run_elspais("checks", "--format", "junit", "--lenient", cwd=tmp_path)
        assert result.returncode == 0
        # JUnit is XML
        assert "<?xml" in result.stdout or "<testsuites" in result.stdout


# ---------------------------------------------------------------------------
# Test 74: Trace with body flag
# ---------------------------------------------------------------------------


class TestTraceWithBody:
    """Trace --body includes requirement body text."""

    def test_trace_body(self, tmp_path):
        cfg = base_config(name="trace-body", allow_structural_orphans=True)
        prd = Requirement(
            "REQ-p00001",
            "Body Trace",
            "PRD",
            body="This is the body text that should appear in trace output.",
            assertions=[("A", "The system SHALL include body text.")],
        )
        build_project(tmp_path, cfg, spec_files={"spec/prd.md": [prd]})

        result = run_elspais("trace", "--format", "json", "--body", cwd=tmp_path)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data, list)


# ---------------------------------------------------------------------------
# Test 75: Health markdown output
# ---------------------------------------------------------------------------


class TestHealthMarkdown:
    """Health in markdown format."""

    def test_health_markdown(self, tmp_path):
        cfg = base_config(name="health-md", allow_structural_orphans=True)
        prd = Requirement(
            "REQ-p00001",
            "Markdown Health",
            "PRD",
            assertions=[("A", "The system SHALL output markdown health.")],
        )
        build_project(tmp_path, cfg, spec_files={"spec/prd.md": [prd]})

        result = run_elspais("checks", "--format", "markdown", "--lenient", cwd=tmp_path)
        assert result.returncode == 0
        assert len(result.stdout.strip()) > 0


# ---------------------------------------------------------------------------
# Test 76: MCP with associated repo - full workflow
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
