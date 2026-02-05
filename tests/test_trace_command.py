# Validates: REQ-p00003-A, REQ-p00003-B, REQ-p00006-A
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
        req_file.write_text(
            """# REQ-p00001: Test Requirement

**Level**: PRD | **Status**: Active

**Purpose:** A test requirement for trace command.

## Assertions

A. The system SHALL do something.

*End* *Test Requirement* | **Hash**: abcd1234
"""
        )
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
        req_file.write_text(
            """# REQ-p00001: Parent Requirement

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
"""
        )
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


class TestTraceReportPresets:
    """Tests for --report preset functionality."""

    @pytest.fixture
    def temp_spec_dir(self, tmp_path: Path) -> Path:
        """Create a temporary spec directory with requirements."""
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        req_file = spec_dir / "requirements.md"
        req_file.write_text(
            """# REQ-p00001: Parent Requirement

**Level**: PRD | **Status**: Active

**Purpose:** A parent requirement.

## Assertions

A. The system SHALL provide a feature.
B. The system SHALL be reliable.

*End* *Parent Requirement* | **Hash**: abcd1234

---

# REQ-d00001: Child Requirement

**Level**: Dev | **Status**: Draft | **Implements**: REQ-p00001

**Purpose:** A child implementation.

## Assertions

A. The implementation SHALL follow the spec.

*End* *Child Requirement* | **Hash**: efgh5678
"""
        )
        return spec_dir

    def test_report_minimal_has_fewer_columns(self, temp_spec_dir: Path, tmp_path: Path):
        """Test --report minimal produces fewer columns."""
        from elspais.commands import trace

        args = argparse.Namespace(
            config=None,
            spec_dir=temp_spec_dir,
            format="csv",
            output=str(tmp_path / "minimal.csv"),
            quiet=True,
            view=False,
            embed_content=False,
            edit_mode=False,
            review_mode=False,
            server=False,
            graph_json=False,
            report="minimal",
        )

        result = trace.run(args)
        assert result == 0

        content = (tmp_path / "minimal.csv").read_text()
        # Minimal should have: id, title, status (no level, no implements)
        assert "id,title,status" in content
        assert "level" not in content.split("\n")[0]
        assert "implements" not in content.split("\n")[0]

    def test_report_standard_has_default_columns(self, temp_spec_dir: Path, tmp_path: Path):
        """Test --report standard produces default columns."""
        from elspais.commands import trace

        args = argparse.Namespace(
            config=None,
            spec_dir=temp_spec_dir,
            format="csv",
            output=str(tmp_path / "standard.csv"),
            quiet=True,
            view=False,
            embed_content=False,
            edit_mode=False,
            review_mode=False,
            server=False,
            graph_json=False,
            report="standard",
        )

        result = trace.run(args)
        assert result == 0

        content = (tmp_path / "standard.csv").read_text()
        # Standard should have: id, title, level, status, implements
        header = content.split("\n")[0]
        assert "id" in header
        assert "title" in header
        assert "level" in header
        assert "status" in header
        assert "implements" in header

    def test_report_full_has_all_columns(self, temp_spec_dir: Path, tmp_path: Path):
        """Test --report full produces all columns including assertions."""
        from elspais.commands import trace

        args = argparse.Namespace(
            config=None,
            spec_dir=temp_spec_dir,
            format="csv",
            output=str(tmp_path / "full.csv"),
            quiet=True,
            view=False,
            embed_content=False,
            edit_mode=False,
            review_mode=False,
            server=False,
            graph_json=False,
            report="full",
        )

        result = trace.run(args)
        assert result == 0

        content = (tmp_path / "full.csv").read_text()
        header = content.split("\n")[0]
        # Full should have all columns including assertions
        assert "id" in header
        assert "title" in header
        assert "level" in header
        assert "status" in header
        assert "implements" in header
        assert "hash" in header
        assert "file" in header
        assert "assertions" in header

    def test_report_full_json_includes_assertions(self, temp_spec_dir: Path, tmp_path: Path):
        """Test --report full with JSON format includes assertions."""
        from elspais.commands import trace

        args = argparse.Namespace(
            config=None,
            spec_dir=temp_spec_dir,
            format="json",
            output=str(tmp_path / "full.json"),
            quiet=True,
            view=False,
            embed_content=False,
            edit_mode=False,
            review_mode=False,
            server=False,
            graph_json=False,
            report="full",
        )

        result = trace.run(args)
        assert result == 0

        content = (tmp_path / "full.json").read_text()
        data = json.loads(content)
        assert isinstance(data, list)

        # Find REQ-p00001 and verify it has assertions
        parent = next((r for r in data if r.get("id") == "REQ-p00001"), None)
        assert parent is not None
        assert "assertions" in parent
        assert len(parent["assertions"]) == 2

    def test_report_minimal_json_excludes_assertions(self, temp_spec_dir: Path, tmp_path: Path):
        """Test --report minimal with JSON format excludes assertions."""
        from elspais.commands import trace

        args = argparse.Namespace(
            config=None,
            spec_dir=temp_spec_dir,
            format="json",
            output=str(tmp_path / "minimal.json"),
            quiet=True,
            view=False,
            embed_content=False,
            edit_mode=False,
            review_mode=False,
            server=False,
            graph_json=False,
            report="minimal",
        )

        result = trace.run(args)
        assert result == 0

        content = (tmp_path / "minimal.json").read_text()
        data = json.loads(content)
        assert isinstance(data, list)

        # Minimal should not include assertions
        parent = next((r for r in data if r.get("id") == "REQ-p00001"), None)
        assert parent is not None
        assert "assertions" not in parent

    def test_report_invalid_preset_returns_error(self, temp_spec_dir: Path, capsys):
        """Test invalid --report preset returns error."""
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
            server=False,
            graph_json=False,
            report="nonexistent",
        )

        result = trace.run(args)
        assert result == 1

        captured = capsys.readouterr()
        assert "Unknown report preset" in captured.err
        assert "minimal" in captured.err  # Should list available presets

    def test_report_default_is_standard(self, temp_spec_dir: Path, tmp_path: Path):
        """Test that no --report defaults to standard."""
        from elspais.commands import trace

        # Run without --report
        args_no_report = argparse.Namespace(
            config=None,
            spec_dir=temp_spec_dir,
            format="csv",
            output=str(tmp_path / "default.csv"),
            quiet=True,
            view=False,
            embed_content=False,
            edit_mode=False,
            review_mode=False,
            server=False,
            graph_json=False,
            report=None,
        )

        result1 = trace.run(args_no_report)
        assert result1 == 0

        # Run with explicit --report standard
        args_standard = argparse.Namespace(
            config=None,
            spec_dir=temp_spec_dir,
            format="csv",
            output=str(tmp_path / "standard.csv"),
            quiet=True,
            view=False,
            embed_content=False,
            edit_mode=False,
            review_mode=False,
            server=False,
            graph_json=False,
            report="standard",
        )

        result2 = trace.run(args_standard)
        assert result2 == 0

        # Both should produce the same headers
        default_header = (tmp_path / "default.csv").read_text().split("\n")[0]
        standard_header = (tmp_path / "standard.csv").read_text().split("\n")[0]
        assert default_header == standard_header


class TestTraceAdvancedFeaturesNotImplemented:
    """Tests that advanced features show appropriate errors."""

    @pytest.fixture
    def temp_spec_dir(self, tmp_path: Path) -> Path:
        """Create minimal spec directory."""
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        (spec_dir / "dummy.md").write_text(
            "# REQ-p00001: Dummy\n**Level**: PRD | **Status**: Active\n"
        )
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
