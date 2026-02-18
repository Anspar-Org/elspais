# Implements: REQ-p00080-A, REQ-p00080-F
"""Tests for the pdf CLI command registration and tool checks.

Validates REQ-p00080-A: The tool SHALL provide an elspais pdf CLI command.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from elspais.cli import create_parser
from elspais.commands.pdf_cmd import _check_tool


class TestPdfCommandRegistration:
    """Validates REQ-p00080-A: CLI command registration."""

    def test_REQ_p00080_A_pdf_command_registered(self):
        """pdf subcommand is recognized by the parser."""
        parser = create_parser()
        args = parser.parse_args(["pdf"])
        assert args.command == "pdf"

    def test_REQ_p00080_A_output_default(self):
        """--output defaults to spec-output.pdf."""
        parser = create_parser()
        args = parser.parse_args(["pdf"])
        assert args.output == Path("spec-output.pdf")

    def test_REQ_p00080_A_output_custom(self):
        """--output accepts a custom path."""
        parser = create_parser()
        args = parser.parse_args(["pdf", "--output", "my-doc.pdf"])
        assert args.output == Path("my-doc.pdf")

    def test_REQ_p00080_A_engine_default(self):
        """--engine defaults to xelatex."""
        parser = create_parser()
        args = parser.parse_args(["pdf"])
        assert args.engine == "xelatex"

    def test_REQ_p00080_A_engine_custom(self):
        """--engine accepts a custom engine."""
        parser = create_parser()
        args = parser.parse_args(["pdf", "--engine", "lualatex"])
        assert args.engine == "lualatex"

    def test_REQ_p00080_A_template_default(self):
        """--template defaults to None."""
        parser = create_parser()
        args = parser.parse_args(["pdf"])
        assert args.template is None

    def test_REQ_p00080_A_template_custom(self):
        """--template accepts a path."""
        parser = create_parser()
        args = parser.parse_args(["pdf", "--template", "custom.latex"])
        assert args.template == Path("custom.latex")

    def test_REQ_p00080_A_title_default(self):
        """--title defaults to None."""
        parser = create_parser()
        args = parser.parse_args(["pdf"])
        assert args.title is None

    def test_REQ_p00080_A_title_custom(self):
        """--title accepts a string."""
        parser = create_parser()
        args = parser.parse_args(["pdf", "--title", "My Specs"])
        assert args.title == "My Specs"


class TestToolAvailability:
    """Validates REQ-p00080-A: Tool availability checks."""

    def test_REQ_p00080_A_check_tool_found(self):
        """_check_tool returns a path for known commands."""
        result = _check_tool("python3")
        assert result is not None

    def test_REQ_p00080_A_check_tool_not_found(self):
        """_check_tool returns None for missing commands."""
        result = _check_tool("nonexistent_tool_xyz_12345")
        assert result is None

    def test_REQ_p00080_A_run_fails_without_pandoc(self):
        """run() returns 1 when pandoc is not found."""
        from elspais.commands.pdf_cmd import run

        parser = create_parser()
        args = parser.parse_args(["pdf"])
        with patch("elspais.commands.pdf_cmd._check_tool", return_value=None):
            rc = run(args)
        assert rc == 1

    def test_REQ_p00080_A_run_fails_without_engine(self):
        """run() returns 1 when engine is not found but pandoc is."""
        from elspais.commands.pdf_cmd import run

        parser = create_parser()
        args = parser.parse_args(["pdf"])

        def selective_check(name):
            if name == "pandoc":
                return "/usr/bin/pandoc"
            return None

        with patch("elspais.commands.pdf_cmd._check_tool", side_effect=selective_check):
            rc = run(args)
        assert rc == 1


class TestOverviewArgs:
    """Validates REQ-p00080-F: --overview and --max-depth CLI arguments."""

    def test_REQ_p00080_F_overview_flag_registered(self):
        """The --overview flag is available on the pdf parser."""
        parser = create_parser()
        args = parser.parse_args(["pdf", "--overview"])
        assert args.overview is True

    def test_REQ_p00080_F_overview_default_false(self):
        """The --overview flag defaults to False."""
        parser = create_parser()
        args = parser.parse_args(["pdf"])
        assert args.overview is False

    def test_REQ_p00080_F_max_depth_registered(self):
        """The --max-depth flag is available on the pdf parser."""
        parser = create_parser()
        args = parser.parse_args(["pdf", "--max-depth", "2"])
        assert args.max_depth == 2

    def test_REQ_p00080_F_max_depth_default_none(self):
        """The --max-depth flag defaults to None."""
        parser = create_parser()
        args = parser.parse_args(["pdf"])
        assert args.max_depth is None
