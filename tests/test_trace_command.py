# Validates REQ-p00003-A, REQ-p00003-B, REQ-p00006-A
# Validates REQ-p00050-B
# Validates REQ-d00052-B, REQ-d00052-C
"""Tests for the trace command."""

import argparse
import json
from pathlib import Path

import pytest


class TestTraceCommand:
    """Tests for basic trace command functionality."""

    @pytest.fixture
    def temp_spec_dir(self, tmp_path: Path) -> Path:
        """Create a temporary spec directory with a requirement."""
        (tmp_path / ".elspais.toml").write_text("")
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

    # Implements: REQ-p00003-A
    def test_trace_markdown_format(self, temp_spec_dir: Path, capsys):
        """Test trace command with markdown format."""
        from elspais.commands import trace

        args = argparse.Namespace(
            config=None,
            spec_dir=temp_spec_dir,
            format="markdown",
            quiet=True,
        )

        result = trace.run(args)
        assert result == 0

        content = capsys.readouterr().out
        assert "Traceability Matrix" in content
        assert "REQ-p00001" in content

    # Implements: REQ-p00003-A
    def test_trace_html_format(self, temp_spec_dir: Path, capsys):
        """Test trace command with basic HTML format."""
        from elspais.commands import trace

        args = argparse.Namespace(
            config=None,
            spec_dir=temp_spec_dir,
            format="html",
            quiet=True,
        )

        result = trace.run(args)
        assert result == 0

        content = capsys.readouterr().out
        assert "<!DOCTYPE html>" in content
        assert "REQ-p00001" in content

    # Implements: REQ-d00084-A
    def test_trace_json_format(self, temp_spec_dir: Path, capsys):
        """Test trace command with JSON format."""
        from elspais.commands import trace

        args = argparse.Namespace(
            config=None,
            spec_dir=temp_spec_dir,
            format="json",
            quiet=True,
        )

        result = trace.run(args)
        assert result == 0

        content = capsys.readouterr().out
        data = json.loads(content)
        # JSON format returns a list of dicts, not a dict keyed by ID
        assert isinstance(data, list)
        assert any(item["id"] == "REQ-p00001" for item in data)

    # Implements: REQ-p00003-A
    def test_trace_csv_format(self, temp_spec_dir: Path, capsys):
        """Test trace command with CSV format."""
        from elspais.commands import trace

        args = argparse.Namespace(
            config=None,
            spec_dir=temp_spec_dir,
            format="csv",
            quiet=True,
        )

        result = trace.run(args)
        assert result == 0

        content = capsys.readouterr().out
        header = content.split("\n")[0]
        assert "ID" in header
        assert "Title" in header
        assert "REQ-p00001" in content


class TestTraceReportPresets:
    """Tests for --preset functionality."""

    @pytest.fixture
    def temp_spec_dir(self, tmp_path: Path) -> Path:
        """Create a temporary spec directory with requirements."""
        (tmp_path / ".elspais.toml").write_text("")
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

    # Implements: REQ-d00084-B
    def test_report_minimal_has_fewer_columns(self, temp_spec_dir: Path, capsys):
        """Test --preset minimal produces fewer columns."""
        from elspais.commands import trace

        args = argparse.Namespace(
            config=None,
            spec_dir=temp_spec_dir,
            format="csv",
            quiet=True,
            preset="minimal",
        )

        result = trace.run(args)
        assert result == 0

        content = capsys.readouterr().out
        header = content.split("\n")[0]
        # Minimal should have: ID, Title, Level, Status (no coverage columns)
        assert "ID" in header
        assert "Title" in header
        assert "Level" in header
        assert "Status" in header
        assert "Implemented" not in header
        assert "Validated" not in header

    # Implements: REQ-d00084-B
    def test_report_standard_has_default_columns(self, temp_spec_dir: Path, capsys):
        """Test --preset standard produces default columns with coverage."""
        from elspais.commands import trace

        args = argparse.Namespace(
            config=None,
            spec_dir=temp_spec_dir,
            format="csv",
            quiet=True,
            preset="standard",
        )

        result = trace.run(args)
        assert result == 0

        content = capsys.readouterr().out
        # Standard should have: ID, Title, Level, Status, Implemented, Validated
        header = content.split("\n")[0]
        assert "ID" in header
        assert "Title" in header
        assert "Level" in header
        assert "Status" in header
        assert "Implemented" in header
        assert "Validated" in header

    # Implements: REQ-d00084-B
    def test_report_full_has_all_columns(self, temp_spec_dir: Path, capsys):
        """Test --preset full produces all columns including Passing."""
        from elspais.commands import trace

        args = argparse.Namespace(
            config=None,
            spec_dir=temp_spec_dir,
            format="csv",
            quiet=True,
            preset="full",
        )

        result = trace.run(args)
        assert result == 0

        content = capsys.readouterr().out
        header = content.split("\n")[0]
        # Full should have all coverage columns
        assert "ID" in header
        assert "Title" in header
        assert "Level" in header
        assert "Status" in header
        assert "Implemented" in header
        assert "Validated" in header
        assert "Passing" in header

    # Implements: REQ-d00084-D
    def test_report_full_json_includes_coverage(self, temp_spec_dir: Path, capsys):
        """Test --preset full with JSON format includes coverage columns."""
        from elspais.commands import trace

        args = argparse.Namespace(
            config=None,
            spec_dir=temp_spec_dir,
            format="json",
            quiet=True,
            preset="full",
        )

        result = trace.run(args)
        assert result == 0

        content = capsys.readouterr().out
        data = json.loads(content)
        assert isinstance(data, list)

        # Find REQ-p00001 and verify it has coverage fields
        parent = next((r for r in data if r.get("id") == "REQ-p00001"), None)
        assert parent is not None
        assert "implemented" in parent
        assert "validated" in parent
        assert "passing" in parent

    # Implements: REQ-d00084-B
    def test_report_minimal_json_excludes_coverage(self, temp_spec_dir: Path, capsys):
        """Test --preset minimal with JSON format excludes coverage columns."""
        from elspais.commands import trace

        args = argparse.Namespace(
            config=None,
            spec_dir=temp_spec_dir,
            format="json",
            quiet=True,
            preset="minimal",
        )

        result = trace.run(args)
        assert result == 0

        content = capsys.readouterr().out
        data = json.loads(content)
        assert isinstance(data, list)

        # Minimal should not include coverage columns
        parent = next((r for r in data if r.get("id") == "REQ-p00001"), None)
        assert parent is not None
        assert "implemented" not in parent
        assert "validated" not in parent

    # Implements: REQ-d00084-B
    def test_report_invalid_preset_returns_error(self, temp_spec_dir: Path, capsys):
        """Test invalid --preset returns error."""
        from elspais.commands import trace

        args = argparse.Namespace(
            config=None,
            spec_dir=temp_spec_dir,
            format="markdown",
            quiet=False,
            preset="nonexistent",
        )

        result = trace.run(args)
        assert result == 1

        captured = capsys.readouterr()
        assert "Unknown preset" in captured.err
        assert "minimal" in captured.err  # Should list available presets

    # Implements: REQ-d00084-B
    def test_report_default_is_standard(self, temp_spec_dir: Path, capsys):
        """Test that no --preset defaults to standard."""
        from elspais.commands import trace

        # Run without --preset
        args_no_preset = argparse.Namespace(
            config=None,
            spec_dir=temp_spec_dir,
            format="csv",
            quiet=True,
            preset=None,
        )

        result1 = trace.run(args_no_preset)
        assert result1 == 0

        default_output = capsys.readouterr().out

        # Run with explicit --preset standard
        args_standard = argparse.Namespace(
            config=None,
            spec_dir=temp_spec_dir,
            format="csv",
            quiet=True,
            preset="standard",
        )

        result2 = trace.run(args_standard)
        assert result2 == 0

        standard_output = capsys.readouterr().out

        # Both should produce the same headers
        default_header = default_output.split("\n")[0]
        standard_header = standard_output.split("\n")[0]
        assert default_header == standard_header
