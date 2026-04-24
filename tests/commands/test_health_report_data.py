# Verifies: REQ-d00085
"""Tests for _ReportData intermediate representation and _build_report_data builder.

Validates that the builder correctly extracts stat computation logic:
category icon selection, pass/fail/skip counting, check icon selection,
summary line, and hint string.
"""

from __future__ import annotations

from elspais.commands.health import (
    _FOLLOWUP_COMMANDS,
    HealthCheck,
    HealthReport,
    _build_hint,
    _build_report_data,
    _render_markdown,
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


def _checks_cli_flags() -> set[str]:
    """Flags accepted by `elspais checks`, derived from ChecksArgs metadata."""
    import dataclasses
    import typing

    from elspais.commands.args import ChecksArgs

    flags: set[str] = {"-h", "--help"}
    hints = typing.get_type_hints(ChecksArgs, include_extras=True)
    for field in dataclasses.fields(ChecksArgs):
        t = hints[field.name]
        arg_name = field.name.replace("_", "-")
        aliases: tuple[str, ...] = ()
        if hasattr(t, "__metadata__"):
            for meta in typing.get_args(t)[1:]:
                if hasattr(meta, "name") and meta.name:
                    arg_name = meta.name
                if hasattr(meta, "aliases") and meta.aliases:
                    aliases = meta.aliases
        flags.add(f"--{arg_name}")
        if field.type is bool or field.type == "bool":
            flags.add(f"--no-{arg_name}")
        flags.update(aliases)
    return flags


class TestFollowupCommandsAreValid:
    """Regression: hints in _FOLLOWUP_COMMANDS must use real CLI flags.

    Commit c04d237 added `--terms` to hints for terms.* checks but never
    added the corresponding flag to ChecksArgs, so every hint referencing
    `--terms` produced an "Unrecognized options" error when users ran it.
    """

    def test_followup_checks_flags_are_real(self) -> None:
        import shlex

        valid = _checks_cli_flags()
        for name, cmd in _FOLLOWUP_COMMANDS.items():
            tokens = shlex.split(cmd)
            if tokens[:2] != ["elspais", "checks"]:
                continue
            for tok in tokens[2:]:
                if tok.startswith("-"):
                    assert tok in valid, (
                        f"_FOLLOWUP_COMMANDS[{name!r}] uses unknown flag {tok!r} "
                        f"in {cmd!r}; known flags: {sorted(valid)}"
                    )

    def test_build_hint_uses_real_flags(self) -> None:
        """_build_hint output for each single-category failure is a valid CLI invocation."""
        import shlex

        valid = _checks_cli_flags()
        for category in ("spec", "code", "tests", "uat", "terms", "config"):
            report = HealthReport()
            report.add(
                HealthCheck(
                    name=f"{category}.x",
                    passed=False,
                    message="fail",
                    category=category,
                    severity="error",
                )
            )
            hint = _build_hint(report, already_verbose=False)
            assert hint is not None
            # Extract each `elspais ...` invocation from the hint text and
            # verify every flag on `elspais checks` lines is real.
            for line in hint.split("\n"):
                # Pull the quoted command string(s) out of the hint line
                for quoted in shlex.split(line, posix=True):
                    if not quoted.startswith("elspais "):
                        continue
                    tokens = shlex.split(quoted)
                    if tokens[:2] != ["elspais", "checks"] and tokens[:3] != [
                        "elspais",
                        "-v",
                        "checks",
                    ]:
                        continue
                    for tok in tokens:
                        if tok.startswith("--"):
                            assert tok in valid, (
                                f"_build_hint for category {category!r} uses "
                                f"unknown flag {tok!r} in {quoted!r}"
                            )


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

    def test_REQ_d00085_followup_shown_when_unhealthy(self) -> None:
        """Follow-up section appears when a failing check has a known follow-up command."""
        from elspais.commands.health import _render_text

        report = HealthReport()
        report.add(
            HealthCheck(
                name="spec.hash_integrity",
                passed=False,
                message="2 stale hashes",
                category="spec",
                severity="error",
            )
        )
        data = _build_report_data(report, verbose=False)
        output = _render_text(data)
        assert "Follow-up:" in output
        assert "elspais fix" in output

    def test_REQ_d00085_info_check_tilde(self) -> None:
        """Info-severity checks render with tilde icon."""
        from elspais.commands.health import _render_text

        report = _make_mixed_report()
        data = _build_report_data(report)
        output = _render_text(data)
        assert "  ~ code.coverage: info only" in output

    def test_REQ_d00085_hint_rendered_when_unhealthy(self) -> None:
        """Hint line appears in text output when report has failures/warnings."""
        from elspais.commands.health import _render_text

        report = _make_mixed_report()
        data = _build_report_data(report, verbose=False)
        assert data.hint is not None
        output = _render_text(data)
        assert data.hint in output

    def test_REQ_d00085_hint_rendered_for_warnings_only(self) -> None:
        """Hint is rendered when report has warnings but no errors (regression guard)."""
        from elspais.commands.health import _render_text

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
        data = _build_report_data(report, verbose=False)
        output = _render_text(data)
        assert "Run 'elspais -v checks" in output

    def test_REQ_d00085_hint_absent_when_healthy(self) -> None:
        """Hint line is not rendered when report is healthy."""
        from elspais.commands.health import _render_text

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
        data = _build_report_data(report)
        output = _render_text(data)
        assert "Run 'elspais" not in output


class TestRenderMarkdown:
    """Tests for _render_markdown checklist renderer."""

    def test_no_h1_title(self) -> None:
        report = _make_mixed_report()
        data = _build_report_data(report)
        output = _render_markdown(data)
        assert not output.startswith("# ")
        assert "# Health Report" not in output

    def test_category_header_h2_with_icon(self) -> None:
        report = _make_mixed_report()
        data = _build_report_data(report)
        output = _render_markdown(data)
        assert "## \u2717 SPEC (1 passed, 1 failed)" in output

    def test_passing_check_uses_checked_box(self) -> None:
        report = _make_mixed_report()
        data = _build_report_data(report)
        output = _render_markdown(data)
        assert "- [x] spec.format: all valid" in output

    def test_failing_check_uses_unchecked_box(self) -> None:
        report = _make_mixed_report()
        data = _build_report_data(report)
        output = _render_markdown(data)
        assert "- [ ] spec.refs: 2 broken references" in output

    def test_info_check_uses_tilde_prefix(self) -> None:
        report = _make_mixed_report()
        data = _build_report_data(report)
        output = _render_markdown(data)
        assert "- [ ] ~ code.coverage: info only" in output

    def test_no_tables(self) -> None:
        report = _make_mixed_report()
        data = _build_report_data(report)
        output = _render_markdown(data)
        assert "| Check" not in output
        assert "|---" not in output

    def test_no_details_blocks(self) -> None:
        from elspais.commands.health import HealthFinding

        report = HealthReport()
        report.add(
            HealthCheck(
                name="ok",
                passed=True,
                message="good",
                category="spec",
                findings=[HealthFinding(message="detail")],
            )
        )
        data = _build_report_data(report)
        output = _render_markdown(data)
        assert "<details>" not in output

    def test_summary_line(self) -> None:
        report = _make_mixed_report()
        data = _build_report_data(report)
        output = _render_markdown(data)
        assert "UNHEALTHY" in output

    def test_hint_rendered_when_unhealthy(self) -> None:
        """Hint line appears in markdown output when report has failures/warnings."""
        report = _make_mixed_report()
        data = _build_report_data(report, verbose=False)
        assert data.hint is not None
        output = _render_markdown(data)
        assert data.hint in output

    def test_hint_absent_when_healthy(self) -> None:
        """Hint line is not rendered when report is healthy."""
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
        data = _build_report_data(report)
        output = _render_markdown(data)
        assert "Run 'elspais" not in output

    def test_separator_between_categories(self) -> None:
        report = _make_mixed_report()
        data = _build_report_data(report)
        output = _render_markdown(data)
        assert "---" in output

    def test_same_stats_as_text(self) -> None:
        from elspais.commands.health import _render_text

        report = _make_mixed_report()
        data = _build_report_data(report)
        text = _render_text(data)
        md = _render_markdown(data)
        assert "1 passed, 1 failed" in text
        assert "1 passed, 1 failed" in md
