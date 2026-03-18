# Verifies: REQ-d00085
"""Tests for SARIF v2.1.0 JSON rendering of health reports.

Validates REQ-d00085-J: The ``--format sarif`` option SHALL render health
findings as SARIF v2.1.0 JSON, with one ``reportingDescriptor`` per unique
check name, one ``result`` per ``HealthFinding`` with physical locations,
passing checks omitted, and coverage stats in ``run.properties``.
"""

from __future__ import annotations

import argparse
import json

from elspais.commands.health import (
    HealthCheck,
    HealthFinding,
    HealthReport,
    _format_report,
    _render_sarif,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SARIF_SCHEMA = (
    "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/main/"
    "sarif-2.1/schema/sarif-schema-2.1.0.json"
)


def _make_check(
    name: str = "check_foo",
    passed: bool = True,
    message: str = "ok",
    category: str = "config",
    severity: str = "error",
    details: dict | None = None,
    findings: list[HealthFinding] | None = None,
) -> HealthCheck:
    return HealthCheck(
        name=name,
        passed=passed,
        message=message,
        category=category,
        severity=severity,
        details=details or {},
        findings=findings or [],
    )


def _make_args(fmt: str = "sarif") -> argparse.Namespace:
    return argparse.Namespace(format=fmt, lenient=False, quiet=False, verbose=False)


def _parse_sarif(report: HealthReport) -> dict:
    raw = _render_sarif(report)
    return json.loads(raw)


# ---------------------------------------------------------------------------
# 1. Valid JSON with SARIF schema and version
# ---------------------------------------------------------------------------


class TestREQd00085JSarifEnvelope:
    """Validates REQ-d00085-J: SARIF envelope structure."""

    def test_REQ_d00085_J_schema_and_version(self) -> None:
        report = HealthReport()
        report.add(_make_check(passed=False, message="bad"))
        sarif = _parse_sarif(report)

        assert sarif["$schema"] == SARIF_SCHEMA
        assert sarif["version"] == "2.1.0"
        assert "runs" in sarif
        assert len(sarif["runs"]) == 1

    def test_REQ_d00085_J_tool_driver_name(self) -> None:
        report = HealthReport()
        report.add(_make_check(passed=False, message="bad"))
        sarif = _parse_sarif(report)

        driver = sarif["runs"][0]["tool"]["driver"]
        assert driver["name"] == "elspais"


# ---------------------------------------------------------------------------
# 2. reportingDescriptors from failing checks
# ---------------------------------------------------------------------------


class TestREQd00085JReportingDescriptors:
    """Validates REQ-d00085-J: rule mapping from failing checks."""

    def test_REQ_d00085_J_unique_check_maps_to_rule(self) -> None:
        report = HealthReport()
        report.add(
            _make_check(
                name="duplicate_ids",
                passed=False,
                message="Found duplicates",
                findings=[HealthFinding(message="dup A")],
            )
        )
        sarif = _parse_sarif(report)

        rules = sarif["runs"][0]["tool"]["driver"]["rules"]
        assert len(rules) == 1
        assert rules[0]["id"] == "duplicate_ids"

    def test_REQ_d00085_J_multiple_failing_checks_produce_multiple_rules(self) -> None:
        report = HealthReport()
        report.add(
            _make_check(
                name="check_a",
                passed=False,
                message="fail a",
                findings=[HealthFinding(message="a1")],
            )
        )
        report.add(
            _make_check(
                name="check_b",
                passed=False,
                message="fail b",
                severity="warning",
                findings=[HealthFinding(message="b1")],
            )
        )
        sarif = _parse_sarif(report)

        rules = sarif["runs"][0]["tool"]["driver"]["rules"]
        rule_ids = {r["id"] for r in rules}
        assert rule_ids == {"check_a", "check_b"}


# ---------------------------------------------------------------------------
# 3. Results from HealthFindings
# ---------------------------------------------------------------------------


class TestREQd00085JResults:
    """Validates REQ-d00085-J: result mapping from findings."""

    def test_REQ_d00085_J_each_finding_maps_to_result(self) -> None:
        report = HealthReport()
        report.add(
            _make_check(
                name="broken_refs",
                passed=False,
                message="broken",
                findings=[
                    HealthFinding(message="ref A broken"),
                    HealthFinding(message="ref B broken"),
                ],
            )
        )
        sarif = _parse_sarif(report)

        results = sarif["runs"][0]["results"]
        assert len(results) == 2
        messages = {r["message"]["text"] for r in results}
        assert "ref A broken" in messages
        assert "ref B broken" in messages

    def test_REQ_d00085_J_finding_without_findings_uses_check_message(self) -> None:
        """A failing check with no findings still produces a result."""
        report = HealthReport()
        report.add(
            _make_check(
                name="config_missing",
                passed=False,
                message="Config file not found",
                findings=[],
            )
        )
        sarif = _parse_sarif(report)

        results = sarif["runs"][0]["results"]
        assert len(results) == 1
        assert results[0]["message"]["text"] == "Config file not found"


# ---------------------------------------------------------------------------
# 4. Severity level mapping
# ---------------------------------------------------------------------------


class TestREQd00085JSeverityMapping:
    """Validates REQ-d00085-J: severity to SARIF level mapping."""

    def test_REQ_d00085_J_error_maps_to_error(self) -> None:
        report = HealthReport()
        report.add(
            _make_check(
                name="c1",
                passed=False,
                message="err",
                severity="error",
                findings=[HealthFinding(message="e")],
            )
        )
        sarif = _parse_sarif(report)
        assert sarif["runs"][0]["results"][0]["level"] == "error"

    def test_REQ_d00085_J_warning_maps_to_warning(self) -> None:
        report = HealthReport()
        report.add(
            _make_check(
                name="c1",
                passed=False,
                message="warn",
                severity="warning",
                findings=[HealthFinding(message="w")],
            )
        )
        sarif = _parse_sarif(report)
        assert sarif["runs"][0]["results"][0]["level"] == "warning"

    def test_REQ_d00085_J_info_maps_to_note(self) -> None:
        report = HealthReport()
        report.add(
            _make_check(
                name="c1",
                passed=False,
                message="info",
                severity="info",
                findings=[HealthFinding(message="i")],
            )
        )
        sarif = _parse_sarif(report)
        assert sarif["runs"][0]["results"][0]["level"] == "note"


# ---------------------------------------------------------------------------
# 5. Physical locations from file_path
# ---------------------------------------------------------------------------


class TestREQd00085JPhysicalLocation:
    """Validates REQ-d00085-J: physical location mapping."""

    def test_REQ_d00085_J_file_path_produces_artifact_location(self) -> None:
        report = HealthReport()
        report.add(
            _make_check(
                name="c1",
                passed=False,
                message="bad",
                findings=[
                    HealthFinding(message="issue", file_path="spec/reqs.md"),
                ],
            )
        )
        sarif = _parse_sarif(report)

        result = sarif["runs"][0]["results"][0]
        loc = result["locations"][0]["physicalLocation"]
        assert loc["artifactLocation"]["uri"] == "spec/reqs.md"

    def test_REQ_d00085_J_no_file_path_omits_locations(self) -> None:
        report = HealthReport()
        report.add(
            _make_check(
                name="c1",
                passed=False,
                message="bad",
                findings=[HealthFinding(message="no location")],
            )
        )
        sarif = _parse_sarif(report)

        result = sarif["runs"][0]["results"][0]
        assert "locations" not in result or result["locations"] == []


# ---------------------------------------------------------------------------
# 6. Line numbers in region
# ---------------------------------------------------------------------------


class TestREQd00085JRegion:
    """Validates REQ-d00085-J: region with startLine."""

    def test_REQ_d00085_J_line_produces_start_line(self) -> None:
        report = HealthReport()
        report.add(
            _make_check(
                name="c1",
                passed=False,
                message="bad",
                findings=[
                    HealthFinding(message="issue", file_path="spec/reqs.md", line=42),
                ],
            )
        )
        sarif = _parse_sarif(report)

        loc = sarif["runs"][0]["results"][0]["locations"][0]["physicalLocation"]
        assert loc["region"]["startLine"] == 42

    def test_REQ_d00085_J_no_line_omits_region(self) -> None:
        report = HealthReport()
        report.add(
            _make_check(
                name="c1",
                passed=False,
                message="bad",
                findings=[
                    HealthFinding(message="issue", file_path="spec/reqs.md"),
                ],
            )
        )
        sarif = _parse_sarif(report)

        loc = sarif["runs"][0]["results"][0]["locations"][0]["physicalLocation"]
        assert "region" not in loc


# ---------------------------------------------------------------------------
# 7. Passing checks omitted
# ---------------------------------------------------------------------------


class TestREQd00085JPassingChecksOmitted:
    """Validates REQ-d00085-J: passing checks excluded from output."""

    def test_REQ_d00085_J_passing_check_not_in_rules(self) -> None:
        report = HealthReport()
        report.add(_make_check(name="good_check", passed=True, message="ok"))
        report.add(
            _make_check(
                name="bad_check",
                passed=False,
                message="fail",
                findings=[HealthFinding(message="f")],
            )
        )
        sarif = _parse_sarif(report)

        rules = sarif["runs"][0]["tool"]["driver"]["rules"]
        rule_ids = {r["id"] for r in rules}
        assert "good_check" not in rule_ids
        assert "bad_check" in rule_ids

    def test_REQ_d00085_J_passing_check_not_in_results(self) -> None:
        report = HealthReport()
        report.add(_make_check(name="good_check", passed=True, message="ok"))
        report.add(
            _make_check(
                name="bad_check",
                passed=False,
                message="fail",
                findings=[HealthFinding(message="f")],
            )
        )
        sarif = _parse_sarif(report)

        results = sarif["runs"][0]["results"]
        rule_ids = {r.get("ruleId") for r in results}
        assert "good_check" not in rule_ids


# ---------------------------------------------------------------------------
# 8. _format_report dispatches to SARIF
# ---------------------------------------------------------------------------


class TestREQd00085JFormatDispatch:
    """Validates REQ-d00085-J: format dispatch integration."""

    def test_REQ_d00085_J_format_report_sarif_dispatch(self) -> None:
        report = HealthReport()
        report.add(
            _make_check(
                name="c1",
                passed=False,
                message="bad",
                findings=[HealthFinding(message="f")],
            )
        )
        args = _make_args(fmt="sarif")
        raw = _format_report(report, args)
        sarif = json.loads(raw)

        assert sarif["version"] == "2.1.0"
        assert sarif["$schema"] == SARIF_SCHEMA


# ---------------------------------------------------------------------------
# 9. All passing produces empty results
# ---------------------------------------------------------------------------


class TestREQd00085JAllPassing:
    """Validates REQ-d00085-J: all-passing report."""

    def test_REQ_d00085_J_all_passing_empty_results(self) -> None:
        report = HealthReport()
        report.add(_make_check(name="ok1", passed=True, message="fine"))
        report.add(_make_check(name="ok2", passed=True, message="also fine"))
        sarif = _parse_sarif(report)

        assert sarif["runs"][0]["results"] == []
        assert sarif["runs"][0]["tool"]["driver"]["rules"] == []


# ---------------------------------------------------------------------------
# 10. run.properties contains coverage stats
# ---------------------------------------------------------------------------


class TestREQd00085JRunProperties:
    """Validates REQ-d00085-J: coverage stats in run.properties."""

    def test_REQ_d00085_J_run_properties_has_coverage_stats(self) -> None:
        report = HealthReport()
        report.add(_make_check(name="ok", passed=True, message="ok"))
        report.add(
            _make_check(
                name="fail",
                passed=False,
                message="bad",
                findings=[HealthFinding(message="f")],
            )
        )
        report.add(
            _make_check(
                name="warn",
                passed=False,
                message="meh",
                severity="warning",
                findings=[HealthFinding(message="w")],
            )
        )
        sarif = _parse_sarif(report)

        props = sarif["runs"][0]["properties"]
        assert props["passed"] == 1
        assert props["failed"] == 1
        assert props["warnings"] == 1


# ---------------------------------------------------------------------------
# 11. ruleIndex links results to rules
# ---------------------------------------------------------------------------


class TestREQd00085JRuleIndex:
    """Validates REQ-d00085-J: ruleIndex correspondence."""

    def test_REQ_d00085_J_rule_index_matches_rules_array(self) -> None:
        report = HealthReport()
        report.add(
            _make_check(
                name="alpha",
                passed=False,
                message="a",
                findings=[HealthFinding(message="a1")],
            )
        )
        report.add(
            _make_check(
                name="beta",
                passed=False,
                message="b",
                findings=[
                    HealthFinding(message="b1"),
                    HealthFinding(message="b2"),
                ],
            )
        )
        sarif = _parse_sarif(report)

        rules = sarif["runs"][0]["tool"]["driver"]["rules"]
        results = sarif["runs"][0]["results"]

        for result in results:
            rule_id = result["ruleId"]
            rule_index = result["ruleIndex"]
            assert rules[rule_index]["id"] == rule_id
