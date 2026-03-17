# Validates: REQ-d00085
"""Tests for HealthFinding dataclass and its integration with HealthCheck/HealthReport.

Validates REQ-d00085-I: HealthFinding dataclass with message, file_path, line,
node_id, and related fields; to_dict() serialization; renderer compatibility.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from elspais.commands.health import (
    HealthCheck,
    HealthFinding,
    HealthReport,
    _print_text_report,
    _render_junit,
    _render_markdown,
)


class TestHealthFindingDataclass:
    """Validates REQ-d00085-I: HealthFinding dataclass instantiation and defaults."""

    def test_REQ_d00085_I_finding_instantiation_all_fields(self) -> None:
        """HealthFinding can be instantiated with all fields explicitly."""
        finding = HealthFinding(
            message="Broken reference to REQ-p00002",
            file_path="spec/dev/req-d00010.md",
            line=42,
            node_id="REQ-d00010-A",
            related=["REQ-p00002", "REQ-p00003"],
        )
        assert finding.message == "Broken reference to REQ-p00002"
        assert finding.file_path == "spec/dev/req-d00010.md"
        assert finding.line == 42
        assert finding.node_id == "REQ-d00010-A"
        assert finding.related == ["REQ-p00002", "REQ-p00003"]

    def test_REQ_d00085_I_finding_defaults(self) -> None:
        """HealthFinding has correct defaults: None for optional fields, [] for related."""
        finding = HealthFinding(message="Something went wrong")
        assert finding.message == "Something went wrong"
        assert finding.file_path is None
        assert finding.line is None
        assert finding.node_id is None
        assert finding.related == []

    def test_REQ_d00085_I_finding_partial_fields(self) -> None:
        """HealthFinding can be instantiated with a subset of optional fields."""
        finding = HealthFinding(
            message="Missing assertion",
            node_id="REQ-d00050",
        )
        assert finding.message == "Missing assertion"
        assert finding.file_path is None
        assert finding.line is None
        assert finding.node_id == "REQ-d00050"
        assert finding.related == []


class TestHealthCheckFindings:
    """Validates REQ-d00085-I: HealthCheck carries a findings list."""

    def test_REQ_d00085_I_healthcheck_findings_default_empty(self) -> None:
        """HealthCheck.findings defaults to an empty list."""
        check = HealthCheck(
            name="spec.refs",
            passed=True,
            message="All references valid",
            category="spec",
        )
        assert check.findings == []

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

    def test_REQ_d00085_I_finding_to_dict(self) -> None:
        """HealthFinding serializes to dict with all fields."""
        finding = HealthFinding(
            message="Broken link",
            file_path="spec/dev/req-d00010.md",
            line=7,
            node_id="REQ-d00010-B",
            related=["REQ-p00001"],
        )
        # HealthFinding should support to_dict or be serialized via dataclasses.asdict
        from dataclasses import asdict

        d = asdict(finding)
        assert d == {
            "message": "Broken link",
            "file_path": "spec/dev/req-d00010.md",
            "line": 7,
            "node_id": "REQ-d00010-B",
            "related": ["REQ-p00001"],
            "repo": None,
        }

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

    def test_REQ_d00085_I_report_to_dict_empty_findings(self) -> None:
        """Empty findings list serializes as empty array in to_dict()."""
        check = HealthCheck(
            name="spec.ok",
            passed=True,
            message="All good",
            category="spec",
        )
        report = HealthReport(checks=[check])
        d = report.to_dict()
        check_dict = d["checks"][0]
        assert "findings" in check_dict
        assert check_dict["findings"] == []


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
        """Markdown rendering output is the same whether findings are present or not."""
        report_with = self._make_report_with_findings()
        report_without = self._make_report_without_findings()

        md_with = _render_markdown(report_with)
        md_without = _render_markdown(report_without)

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
