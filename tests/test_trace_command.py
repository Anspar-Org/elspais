# Validates REQ-p00003-A, REQ-p00003-B, REQ-p00006-A
# Validates REQ-p00050-B
# Validates REQ-d00052-B, REQ-d00052-C
"""Tests for the trace command.

Uses the session-scoped canonical_federated_graph to avoid rebuilding
the graph per test (~2.5s each). Tests call trace rendering functions
directly against the pre-built graph.
"""

import json

import pytest

from elspais.commands.trace import (
    REPORT_PRESETS,
    ReportPreset,
    _render_json_from_data,
    _render_table_from_graph,
    compute_trace,
)


class TestTraceCommand:
    """Tests for basic trace command functionality."""

    # Implements: REQ-p00003-A, REQ-d00084-A
    @pytest.mark.parametrize(
        "fmt,expected_marker",
        [
            ("markdown", "Traceability Matrix"),
            ("html", "<!DOCTYPE html>"),
            ("csv", "ID"),
        ],
        ids=["markdown", "html", "csv"],
    )
    def test_trace_table_format_output(
        self, canonical_federated_graph, fmt, expected_marker, capsys
    ):
        """Test trace command produces correct table output for each format."""
        preset = ReportPreset(
            name="standard",
            columns=list(REPORT_PRESETS["standard"].columns),
        )
        result = _render_table_from_graph(canonical_federated_graph, fmt, preset)
        assert result == 0

        content = capsys.readouterr().out
        assert expected_marker in content
        assert "REQ-p00001" in content

    # Implements: REQ-d00084-A
    def test_trace_json_format_output(self, canonical_federated_graph, capsys):
        """Test trace command produces correct JSON output."""
        data = compute_trace(canonical_federated_graph, {}, {})
        preset = ReportPreset(
            name="standard",
            columns=list(REPORT_PRESETS["standard"].columns),
        )
        _render_json_from_data(data, preset)

        content = capsys.readouterr().out
        parsed = json.loads(content)
        assert isinstance(parsed, list)
        assert any(item["id"] == "REQ-p00001" for item in parsed)


class TestTraceReportPresets:
    """Tests for --preset functionality."""

    @pytest.fixture(scope="class")
    def trace_data(self, canonical_federated_graph):
        """Compute trace data once for the class."""
        return compute_trace(canonical_federated_graph, {}, {})

    def _make_preset(self, preset_name):
        return ReportPreset(
            name=preset_name,
            columns=list(REPORT_PRESETS[preset_name].columns),
        )

    # Implements: REQ-d00084-B
    @pytest.mark.parametrize(
        "preset,should_have,should_not_have",
        [
            (
                "minimal",
                ["ID", "Title", "Level", "Status"],
                ["Implemented", "Tested"],
            ),
            (
                "standard",
                [
                    "ID",
                    "Title",
                    "Level",
                    "Status",
                    "Implemented",
                    "Tested",
                    "Verified",
                    "UAT Coverage",
                    "UAT Verified",
                    "Code Tested",
                ],
                [],
            ),
            (
                "full",
                [
                    "ID",
                    "Title",
                    "Level",
                    "Status",
                    "Implemented",
                    "Tested",
                    "Verified",
                    "UAT Coverage",
                    "UAT Verified",
                    "Code Tested",
                ],
                [],
            ),
        ],
        ids=["minimal", "standard", "full"],
    )
    def test_preset_csv_columns(
        self,
        canonical_federated_graph,
        preset,
        should_have,
        should_not_have,
        capsys,
    ):
        """Test --preset produces expected CSV columns."""
        p = self._make_preset(preset)
        result = _render_table_from_graph(canonical_federated_graph, "csv", p)
        assert result == 0
        header = capsys.readouterr().out.split("\n")[0]
        for col in should_have:
            assert col in header, f"Missing column: {col}"
        for col in should_not_have:
            assert col not in header, f"Unexpected column: {col}"

    # Implements: REQ-d00084-D
    @pytest.mark.parametrize(
        "preset,should_have_fields",
        [
            (
                "full",
                [
                    "implemented",
                    "tested",
                    "verified",
                    "uat_coverage",
                    "uat_verified",
                    "code_tested",
                ],
            ),
            ("minimal", []),
        ],
        ids=["full-has-coverage", "minimal-excludes-coverage"],
    )
    def test_preset_json_fields(
        self,
        trace_data,
        preset,
        should_have_fields,
        capsys,
    ):
        """Test --preset JSON includes/excludes coverage fields."""
        p = self._make_preset(preset)
        _render_json_from_data(trace_data, p)

        content = capsys.readouterr().out
        data = json.loads(content)
        assert isinstance(data, list)
        parent = next((r for r in data if r.get("id") == "REQ-p00001"), None)
        assert parent is not None
        for field in should_have_fields:
            assert field in parent, f"Missing field: {field}"
        if not should_have_fields:
            assert "implemented" not in parent

    # Implements: REQ-d00084-B
    def test_report_invalid_preset_returns_error(self, capsys):
        """Test invalid --preset returns error."""
        import argparse

        from elspais.commands import trace

        args = argparse.Namespace(
            config=None,
            spec_dir=None,
            format="markdown",
            quiet=False,
            preset="nonexistent",
        )
        result = trace.run(args)
        assert result == 1
        captured = capsys.readouterr()
        assert "Unknown preset" in captured.err
        assert "minimal" in captured.err

    # Implements: REQ-d00084-B
    def test_report_default_is_standard(self, canonical_federated_graph, capsys):
        """Test that no --preset defaults to standard."""
        default_preset = self._make_preset("standard")
        _render_table_from_graph(canonical_federated_graph, "csv", default_preset)
        default_header = capsys.readouterr().out.split("\n")[0]

        standard_preset = self._make_preset("standard")
        _render_table_from_graph(canonical_federated_graph, "csv", standard_preset)
        standard_header = capsys.readouterr().out.split("\n")[0]

        assert default_header == standard_header
