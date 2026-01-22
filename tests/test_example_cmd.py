"""
Tests for the example command.
"""

import argparse
import io
from pathlib import Path
from unittest.mock import patch


class TestExampleCommand:
    """Tests for the example command."""

    def test_example_default_output(self):
        """Test example command without arguments shows quick reference."""
        from elspais.commands.example_cmd import run

        args = argparse.Namespace(
            example_type=None,
            full=False,
            config=None,
        )

        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            result = run(args)

        assert result == 0
        output = mock_stdout.getvalue()
        assert "Requirement Format Quick Reference" in output

    def test_example_requirement_subcommand(self):
        """Test example requirement shows requirement templates."""
        from elspais.commands.example_cmd import run

        args = argparse.Namespace(
            example_type="requirement",
            full=False,
            config=None,
        )

        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            result = run(args)

        assert result == 0
        output = mock_stdout.getvalue()
        assert "# Requirement Templates" in output
        assert "PRD (Product Requirement)" in output
        assert "OPS (Operations Requirement)" in output
        assert "DEV (Development Requirement)" in output
        assert "REQ-p00001" in output
        assert "REQ-o00001" in output
        assert "REQ-d00001" in output

    def test_example_journey_subcommand(self):
        """Test example journey shows journey template."""
        from elspais.commands.example_cmd import run

        args = argparse.Namespace(
            example_type="journey",
            full=False,
            config=None,
        )

        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            result = run(args)

        assert result == 0
        output = mock_stdout.getvalue()
        assert "JNY-" in output
        assert "Actor" in output
        assert "Goal" in output
        assert "Steps" in output
        assert "Requirements" in output

    def test_example_assertion_subcommand(self):
        """Test example assertion shows assertion rules."""
        from elspais.commands.example_cmd import run

        args = argparse.Namespace(
            example_type="assertion",
            full=False,
            config=None,
        )

        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            result = run(args)

        assert result == 0
        output = mock_stdout.getvalue()
        assert "Assertion Format Rules" in output
        assert "SHALL" in output
        assert "Label Styles" in output
        assert "Placeholders" in output

    def test_example_ids_subcommand_no_config(self):
        """Test example ids with no config uses defaults."""
        from elspais.commands.example_cmd import run

        args = argparse.Namespace(
            example_type="ids",
            full=False,
            config=None,
        )

        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            result = run(args)

        assert result == 0
        output = mock_stdout.getvalue()
        assert "Requirement ID Patterns" in output
        assert "REQ-p00001" in output
        assert "REQ-o00001" in output
        assert "REQ-d00001" in output

    def test_example_ids_subcommand_with_config(self, tmp_path: Path):
        """Test example ids reads from config file."""
        from elspais.commands.example_cmd import run

        # Create a config file
        config_file = tmp_path / ".elspais.toml"
        config_file.write_text(
            """
[patterns]
prefix = "SPEC"
id_template = "{prefix}-{type}{id}"

[patterns.types]
prd = { id = "p", name = "Product", level = 1 }
ops = { id = "o", name = "Operations", level = 2 }
dev = { id = "d", name = "Development", level = 3 }
"""
        )

        args = argparse.Namespace(
            example_type="ids",
            full=False,
            config=config_file,
        )

        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            result = run(args)

        assert result == 0
        output = mock_stdout.getvalue()
        assert "SPEC" in output

    def test_example_full_no_spec_file(self, tmp_path: Path, monkeypatch):
        """Test --full flag when no spec file exists."""
        from elspais.commands.example_cmd import run

        monkeypatch.chdir(tmp_path)

        args = argparse.Namespace(
            example_type=None,
            full=True,
            config=None,
        )

        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            result = run(args)

        assert result == 1
        output = mock_stdout.getvalue()
        assert "No requirements specification found" in output

    def test_example_full_with_spec_file(self, tmp_path: Path, monkeypatch):
        """Test --full flag with requirements-spec.md."""
        from elspais.commands.example_cmd import run

        monkeypatch.chdir(tmp_path)

        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        spec_content = "# Requirements Specification\n\nThis is the full spec."
        (spec_dir / "requirements-spec.md").write_text(spec_content)

        args = argparse.Namespace(
            example_type=None,
            full=True,
            config=None,
        )

        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            result = run(args)

        assert result == 0
        output = mock_stdout.getvalue()
        assert "Requirements Specification" in output
        assert "This is the full spec" in output

    def test_example_full_with_alternate_filename(self, tmp_path: Path, monkeypatch):
        """Test --full flag with requirements-format.md (alternate name)."""
        from elspais.commands.example_cmd import run

        monkeypatch.chdir(tmp_path)

        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        spec_content = "# Format Guide\n\nAlternate file name."
        (spec_dir / "requirements-format.md").write_text(spec_content)

        args = argparse.Namespace(
            example_type=None,
            full=True,
            config=None,
        )

        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            result = run(args)

        assert result == 0
        output = mock_stdout.getvalue()
        assert "Format Guide" in output
        assert "Alternate file name" in output


class TestExampleTemplateContent:
    """Tests for template content correctness."""

    def test_requirement_template_has_assertions_section(self):
        """Test that requirement templates include assertions section."""
        from elspais.commands.example_cmd import REQUIREMENT_TEMPLATE_DEV

        assert "## Assertions" in REQUIREMENT_TEMPLATE_DEV
        assert "SHALL" in REQUIREMENT_TEMPLATE_DEV

    def test_requirement_template_has_footer(self):
        """Test that requirement templates include footer."""
        from elspais.commands.example_cmd import REQUIREMENT_TEMPLATE_PRD

        assert "*End*" in REQUIREMENT_TEMPLATE_PRD
        assert "**Hash**:" in REQUIREMENT_TEMPLATE_PRD

    def test_journey_template_has_required_sections(self):
        """Test that journey template has all required sections."""
        from elspais.commands.example_cmd import JOURNEY_TEMPLATE

        assert "Actor" in JOURNEY_TEMPLATE
        assert "Goal" in JOURNEY_TEMPLATE
        assert "Steps" in JOURNEY_TEMPLATE
        assert "Requirements" in JOURNEY_TEMPLATE

    def test_assertion_rules_has_configuration(self):
        """Test that assertion rules shows configuration."""
        from elspais.commands.example_cmd import ASSERTION_RULES

        assert "[patterns.assertions]" in ASSERTION_RULES
        assert "[rules.format]" in ASSERTION_RULES
        assert "label_style" in ASSERTION_RULES


class TestCLIIntegration:
    """Integration tests using the CLI entry point."""

    def test_cli_example_help(self):
        """Test elspais example --help works."""
        from elspais.cli import create_parser

        parser = create_parser()
        # Verify example command is registered
        args = parser.parse_args(["example"])
        assert args.command == "example"

    def test_cli_example_requirement(self):
        """Test elspais example requirement works."""
        from elspais.cli import create_parser

        parser = create_parser()
        args = parser.parse_args(["example", "requirement"])
        assert args.command == "example"
        assert args.example_type == "requirement"

    def test_cli_example_with_full_flag(self):
        """Test elspais example --full works."""
        from elspais.cli import create_parser

        parser = create_parser()
        args = parser.parse_args(["example", "--full"])
        assert args.command == "example"
        assert args.full is True

    def test_cli_main_help_includes_example(self, capsys):
        """Test main --help mentions example command."""
        from elspais.cli import create_parser

        parser = create_parser()
        help_text = parser.format_help()

        assert "example" in help_text
        assert "elspais example" in help_text
        assert "Documentation:" in help_text
