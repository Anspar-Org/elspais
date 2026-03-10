# Validates: REQ-d00125-A, REQ-d00125-B, REQ-d00125-C, REQ-d00125-D,
#            REQ-d00125-E, REQ-d00125-F, REQ-d00125-G, REQ-d00125-H
"""End-to-end subprocess tests for elspais analysis CLI command.

Each test invokes the elspais binary as a subprocess and validates
return codes, output format, and content for foundation analysis.
"""

import json
import shutil

import pytest

from .conftest import run_elspais

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        shutil.which("elspais") is None,
        reason="elspais CLI not found on PATH",
    ),
]


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
        assert "exactly 3" in result.stdout

    def test_REQ_d00125_B_weights_non_numeric_errors(self):
        result = run_elspais("analysis", "--weights", "a,b,c")
        assert result.returncode == 1
        assert "numeric" in result.stdout
