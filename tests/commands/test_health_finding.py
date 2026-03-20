# Verifies: REQ-d00085
"""Tests for HealthFinding dataclass and its integration with HealthCheck/HealthReport.

Validates REQ-d00085-I: HealthFinding dataclass with message, file_path, line,
node_id, and related fields; to_dict() serialization; renderer compatibility.
"""

from __future__ import annotations

import argparse
import xml.etree.ElementTree as ET

import pytest

from elspais.commands.health import (
    HealthCheck,
    HealthFinding,
    HealthReport,
    _format_report,
    _print_text_report,
    _render_junit,
)


class TestHealthCheckFindings:
    """Validates REQ-d00085-I: HealthCheck carries a findings list."""

    def test_REQ_d00085_I_healthcheck_findings_accepts_finding_instances(self) -> None:
        """HealthCheck.findings accepts HealthFinding instances."""
        f1 = HealthFinding(message="ref broken", file_path="spec/a.md", line=10)
        f2 = HealthFinding(message="id missing", node_id="REQ-x00001")
        check = HealthCheck(
            name="spec.refs",
            passed=False,
            message="2 broken references",
            category="spec",
            findings=[f1, f2],
        )
        assert len(check.findings) == 2
        assert check.findings[0].message == "ref broken"
        assert check.findings[1].node_id == "REQ-x00001"


class TestHealthFindingSerialization:
    """Validates REQ-d00085-I: to_dict() serialization includes findings."""

    def test_REQ_d00085_I_report_to_dict_includes_findings(self) -> None:
        """HealthReport.to_dict() includes findings in each check's serialization."""
        f1 = HealthFinding(message="bad ref", file_path="spec/a.md", line=3)
        check = HealthCheck(
            name="spec.refs",
            passed=False,
            message="1 broken ref",
            category="spec",
            findings=[f1],
        )
        report = HealthReport(checks=[check])
        d = report.to_dict()
        check_dict = d["checks"][0]
        assert "findings" in check_dict
        assert len(check_dict["findings"]) == 1
        assert check_dict["findings"][0]["message"] == "bad ref"
        assert check_dict["findings"][0]["file_path"] == "spec/a.md"
        assert check_dict["findings"][0]["line"] == 3


class TestHealthFindingRendererCompat:
    """Validates REQ-d00085-I: Existing renderers remain unchanged when findings present."""

    def _make_report_with_findings(self) -> HealthReport:
        """Helper: create a report with checks that have findings."""
        finding = HealthFinding(
            message="Dangling ref",
            file_path="spec/ops/req-o00001.md",
            line=15,
            node_id="REQ-o00001-A",
        )
        check_fail = HealthCheck(
            name="spec.refs",
            passed=False,
            message="1 broken reference found",
            category="spec",
            severity="error",
            findings=[finding],
        )
        check_pass = HealthCheck(
            name="spec.parseable",
            passed=True,
            message="Parsed 5 requirements",
            category="spec",
        )
        return HealthReport(checks=[check_fail, check_pass])

    def _make_report_without_findings(self) -> HealthReport:
        """Helper: create an equivalent report without findings."""
        check_fail = HealthCheck(
            name="spec.refs",
            passed=False,
            message="1 broken reference found",
            category="spec",
            severity="error",
        )
        check_pass = HealthCheck(
            name="spec.parseable",
            passed=True,
            message="Parsed 5 requirements",
            category="spec",
        )
        return HealthReport(checks=[check_fail, check_pass])

    def test_REQ_d00085_I_text_rendering_unaffected(self, capsys: pytest.CaptureFixture) -> None:
        """Text rendering output is the same whether findings are present or not."""
        report_with = self._make_report_with_findings()
        report_without = self._make_report_without_findings()

        _print_text_report(report_with)
        output_with = capsys.readouterr().out

        _print_text_report(report_without)
        output_without = capsys.readouterr().out

        assert output_with == output_without

    def test_REQ_d00085_I_markdown_rendering_unaffected(self) -> None:
        """Markdown rendering is the same with or without findings."""
        report_with = self._make_report_with_findings()
        report_without = self._make_report_without_findings()

        args = argparse.Namespace(
            format="markdown",
            verbose=False,
            quiet=False,
            lenient=False,
            include_passing_details=False,
        )
        md_with = _format_report(report_with, args)
        md_without = _format_report(report_without, args)

        assert md_with == md_without

    def test_REQ_d00085_I_junit_rendering_unaffected(self) -> None:
        """JUnit XML rendering output is the same whether findings are present or not."""
        report_with = self._make_report_with_findings()
        report_without = self._make_report_without_findings()

        junit_with = _render_junit(report_with)
        junit_without = _render_junit(report_without)

        # Parse both to compare structure (ignore whitespace differences)
        tree_with = ET.fromstring(junit_with)
        tree_without = ET.fromstring(junit_without)

        assert ET.tostring(tree_with) == ET.tostring(tree_without)


class TestRetiredFindingDowngrade:
    """Retired requirements' findings should not count as health errors."""

    def test_all_retired_findings_downgrades_check(self) -> None:
        """A check where ALL findings are for retired REQs is downgraded to info."""
        from elspais.commands.health import _downgrade_retired_findings

        finding = HealthFinding(
            message="Hash mismatch",
            node_id="REQ-d00099",
        )
        check = HealthCheck(
            name="spec.hash_integrity",
            passed=False,
            message="1 requirement(s) have stale hashes: REQ-d00099",
            category="spec",
            severity="warning",
            findings=[finding],
        )
        _downgrade_retired_findings([check], retired_ids={"REQ-d00099"})

        assert check.passed is True
        assert check.severity == "info"
        assert finding.retired is True
        assert "[retired only]" in check.message

    def test_mixed_findings_keeps_check_failed(self) -> None:
        """A check with both retired and active findings stays failed."""
        from elspais.commands.health import _downgrade_retired_findings

        retired_finding = HealthFinding(message="Hash mismatch", node_id="REQ-d00099")
        active_finding = HealthFinding(message="Hash mismatch", node_id="REQ-d00001")
        check = HealthCheck(
            name="spec.hash_integrity",
            passed=False,
            message="2 requirement(s) have stale hashes",
            category="spec",
            severity="warning",
            findings=[retired_finding, active_finding],
        )
        _downgrade_retired_findings([check], retired_ids={"REQ-d00099"})

        assert check.passed is False
        assert check.severity == "warning"
        assert retired_finding.retired is True
        assert active_finding.retired is False

    def test_passing_check_not_affected(self) -> None:
        """Passing checks are not modified by downgrade."""
        from elspais.commands.health import _downgrade_retired_findings

        check = HealthCheck(
            name="spec.hash_integrity",
            passed=True,
            message="All hashes up to date",
            category="spec",
        )
        _downgrade_retired_findings([check], retired_ids={"REQ-d00099"})

        assert check.passed is True

    def test_retired_finding_to_dict_includes_flag(self) -> None:
        """Retired findings include 'retired: true' in serialization."""
        finding = HealthFinding(message="Stale hash", node_id="REQ-d00099", retired=True)
        d = finding.to_dict()
        assert d["retired"] is True

    def test_non_retired_finding_to_dict_omits_flag(self) -> None:
        """Non-retired findings omit 'retired' from serialization."""
        finding = HealthFinding(message="Stale hash", node_id="REQ-d00099")
        d = finding.to_dict()
        assert "retired" not in d


class TestDetailHint:
    """Unhealthy reports should show a hint about how to get details."""

    def test_hint_shown_when_unhealthy(self, capsys: pytest.CaptureFixture) -> None:
        """When report has errors, hint shows verbose and JSON commands."""
        check = HealthCheck(
            name="spec.hash_integrity",
            passed=False,
            message="2 stale hashes",
            category="spec",
            severity="error",
            findings=[HealthFinding(message="bad", node_id="REQ-001")],
        )
        report = HealthReport(checks=[check])
        _print_text_report(report, verbose=False)
        output = capsys.readouterr().out
        assert "elspais -v checks --spec" in output
        assert "--format json -o health.json" in output

    def test_hint_skips_verbose_suggestion_when_already_verbose(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """When already verbose, hint only shows JSON command."""
        check = HealthCheck(
            name="spec.hash_integrity",
            passed=False,
            message="2 stale hashes",
            category="spec",
            severity="error",
            findings=[HealthFinding(message="bad", node_id="REQ-001")],
        )
        report = HealthReport(checks=[check])
        _print_text_report(report, verbose=True)
        output = capsys.readouterr().out
        assert "elspais -v checks --spec" not in output
        assert "--format json -o health.json" in output

    def test_hint_not_shown_when_healthy(self, capsys: pytest.CaptureFixture) -> None:
        """Healthy reports don't show the hint."""
        check = HealthCheck(
            name="spec.ok",
            passed=True,
            message="All good",
            category="spec",
        )
        report = HealthReport(checks=[check])
        _print_text_report(report, verbose=False)
        output = capsys.readouterr().out
        assert "elspais checks" not in output

    def test_hint_no_scope_flag_when_multiple_categories_fail(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """When multiple categories fail, hint omits scope flags."""
        checks = [
            HealthCheck(
                name="spec.hash",
                passed=False,
                message="stale",
                category="spec",
                severity="error",
                findings=[HealthFinding(message="bad", node_id="REQ-001")],
            ),
            HealthCheck(
                name="code.unlinked",
                passed=False,
                message="unlinked",
                category="code",
                severity="warning",
                findings=[HealthFinding(message="bad", node_id="CODE-001")],
            ),
        ]
        report = HealthReport(checks=checks)
        _print_text_report(report, verbose=False)
        output = capsys.readouterr().out
        assert "elspais -v checks" in output
        assert "--spec" not in output
        assert "--code" not in output
