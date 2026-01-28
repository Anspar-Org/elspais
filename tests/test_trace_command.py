"""Tests for the trace command."""

import argparse
import json
import tempfile
from pathlib import Path

import pytest


class TestTraceCommand:
    """Tests for basic trace command functionality."""

    @pytest.fixture
    def temp_spec_dir(self, tmp_path: Path) -> Path:
        """Create a temporary spec directory with a requirement."""
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        # Create a simple requirement file
        req_file = spec_dir / "requirements.md"
        req_file.write_text("""# REQ-p00001: Test Requirement

**Level**: PRD | **Status**: Active

**Purpose:** A test requirement for trace command.

## Assertions

A. The system SHALL do something.

*End* *Test Requirement* | **Hash**: abcd1234
""")
        return spec_dir

    def test_trace_markdown_format(self, temp_spec_dir: Path, tmp_path: Path):
        """Test trace command with markdown format."""
        from elspais.commands import trace

        args = argparse.Namespace(
            config=None,
            spec_dir=temp_spec_dir,
            format="markdown",
            output=str(tmp_path / "output.md"),
            quiet=True,
            view=False,
            embed_content=False,
            edit_mode=False,
            review_mode=False,
            server=False,
            graph_json=False,
        )

        result = trace.run(args)
        assert result == 0

        output_path = tmp_path / "output.md"
        assert output_path.exists()
        content = output_path.read_text()
        assert "Traceability Matrix" in content
        assert "REQ-p00001" in content

    def test_trace_html_format(self, temp_spec_dir: Path, tmp_path: Path):
        """Test trace command with basic HTML format."""
        from elspais.commands import trace

        args = argparse.Namespace(
            config=None,
            spec_dir=temp_spec_dir,
            format="html",
            output=str(tmp_path / "output.html"),
            quiet=True,
            view=False,
            embed_content=False,
            edit_mode=False,
            review_mode=False,
            server=False,
            graph_json=False,
        )

        result = trace.run(args)
        assert result == 0

        output_path = tmp_path / "output.html"
        assert output_path.exists()
        content = output_path.read_text()
        assert "<!DOCTYPE html>" in content
        assert "REQ-p00001" in content

    def test_trace_json_format(self, temp_spec_dir: Path, tmp_path: Path):
        """Test trace command with JSON format."""
        from elspais.commands import trace

        args = argparse.Namespace(
            config=None,
            spec_dir=temp_spec_dir,
            format="json",
            output=str(tmp_path / "output.json"),
            quiet=True,
            view=False,
            embed_content=False,
            edit_mode=False,
            review_mode=False,
            server=False,
            graph_json=False,
        )

        result = trace.run(args)
        assert result == 0

        output_path = tmp_path / "output.json"
        assert output_path.exists()
        content = output_path.read_text()
        data = json.loads(content)
        # JSON format returns a list of dicts, not a dict keyed by ID
        assert isinstance(data, list)
        assert any(item["id"] == "REQ-p00001" for item in data)

    def test_trace_csv_format(self, temp_spec_dir: Path, tmp_path: Path):
        """Test trace command with CSV format."""
        from elspais.commands import trace

        args = argparse.Namespace(
            config=None,
            spec_dir=temp_spec_dir,
            format="csv",
            output=str(tmp_path / "output.csv"),
            quiet=True,
            view=False,
            embed_content=False,
            edit_mode=False,
            review_mode=False,
            server=False,
            graph_json=False,
        )

        result = trace.run(args)
        assert result == 0

        output_path = tmp_path / "output.csv"
        assert output_path.exists()
        content = output_path.read_text()
        assert "id,title,level,status,implements" in content
        assert "REQ-p00001" in content


class TestTraceViewCommand:
    """Tests for trace --view functionality."""

    @pytest.fixture
    def temp_spec_dir(self, tmp_path: Path) -> Path:
        """Create a temporary spec directory with requirements."""
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        # Create requirements with hierarchy
        req_file = spec_dir / "requirements.md"
        req_file.write_text("""# REQ-p00001: Parent Requirement

**Level**: PRD | **Status**: Active

**Purpose:** A parent requirement.

## Assertions

A. The system SHALL provide a feature.

*End* *Parent Requirement* | **Hash**: abcd1234

---

# REQ-d00001: Child Requirement

**Level**: Dev | **Status**: Active | **Implements**: REQ-p00001

**Purpose:** A child requirement implementing the parent.

## Assertions

A. The implementation SHALL follow the spec.

*End* *Child Requirement* | **Hash**: efgh5678
""")
        return spec_dir

    def test_trace_view_generates_interactive_html(self, temp_spec_dir: Path, tmp_path: Path):
        """Test trace --view generates interactive HTML."""
        from elspais.commands import trace

        args = argparse.Namespace(
            config=None,
            spec_dir=temp_spec_dir,
            format="markdown",  # format is ignored when view=True
            output=str(tmp_path / "view.html"),
            quiet=True,
            view=True,
            embed_content=False,
            edit_mode=False,
            review_mode=False,
            server=False,
            graph_json=False,
        )

        result = trace.run(args)
        assert result == 0

        output_path = tmp_path / "view.html"
        assert output_path.exists()
        content = output_path.read_text()

        # Check for interactive HTML structure
        assert "<!DOCTYPE html>" in content
        assert "Requirements Traceability" in content
        assert "req-row" in content  # Interactive row class
        assert "REQ-p00001" in content
        assert "REQ-d00001" in content

    def test_trace_view_default_output_path(self, temp_spec_dir: Path, monkeypatch):
        """Test trace --view uses default output path when none specified."""
        from elspais.commands import trace

        # Change to a temp directory for output
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.chdir(tmpdir)

            args = argparse.Namespace(
                config=None,
                spec_dir=temp_spec_dir,
                format="markdown",
                output=None,  # No output specified
                quiet=True,
                view=True,
                embed_content=False,
                edit_mode=False,
                review_mode=False,
                server=False,
                graph_json=False,
            )

            result = trace.run(args)
            assert result == 0

            # Should create default file
            default_path = Path(tmpdir) / "traceability_view.html"
            assert default_path.exists()

    def test_trace_view_with_embed_content(self, temp_spec_dir: Path, tmp_path: Path):
        """Test trace --view --embed-content includes JSON data."""
        from elspais.commands import trace

        args = argparse.Namespace(
            config=None,
            spec_dir=temp_spec_dir,
            format="markdown",
            output=str(tmp_path / "view_embed.html"),
            quiet=True,
            view=True,
            embed_content=True,
            edit_mode=False,
            review_mode=False,
            server=False,
            graph_json=False,
        )

        result = trace.run(args)
        assert result == 0

        output_path = tmp_path / "view_embed.html"
        assert output_path.exists()
        content = output_path.read_text()

        # Check for embedded JSON data
        assert 'id="tree-data"' in content
        assert "application/json" in content
        # Verify it contains requirement data as JSON
        assert '"REQ-p00001"' in content


class TestTraceAdvancedFeaturesNotImplemented:
    """Tests that advanced features show appropriate errors."""

    @pytest.fixture
    def temp_spec_dir(self, tmp_path: Path) -> Path:
        """Create minimal spec directory."""
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        (spec_dir / "dummy.md").write_text("# REQ-p00001: Dummy\n**Level**: PRD | **Status**: Active\n")
        return spec_dir

    def test_edit_mode_not_implemented(self, temp_spec_dir: Path, capsys):
        """Test --edit-mode shows not implemented error."""
        from elspais.commands import trace

        args = argparse.Namespace(
            config=None,
            spec_dir=temp_spec_dir,
            format="markdown",
            output=None,
            quiet=False,
            view=False,
            embed_content=False,
            edit_mode=True,
            review_mode=False,
            server=False,
            graph_json=False,
        )

        result = trace.run(args)
        assert result == 1

        captured = capsys.readouterr()
        assert "not yet implemented" in captured.err

    def test_review_mode_not_implemented(self, temp_spec_dir: Path, capsys):
        """Test --review-mode shows not implemented error."""
        from elspais.commands import trace

        args = argparse.Namespace(
            config=None,
            spec_dir=temp_spec_dir,
            format="markdown",
            output=None,
            quiet=False,
            view=False,
            embed_content=False,
            edit_mode=False,
            review_mode=True,
            server=False,
            graph_json=False,
        )

        result = trace.run(args)
        assert result == 1

        captured = capsys.readouterr()
        assert "not yet implemented" in captured.err

    def test_server_not_implemented(self, temp_spec_dir: Path, capsys):
        """Test --server shows not implemented error."""
        from elspais.commands import trace

        args = argparse.Namespace(
            config=None,
            spec_dir=temp_spec_dir,
            format="markdown",
            output=None,
            quiet=False,
            view=False,
            embed_content=False,
            edit_mode=False,
            review_mode=False,
            server=True,
            graph_json=False,
        )

        result = trace.run(args)
        assert result == 1

        captured = capsys.readouterr()
        assert "not yet implemented" in captured.err
