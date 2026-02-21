# Validates REQ-p00005-A
"""
Tests for the init command.
"""

import argparse
from pathlib import Path


class TestInitConfig:
    """Tests for init command configuration generation."""

    def test_init_creates_config(self, tmp_path: Path, monkeypatch):
        """Test init creates .elspais.toml."""
        from elspais.commands.init import run

        monkeypatch.chdir(tmp_path)

        args = argparse.Namespace(
            type=None,
            associated_prefix=None,
            force=False,
            template=False,
            config=None,
        )

        result = run(args)

        assert result == 0
        config_path = tmp_path / ".elspais.toml"
        assert config_path.exists()
        content = config_path.read_text()
        assert "[project]" in content
        assert 'type = "core"' in content

    def test_init_core_type(self, tmp_path: Path, monkeypatch):
        """Test init with explicit core type."""
        from elspais.commands.init import run

        monkeypatch.chdir(tmp_path)

        args = argparse.Namespace(
            type="core",
            associated_prefix=None,
            force=False,
            template=False,
            config=None,
        )

        result = run(args)

        assert result == 0
        content = (tmp_path / ".elspais.toml").read_text()
        assert 'type = "core"' in content

    def test_init_associated_type(self, tmp_path: Path, monkeypatch):
        """Test init with associated type."""
        from elspais.commands.init import run

        monkeypatch.chdir(tmp_path)

        args = argparse.Namespace(
            type="associated",
            associated_prefix="CAL",
            force=False,
            template=False,
            config=None,
        )

        result = run(args)

        assert result == 0
        content = (tmp_path / ".elspais.toml").read_text()
        assert 'type = "associated"' in content
        assert 'prefix = "CAL"' in content

    def test_init_associated_requires_prefix(self, tmp_path: Path, monkeypatch, capsys):
        """Test init associated type requires --associated-prefix."""
        from elspais.commands.init import run

        monkeypatch.chdir(tmp_path)

        args = argparse.Namespace(
            type="associated",
            associated_prefix=None,
            force=False,
            template=False,
            config=None,
        )

        result = run(args)

        assert result == 1
        captured = capsys.readouterr()
        assert "--associated-prefix required" in captured.out

    def test_init_refuses_overwrite_without_force(self, tmp_path: Path, monkeypatch, capsys):
        """Test init refuses to overwrite existing config."""
        from elspais.commands.init import run

        monkeypatch.chdir(tmp_path)

        config_path = tmp_path / ".elspais.toml"
        config_path.write_text("existing config")

        args = argparse.Namespace(
            type=None,
            associated_prefix=None,
            force=False,
            template=False,
            config=None,
        )

        result = run(args)

        assert result == 1
        captured = capsys.readouterr()
        assert "already exists" in captured.out
        assert config_path.read_text() == "existing config"

    def test_init_overwrites_with_force(self, tmp_path: Path, monkeypatch):
        """Test init overwrites existing config with --force."""
        from elspais.commands.init import run

        monkeypatch.chdir(tmp_path)

        config_path = tmp_path / ".elspais.toml"
        config_path.write_text("existing config")

        args = argparse.Namespace(
            type=None,
            associated_prefix=None,
            force=True,
            template=False,
            config=None,
        )

        result = run(args)

        assert result == 0
        assert "[project]" in config_path.read_text()


class TestInitTemplate:
    """Tests for init --template flag."""

    def test_init_template_creates_example(self, tmp_path: Path, monkeypatch, capsys):
        """Test --template creates example requirement file."""
        from elspais.commands.init import run

        monkeypatch.chdir(tmp_path)

        args = argparse.Namespace(
            type=None,
            associated_prefix=None,
            force=False,
            template=True,
            config=None,
        )

        result = run(args)

        assert result == 0
        example_path = tmp_path / "spec" / "EXAMPLE-requirement.md"
        assert example_path.exists()

        content = example_path.read_text()
        assert "REQ-d00001" in content
        assert "## Assertions" in content
        assert "SHALL" in content
        assert "Example Requirement Title" in content

    def test_init_template_creates_spec_dir(self, tmp_path: Path, monkeypatch):
        """Test --template creates spec directory if needed."""
        from elspais.commands.init import run

        monkeypatch.chdir(tmp_path)

        assert not (tmp_path / "spec").exists()

        args = argparse.Namespace(
            type=None,
            associated_prefix=None,
            force=False,
            template=True,
            config=None,
        )

        result = run(args)

        assert result == 0
        assert (tmp_path / "spec").exists()
        assert (tmp_path / "spec").is_dir()

    def test_init_template_refuses_overwrite(self, tmp_path: Path, monkeypatch, capsys):
        """Test --template refuses to overwrite existing example."""
        from elspais.commands.init import run

        monkeypatch.chdir(tmp_path)

        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        example_path = spec_dir / "EXAMPLE-requirement.md"
        example_path.write_text("existing content")

        args = argparse.Namespace(
            type=None,
            associated_prefix=None,
            force=False,
            template=True,
            config=None,
        )

        result = run(args)

        assert result == 1
        captured = capsys.readouterr()
        assert "already exists" in captured.out
        assert example_path.read_text() == "existing content"

    def test_init_template_overwrites_with_force(self, tmp_path: Path, monkeypatch):
        """Test --template overwrites with --force."""
        from elspais.commands.init import run

        monkeypatch.chdir(tmp_path)

        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        example_path = spec_dir / "EXAMPLE-requirement.md"
        example_path.write_text("existing content")

        args = argparse.Namespace(
            type=None,
            associated_prefix=None,
            force=True,
            template=True,
            config=None,
        )

        result = run(args)

        assert result == 0
        assert "REQ-d00001" in example_path.read_text()

    def test_init_template_uses_config_spec_dir(self, tmp_path: Path, monkeypatch):
        """Test --template uses spec dir from config if available."""
        from elspais.commands.init import run

        monkeypatch.chdir(tmp_path)

        # Create config with custom spec dir
        config_path = tmp_path / ".elspais.toml"
        config_path.write_text(
            """
[directories]
spec = "requirements"
"""
        )

        args = argparse.Namespace(
            type=None,
            associated_prefix=None,
            force=False,
            template=True,
            config=config_path,
        )

        result = run(args)

        assert result == 0
        example_path = tmp_path / "requirements" / "EXAMPLE-requirement.md"
        assert example_path.exists()

    def test_init_template_shows_next_steps(self, tmp_path: Path, monkeypatch, capsys):
        """Test --template shows helpful next steps."""
        from elspais.commands.init import run

        monkeypatch.chdir(tmp_path)

        args = argparse.Namespace(
            type=None,
            associated_prefix=None,
            force=False,
            template=True,
            config=None,
        )

        result = run(args)

        assert result == 0
        captured = capsys.readouterr()
        assert "Next steps:" in captured.out
        assert "elspais validate" in captured.out
        assert "elspais fix" in captured.out


class TestInitCLIIntegration:
    """CLI integration tests for init command."""

    def test_cli_init_template_flag(self):
        """Test init --template flag is registered."""
        from elspais.cli import create_parser

        parser = create_parser()
        args = parser.parse_args(["init", "--template"])
        assert args.command == "init"
        assert args.template is True

    def test_cli_init_template_with_force(self):
        """Test init --template --force flags together."""
        from elspais.cli import create_parser

        parser = create_parser()
        args = parser.parse_args(["init", "--template", "--force"])
        assert args.template is True
        assert args.force is True


class TestExampleRequirementContent:
    """Tests for the example requirement template content."""

    def test_example_has_all_sections(self):
        """Test example requirement has all required sections."""
        from elspais.commands.init import EXAMPLE_REQUIREMENT

        assert "# REQ-d00001:" in EXAMPLE_REQUIREMENT
        assert "**Level**:" in EXAMPLE_REQUIREMENT
        assert "**Status**:" in EXAMPLE_REQUIREMENT
        assert "**Implements**:" in EXAMPLE_REQUIREMENT
        assert "## Assertions" in EXAMPLE_REQUIREMENT
        assert "## Rationale" in EXAMPLE_REQUIREMENT
        assert "*End*" in EXAMPLE_REQUIREMENT
        assert "**Hash**:" in EXAMPLE_REQUIREMENT

    def test_example_uses_shall_in_assertions(self):
        """Test example uses SHALL in assertions."""
        from elspais.commands.init import EXAMPLE_REQUIREMENT

        assert "SHALL" in EXAMPLE_REQUIREMENT
        # Should have at least two assertions (A and B)
        assert "A. The system SHALL" in EXAMPLE_REQUIREMENT
        assert "B. The system SHALL" in EXAMPLE_REQUIREMENT

    def test_example_includes_format_notes(self):
        """Test example includes helpful format notes."""
        from elspais.commands.init import EXAMPLE_REQUIREMENT

        assert "Format Notes" in EXAMPLE_REQUIREMENT
        assert "delete this section" in EXAMPLE_REQUIREMENT.lower()
