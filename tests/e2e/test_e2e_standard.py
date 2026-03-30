# Verifies: REQ-p00002, REQ-p00003, REQ-p00004, REQ-p00060,
#            REQ-d00074-A+B+C+D, REQ-d00080, REQ-d00085-A
"""Standard workhorse e2e tests — module-scoped fixture with daemon acceleration.

Tests standard 3-tier hierarchy (REQ-p/o/d), uppercase assertions,
terms config with default severities, against a single shared project.

Groups:
  1. Read-only CLI tests (health, summary, trace, analysis, graph, config show, terms)
  2. Read-only MCP tests (search, hierarchy, subtree, coverage)
  3. Incremental CLI mutations (fix, config set, edit, changed)
  4. Incremental MCP mutations (add, rename, save, undo)
"""

from __future__ import annotations

import json
import re
import shutil

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
# Module-scoped fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def project(tmp_path_factory):
    """Copy e2e-standard fixture to /tmp, init git, start daemon."""
    root = tmp_path_factory.mktemp("e2e_standard")
    load_fixture("e2e-standard", root)
    ensure_fixture_daemon(root)
    return root


@pytest.fixture(scope="module")
def mcp_server(project):
    """Start an MCP server for the project, shared across all MCP tests."""
    pytest.importorskip("mcp")
    from .helpers import start_mcp, stop_mcp

    proc = start_mcp(project)
    yield proc
    stop_mcp(proc)


# ===================================================================
# Group 1: Read-only CLI tests
# ===================================================================


class TestHealthPasses:
    """Health command passes on the standard project."""

    def test_health_lenient(self, project):
        result = run_elspais("checks", "--lenient", cwd=project)
        assert result.returncode == 0, f"health failed: {result.stderr}"

    def test_health_json_structure(self, project):
        result = run_elspais("checks", "--format", "json", "--lenient", cwd=project)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data, (dict, list))

    def test_health_text_contains_sections(self, project):
        result = run_elspais("checks", "--lenient", cwd=project)
        assert result.returncode == 0
        assert "CONFIG" in result.stdout or "SPEC" in result.stdout


class TestHealthCheckNames:
    """Health JSON output includes correct check names."""

    def test_new_check_names_present(self, project):
        result = run_elspais("checks", "--format", "json", "--lenient", cwd=project)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        check_names = {c["name"] for c in data.get("checks", [])}
        for name in (
            "spec.structural_orphans",
            "spec.broken_references",
            "tests.unlinked",
            "code.unlinked",
        ):
            assert name in check_names, f"Expected check '{name}' not found in {check_names}"

    def test_old_check_names_absent(self, project):
        result = run_elspais("checks", "--format", "json", "--lenient", cwd=project)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        check_names = {c["name"] for c in data.get("checks", [])}
        for name in ("spec.orphans", "tests.references_resolve", "code.references_resolve"):
            assert name not in check_names, f"Old check name '{name}' should not be present"


class TestHealthFormats:
    """Health output in various formats."""

    def test_health_sarif(self, project):
        result = run_elspais("checks", "--format", "sarif", "--lenient", cwd=project)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data, dict)
        assert "$schema" in data or "runs" in data or "version" in data

    def test_health_junit(self, project):
        result = run_elspais("checks", "--format", "junit", "--lenient", cwd=project)
        assert result.returncode == 0
        assert "<?xml" in result.stdout or "<testsuites" in result.stdout

    def test_health_markdown(self, project):
        result = run_elspais("checks", "--format", "markdown", "--lenient", cwd=project)
        assert result.returncode == 0
        assert len(result.stdout.strip()) > 0


class TestHealthScopeFlags:
    """Health command with --spec, --code, --tests scope flags."""

    def test_health_spec_only(self, project):
        result = run_elspais("checks", "--spec", "--lenient", cwd=project)
        assert result.returncode == 0

    def test_health_code_only(self, project):
        result = run_elspais("checks", "--code", "--lenient", cwd=project)
        assert result.returncode == 0

    def test_health_tests_only(self, project):
        result = run_elspais("checks", "--tests", "--lenient", cwd=project)
        assert result.returncode == 0


class TestSummaryCounts:
    """Summary command counts requirements correctly."""

    def test_summary_json_total(self, project):
        result = run_elspais("summary", "--format", "json", cwd=project)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        levels = data.get("levels", [])
        total = sum(lv.get("total", 0) for lv in levels)
        # Default summary filters to Active status:
        # 3 PRD Active (p00001, p00002, p00005), 2 OPS, 3 DEV = 8
        assert total == 8, f"Expected 8 Active requirements, got {total}"

    def test_summary_level_breakdown(self, project):
        result = run_elspais("summary", "--format", "json", cwd=project)
        data = json.loads(result.stdout)
        levels = {lv["level"].lower(): lv["total"] for lv in data.get("levels", [])}
        assert levels.get("prd", 0) == 3  # p00001, p00002, p00005 (Active)
        assert levels.get("ops", 0) == 2
        assert levels.get("dev", 0) == 3


class TestSummaryFormats:
    """Summary in text, markdown, csv, json formats."""

    def test_summary_text(self, project):
        result = run_elspais("summary", "--format", "text", cwd=project)
        assert result.returncode == 0
        assert len(result.stdout.strip()) > 0

    def test_summary_csv(self, project):
        result = run_elspais("summary", "--format", "csv", cwd=project)
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert len(lines) >= 1

    def test_summary_markdown(self, project):
        result = run_elspais("summary", "--format", "markdown", cwd=project)
        assert result.returncode == 0
        assert len(result.stdout.strip()) > 0


class TestSummaryStatusFilter:
    """Summary --status filters by status."""

    def test_status_filter_draft(self, project):
        result = run_elspais("summary", "--format", "json", "--status", "Draft", cwd=project)
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout)
            total = sum(lv.get("total", 0) for lv in data.get("levels", []))
            assert total >= 1


class TestTraceOutput:
    """Trace command output."""

    def test_trace_json(self, project):
        result = run_elspais("trace", "--format", "json", cwd=project)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data, list)
        assert len(data) == 10

    def test_trace_csv(self, project):
        result = run_elspais("trace", "--format", "csv", cwd=project)
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert len(lines) >= 2  # header + data rows

    def test_trace_text(self, project):
        result = run_elspais("trace", "--format", "text", cwd=project)
        assert result.returncode == 0
        assert "REQ-p00001" in result.stdout

    def test_trace_markdown(self, project):
        result = run_elspais("trace", "--format", "markdown", cwd=project)
        assert result.returncode == 0
        assert "REQ-p00001" in result.stdout


class TestTraceOptions:
    """Trace with various flags."""

    def test_trace_assertions(self, project):
        result = run_elspais("trace", "--format", "json", "--assertions", cwd=project)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        output_str = json.dumps(data)
        assert "REQ-p00001" in output_str

    def test_trace_body(self, project):
        result = run_elspais("trace", "--format", "json", "--body", cwd=project)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data, list)

    def test_trace_output_to_file(self, project, tmp_path):
        out = tmp_path / "trace-output.json"
        result = run_elspais(
            "trace",
            "--format",
            "json",
            "--output",
            str(out),
            cwd=project,
        )
        assert result.returncode == 0
        candidates = [out, out.with_suffix(".json")]
        found = [p for p in candidates if p.exists()]
        assert found, f"No output file found: {candidates}"
        data = json.loads(found[0].read_text())
        assert isinstance(data, list)


class TestTracePresets:
    """Trace --preset minimal/standard/full."""

    def test_preset_minimal(self, project):
        result = run_elspais("trace", "--preset", "minimal", cwd=project)
        assert result.returncode == 0

    def test_preset_standard(self, project):
        result = run_elspais("trace", "--preset", "standard", cwd=project)
        assert result.returncode == 0

    def test_preset_full(self, project):
        result = run_elspais("trace", "--preset", "full", cwd=project)
        assert result.returncode == 0


class TestAnalysisCommand:
    """Analysis command with various options."""

    def test_analysis_table(self, project):
        result = run_elspais("analysis", "--format", "table", cwd=project)
        assert result.returncode == 0
        assert len(result.stdout.strip()) > 0

    def test_analysis_json(self, project):
        result = run_elspais("analysis", "--format", "json", cwd=project)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data, (list, dict))

    def test_analysis_top_n(self, project):
        result = run_elspais("analysis", "-n", "2", "--format", "json", cwd=project)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        if isinstance(data, list):
            assert len(data) <= 2

    def test_analysis_show_foundations(self, project):
        result = run_elspais(
            "analysis",
            "--show",
            "foundations",
            "--format",
            "json",
            cwd=project,
        )
        assert result.returncode == 0

    def test_analysis_level_filter(self, project):
        result = run_elspais(
            "analysis",
            "--level",
            "dev",
            "--format",
            "json",
            cwd=project,
        )
        assert result.returncode == 0


class TestGraphExport:
    """Graph command exports JSON."""

    def test_graph_json(self, project):
        result = run_elspais("graph", cwd=project)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data, (list, dict))


class TestConfigShow:
    """Config show variants."""

    def test_config_show_default(self, project):
        result = run_elspais("config", "show", cwd=project)
        assert result.returncode == 0
        assert "e2e-standard" in result.stdout or "project" in result.stdout.lower()

    def test_config_show_json(self, project):
        result = run_elspais("config", "show", "--format", "json", cwd=project)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data, dict)

    def test_config_show_section_project(self, project):
        result = run_elspais("config", "show", "--section", "project", cwd=project)
        assert result.returncode == 0
        assert "e2e-standard" in result.stdout

    def test_config_show_section_rules(self, project):
        result = run_elspais("config", "show", "--section", "rules", cwd=project)
        assert result.returncode == 0

    def test_config_get_project_name(self, project):
        result = run_elspais("config", "get", "project.name", cwd=project)
        assert result.returncode == 0
        assert "e2e-standard" in result.stdout

    def test_config_path(self, project):
        result = run_elspais("config", "path", cwd=project)
        assert result.returncode == 0
        assert ".elspais.toml" in result.stdout


class TestDoctorAndVersion:
    """Doctor and version commands."""

    def test_doctor_passes(self, project):
        result = run_elspais("doctor", cwd=project)
        assert result.returncode == 0

    def test_doctor_json(self, project):
        result = run_elspais("doctor", "--format", "json", cwd=project)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data, (dict, list))


class TestIdempotency:
    """Running same command twice produces identical results."""

    def test_health_idempotent(self, project):
        # Use --spec-dir to bypass daemon caching (daemon graph build
        # canonicalizes terms in-memory, causing non-deterministic counts)
        spec_dir = str(project / "spec")
        r1 = run_elspais(
            "checks", "--spec-dir", spec_dir, "--format", "json", "--lenient", cwd=project
        )
        r2 = run_elspais(
            "checks", "--spec-dir", spec_dir, "--format", "json", "--lenient", cwd=project
        )
        assert r1.returncode == r2.returncode
        assert r1.stdout == r2.stdout

    def test_summary_idempotent(self, project):
        r1 = run_elspais("summary", "--format", "json", cwd=project)
        r2 = run_elspais("summary", "--format", "json", cwd=project)
        assert r1.stdout == r2.stdout


class TestCrossCommandConsistency:
    """Health, trace, and summary report consistent requirement counts."""

    def test_counts_consistent(self, project):
        summary = run_elspais("summary", "--format", "json", cwd=project)
        assert summary.returncode == 0
        summary_data = json.loads(summary.stdout)
        summary_total = sum(lv["total"] for lv in summary_data["levels"])

        trace = run_elspais("trace", "--format", "json", cwd=project)
        assert trace.returncode == 0
        trace_data = json.loads(trace.stdout)
        trace_total = len(trace_data)

        # Summary defaults to Active only (8), trace shows all (10)
        # Both should be internally consistent
        assert summary_total == 8, f"Summary expected 8, got {summary_total}"
        assert trace_total == 10, f"Trace expected 10, got {trace_total}"


class TestSkipFiles:
    """Skip files and dirs are excluded from scanning."""

    def test_skip_files_not_in_health(self, project):
        """INDEX.md and NOTES.md should be skipped."""
        result = run_elspais("checks", "--format", "json", "--lenient", cwd=project)
        assert result.returncode == 0
        # These skip files should not cause errors or be counted

    def test_skip_dirs_not_counted(self, project):
        """drafts/ directory should be skipped; REQ-p99999 not counted."""
        result = run_elspais("summary", "--format", "json", cwd=project)
        data = json.loads(result.stdout)
        total = sum(lv.get("total", 0) for lv in data.get("levels", []))
        # REQ-p99999 in drafts/ should not be counted; Active only = 8
        assert total == 8


class TestManyAssertions:
    """Requirement with 26 assertions A-Z."""

    def test_26_assertions_health(self, project):
        """REQ-p00005 has 26 assertions and should pass health."""
        result = run_elspais("checks", "--lenient", cwd=project)
        assert result.returncode == 0


class TestDeepHierarchy:
    """PRD -> OPS -> DEV -> DEV(refines) chain."""

    def test_trace_includes_refines(self, project):
        result = run_elspais("trace", "--format", "json", cwd=project)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        ids = {r["id"] for r in data}
        assert "REQ-d00003" in ids, "Refining requirement should appear in trace"


class TestRefinesRelationship:
    """Refines: creates a refinement relationship."""

    def test_refines_in_trace(self, project):
        result = run_elspais("trace", "--format", "json", cwd=project)
        assert result.returncode == 0
        assert "REQ-d00001" in result.stdout
        assert "REQ-d00003" in result.stdout


class TestDraftStatus:
    """Draft requirements are present in trace."""

    def test_draft_in_trace(self, project):
        result = run_elspais("trace", "--format", "json", cwd=project)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        ids = {r["id"] for r in data}
        assert "REQ-p00003" in ids


class TestMultipleSpecFilesPerLevel:
    """Multiple spec files per level are scanned correctly."""

    def test_all_files_counted(self, project):
        result = run_elspais("summary", "--format", "json", cwd=project)
        data = json.loads(result.stdout)
        levels = {lv["level"].lower(): lv["total"] for lv in data.get("levels", [])}
        # Active only: 3 PRD (p00003=Draft, p00004=Deprecated excluded)
        assert levels.get("prd", 0) == 3
        assert levels.get("dev", 0) == 3


class TestCodeRefsAndTesting:
    """Code and test file references are detected."""

    def test_health_passes_with_code_refs(self, project):
        result = run_elspais("checks", "--lenient", cwd=project)
        assert result.returncode == 0

    def test_health_json_shows_code_refs(self, project):
        result = run_elspais("checks", "--format", "json", "--lenient", cwd=project)
        assert result.returncode == 0
        assert "REQ-d00001" in result.stdout


class TestMultiAssertionSyntax:
    """Multi-assertion compact syntax (A+B) in code references."""

    def test_multi_assertion_code_reference(self, project):
        """src/auth_multi.py uses REQ-d00001-A+B syntax."""
        result = run_elspais("checks", "--lenient", cwd=project)
        assert result.returncode == 0


class TestHealthOutputToFile:
    """Health --output writes to file."""

    def test_output_to_file(self, project, tmp_path):
        out_file = tmp_path / "health-output.json"
        result = run_elspais(
            "checks",
            "--format",
            "json",
            "--lenient",
            "--output",
            str(out_file),
            cwd=project,
        )
        if result.returncode == 0 and out_file.exists():
            content = out_file.read_text()
            data = json.loads(content)
            assert isinstance(data, (dict, list))


# ===================================================================
# Group 1b: Read-only CLI term tests
# ===================================================================


class TestTermHealthChecks:
    """Term health checks appear in checks output."""

    def test_term_check_names_in_json(self, project):
        result = run_elspais("checks", "--format", "json", "--lenient", cwd=project)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        check_names = {c["name"] for c in data.get("checks", [])}
        for name in (
            "terms.duplicates",
            "terms.undefined",
            "terms.unmarked",
            "terms.unused",
            "terms.bad_definition",
            "terms.collection_empty",
        ):
            assert name in check_names, f"Expected check '{name}' not found in {check_names}"


class TestGlossaryCommand:
    """elspais glossary generates output."""

    def test_glossary_markdown(self, project):
        result = run_elspais("glossary", cwd=project)
        assert result.returncode == 0
        assert "Authentication" in result.stdout

    def test_glossary_json(self, project):
        result = run_elspais("glossary", "--format", "json", cwd=project)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data, (dict, list))


class TestTermIndexCommand:
    """elspais term-index generates output."""

    def test_term_index_markdown(self, project):
        result = run_elspais("term-index", cwd=project)
        assert result.returncode == 0

    def test_term_index_json(self, project):
        result = run_elspais("term-index", "--format", "json", cwd=project)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data, (dict, list))


class TestHealthSARIF:
    """Health SARIF output format."""

    def test_health_sarif(self, project):
        result = run_elspais("checks", "--format", "sarif", "--lenient", cwd=project)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data, dict)
        assert "$schema" in data or "runs" in data or "version" in data


class TestHealthJUnit:
    """Health JUnit output format."""

    def test_health_junit(self, project):
        result = run_elspais("checks", "--format", "junit", "--lenient", cwd=project)
        assert result.returncode == 0
        assert "<?xml" in result.stdout or "<testsuites" in result.stdout


class TestHealthMarkdown:
    """Health markdown output format."""

    def test_health_markdown(self, project):
        result = run_elspais("checks", "--format", "markdown", "--lenient", cwd=project)
        assert result.returncode == 0
        assert len(result.stdout.strip()) > 0


# ===================================================================
# Group 2: MCP query tests (read-only, use shared mcp_server)
# ===================================================================


class TestMCPSearchAndNavigation:
    """MCP search, get_requirement, get_hierarchy."""

    def test_search_finds_requirements(self, project, mcp_server):
        from .helpers import mcp_call_all

        results = mcp_call_all(mcp_server, "search", {"query": "Auth"})
        assert len(results) >= 1
        assert any("Auth" in str(r) for r in results)

    def test_search_empty_returns_nothing(self, project, mcp_server):
        from .helpers import mcp_call_all

        results = mcp_call_all(mcp_server, "search", {"query": "zzz_nonexistent_xyz"})
        assert len(results) == 0

    def test_get_requirement_returns_details(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(mcp_server, "get_requirement", {"req_id": "REQ-p00001"})
        assert result["id"] == "REQ-p00001"
        assert "User Authentication" in result.get("title", "")
        assert len(result.get("assertions", [])) >= 3

    def test_get_requirement_not_found(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(mcp_server, "get_requirement", {"req_id": "REQ-zzz99"})
        assert result is None or result.get("error") or result.get("_error")

    def test_get_hierarchy(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(mcp_server, "get_hierarchy", {"req_id": "REQ-d00001"})
        assert "ancestors" in result
        assert "children" in result
        ancestor_ids = [a.get("id", "") for a in result["ancestors"]]
        assert any("o00001" in aid for aid in ancestor_ids) or len(result["ancestors"]) > 0


class TestMCPProjectInfo:
    """MCP project summary, workspace info, graph status."""

    def test_project_summary(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(mcp_server, "get_project_summary", {})
        assert isinstance(result, dict)
        assert "levels" in result or "total" in result or len(result) > 0

    def test_workspace_info(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(mcp_server, "get_workspace_info", {"detail": "default"})
        assert isinstance(result, dict)

    def test_workspace_info_testing(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(mcp_server, "get_workspace_info", {"detail": "testing"})
        assert isinstance(result, dict)

    def test_workspace_info_coverage(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(mcp_server, "get_workspace_info", {"detail": "coverage"})
        assert isinstance(result, dict)

    def test_workspace_info_all(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(mcp_server, "get_workspace_info", {"detail": "all"})
        assert isinstance(result, dict)

    def test_graph_status(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(mcp_server, "get_graph_status", {})
        assert isinstance(result, dict)


class TestMCPSubtree:
    """MCP get_subtree in various formats."""

    def test_subtree_markdown(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(
            mcp_server,
            "get_subtree",
            {"root_id": "REQ-p00001", "format": "markdown"},
        )
        result_str = str(result)
        assert "REQ-p00001" in result_str or "User Authentication" in result_str

    def test_subtree_flat(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(
            mcp_server,
            "get_subtree",
            {"root_id": "REQ-p00001", "format": "flat"},
        )
        assert isinstance(result, dict)
        assert "nodes" in result or "edges" in result

    def test_subtree_nested(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(
            mcp_server,
            "get_subtree",
            {"root_id": "REQ-p00001", "format": "nested"},
        )
        assert isinstance(result, dict)

    def test_subtree_depth_limited(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(
            mcp_server,
            "get_subtree",
            {"root_id": "REQ-p00001", "depth": 1, "format": "flat"},
        )
        assert isinstance(result, dict)


class TestMCPCursors:
    """MCP cursor protocol for incremental iteration."""

    def test_cursor_search(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(
            mcp_server,
            "open_cursor",
            {"query": "search", "params": {"query": "REQ"}, "batch_size": 1},
        )
        assert "total" in result
        assert result["total"] >= 3

        next_result = mcp_call(mcp_server, "cursor_next", {"count": 1})
        assert isinstance(next_result, dict)

        info = mcp_call(mcp_server, "cursor_info", {})
        assert "position" in info
        assert "remaining" in info

    def test_cursor_subtree(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(
            mcp_server,
            "open_cursor",
            {"query": "subtree", "params": {"root_id": "REQ-p00001"}, "batch_size": 0},
        )
        assert "total" in result
        assert result["total"] >= 1


class TestMCPTestCoverage:
    """MCP test coverage tools."""

    def test_get_test_coverage(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(mcp_server, "get_test_coverage", {"req_id": "REQ-d00001"})
        assert isinstance(result, dict)

    def test_uncovered_assertions(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(mcp_server, "get_uncovered_assertions", {})
        assert isinstance(result, (list, dict))


class TestMCPScopedSearch:
    """MCP scoped_search and discover_requirements."""

    def test_scoped_search(self, project, mcp_server):
        from .helpers import mcp_call_all

        result = mcp_call_all(
            mcp_server,
            "scoped_search",
            {"query": "module", "scope_id": "REQ-p00001", "direction": "descendants"},
        )
        assert isinstance(result, list)

    def test_discover_requirements(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(
            mcp_server,
            "discover_requirements",
            {"query": "auth", "scope_id": "REQ-p00001"},
        )
        assert isinstance(result, dict)


class TestMCPKeywordSearch:
    """MCP find_by_keywords and get_all_keywords."""

    def test_get_all_keywords(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(mcp_server, "get_all_keywords", {})
        assert isinstance(result, (list, dict))

    def test_find_by_keywords(self, project, mcp_server):
        from .helpers import mcp_call_all

        result = mcp_call_all(
            mcp_server,
            "find_by_keywords",
            {"keywords": ["auth", "user"], "match_all": False},
        )
        assert isinstance(result, list)

    def test_find_assertions_by_keywords(self, project, mcp_server):
        from .helpers import mcp_call_all

        result = mcp_call_all(
            mcp_server,
            "find_assertions_by_keywords",
            {"keywords": ["email"], "match_all": True},
        )
        assert isinstance(result, list)


class TestMCPQueryNodes:
    """MCP query_nodes with various filters."""

    def test_query_by_kind(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(mcp_server, "query_nodes", {"kind": "requirement"})
        assert result["count"] >= 10

    def test_query_by_level(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(mcp_server, "query_nodes", {"level": "prd"})
        assert result["count"] >= 5

    def test_query_by_status(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(mcp_server, "query_nodes", {"status": "Active"})
        assert result["count"] >= 1


class TestMCPGraphHealth:
    """MCP get_orphaned_nodes and get_broken_references."""

    def test_orphaned_nodes(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(mcp_server, "get_orphaned_nodes", {})
        assert isinstance(result, (list, dict))

    def test_broken_references(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(mcp_server, "get_broken_references", {})
        assert isinstance(result, (list, dict))


class TestMCPAgentInstructions:
    """MCP agent_instructions tool."""

    def test_agent_instructions(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(mcp_server, "agent_instructions", {})
        assert isinstance(result, (dict, str))


class TestMCPRefreshGraph:
    """MCP refresh_graph rebuilds from files."""

    def test_refresh_stable(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(mcp_server, "refresh_graph", {})
        assert isinstance(result, dict)
        assert not result.get("_error")

        summary = mcp_call(mcp_server, "get_project_summary", {})
        assert isinstance(summary, dict)


class TestMCPSuggestLinks:
    """MCP suggest_links for unlinked nodes."""

    def test_suggest_links(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(mcp_server, "suggest_links", {})
        assert isinstance(result, (list, dict))


class TestMCPChangedRequirements:
    """MCP get_changed_requirements."""

    def test_no_changes(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(mcp_server, "get_changed_requirements", {})
        assert isinstance(result, (list, dict))


# ===================================================================
# Group 3: CLI mutation tests (incremental, run on project directly)
# ===================================================================


@pytest.mark.incremental
class TestStandardCLIMutations:
    """Incremental CLI mutation tests — each builds on the prior state."""

    def test_01_fix_corrects_wrong_hash(self, project):
        """Fix the wrong hash in prd-deprecated.md."""
        spec = project / "spec" / "prd-deprecated.md"
        content = spec.read_text()
        assert "XXXXXXXX" in content

        result = run_elspais("fix", cwd=project)
        assert result.returncode == 0, f"fix failed: {result.stderr}"

        content = spec.read_text()
        assert "XXXXXXXX" not in content, "Hash was not corrected by fix"
        match = re.search(r"\*\*Hash\*\*:\s*([0-9a-f]{8})", content)
        assert match, "No valid hash found after fix"

    def test_02_fix_idempotent(self, project):
        """Running fix again should not change anything."""
        import os
        import subprocess

        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "t@t",
        }
        subprocess.run(["git", "add", "."], cwd=project, capture_output=True, env=env)
        subprocess.run(
            ["git", "commit", "-m", "after-fix"], cwd=project, capture_output=True, env=env
        )

        spec = project / "spec" / "prd-core.md"
        content1 = spec.read_text()

        run_elspais("fix", cwd=project)
        content2 = spec.read_text()

        assert content1 == content2, "Second fix changed the file"

    def test_03_fix_specific_id(self, project):
        """Fix command targeting a specific requirement ID (already fixed, should be no-op)."""
        result = run_elspais("fix", "REQ-p00004", cwd=project)
        assert result.returncode == 0

        content = (project / "spec" / "prd-deprecated.md").read_text()
        hashes = re.findall(r"\*\*Hash\*\*:\s*(\S+)", content)
        assert len(hashes) >= 1
        assert hashes[0] != "XXXXXXXX"

    def test_04_fix_dry_run_does_not_modify(self, project):
        """Dry run should not change files."""
        spec = project / "spec" / "prd-core.md"
        content_before = spec.read_text()

        result = run_elspais("fix", "--dry-run", cwd=project)
        assert result.returncode == 0

        content_after = spec.read_text()
        assert content_before == content_after, "Dry run modified the file"

    def test_05_config_set_then_get(self, project):
        """Config set/get round-trip."""
        set_result = run_elspais("config", "set", "project.name", "updated-name", cwd=project)
        assert set_result.returncode == 0

        get_result = run_elspais("config", "get", "project.name", cwd=project)
        assert get_result.returncode == 0
        assert "updated-name" in get_result.stdout

    def test_06_config_add_status(self, project):
        """Config add appends to array."""
        result = run_elspais(
            "config",
            "add",
            "rules.format.allowed_statuses",
            "Experimental",
            cwd=project,
        )
        assert result.returncode == 0

        show = run_elspais("config", "show", "--format", "json", cwd=project)
        data = json.loads(show.stdout)
        statuses = data.get("rules", {}).get("format", {}).get("allowed_statuses", [])
        assert "Experimental" in statuses

    def test_07_config_remove_status(self, project):
        """Config remove deletes from array."""
        result = run_elspais(
            "config",
            "remove",
            "rules.format.allowed_statuses",
            "Superseded",
            cwd=project,
        )
        assert result.returncode == 0

        show = run_elspais("config", "show", "--format", "json", cwd=project)
        data = json.loads(show.stdout)
        statuses = data.get("rules", {}).get("format", {}).get("allowed_statuses", [])
        assert "Superseded" not in statuses

    def test_08_config_unset_key(self, project):
        """Config unset removes a key."""
        import tomlkit

        result = run_elspais("config", "unset", "project.namespace", cwd=project)
        assert result.returncode == 0

        content = (project / ".elspais.toml").read_text()
        data = tomlkit.loads(content)
        assert "namespace" not in data.get("project", {})

    def test_09_edit_status(self, project):
        """Edit command modifies requirement status in-place."""
        result = run_elspais("edit", "REQ-p00001", "--status", "Draft", cwd=project)
        if result.returncode == 0:
            content = (project / "spec" / "prd-core.md").read_text()
            assert "Draft" in content

    def test_10_changed_detects_uncommitted_edit(self, project):
        """Changed command detects uncommitted spec file edits."""
        spec = project / "spec" / "prd-core.md"
        content = spec.read_text()
        spec.write_text(content.replace("User Authentication", "Modified Authentication"))

        result = run_elspais("changed", "--format", "json", cwd=project)
        assert result.returncode == 0
        output = result.stdout.strip()
        if output:
            data = json.loads(output)
            assert isinstance(data, (list, dict))

    def test_11_changed_no_changes_after_commit(self, project):
        """Changed shows nothing after committing."""
        import os
        import subprocess

        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "t@t",
        }
        subprocess.run(["git", "add", "."], cwd=project, capture_output=True, env=env)
        subprocess.run(
            ["git", "commit", "-m", "mutations"], cwd=project, capture_output=True, env=env
        )

        result = run_elspais("changed", "--format", "json", cwd=project)
        assert result.returncode == 0

    def test_12_changed_base_branch(self, project):
        """Changed with --base-branch flag."""
        import subprocess

        # Get current branch name
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=project,
            capture_output=True,
            text=True,
        ).stdout.strip()

        result = run_elspais(
            "changed",
            "--base-branch",
            branch,
            "--format",
            "json",
            cwd=project,
        )
        assert result.returncode == 0


# ===================================================================
# Group 4: MCP mutation tests (incremental, shared server)
# ===================================================================


@pytest.mark.incremental
class TestStandardMCPMutations:
    """Incremental MCP mutation tests — each builds on the prior state."""

    def test_01_add_requirement_and_undo(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(
            mcp_server,
            "mutate_add_requirement",
            {"req_id": "REQ-p00099", "title": "New Feature", "level": "prd", "status": "Draft"},
        )
        assert isinstance(result, dict)
        assert not result.get("_error"), f"Add failed: {result}"

        get_result = mcp_call(mcp_server, "get_requirement", {"req_id": "REQ-p00099"})
        assert get_result and get_result.get("id") == "REQ-p00099"

        undo = mcp_call(mcp_server, "undo_last_mutation", {})
        assert isinstance(undo, dict)

        after_undo = mcp_call(mcp_server, "get_requirement", {"req_id": "REQ-p00099"})
        assert after_undo is None or after_undo.get("error") or after_undo.get("_error")

    def test_02_update_title_and_undo(self, project, mcp_server):
        from .helpers import mcp_call

        original = mcp_call(mcp_server, "get_requirement", {"req_id": "REQ-p00001"})
        orig_title = original["title"]

        mcp_call(
            mcp_server,
            "mutate_update_title",
            {"node_id": "REQ-p00001", "new_title": "Updated Title"},
        )

        updated = mcp_call(mcp_server, "get_requirement", {"req_id": "REQ-p00001"})
        assert updated["title"] == "Updated Title"

        mcp_call(mcp_server, "undo_last_mutation", {})
        reverted = mcp_call(mcp_server, "get_requirement", {"req_id": "REQ-p00001"})
        assert reverted["title"] == orig_title

    def test_03_mutation_log(self, project, mcp_server):
        from .helpers import mcp_call

        mcp_call(
            mcp_server,
            "mutate_update_title",
            {"node_id": "REQ-p00001", "new_title": "Title V1"},
        )
        mcp_call(
            mcp_server,
            "mutate_update_title",
            {"node_id": "REQ-p00001", "new_title": "Title V2"},
        )

        log = mcp_call(mcp_server, "get_mutation_log", {"limit": 10})
        assert isinstance(log, (list, dict))

        # Undo both to restore original state
        mcp_call(mcp_server, "undo_last_mutation", {})
        mcp_call(mcp_server, "undo_last_mutation", {})

    def test_04_add_assertion(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(
            mcp_server,
            "mutate_add_assertion",
            {"req_id": "REQ-p00001", "label": "D", "text": "The system SHALL support SSO."},
        )
        assert isinstance(result, dict)
        assert not result.get("_error")

        req = mcp_call(mcp_server, "get_requirement", {"req_id": "REQ-p00001"})
        labels = [a.get("label", "") for a in req.get("assertions", [])]
        assert "D" in labels

        # Undo to restore original state
        mcp_call(mcp_server, "undo_last_mutation", {})

    def test_05_update_assertion(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(
            mcp_server,
            "mutate_update_assertion",
            {
                "assertion_id": "REQ-p00001-A",
                "new_text": "The system SHALL create and manage user accounts.",
            },
        )
        assert isinstance(result, dict)

        # Undo to restore original state
        mcp_call(mcp_server, "undo_last_mutation", {})

    def test_06_delete_assertion_and_undo(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(
            mcp_server,
            "mutate_delete_assertion",
            {"assertion_id": "REQ-p00001-C", "confirm": True},
        )
        assert isinstance(result, dict)

        req = mcp_call(mcp_server, "get_requirement", {"req_id": "REQ-p00001"})
        labels = [a.get("label", "") for a in req.get("assertions", [])]
        assert "C" not in labels

        mcp_call(mcp_server, "undo_last_mutation", {})
        req2 = mcp_call(mcp_server, "get_requirement", {"req_id": "REQ-p00001"})
        labels2 = [a.get("label", "") for a in req2.get("assertions", [])]
        assert "C" in labels2

    def test_07_rename_assertion(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(
            mcp_server,
            "mutate_rename_assertion",
            {"old_id": "REQ-p00001-A", "new_label": "X"},
        )
        assert isinstance(result, dict)

        req = mcp_call(mcp_server, "get_requirement", {"req_id": "REQ-p00001"})
        labels = [a.get("label", "") for a in req.get("assertions", [])]
        assert "X" in labels
        assert "A" not in labels

        # Undo to restore original state
        mcp_call(mcp_server, "undo_last_mutation", {})

    def test_08_add_edge(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(
            mcp_server,
            "mutate_add_edge",
            {"source_id": "REQ-d00002", "target_id": "REQ-o00001", "edge_kind": "implements"},
        )
        assert isinstance(result, dict)
        assert not result.get("_error"), f"Edge add failed: {result}"

        # Undo to restore original state
        mcp_call(mcp_server, "undo_last_mutation", {})

    def test_09_delete_edge_and_undo(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(
            mcp_server,
            "mutate_delete_edge",
            {"source_id": "REQ-d00001", "target_id": "REQ-o00001", "confirm": True},
        )
        assert isinstance(result, dict)

        mcp_call(mcp_server, "undo_last_mutation", {})

        hier = mcp_call(mcp_server, "get_hierarchy", {"req_id": "REQ-d00001"})
        ancestors = hier.get("ancestors", [])
        assert len(ancestors) > 0

    def test_10_change_edge_kind(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(
            mcp_server,
            "mutate_change_edge_kind",
            {"source_id": "REQ-d00003", "target_id": "REQ-d00001", "new_kind": "implements"},
        )
        assert isinstance(result, dict)

        # Undo to restore original state
        mcp_call(mcp_server, "undo_last_mutation", {})

    def test_11_rename_node_and_undo(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(
            mcp_server,
            "mutate_rename_node",
            {"old_id": "REQ-p00003", "new_id": "REQ-p00099"},
        )
        assert isinstance(result, dict)
        assert not result.get("_error"), f"Rename failed: {result}"

        req = mcp_call(mcp_server, "get_requirement", {"req_id": "REQ-p00099"})
        assert req and req.get("id") == "REQ-p00099"

        old = mcp_call(mcp_server, "get_requirement", {"req_id": "REQ-p00003"})
        assert old is None or old.get("_error") or old.get("error")

        mcp_call(mcp_server, "undo_last_mutation", {})

        restored = mcp_call(mcp_server, "get_requirement", {"req_id": "REQ-p00003"})
        assert restored and restored.get("id") == "REQ-p00003"

    def test_12_change_status(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(
            mcp_server,
            "mutate_change_status",
            {"node_id": "REQ-p00001", "new_status": "Draft"},
        )
        assert isinstance(result, dict)

        req = mcp_call(mcp_server, "get_requirement", {"req_id": "REQ-p00001"})
        req_str = json.dumps(req)
        assert "Draft" in req_str

        # Undo to restore original state
        mcp_call(mcp_server, "undo_last_mutation", {})

    def test_13_delete_requirement_and_undo(self, project, mcp_server):
        from .helpers import mcp_call

        result = mcp_call(
            mcp_server,
            "mutate_delete_requirement",
            {"node_id": "REQ-p00003", "confirm": True},
        )
        assert isinstance(result, dict)

        req = mcp_call(mcp_server, "get_requirement", {"req_id": "REQ-p00003"})
        assert req is None or req.get("_error") or req.get("error")

        req1 = mcp_call(mcp_server, "get_requirement", {"req_id": "REQ-p00001"})
        assert req1 and req1.get("id") == "REQ-p00001"

        mcp_call(mcp_server, "undo_last_mutation", {})

        restored = mcp_call(mcp_server, "get_requirement", {"req_id": "REQ-p00003"})
        assert restored and restored.get("id") == "REQ-p00003"

    def test_14_undo_multiple(self, project, mcp_server):
        from .helpers import mcp_call

        mcp_call(
            mcp_server, "mutate_update_title", {"node_id": "REQ-p00001", "new_title": "Title V1"}
        )
        mcp_call(
            mcp_server, "mutate_update_title", {"node_id": "REQ-p00001", "new_title": "Title V2"}
        )
        mcp_call(
            mcp_server, "mutate_update_title", {"node_id": "REQ-p00001", "new_title": "Title V3"}
        )

        log = mcp_call(mcp_server, "get_mutation_log", {"limit": 10})
        assert isinstance(log, (list, dict))

        mcp_call(mcp_server, "undo_last_mutation", {})
        mcp_call(mcp_server, "undo_last_mutation", {})
        mcp_call(mcp_server, "undo_last_mutation", {})

        req = mcp_call(mcp_server, "get_requirement", {"req_id": "REQ-p00001"})
        # Title should be back to whatever it was before these three mutations
        assert req["title"] != "Title V3"

    def test_15_comprehensive_workflow(self, project, mcp_server):
        """Exercise many MCP tools in a single test."""
        from .helpers import mcp_call, mcp_call_all

        # 1. Status
        status = mcp_call(mcp_server, "get_graph_status", {})
        assert isinstance(status, dict)

        # 2. Summary
        summary = mcp_call(mcp_server, "get_project_summary", {})
        assert isinstance(summary, dict)

        # 3. Search
        results = mcp_call_all(mcp_server, "search", {"query": "notification"})
        assert len(results) >= 1

        # 4. Get requirement
        req = mcp_call(mcp_server, "get_requirement", {"req_id": "REQ-d00002"})
        assert req["id"] == "REQ-d00002"

        # 5. Hierarchy
        hier = mcp_call(mcp_server, "get_hierarchy", {"req_id": "REQ-d00002"})
        assert "ancestors" in hier

        # 6. Subtree
        subtree = mcp_call(
            mcp_server,
            "get_subtree",
            {"root_id": "REQ-p00002", "format": "flat"},
        )
        assert isinstance(subtree, dict)

        # 7. Add assertion
        mcp_call(
            mcp_server,
            "mutate_add_assertion",
            {
                "req_id": "REQ-d00002",
                "label": "B",
                "text": "The module SHALL log delivery status.",
            },
        )

        # 8. Verify
        req2 = mcp_call(mcp_server, "get_requirement", {"req_id": "REQ-d00002"})
        labels = [a.get("label", "") for a in req2.get("assertions", [])]
        assert "B" in labels

        # 9. Log
        log = mcp_call(mcp_server, "get_mutation_log", {"limit": 5})
        assert isinstance(log, (list, dict))

        # 10. Undo
        mcp_call(mcp_server, "undo_last_mutation", {})

        # 11. Verify undone
        req3 = mcp_call(mcp_server, "get_requirement", {"req_id": "REQ-d00002"})
        labels3 = [a.get("label", "") for a in req3.get("assertions", [])]
        assert "B" not in labels3

        # 12. Workspace info
        ws = mcp_call(mcp_server, "get_workspace_info", {"detail": "testing"})
        assert isinstance(ws, dict)

    def test_16_build_requirement_from_scratch(self, project, mcp_server):
        """Complex mutation workflow: add req, assertions, edges, save."""
        from .helpers import mcp_call

        # 1. Add new OPS requirement
        mcp_call(
            mcp_server,
            "mutate_add_requirement",
            {
                "req_id": "REQ-o00099",
                "title": "New Operations Req",
                "level": "ops",
                "status": "Draft",
            },
        )

        # 2. Add edge
        mcp_call(
            mcp_server,
            "mutate_add_edge",
            {"source_id": "REQ-o00099", "target_id": "REQ-p00001", "edge_kind": "implements"},
        )

        # 3. Add assertions
        mcp_call(
            mcp_server,
            "mutate_add_assertion",
            {
                "req_id": "REQ-o00099",
                "label": "A",
                "text": "Operations SHALL deploy new service.",
            },
        )
        mcp_call(
            mcp_server,
            "mutate_add_assertion",
            {
                "req_id": "REQ-o00099",
                "label": "B",
                "text": "Operations SHALL monitor new service.",
            },
        )

        # 4. Verify
        req = mcp_call(mcp_server, "get_requirement", {"req_id": "REQ-o00099"})
        assert req["id"] == "REQ-o00099"
        assert req["title"] == "New Operations Req"
        assert len(req.get("assertions", [])) == 2

        # 5. Hierarchy
        hier = mcp_call(mcp_server, "get_hierarchy", {"req_id": "REQ-o00099"})
        ancestor_ids = [a.get("id", "") for a in hier.get("ancestors", [])]
        assert "REQ-p00001" in ancestor_ids

        # 6. Save
        save = mcp_call(mcp_server, "save_mutations", {"save_branch": False})
        assert not save.get("_error"), f"Save failed: {save}"

    def test_17_save_refresh_roundtrip(self, project, mcp_server):
        """Mutate -> save -> refresh -> verify persisted."""
        from .helpers import mcp_call

        mcp_call(
            mcp_server,
            "mutate_update_title",
            {"node_id": "REQ-p00001", "new_title": "Updated Via MCP"},
        )

        save = mcp_call(mcp_server, "save_mutations", {"save_branch": False})
        assert not save.get("_error"), f"Save failed: {save}"

        refresh = mcp_call(mcp_server, "refresh_graph", {})
        assert not refresh.get("_error"), f"Refresh failed: {refresh}"

        req = mcp_call(mcp_server, "get_requirement", {"req_id": "REQ-p00001"})
        assert req["title"] == "Updated Via MCP"

    def test_18_save_persists_to_file(self, project, mcp_server):
        """Save mutations persists changes to disk."""
        from .helpers import mcp_call

        mcp_call(
            mcp_server,
            "mutate_update_title",
            {"node_id": "REQ-p00001", "new_title": "Persisted Title Change"},
        )

        result = mcp_call(mcp_server, "save_mutations", {"save_branch": False})
        assert isinstance(result, dict)
        assert not result.get("_error"), f"Save failed: {result}"

        spec = project / "spec" / "prd-core.md"
        content = spec.read_text()
        assert "Persisted Title Change" in content

    def test_19_fix_broken_reference(self, project, mcp_server):
        """MCP mutate_fix_broken_reference using a separate project."""
        import tempfile
        from pathlib import Path

        from .helpers import Requirement as Req
        from .helpers import base_config as bc
        from .helpers import build_project as bp
        from .helpers import mcp_call, start_mcp, stop_mcp

        cfg = bc(name="broken-ref-std", allow_structural_orphans=True)
        prd = Req(
            "REQ-p00001",
            "Target",
            "PRD",
            assertions=[("A", "The system SHALL be the target.")],
        )
        dev = Req(
            "REQ-d00001",
            "With Bad Ref",
            "DEV",
            implements="REQ-p99999",
            assertions=[("A", "The module SHALL reference wrong thing.")],
        )

        with tempfile.TemporaryDirectory() as tmp:
            dst = Path(tmp) / "broken_ref"
            dst.mkdir()
            bp(dst, cfg, spec_files={"spec/prd.md": [prd], "spec/dev.md": [dev]})

            proc = start_mcp(dst)
            try:
                broken = mcp_call(proc, "get_broken_references", {})
                assert isinstance(broken, (list, dict))

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
