# Verifies: REQ-d00085
"""Tests for _ReportData intermediate representation and _build_report_data builder.

Validates that the builder correctly extracts stat computation logic:
category icon selection, pass/fail/skip counting, check icon selection,
summary line, and hint string.
"""

from __future__ import annotations

from elspais.commands.health import (
    HealthCheck,
    HealthReport,
    _build_hint,
    _build_report_data,
)


def _make_mixed_report() -> HealthReport:
    """Build a report with config(pass) + spec(pass,fail) + code(info)."""
    report = HealthReport()
    report.add(
        HealthCheck(
            name="config.toml",
            passed=True,
            message="valid",
            category="config",
            severity="error",
        )
    )
    report.add(
        HealthCheck(
            name="spec.format",
            passed=True,
            message="all valid",
            category="spec",
            severity="error",
        )
    )
    report.add(
        HealthCheck(
            name="spec.refs",
            passed=False,
            message="2 broken references",
            category="spec",
            severity="error",
        )
    )
    report.add(
        HealthCheck(
            name="code.coverage",
            passed=True,
            message="info only",
            category="code",
            severity="info",
        )
    )
    return report


class TestBuildReportData:
    """Tests for _build_report_data builder function."""

    def test_REQ_d00085_sections_only_for_nonempty_categories(self) -> None:
        """Only categories with checks get sections."""
        report = _make_mixed_report()
        rd = _build_report_data(report)
        names = [s.name for s in rd.sections]
        assert names == ["CONFIG", "SPEC", "CODE"]
        # "tests" and "uat" have no checks, should be absent
        assert "TESTS" not in names
        assert "UAT" not in names

    def test_REQ_d00085_info_checks_excluded_from_stats(self) -> None:
        """Info-severity checks are counted as skipped, not in pass/fail totals."""
        report = _make_mixed_report()
        rd = _build_report_data(report)
        code_section = [s for s in rd.sections if s.name == "CODE"][0]
        # code has 1 info check -> 0 passed, 0 failed, 1 skipped
        assert code_section.stats == "0 passed, 0 failed, 1 skipped"

    def test_REQ_d00085_check_icons_correct(self) -> None:
        """Check icons match severity and pass/fail status."""
        report = _make_mixed_report()
        rd = _build_report_data(report)
        spec_section = [s for s in rd.sections if s.name == "SPEC"][0]
        # spec.format passed -> checkmark, spec.refs failed error -> cross
        icons = {c.name: c.icon for c in spec_section.checks}
        assert icons["spec.format"] == "\u2713"
        assert icons["spec.refs"] == "\u2717"

    def test_REQ_d00085_info_check_gets_tilde(self) -> None:
        """Info-severity checks get tilde icon."""
        report = _make_mixed_report()
        rd = _build_report_data(report)
        code_section = [s for s in rd.sections if s.name == "CODE"][0]
        assert code_section.checks[0].icon == "~"

    def test_REQ_d00085_summary_line_unhealthy(self) -> None:
        """Summary line for unhealthy report includes error count."""
        report = _make_mixed_report()
        rd = _build_report_data(report)
        assert not rd.is_healthy
        assert "UNHEALTHY" in rd.summary_line
        assert "1 errors" in rd.summary_line or "1 error" in rd.summary_line

    def test_REQ_d00085_summary_line_healthy(self) -> None:
        """Summary line for healthy report says HEALTHY."""
        report = HealthReport()
        report.add(
            HealthCheck(
                name="config.toml",
                passed=True,
                message="ok",
                category="config",
                severity="error",
            )
        )
        rd = _build_report_data(report)
        assert rd.is_healthy
        assert "HEALTHY" in rd.summary_line

    def test_REQ_d00085_category_icon_all_pass(self) -> None:
        """Category with all checks passed gets checkmark icon."""
        report = _make_mixed_report()
        rd = _build_report_data(report)
        config_section = [s for s in rd.sections if s.name == "CONFIG"][0]
        assert config_section.icon == "\u2713"

    def test_REQ_d00085_category_icon_has_errors(self) -> None:
        """Category with error failures gets cross icon."""
        report = _make_mixed_report()
        rd = _build_report_data(report)
        spec_section = [s for s in rd.sections if s.name == "SPEC"][0]
        assert spec_section.icon == "\u2717"

    def test_REQ_d00085_category_icon_warnings_only(self) -> None:
        """Category with only warnings gets warning icon."""
        report = HealthReport()
        report.add(
            HealthCheck(
                name="spec.format",
                passed=True,
                message="ok",
                category="spec",
                severity="error",
            )
        )
        report.add(
            HealthCheck(
                name="spec.style",
                passed=False,
                message="style issues",
                category="spec",
                severity="warning",
            )
        )
        rd = _build_report_data(report)
        spec_section = [s for s in rd.sections if s.name == "SPEC"][0]
        assert spec_section.icon == "\u26a0"

    def test_REQ_d00085_hint_none_when_healthy(self) -> None:
        """Hint is None when report is healthy."""
        report = HealthReport()
        report.add(
            HealthCheck(
                name="config.toml",
                passed=True,
                message="ok",
                category="config",
                severity="error",
            )
        )
        rd = _build_report_data(report)
        assert rd.hint is None

    def test_REQ_d00085_hint_present_when_unhealthy(self) -> None:
        """Hint is present when report is unhealthy."""
        report = _make_mixed_report()
        rd = _build_report_data(report)
        assert rd.hint is not None
        assert "elspais" in rd.hint
        assert "checks" in rd.hint

    def test_REQ_d00085_warning_check_icon(self) -> None:
        """Warning-severity failed check gets warning icon."""
        report = HealthReport()
        report.add(
            HealthCheck(
                name="spec.style",
                passed=False,
                message="issues",
                category="spec",
                severity="warning",
            )
        )
        rd = _build_report_data(report)
        assert rd.sections[0].checks[0].icon == "\u26a0"


class TestBuildHint:
    """Tests for _build_hint function."""

    def test_REQ_d00085_hint_uses_checks_command(self) -> None:
        """Hint references 'elspais checks', not 'elspais health'."""
        report = _make_mixed_report()
        hint = _build_hint(report, already_verbose=False)
        assert hint is not None
        assert "elspais" in hint
        assert "checks" in hint
        # Should not reference 'elspais health' command (but health.json filename is fine)
        assert "elspais health" not in hint
        assert "'elspais -v health" not in hint

    def test_REQ_d00085_hint_verbose_omits_v_flag(self) -> None:
        """When already verbose, hint doesn't suggest -v."""
        report = _make_mixed_report()
        hint = _build_hint(report, already_verbose=True)
        assert hint is not None
        assert "-v checks" not in hint

    def test_REQ_d00085_hint_not_verbose_suggests_v(self) -> None:
        """When not verbose, hint suggests -v."""
        report = _make_mixed_report()
        hint = _build_hint(report, already_verbose=False)
        assert hint is not None
        assert "-v checks" in hint

    def test_REQ_d00085_hint_none_for_healthy(self) -> None:
        """Returns None for healthy report."""
        report = HealthReport()
        report.add(
            HealthCheck(
                name="config.toml",
                passed=True,
                message="ok",
                category="config",
                severity="error",
            )
        )
        hint = _build_hint(report, already_verbose=False)
        assert hint is None


class TestRenderText:
    """Tests for _render_text plain-text renderer."""

    def test_REQ_d00085_category_header_format(self) -> None:
        """Category header includes icon, name, and stats."""
        from elspais.commands.health import _render_text

        report = _make_mixed_report()
        data = _build_report_data(report)
        output = _render_text(data)
        assert "\u2717 SPEC (1 passed, 1 failed)" in output
        assert "-" * 40 in output

    def test_REQ_d00085_check_line_format(self) -> None:
        """Check lines are indented with icon, name, and message."""
        from elspais.commands.health import _render_text

        report = _make_mixed_report()
        data = _build_report_data(report)
        output = _render_text(data)
        assert "  \u2713 spec.format: all valid" in output
        assert "  \u2717 spec.refs: 2 broken references" in output

    def test_REQ_d00085_summary_block(self) -> None:
        """Summary block has separator and status."""
        from elspais.commands.health import _render_text

        report = _make_mixed_report()
        data = _build_report_data(report)
        output = _render_text(data)
        assert "=" * 40 in output
        assert "UNHEALTHY" in output

    def test_REQ_d00085_hint_shown_when_unhealthy(self) -> None:
        """Hint appears in output when report is unhealthy and not verbose."""
        from elspais.commands.health import _render_text

        report = _make_mixed_report()
        data = _build_report_data(report, verbose=False)
        output = _render_text(data)
        assert "elspais -v checks" in output

    def test_REQ_d00085_info_check_tilde(self) -> None:
        """Info-severity checks render with tilde icon."""
        from elspais.commands.health import _render_text

        report = _make_mixed_report()
        data = _build_report_data(report)
        output = _render_text(data)
        assert "  ~ code.coverage: info only" in output
