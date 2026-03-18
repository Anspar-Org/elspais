# Verifies: REQ-d00085
"""Tests for JUnit XML rendering of health reports.

Validates REQ-d00085-H: The ``--format junit`` option SHALL render health
checks as JUnit XML, mapping categories to ``<testsuite>`` elements, checks
to ``<testcase>`` elements, failures to ``<failure>`` elements, warnings to
``<system-err>``, and info to ``<system-out>``.
"""

from __future__ import annotations

import argparse
import xml.etree.ElementTree as ET

from elspais.commands.health import HealthCheck, HealthReport, _format_report, _render_junit

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_check(
    name: str = "check_foo",
    passed: bool = True,
    message: str = "ok",
    category: str = "config",
    severity: str = "error",
    details: dict | None = None,
) -> HealthCheck:
    return HealthCheck(
        name=name,
        passed=passed,
        message=message,
        category=category,
        severity=severity,
        details=details or {},
    )


def _make_args(fmt: str = "junit") -> argparse.Namespace:
    return argparse.Namespace(format=fmt, lenient=False, quiet=False, verbose=False)


def _parse_xml(xml_str: str) -> ET.Element:
    return ET.fromstring(xml_str)


# ---------------------------------------------------------------------------
# 1. Valid XML with <testsuites> root
# ---------------------------------------------------------------------------


class TestRenderJunit:
    """Validates REQ-d00085-H: JUnit XML rendering."""

    def test_REQ_d00085_H_produces_valid_xml_with_testsuites_root(self) -> None:
        """_render_junit must return valid XML with a <testsuites> root element."""
        report = HealthReport()
        report.add(_make_check())

        xml_str = _render_junit(report)
        root = _parse_xml(xml_str)

        assert root.tag == "testsuites"

    # -------------------------------------------------------------------
    # 2. Category -> <testsuite>
    # -------------------------------------------------------------------

    def test_REQ_d00085_H_category_maps_to_testsuite(self) -> None:
        """Each distinct category must produce a <testsuite> with matching name."""
        report = HealthReport()
        report.add(_make_check(name="c1", category="config"))
        report.add(_make_check(name="c2", category="spec"))
        report.add(_make_check(name="c3", category="code"))

        root = _parse_xml(_render_junit(report))

        suite_names = sorted(ts.get("name") for ts in root.findall("testsuite"))
        assert suite_names == ["code", "config", "spec"]

    # -------------------------------------------------------------------
    # 3. Check -> <testcase> with name and classname
    # -------------------------------------------------------------------

    def test_REQ_d00085_H_check_maps_to_testcase(self) -> None:
        """Each check must become a <testcase> with correct name and classname."""
        report = HealthReport()
        report.add(_make_check(name="check_toml_syntax", category="config"))

        root = _parse_xml(_render_junit(report))
        tc = root.find(".//testcase")

        assert tc is not None
        assert tc.get("name") == "check_toml_syntax"
        assert tc.get("classname") == "elspais.health.config"

    # -------------------------------------------------------------------
    # 4. Passing check -> empty <testcase>
    # -------------------------------------------------------------------

    def test_REQ_d00085_H_passing_check_has_no_failure(self) -> None:
        """A passing check must produce a <testcase> with no child elements."""
        report = HealthReport()
        report.add(_make_check(passed=True))

        root = _parse_xml(_render_junit(report))
        tc = root.find(".//testcase")

        assert tc is not None
        assert tc.find("failure") is None
        assert tc.find("error") is None
        assert tc.find("system-err") is None

    # -------------------------------------------------------------------
    # 5. Failed error -> <failure>
    # -------------------------------------------------------------------

    def test_REQ_d00085_H_failed_error_produces_failure_element(self) -> None:
        """A failed check with severity=error must produce a <failure> child."""
        report = HealthReport()
        report.add(
            _make_check(
                name="check_broken",
                passed=False,
                message="3 broken references",
                severity="error",
                details={"broken": ["REQ-a00001", "REQ-a00002", "REQ-a00003"]},
            )
        )

        root = _parse_xml(_render_junit(report))
        tc = root.find(".//testcase")
        failure = tc.find("failure")

        assert failure is not None
        assert "3 broken references" in (failure.get("message") or failure.text or "")

    # -------------------------------------------------------------------
    # 6. Failed warning -> <system-err> with WARNING prefix
    # -------------------------------------------------------------------

    def test_REQ_d00085_H_failed_warning_produces_system_err(self) -> None:
        """A failed check with severity=warning must produce <system-err>
        containing a WARNING prefix."""
        report = HealthReport()
        report.add(
            _make_check(
                name="check_coverage",
                passed=False,
                message="low coverage",
                severity="warning",
            )
        )

        root = _parse_xml(_render_junit(report))
        tc = root.find(".//testcase")
        sys_err = tc.find("system-err")

        assert sys_err is not None
        assert sys_err.text is not None
        assert sys_err.text.startswith("WARNING")

    # -------------------------------------------------------------------
    # 7. Info -> <system-out>
    # -------------------------------------------------------------------

    def test_REQ_d00085_H_info_check_produces_system_out(self) -> None:
        """A check with severity=info must produce a <system-out> element."""
        report = HealthReport()
        report.add(
            _make_check(
                name="check_version",
                passed=True,
                message="version 1.2.3",
                severity="info",
            )
        )

        root = _parse_xml(_render_junit(report))
        tc = root.find(".//testcase")
        sys_out = tc.find("system-out")

        assert sys_out is not None
        assert "version 1.2.3" in (sys_out.text or "")

    # -------------------------------------------------------------------
    # 8. _format_report dispatches to junit
    # -------------------------------------------------------------------

    def test_REQ_d00085_H_format_report_dispatches_junit(self) -> None:
        """_format_report with format='junit' must produce JUnit XML."""
        report = HealthReport()
        report.add(_make_check())

        args = _make_args(fmt="junit")
        output = _format_report(report, args)

        root = _parse_xml(output)
        assert root.tag == "testsuites"

    # -------------------------------------------------------------------
    # 9. Testsuite counts are correct
    # -------------------------------------------------------------------

    def test_REQ_d00085_H_testsuite_counts(self) -> None:
        """Each <testsuite> must have correct tests/failures/errors counts."""
        report = HealthReport()
        report.add(_make_check(name="c1", category="spec", passed=True))
        report.add(_make_check(name="c2", category="spec", passed=False, severity="error"))
        report.add(_make_check(name="c3", category="spec", passed=False, severity="warning"))

        root = _parse_xml(_render_junit(report))
        suite = root.find("testsuite[@name='spec']")

        assert suite is not None
        assert suite.get("tests") == "3"
        assert suite.get("failures") == "1"
        assert suite.get("errors") == "0"

    # -------------------------------------------------------------------
    # 10. Empty report -> valid XML
    # -------------------------------------------------------------------

    def test_REQ_d00085_H_empty_report_produces_valid_xml(self) -> None:
        """An empty report must still produce valid XML with <testsuites>."""
        report = HealthReport()

        xml_str = _render_junit(report)
        root = _parse_xml(xml_str)

        assert root.tag == "testsuites"
        assert len(root.findall("testsuite")) == 0
