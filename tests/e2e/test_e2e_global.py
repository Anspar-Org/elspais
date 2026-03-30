# Verifies: REQ-p00002, REQ-p00003, REQ-p00004, REQ-p00013-C, REQ-p00080,
#            REQ-d00010, REQ-d00080, REQ-d00085-A,
#            REQ-d00125-A, REQ-d00125-B, REQ-d00125-C, REQ-d00125-D,
#            REQ-d00125-E, REQ-d00125-F, REQ-d00125-G, REQ-d00125-H
"""Global-scope e2e tests — run against REPO_ROOT with daemon acceleration.

These tests validate CLI commands against the elspais repository itself.
The session-scoped daemon warm-up ensures fast responses (~0.3s per call).
"""

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from tests.e2e.conftest import (
    REPO_ROOT,
    requires_elspais,
    requires_pandoc,
    requires_xelatex,
    run_elspais,
)

pytestmark = [
    pytest.mark.e2e,
    requires_elspais,
]


# ===================================================================
# From test_cli_commands.py
# ===================================================================


class TestVersion:
    """Version command output."""

    def test_version_returns_zero(self):
        result = run_elspais("version")
        assert result.returncode == 0

    def test_version_output_contains_number(self):
        result = run_elspais("version")
        assert "." in result.stdout, f"Expected version number in output: {result.stdout!r}"


class TestDoctor:
    """Validates REQ-d00080: doctor command diagnostics."""

    def test_REQ_d00080_A_doctor_returns_zero(self):
        result = run_elspais("doctor")
        assert result.returncode == 0

    def test_REQ_d00080_A_doctor_json_valid(self):
        result = run_elspais("doctor", "--format", "json")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data, (dict, list))


class TestSummary:
    """Validates REQ-p00003: summary command output formats."""

    def test_REQ_p00003_A_summary_text_returns_zero(self):
        result = run_elspais("summary")
        assert result.returncode == 0
        assert len(result.stdout.strip()) > 0

    def test_REQ_p00003_A_summary_json_valid(self):
        result = run_elspais("summary", "--format", "json")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data, dict)

    def test_REQ_p00003_A_summary_csv_returns_zero(self):
        result = run_elspais("summary", "--format", "csv")
        assert result.returncode == 0


class TestGraph:
    """Validates REQ-p00003: graph command output."""

    def test_REQ_p00003_A_graph_returns_zero(self):
        result = run_elspais("graph")
        assert result.returncode == 0
        assert len(result.stdout.strip()) > 0


class TestConfig:
    """Validates REQ-p00002: config subcommands."""

    def test_REQ_p00002_A_config_show_returns_zero(self):
        result = run_elspais("config", "show")
        assert result.returncode == 0

    def test_REQ_p00002_A_config_path_returns_toml(self):
        result = run_elspais("config", "path")
        assert result.returncode == 0
        assert ".toml" in result.stdout

    def test_REQ_p00002_A_config_get_namespace(self):
        result = run_elspais("config", "get", "project.namespace")
        assert result.returncode == 0
        assert "REQ" in result.stdout


class TestExample:
    """Example command output."""

    def test_example_returns_zero(self):
        result = run_elspais("example")
        assert result.returncode == 0

    def test_example_ids_shows_req_ids(self):
        result = run_elspais("example", "ids")
        assert result.returncode == 0
        assert "REQ" in result.stdout


class TestDocs:
    """Docs command output."""

    def test_docs_lists_topics_in_help(self):
        result = run_elspais("docs", "--help")
        assert result.returncode == 0
        assert "quickstart" in result.stdout

    def test_docs_quickstart_plain(self):
        result = run_elspais("docs", "quickstart", "--plain")
        assert result.returncode == 0
        assert len(result.stdout) > 100


class TestChanged:
    """Validates REQ-p00004: changed command."""

    def test_REQ_p00004_A_changed_returns_zero(self):
        result = run_elspais("changed")
        assert result.returncode == 0


class TestRules:
    """Validates REQ-p00002: rules command output."""

    def test_REQ_p00002_A_rules_list_returns_zero(self):
        result = run_elspais("rules", "list")
        assert result.returncode == 0
        output = result.stdout.lower()
        assert any(
            term in output for term in ["implements", "->", "rule", "hierarchy"]
        ), f"Expected hierarchy rule content in: {result.stdout[:200]}"


class TestHealth:
    """Validates REQ-p00002: health command output formats."""

    def test_REQ_p00002_A_health_lenient_returns_zero(self):
        result = run_elspais("checks", "--lenient")
        assert result.returncode == 0

    def test_REQ_p00002_A_health_json_valid(self):
        result = run_elspais("checks", "--format", "json", "--lenient")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data, (dict, list))

    def test_REQ_p00002_A_health_markdown_returns_zero(self):
        result = run_elspais("checks", "--format", "markdown", "--lenient")
        assert result.returncode == 0

    def test_REQ_p00002_A_health_spec_only_returns_zero(self):
        result = run_elspais("checks", "--spec", "--lenient")
        assert result.returncode == 0

    def test_REQ_p00002_A_health_junit_produces_valid_xml(self):
        result = run_elspais("checks", "--format", "junit", "--lenient")
        assert result.returncode == 0
        root = ET.fromstring(result.stdout)
        assert root.tag == "testsuites"

    def test_REQ_p00002_A_health_junit_has_testsuites(self):
        result = run_elspais("checks", "--format", "junit", "--lenient")
        assert result.returncode == 0
        root = ET.fromstring(result.stdout)
        suites = root.findall("testsuite")
        assert len(suites) >= 1, "Expected at least one <testsuite> element"

    def test_REQ_p00002_A_health_sarif_produces_valid_json(self):
        result = run_elspais("checks", "--format", "sarif", "--lenient")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["version"] == "2.1.0"
        assert "$schema" in data

    def test_REQ_p00002_A_health_sarif_has_runs(self):
        result = run_elspais("checks", "--format", "sarif", "--lenient")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert len(data["runs"]) == 1
        assert data["runs"][0]["tool"]["driver"]["name"] == "elspais"

    def test_REQ_p00002_A_health_junit_output_to_file(self, tmp_path):
        out = tmp_path / "health.xml"
        result = run_elspais("checks", "--format", "junit", "--lenient", "-o", str(out))
        assert result.returncode == 0
        assert out.exists(), f"Expected {out} to be created"
        root = ET.parse(str(out)).getroot()
        assert root.tag == "testsuites"

    def test_REQ_p00002_A_health_sarif_output_to_file(self, tmp_path):
        out = tmp_path / "health.sarif"
        result = run_elspais("checks", "--format", "sarif", "--lenient", "-o", str(out))
        assert result.returncode == 0
        assert out.exists(), f"Expected {out} to be created"
        data = json.loads(out.read_text())
        assert data["version"] == "2.1.0"

    def test_REQ_p00002_A_health_include_passing_details(self):
        result = run_elspais("checks", "--include-passing-details", "--lenient")
        assert result.returncode == 0


class TestFix:
    """Validates REQ-p00004: fix command dry-run."""

    def test_REQ_p00004_A_fix_dry_run_no_crash(self):
        result = run_elspais("fix", "--dry-run")
        # fix may return 0 (nothing to fix) or 1 (issues found); just shouldn't crash
        assert result.returncode in (
            0,
            1,
        ), f"fix --dry-run crashed with rc={result.returncode}: {result.stderr}"


class TestPdf:
    """Validates REQ-p00080-A: PDF generation end-to-end."""

    @requires_pandoc
    @requires_xelatex
    def test_REQ_p00080_A_generates_pdf(self, tmp_path):
        out = tmp_path / "test-output.pdf"
        result = run_elspais("pdf", "--output", str(out))
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert out.exists(), "PDF file was not created"
        assert out.stat().st_size > 0, "PDF file is empty"
        with open(out, "rb") as f:
            assert f.read(4) == b"%PDF"

    @requires_pandoc
    @requires_xelatex
    def test_REQ_p00080_F_generates_overview_pdf(self, tmp_path):
        out = tmp_path / "overview.pdf"
        result = run_elspais("pdf", "--overview", "--output", str(out))
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert out.exists()
        assert out.stat().st_size > 0
        with open(out, "rb") as f:
            assert f.read(4) == b"%PDF"


# ===================================================================
# From test_analysis_cmd.py
# ===================================================================


class TestAnalysisTableOutput:
    """Validates REQ-d00125-C: table format output.

    Validates REQ-d00125-G: table columns (Rank, ID, Title, Centrality,
    Fan-In, Uncovered, Score).
    """

    def test_REQ_d00125_C_table_output_returns_zero(self):
        result = run_elspais("analysis")
        assert result.returncode == 0

    def test_REQ_d00125_G_table_contains_column_headers(self):
        result = run_elspais("analysis")
        assert result.returncode == 0
        output = result.stdout
        assert "Rank" in output
        assert "ID" in output
        assert "Centrality" in output
        assert "Fan-In" in output
        assert "Uncovered" in output
        assert "Score" in output

    def test_REQ_d00125_G_table_contains_foundations_header(self):
        result = run_elspais("analysis")
        assert result.returncode == 0
        assert "Top Foundations:" in result.stdout

    def test_REQ_d00125_C_table_is_default_format(self):
        """Verify table is the default when --format is not specified."""
        result = run_elspais("analysis")
        assert result.returncode == 0
        # Table output should NOT be valid JSON
        with pytest.raises(json.JSONDecodeError):
            json.loads(result.stdout)


class TestAnalysisJsonOutput:
    """Validates REQ-d00125-C: JSON format output.

    Validates REQ-d00125-H: JSON serializes FoundationReport.
    """

    def test_REQ_d00125_C_json_output_returns_zero(self):
        result = run_elspais("analysis", "--format", "json")
        assert result.returncode == 0

    def test_REQ_d00125_H_json_output_valid(self):
        result = run_elspais("analysis", "--format", "json")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data, dict)

    def test_REQ_d00125_H_json_contains_report_fields(self):
        result = run_elspais("analysis", "--format", "json")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "ranked_nodes" in data
        assert "top_foundations" in data
        assert "actionable_leaves" in data
        assert "graph_stats" in data

    def test_REQ_d00125_H_json_ranked_nodes_is_list(self):
        result = run_elspais("analysis", "--format", "json")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data["ranked_nodes"], list)
        assert isinstance(data["top_foundations"], list)
        assert isinstance(data["actionable_leaves"], list)


class TestAnalysisOptions:
    """Validates REQ-d00125-A: --top N option.

    Validates REQ-d00125-B: --weights option.
    Validates REQ-d00125-D: --show option.
    Validates REQ-d00125-E: --level filter.
    Validates REQ-d00125-F: --include-code flag.
    """

    def test_REQ_d00125_A_top_limits_results(self):
        result = run_elspais("analysis", "--top", "3", "--format", "json")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert len(data["top_foundations"]) <= 3

    def test_REQ_d00125_A_top_default_is_10(self):
        result = run_elspais("analysis", "--format", "json")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert len(data["top_foundations"]) <= 10

    def test_REQ_d00125_D_show_foundations_only(self):
        result = run_elspais("analysis", "--show", "foundations")
        assert result.returncode == 0
        output = result.stdout
        assert "Top Foundations:" in output or "No requirements found" in output
        assert "Most Impactful Work Items:" not in output

    def test_REQ_d00125_D_show_leaves_only(self):
        result = run_elspais("analysis", "--show", "leaves")
        assert result.returncode == 0
        output = result.stdout
        assert "Top Foundations:" not in output

    def test_REQ_d00125_D_show_all_default(self):
        result = run_elspais("analysis")
        assert result.returncode == 0
        output = result.stdout
        # "all" is default; should show foundations section
        assert "Top Foundations:" in output or "No requirements found" in output

    def test_REQ_d00125_E_level_filter_dev(self):
        result = run_elspais("analysis", "--level", "dev", "--format", "json")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        for node in data["ranked_nodes"]:
            assert node["level"] == "DEV"

    def test_REQ_d00125_E_level_filter_prd(self):
        result = run_elspais("analysis", "--level", "prd", "--format", "json")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        for node in data["ranked_nodes"]:
            assert node["level"] == "PRD"

    def test_REQ_d00125_F_include_code_smoke(self):
        result = run_elspais("analysis", "--include-code")
        assert result.returncode == 0

    def test_REQ_d00125_F_include_code_with_json(self):
        result = run_elspais("analysis", "--include-code", "--format", "json")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data, dict)

    def test_REQ_d00125_B_custom_weights(self):
        result = run_elspais("analysis", "--weights", "1.0,0.0,0.0", "--format", "json")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data["ranked_nodes"], list)

    def test_REQ_d00125_B_weights_invalid_count_errors(self):
        result = run_elspais("analysis", "--weights", "1.0,0.0")
        assert result.returncode == 1
        assert "3 or 4" in result.stdout

    def test_REQ_d00125_B_weights_non_numeric_errors(self):
        result = run_elspais("analysis", "--weights", "a,b,c")
        assert result.returncode == 1
        assert "numeric" in result.stdout


# ===================================================================
# From test_self_validation.py
# ===================================================================


class TestHealthSelfValidation:
    """Validates REQ-p00013-C: health command passes on own repo."""

    def test_REQ_p00013_C_health_passes(self):
        result = run_elspais("checks", "--lenient")
        assert result.returncode == 0, f"health --lenient failed: {result.stderr}"

    def test_REQ_p00013_C_health_json_zero_errors(self):
        result = run_elspais("checks", "--format", "json", "--lenient")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert (
            data["summary"]["failed"] == 0
        ), f"Expected 0 failures, got {data['summary']['failed']}"

    def test_REQ_p00013_C_health_is_healthy(self):
        result = run_elspais("checks", "--format", "json", "--lenient")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["healthy"] is True, f"Expected healthy=true, got {data!r}"


class TestDoctorSelfValidation:
    """Validates REQ-p00013-C: doctor command passes on own repo."""

    def test_REQ_p00013_C_doctor_passes(self):
        result = run_elspais("doctor")
        assert result.returncode == 0, f"doctor failed: {result.stderr}"


class TestSummarySelfValidation:
    """Validates REQ-p00013-C: summary reflects real repo content."""

    @pytest.fixture()
    def summary_data(self):
        result = run_elspais("summary", "--format", "json")
        assert result.returncode == 0
        return json.loads(result.stdout)

    def test_REQ_p00013_C_summary_has_all_levels(self, summary_data):
        level_names = {entry["level"] for entry in summary_data["levels"]}
        for expected in ("PRD", "OPS", "DEV"):
            assert (
                expected in level_names
            ), f"Missing level {expected} in summary; found {level_names}"

    def test_REQ_p00013_C_summary_nonzero_counts(self, summary_data):
        for entry in summary_data["levels"]:
            assert entry["total"] > 0, f"Level {entry['level']} has total=0"

    def test_REQ_p00013_C_summary_has_assertions(self, summary_data):
        for entry in summary_data["levels"]:
            assert entry["total_assertions"] > 0, f"Level {entry['level']} has total_assertions=0"


class TestTraceSelfValidation:
    """Validates REQ-p00013-C: trace output contains requirements and tests."""

    @pytest.fixture()
    def trace_data(self, tmp_path):
        out = tmp_path / "trace"
        result = run_elspais("trace", "--format", "json", "--output", str(out))
        assert result.returncode == 0, f"trace failed: {result.stderr}"
        candidates = [out, out.with_suffix(".json"), Path(f"{out}.json")]
        found = [p for p in candidates if p.exists()]
        assert found, f"No trace output file found among {candidates}"
        return json.loads(found[0].read_text())

    def test_REQ_p00013_C_trace_json_has_requirements(self, trace_data):
        text = json.dumps(trace_data).lower()
        assert "req" in text, "Trace JSON contains no requirement references"

    def test_REQ_p00013_C_trace_json_has_tests(self, trace_data):
        text = json.dumps(trace_data).lower()
        assert "test" in text, "Trace JSON contains no test references"


class TestGraphSelfValidation:
    """Validates REQ-p00013-C: graph command produces meaningful output."""

    def test_REQ_p00013_C_graph_has_node_kinds(self):
        result = run_elspais("graph")
        assert result.returncode == 0, f"graph failed: {result.stderr}"
        output = result.stdout.lower()
        assert len(output.strip()) > 0, "graph produced empty output"
        assert "req" in output, "graph output contains no requirement references"


class TestSubdirDetection:
    """Validates REQ-p00013-C: git root auto-detection from subdirectory."""

    def test_REQ_p00013_C_works_from_subdirectory(self):
        subdir = REPO_ROOT / "tests"
        result = run_elspais("checks", "--lenient", cwd=subdir)
        assert result.returncode == 0, f"health --lenient failed from subdirectory: {result.stderr}"


# ===================================================================
# From test_workflows.py
# ===================================================================


class TestHealthSummaryConsistency:
    """Validates REQ-d00085-A: summary is consistent across runs."""

    def test_REQ_d00085_A_health_summary_same_total(self):
        health_result = run_elspais("checks", "--format", "json", "--lenient")
        assert health_result.returncode == 0, f"health failed: {health_result.stderr}"
        health_data = json.loads(health_result.stdout)
        assert isinstance(health_data, (dict, list))

        summary_result = run_elspais("summary", "--format", "json")
        assert summary_result.returncode == 0, f"summary failed: {summary_result.stderr}"
        summary_data = json.loads(summary_result.stdout)
        assert isinstance(summary_data, dict)

        # Summary should report a positive total
        levels = summary_data.get("levels", [])
        summary_total = sum(lvl.get("total", 0) for lvl in levels)
        assert summary_total > 0, "Expected at least one requirement in summary"

        # Run summary again - should be identical
        summary_result2 = run_elspais("summary", "--format", "json")
        assert summary_result2.returncode == 0
        summary_data2 = json.loads(summary_result2.stdout)
        levels2 = summary_data2.get("levels", [])
        summary_total2 = sum(lvl.get("total", 0) for lvl in levels2)
        assert (
            summary_total == summary_total2
        ), f"Summary totals differ between runs: {summary_total} vs {summary_total2}"


class TestSummaryIdempotent:
    """Validates REQ-d00085-A: summary produces consistent results across runs."""

    def test_REQ_d00085_A_summary_consistent_across_runs(self):
        result1 = run_elspais("summary", "--format", "json")
        assert result1.returncode == 0, f"summary run 1 failed: {result1.stderr}"
        data1 = json.loads(result1.stdout)

        result2 = run_elspais("summary", "--format", "json")
        assert result2.returncode == 0, f"summary run 2 failed: {result2.stderr}"
        data2 = json.loads(result2.stdout)

        levels1 = data1.get("levels", [])
        levels2 = data2.get("levels", [])
        total1 = sum(lvl.get("total", 0) for lvl in levels1)
        total2 = sum(lvl.get("total", 0) for lvl in levels2)

        assert total1 > 0, "Expected at least one requirement"
        assert total1 == total2, f"Summary totals differ between runs: {total1} vs {total2}"


# ===================================================================
# From test_e2e_edge_cases.py
# ===================================================================


class TestDocsCommandGlobal:
    """Docs command displays user documentation (global scope)."""

    def test_docs_quickstart(self):
        result = run_elspais("docs", "quickstart", "--plain")
        # docs command may work from any directory
        if result.returncode == 0:
            assert len(result.stdout.strip()) > 0

    def test_docs_commands(self):
        result = run_elspais("docs", "commands", "--plain")
        if result.returncode == 0:
            assert len(result.stdout.strip()) > 0


class TestExampleCommandGlobal:
    """Example command shows format examples (global scope)."""

    def test_example_requirement(self):
        result = run_elspais("example", "requirement")
        assert result.returncode == 0
        assert "REQ" in result.stdout or "SHALL" in result.stdout

    def test_example_assertion(self):
        result = run_elspais("example", "assertion")
        assert result.returncode == 0
