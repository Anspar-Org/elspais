# Verifies: REQ-d00085
"""Tests for --skip-passing-details / --include-passing-details CLI flags.

Validates REQ-d00085-E and REQ-d00085-F: passing check detail control across
all output formats (text, markdown, json, junit, sarif).
"""

from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET

from elspais.commands.health import (
    HealthCheck,
    HealthFinding,
    HealthReport,
    _format_report,
)


def _make_passing_report() -> HealthReport:
    """Create a report with a single passing check that has details and findings."""
    report = HealthReport()
    report.add(
        HealthCheck(
            name="valid_references",
            passed=True,
            message="All 12 references resolved",
            category="spec",
            severity="error",
            details={"total_refs": 12, "resolved": 12},
            findings=[
                HealthFinding(
                    message="REQ-p00001-A resolves to spec/prd/req-p00001.md",
                    file_path="spec/dev/req-d00010.md",
                    line=5,
                ),
                HealthFinding(
                    message="REQ-p00002-B resolves to spec/prd/req-p00002.md",
                    file_path="spec/dev/req-d00011.md",
                    line=8,
                ),
            ],
        )
    )
    return report


def _make_args(**kwargs) -> argparse.Namespace:
    """Create an argparse.Namespace with sensible defaults for health formatting."""
    defaults = {
        "format": "text",
        "verbose": False,
        "quiet": False,
        "lenient": False,
        "include_passing_details": False,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


class TestPassingDetailFlagsCLI:
    """Validates REQ-d00085-E: CLI accepts --include-passing-details and --skip-passing-details."""

    def test_REQ_d00085_E_include_passing_details_flag_accepted(self) -> None:
        """The --include-passing-details flag is accepted by the health subcommand parser."""
        from elspais.cli import parse_args

        args = parse_args(["health", "--include-passing-details"])
        assert args.include_passing_details is True

    def test_REQ_d00085_E_no_include_passing_details_flag_accepted(self) -> None:
        """The --no-include-passing-details flag is accepted (this is the default)."""
        from elspais.cli import parse_args

        args = parse_args(["health", "--no-include-passing-details"])
        assert args.include_passing_details is False

    def test_REQ_d00085_E_default_skips_passing_details(self) -> None:
        """Without either flag, passing details are skipped by default."""
        from elspais.cli import parse_args

        args = parse_args(["health"])
        # Default behavior: skip passing details
        assert args.include_passing_details is False


class TestTextFormatPassingDetails:
    """Validates REQ-d00085-E: text format respects passing-detail flags."""

    def test_REQ_d00085_E_text_include_passing_details_shows_details(self) -> None:
        """Text format with --include-passing-details shows details for passing checks."""
        report = _make_passing_report()
        args = _make_args(format="text", verbose=True, include_passing_details=True)
        output = _format_report(report, args)
        # With include-passing-details, passing check details should be visible
        assert "total_refs" in output
        assert "resolved" in output

    def test_REQ_d00085_E_text_skip_passing_details_hides_details(self) -> None:
        """Text format with default --skip-passing-details hides details for passing checks."""
        report = _make_passing_report()
        args = _make_args(format="text", verbose=True, include_passing_details=False)
        output = _format_report(report, args)
        # With skip-passing-details (default), passing check details should be hidden
        # even in verbose mode — details keys like total_refs should not appear
        assert "total_refs" not in output
        assert "total_refs: 12" not in output
        # But the check name and message should still appear
        assert "valid_references" in output
        assert "All 12 references resolved" in output


class TestMarkdownFormatPassingDetails:
    """Validates REQ-d00085-F: markdown format respects passing-detail flags."""

    def test_REQ_d00085_F_markdown_include_passing_details_shows_findings(self) -> None:
        """Markdown with --include-passing-details shows <details> block for passing checks."""
        report = _make_passing_report()
        args = _make_args(format="markdown", include_passing_details=True)
        output = _format_report(report, args)
        # Should include findings detail for passing checks
        assert "REQ-p00001-A" in output
        assert "<details>" in output or "REQ-p00001-A resolves" in output

    def test_REQ_d00085_F_markdown_skip_passing_details_hides_findings(self) -> None:
        """Markdown with --skip-passing-details hides findings for passing checks."""
        report = _make_passing_report()
        args = _make_args(format="markdown", include_passing_details=False)
        output = _format_report(report, args)
        # Passing check row should appear in the table
        assert "valid_references" in output
        assert "PASS" in output
        # But individual findings should NOT appear
        assert "REQ-p00001-A resolves" not in output


class TestJUnitFormatPassingDetails:
    """Validates REQ-d00085-E: JUnit format respects passing-detail flags."""

    def test_REQ_d00085_E_junit_include_passing_details_shows_system_out(self) -> None:
        """JUnit with --include-passing-details adds system-out for passing checks."""
        report = _make_passing_report()
        args = _make_args(format="junit", include_passing_details=True)
        output = _format_report(report, args)
        root = ET.fromstring(output)
        testcases = root.findall(".//testcase[@name='valid_references']")
        assert len(testcases) == 1
        tc = testcases[0]
        # With include, passing checks should have system-out with details
        sys_out = tc.find("system-out")
        assert sys_out is not None
        assert "REQ-p00001-A" in (sys_out.text or "")

    def test_REQ_d00085_E_junit_skip_passing_details_no_system_out(self) -> None:
        """JUnit with --skip-passing-details omits <system-out> for passing checks."""
        report = _make_passing_report()
        args = _make_args(format="junit", include_passing_details=False)
        output = _format_report(report, args)
        root = ET.fromstring(output)
        testcases = root.findall(".//testcase[@name='valid_references']")
        assert len(testcases) == 1
        tc = testcases[0]
        # With skip (default), passing checks should have no system-out
        sys_out = tc.find("system-out")
        assert sys_out is None


class TestJSONFormatPassingDetails:
    """Validates REQ-d00085-E: JSON format always includes full details."""

    def test_REQ_d00085_E_json_always_includes_details(self) -> None:
        """JSON format includes full details regardless of passing-detail flags."""
        report = _make_passing_report()
        # Even with skip-passing-details, JSON should include everything
        args = _make_args(format="json", include_passing_details=False)
        output = _format_report(report, args)
        data = json.loads(output)
        checks = data["checks"]
        passing = [c for c in checks if c["passed"]]
        assert len(passing) == 1
        # JSON always includes findings array
        assert "findings" in passing[0]
        assert len(passing[0]["findings"]) == 2


class TestSARIFFormatPassingDetails:
    """Validates REQ-d00085-E: SARIF format always omits passing checks."""

    def test_REQ_d00085_E_sarif_omits_passing_regardless_of_flag(self) -> None:
        """SARIF format omits passing checks entirely regardless of flags."""
        report = _make_passing_report()
        args = _make_args(format="sarif", include_passing_details=True)
        output = _format_report(report, args)
        data = json.loads(output)
        results = data["runs"][0]["results"]
        # SARIF only includes failing checks, so passing checks should be absent
        assert len(results) == 0
