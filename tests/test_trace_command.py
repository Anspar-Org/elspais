# Validates REQ-p00003-A, REQ-p00003-B, REQ-p00006-A
# Validates REQ-p00050-B
# Validates REQ-d00052-B, REQ-d00052-C
"""Tests for the trace command."""

import argparse
import json
from pathlib import Path

import pytest


class TestTraceCommand:
    """Tests for basic trace command functionality."""

    # Implements: REQ-p00003-A, REQ-d00084-A
    @pytest.mark.parametrize(
        "fmt,expected_marker",
        [
            ("markdown", "Traceability Matrix"),
            ("html", "<!DOCTYPE html>"),
            ("json", None),  # JSON checked separately
            ("csv", "ID"),
        ],
        ids=["markdown", "html", "json", "csv"],
    )
    def test_trace_format_output(
        self, hht_like_fixture: Path, fmt: str, expected_marker: str | None, capsys
    ):
        """Test trace command produces correct output for each format."""
        from elspais.commands import trace

        args = argparse.Namespace(
            config=None,
            spec_dir=hht_like_fixture / "spec",
            format=fmt,
            quiet=True,
        )

        result = trace.run(args)
        assert result == 0

        content = capsys.readouterr().out
        if fmt == "json":
            data = json.loads(content)
            assert isinstance(data, list)
            assert any(item["id"] == "REQ-p00001" for item in data)
        else:
            assert expected_marker in content
            assert "REQ-p00001" in content


class TestTraceReportPresets:
    """Tests for --preset functionality."""

    @pytest.fixture
    def preset_spec_dir(self, hht_like_fixture: Path) -> Path:
        """Use the static hht-like fixture spec dir."""
        return hht_like_fixture / "spec"

    def _run_trace(self, spec_dir: Path, fmt: str, preset: str | None, capsys):
        """Helper to run trace with given format and preset."""
        from elspais.commands import trace

        args = argparse.Namespace(
            config=None,
            spec_dir=spec_dir,
            format=fmt,
            quiet=True,
            preset=preset,
        )
        result = trace.run(args)
        content = capsys.readouterr()
        return result, content

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
        preset_spec_dir: Path,
        preset: str,
        should_have: list[str],
        should_not_have: list[str],
        capsys,
    ):
        """Test --preset produces expected CSV columns."""
        result, captured = self._run_trace(preset_spec_dir, "csv", preset, capsys)
        assert result == 0
        header = captured.out.split("\n")[0]
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
        preset_spec_dir: Path,
        preset: str,
        should_have_fields: list[str],
        capsys,
    ):
        """Test --preset JSON includes/excludes coverage fields."""
        result, captured = self._run_trace(preset_spec_dir, "json", preset, capsys)
        assert result == 0
        data = json.loads(captured.out)
        assert isinstance(data, list)
        parent = next((r for r in data if r.get("id") == "REQ-p00001"), None)
        assert parent is not None
        for field in should_have_fields:
            assert field in parent, f"Missing field: {field}"
        if not should_have_fields:
            assert "implemented" not in parent

    # Implements: REQ-d00084-B
    def test_report_invalid_preset_returns_error(self, preset_spec_dir: Path, capsys):
        """Test invalid --preset returns error."""
        result, captured = self._run_trace(preset_spec_dir, "markdown", "nonexistent", capsys)
        assert result == 1
        assert "Unknown preset" in captured.err
        assert "minimal" in captured.err

    # Implements: REQ-d00084-B
    def test_report_default_is_standard(self, preset_spec_dir: Path, capsys):
        """Test that no --preset defaults to standard."""
        result1, cap1 = self._run_trace(preset_spec_dir, "csv", None, capsys)
        assert result1 == 0
        result2, cap2 = self._run_trace(preset_spec_dir, "csv", "standard", capsys)
        assert result2 == 0
        assert cap1.out.split("\n")[0] == cap2.out.split("\n")[0]
