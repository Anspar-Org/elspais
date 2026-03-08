# Validates REQ-d00085-A, REQ-d00085-B, REQ-d00085-C, REQ-d00085-D,
# Validates REQ-d00085-E, REQ-d00085-F, REQ-d00085-G
"""Tests for elspais composable report system.

Validates that report.run() orchestrates multiple sections, applies shared
flags globally, computes worst-of-all exit codes, validates format support,
and behaves identically to standalone for single sections.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from elspais.commands import report
from elspais.commands.report import (
    COMPOSABLE_SECTIONS,
    FORMAT_SUPPORT,
    parse_shared_args,
    run,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_spec_dir(tmp_path: Path) -> Path:
    """Create a minimal spec directory with one requirement."""
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()

    req_file = spec_dir / "requirements.md"
    req_file.write_text(
        """# REQ-p00001: Test Requirement

**Level**: PRD | **Status**: Active

**Purpose:** A test requirement for report tests.

## Assertions

A. The system SHALL do something.

*End* *Test Requirement* | **Hash**: abcd1234
"""
    )

    config_file = tmp_path / ".elspais.toml"
    config_file.write_text('[directories]\nspec = ["spec"]\n')
    return spec_dir


def _mock_render_section(name, graph, config, args):
    """A deterministic mock for _render_section."""
    if name == "health":
        return "=== Health Report ===\nAll checks passed.", 0
    elif name == "summary":
        return "=== Coverage Report ===\nPRD: 100%", 0
    elif name == "trace":
        return "=== Trace Matrix ===\nREQ-p00001", 0
    elif name == "changed":
        return "=== Changed ===\nNo changes.", 0
    return f"Error: Unknown section '{name}'", 1


def _mock_render_section_with_warning(name, graph, config, args):
    """Mock that returns exit=1 for health (warnings) and 0 for others."""
    if name == "health":
        return "=== Health Report ===\n1 warning found.", 1
    return _mock_render_section(name, graph, config, args)


def _patch_graph_build():
    """Return a context-manager stack patching the lazy graph/config imports."""
    return [
        patch("elspais.graph.factory.build_graph", return_value=MagicMock()),
        patch("elspais.config.get_config", return_value={}),
        patch("elspais.config.ConfigLoader.from_dict", return_value=MagicMock()),
    ]


# ===========================================================================
# Tests: Multiple sections concatenated in order (REQ-d00085-A)
# ===========================================================================


class TestMultipleSectionsConcatenated:
    """Validates REQ-d00085-A: Multiple sections concatenated in order."""

    def test_REQ_d00085_A_multiple_sections_concatenated(self, capsys):
        """Two sections produce output containing both in order."""
        with patch.object(report, "_render_section", side_effect=_mock_render_section):
            for p in _patch_graph_build():
                p.start()
            try:
                run(["health", "summary"], ["--format", "text"])
            finally:
                patch.stopall()

        captured = capsys.readouterr()
        health_pos = captured.out.find("Health Report")
        coverage_pos = captured.out.find("Coverage Report")
        assert health_pos != -1, "Health output missing"
        assert coverage_pos != -1, "Coverage output missing"
        assert health_pos < coverage_pos, "Health should appear before coverage"

    def test_REQ_d00085_A_three_sections_in_order(self, capsys):
        """Three sections are concatenated in the order specified."""
        with patch.object(report, "_render_section", side_effect=_mock_render_section):
            for p in _patch_graph_build():
                p.start()
            try:
                run(["trace", "health", "summary"], ["--format", "text"])
            finally:
                patch.stopall()

        captured = capsys.readouterr()
        trace_pos = captured.out.find("Trace Matrix")
        health_pos = captured.out.find("Health Report")
        coverage_pos = captured.out.find("Coverage Report")
        assert trace_pos < health_pos < coverage_pos

    def test_REQ_d00085_A_sections_separated_by_blank_lines(self, capsys):
        """Sections are joined with double newlines."""
        with patch.object(report, "_render_section", side_effect=_mock_render_section):
            for p in _patch_graph_build():
                p.start()
            try:
                run(["health", "summary"], ["--format", "text"])
            finally:
                patch.stopall()

        captured = capsys.readouterr()
        assert "\n\n" in captured.out


# ===========================================================================
# Tests: Shared flags apply globally (REQ-d00085-B)
# ===========================================================================


class TestSharedFlagsApplyGlobally:
    """Validates REQ-d00085-B: Shared flags (--format, -q, --lenient) apply globally."""

    def test_REQ_d00085_B_parse_shared_args_format(self):
        """--format is parsed from argv."""
        args = parse_shared_args(["--format", "markdown"])
        assert args.format == "markdown"

    def test_REQ_d00085_B_parse_shared_args_quiet(self):
        """-q flag is parsed from argv."""
        args = parse_shared_args(["-q"])
        assert args.quiet is True

    def test_REQ_d00085_B_parse_shared_args_lenient(self):
        """--lenient flag is parsed from argv."""
        args = parse_shared_args(["--lenient"])
        assert args.lenient is True

    def test_REQ_d00085_B_parse_shared_args_defaults(self):
        """Default values for shared args."""
        args = parse_shared_args([])
        assert args.format == "text"
        assert args.quiet is False
        assert args.lenient is False

    def test_REQ_d00085_B_format_passed_to_all_sections(self):
        """--format flag is passed to each section via the shared args namespace."""
        mock_rs = MagicMock(return_value=("output", 0))
        with patch.object(report, "_render_section", mock_rs):
            for p in _patch_graph_build():
                p.start()
            try:
                run(["health", "summary"], ["--format", "markdown"])
            finally:
                patch.stopall()

        # Both calls should receive the same args object with format=markdown
        assert mock_rs.call_count == 2
        for call in mock_rs.call_args_list:
            args = call[0][3]  # 4th positional arg is args namespace
            assert args.format == "markdown"


# ===========================================================================
# Tests: Exit code is worst-of-all-sections (REQ-d00085-C)
# ===========================================================================


class TestWorstExitCode:
    """Validates REQ-d00085-C: Exit code is worst-of-all-sections."""

    def test_REQ_d00085_C_all_pass_exit_zero(self):
        """All sections passing returns exit 0."""
        with patch.object(report, "_render_section", side_effect=_mock_render_section):
            for p in _patch_graph_build():
                p.start()
            try:
                exit_code = run(["health", "summary"], ["--format", "text"])
            finally:
                patch.stopall()

        assert exit_code == 0

    def test_REQ_d00085_C_one_failure_propagates(self):
        """If health returns 1, overall exit is 1 even if coverage returns 0."""
        with patch.object(report, "_render_section", side_effect=_mock_render_section_with_warning):
            for p in _patch_graph_build():
                p.start()
            try:
                exit_code = run(["health", "summary"], ["--format", "text"])
            finally:
                patch.stopall()

        assert exit_code == 1

    def test_REQ_d00085_C_worst_code_wins(self):
        """The worst exit code across sections is returned."""
        mock_rs = MagicMock(side_effect=[("ok", 0), ("fail", 2)])
        with patch.object(report, "_render_section", mock_rs):
            for p in _patch_graph_build():
                p.start()
            try:
                exit_code = run(["health", "summary"], ["--format", "text"])
            finally:
                patch.stopall()

        assert exit_code == 2


# ===========================================================================
# Tests: Single section behaves identically to standalone (REQ-d00085-D)
# ===========================================================================


class TestSingleSectionIdentical:
    """Validates REQ-d00085-D: Single section behaves identically to standalone."""

    def test_REQ_d00085_D_single_section_returns_its_output(self, capsys):
        """Single section output is printed without extra wrapping."""
        with patch.object(report, "_render_section", side_effect=_mock_render_section):
            for p in _patch_graph_build():
                p.start()
            try:
                exit_code = run(["summary"], ["--format", "text"])
            finally:
                patch.stopall()

        captured = capsys.readouterr()
        assert "Coverage Report" in captured.out
        assert exit_code == 0

    def test_REQ_d00085_D_single_section_exit_code_passthrough(self):
        """Single section exit code is passed through directly."""
        mock_rs = MagicMock(return_value=("output", 1))
        with patch.object(report, "_render_section", mock_rs):
            for p in _patch_graph_build():
                p.start()
            try:
                exit_code = run(["health"], ["--format", "text"])
            finally:
                patch.stopall()

        assert exit_code == 1


# ===========================================================================
# Tests: Format support validation (REQ-d00085-E)
# ===========================================================================


class TestFormatSupportValidation:
    """Validates REQ-d00085-E: Format support validation (invalid format -> error)."""

    def test_REQ_d00085_E_format_support_dict_exists(self):
        """FORMAT_SUPPORT defines valid formats for each composable section."""
        for section in COMPOSABLE_SECTIONS:
            assert section in FORMAT_SUPPORT
            assert isinstance(FORMAT_SUPPORT[section], set)

    def test_REQ_d00085_E_invalid_format_returns_error(self, capsys):
        """Requesting csv for changed section returns exit 1 with error message."""
        exit_code = run(["changed"], ["--format", "csv"])

        captured = capsys.readouterr()
        assert exit_code == 1
        assert "not supported" in captured.err
        assert "changed" in captured.err

    def test_REQ_d00085_E_invalid_format_for_one_section_in_multi(self, capsys):
        """If format is invalid for any section, error is returned early."""
        # csv is not supported for "changed"
        exit_code = run(["summary", "changed"], ["--format", "csv"])

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "not supported" in captured.err

    def test_REQ_d00085_E_valid_format_proceeds(self):
        """A valid format for all requested sections proceeds normally."""
        with patch.object(report, "_render_section", side_effect=_mock_render_section):
            for p in _patch_graph_build():
                p.start()
            try:
                exit_code = run(["health", "summary"], ["--format", "text"])
            finally:
                patch.stopall()

        assert exit_code == 0

    def test_REQ_d00085_E_health_supports_text_markdown_json_junit(self):
        """Health section supports text, markdown, json, junit."""
        assert FORMAT_SUPPORT["health"] == {"text", "markdown", "json", "junit"}

    def test_REQ_d00085_E_changed_supports_text_json_only(self):
        """Changed section supports only text and json."""
        assert FORMAT_SUPPORT["changed"] == {"text", "json"}


# ===========================================================================
# Tests: Quiet mode (REQ-d00085-F)
# ===========================================================================


class TestQuietMode:
    """Validates REQ-d00085-F: -q/--quiet suppresses output to summary."""

    def test_REQ_d00085_F_quiet_with_output_file_no_stderr(self, capsys, tmp_path):
        """With -q and -o, no 'Generated:' message appears on stderr."""
        output_file = tmp_path / "report.txt"
        with patch.object(report, "_render_section", side_effect=_mock_render_section):
            for p in _patch_graph_build():
                p.start()
            try:
                exit_code = run(
                    ["health"],
                    ["--format", "text", "-q", "-o", str(output_file)],
                )
            finally:
                patch.stopall()

        captured = capsys.readouterr()
        assert "Generated:" not in captured.err
        assert exit_code == 0

    def test_REQ_d00085_F_without_quiet_output_file_shows_generated(self, capsys, tmp_path):
        """Without -q, -o shows 'Generated:' on stderr."""
        output_file = tmp_path / "report.txt"
        with patch.object(report, "_render_section", side_effect=_mock_render_section):
            for p in _patch_graph_build():
                p.start()
            try:
                run(
                    ["health"],
                    ["--format", "text", "-o", str(output_file)],
                )
            finally:
                patch.stopall()

        captured = capsys.readouterr()
        assert "Generated:" in captured.err


# ===========================================================================
# Tests: Lenient mode (REQ-d00085-G)
# ===========================================================================


class TestLenientMode:
    """Validates REQ-d00085-G: --lenient allows warnings to pass."""

    def test_REQ_d00085_G_without_lenient_warnings_fail(self):
        """Without --lenient, health warning exit code 1 propagates."""
        with patch.object(
            report,
            "_render_section",
            side_effect=_mock_render_section_with_warning,
        ):
            for p in _patch_graph_build():
                p.start()
            try:
                exit_code = run(["health", "summary"], ["--format", "text"])
            finally:
                patch.stopall()

        assert exit_code == 1

    def test_REQ_d00085_G_lenient_flag_parsed(self):
        """--lenient flag is available in the args namespace passed to sections."""
        mock_rs = MagicMock(return_value=("output", 0))
        with patch.object(report, "_render_section", mock_rs):
            for p in _patch_graph_build():
                p.start()
            try:
                run(["health"], ["--format", "text", "--lenient"])
            finally:
                patch.stopall()

        args = mock_rs.call_args[0][3]
        assert args.lenient is True


# ===========================================================================
# Tests: Output to file (--output)
# ===========================================================================


class TestOutputFile:
    """Validates REQ-d00085-B: --output writes combined report to file."""

    def test_REQ_d00085_B_output_file_written(self, tmp_path):
        """--output writes the combined output to a file."""
        output_file = tmp_path / "report.txt"
        with patch.object(report, "_render_section", side_effect=_mock_render_section):
            for p in _patch_graph_build():
                p.start()
            try:
                exit_code = run(
                    ["health", "summary"],
                    ["--format", "text", "-o", str(output_file)],
                )
            finally:
                patch.stopall()

        assert exit_code == 0
        assert output_file.exists()
        content = output_file.read_text()
        assert "Health Report" in content
        assert "Coverage Report" in content


# ===========================================================================
# Tests: CLI dispatch integration (REQ-d00085-A)
# ===========================================================================


class TestCLIDispatch:
    """Validates REQ-d00085-A: cli.main() dispatches multi-section to report.run."""

    def test_REQ_d00085_A_cli_detects_multiple_sections(self):
        """cli.main() with multiple composable names dispatches to report.run."""
        with patch("elspais.commands.report.run", return_value=0) as mock_run:
            with patch("elspais.config.find_git_root", return_value=None):
                with patch("elspais.config.find_canonical_root", return_value=None):
                    from elspais.cli import main

                    exit_code = main(["health", "summary", "--format", "text"])

        assert exit_code == 0
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[0][0] == ["health", "summary"]
        assert "--format" in call_args[0][1]
        assert "text" in call_args[0][1]

    def test_REQ_d00085_D_cli_single_section_uses_normal_argparse(self):
        """cli.main() with single composable name uses normal argparse dispatch."""
        with patch("elspais.commands.report.run") as mock_report_run:
            from elspais.cli import main

            # Single section should NOT go through report.run
            try:
                main(["summary"])
            except SystemExit:
                pass  # coverage may exit, that's fine

            # report.run should NOT have been called for single section
            mock_report_run.assert_not_called()


# ===========================================================================
# Tests: COMPOSABLE_SECTIONS constant
# ===========================================================================


class TestComposableSections:
    """Validates REQ-d00085-A: The set of composable sections."""

    def test_REQ_d00085_A_composable_sections_tuple(self):
        """COMPOSABLE_SECTIONS contains the expected section names."""
        assert COMPOSABLE_SECTIONS == ("health", "summary", "trace", "changed")

    def test_REQ_d00085_A_all_sections_in_format_support(self):
        """Every composable section has a FORMAT_SUPPORT entry."""
        for section in COMPOSABLE_SECTIONS:
            assert section in FORMAT_SUPPORT


# ===========================================================================
# Tests: Integration with real spec dir
# ===========================================================================


class TestIntegrationWithSpecDir:
    """Validates REQ-d00085-A+D: Integration test with real spec directory."""

    def test_REQ_d00085_D_single_coverage_with_spec_dir(self, tmp_path, monkeypatch):
        """Single coverage section with real spec dir produces output."""
        spec_dir = _make_spec_dir(tmp_path)
        monkeypatch.chdir(tmp_path)

        exit_code = run(
            ["summary"],
            ["--format", "text", "--spec-dir", str(spec_dir)],
        )

        assert exit_code == 0

    def test_REQ_d00085_A_multi_section_with_spec_dir(self, tmp_path, monkeypatch):
        """Multiple sections with real spec dir produces combined output."""
        spec_dir = _make_spec_dir(tmp_path)
        monkeypatch.chdir(tmp_path)

        output_file = tmp_path / "combined.txt"
        run(
            ["summary", "health"],
            [
                "--format",
                "text",
                "--spec-dir",
                str(spec_dir),
                "-o",
                str(output_file),
            ],
        )

        assert output_file.exists()
        content = output_file.read_text()
        # Both sections should appear
        assert "Coverage Summary" in content or "REQ-p00001" in content
