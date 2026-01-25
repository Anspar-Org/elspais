"""Tests for INDEX.md generation.

Validates: REQ-p00001
"""

import pytest
from pathlib import Path

from elspais.core.models import Requirement
from elspais.commands.index import generate_index


class TestGenerateIndex:
    """Tests for generate_index function."""

    def test_trailing_newline(self) -> None:
        """Generated INDEX.md should end with single newline (MD047 compliance)."""
        req = Requirement(
            id="REQ-p00001",
            title="Test Requirement",
            level="PRD",
            status="Active",
            body="Test body",
            file_path=Path("test.md"),
            hash="abc123",
        )
        requirements = {"REQ-p00001": req}

        content = generate_index(requirements, {})

        assert content.endswith("\n"), "File should end with newline"
        assert not content.endswith("\n\n"), "File should not end with double newline"

    def test_headings_structure(self) -> None:
        """Generated INDEX.md should have proper heading structure."""
        req = Requirement(
            id="REQ-p00001",
            title="Test Requirement",
            level="PRD",
            status="Active",
            body="Test body",
            file_path=Path("test.md"),
            hash="abc123",
        )
        requirements = {"REQ-p00001": req}

        content = generate_index(requirements, {})

        # MD041: First line should be H1
        lines = content.split("\n")
        assert lines[0].startswith("# "), "First line should be H1 heading"

        # MD001: H2 follows H1 (not H3, H4, etc.)
        h2_found = any(line.startswith("## ") for line in lines)
        h3_found = any(line.startswith("### ") for line in lines)
        assert h2_found, "Should have H2 headings"
        # H3 only allowed after H2
        if h3_found:
            h2_idx = next(i for i, line in enumerate(lines) if line.startswith("## "))
            h3_idx = next(i for i, line in enumerate(lines) if line.startswith("### "))
            assert h3_idx > h2_idx, "H3 should come after H2"

    def test_blank_lines_around_headings(self) -> None:
        """Headings should be surrounded by blank lines (MD022)."""
        req = Requirement(
            id="REQ-p00001",
            title="Test Requirement",
            level="PRD",
            status="Active",
            body="Test body",
            file_path=Path("test.md"),
            hash="abc123",
        )
        requirements = {"REQ-p00001": req}

        content = generate_index(requirements, {})
        lines = content.split("\n")

        for i, line in enumerate(lines):
            if line.startswith("## "):
                # Check blank line after H2
                if i + 1 < len(lines):
                    assert lines[i + 1] == "", f"H2 at line {i} should have blank line after"

    def test_empty_requirements(self) -> None:
        """Should generate valid markdown with no requirements."""
        content = generate_index({}, {})

        assert content.endswith("\n"), "Empty index should still end with newline"
        assert "# Requirements Index" in content

    def test_multiple_levels(self) -> None:
        """Should group requirements by level correctly."""
        reqs = {
            "REQ-p00001": Requirement(
                id="REQ-p00001",
                title="PRD Req",
                level="PRD",
                status="Active",
                body="",
                file_path=Path("p.md"),
            ),
            "REQ-o00001": Requirement(
                id="REQ-o00001",
                title="OPS Req",
                level="OPS",
                status="Active",
                body="",
                file_path=Path("o.md"),
            ),
            "REQ-d00001": Requirement(
                id="REQ-d00001",
                title="DEV Req",
                level="DEV",
                status="Active",
                body="",
                file_path=Path("d.md"),
            ),
        }

        content = generate_index(reqs, {})

        assert "## Product Requirements (PRD)" in content
        assert "## Operations Requirements (OPS)" in content
        assert "## Development Requirements (DEV)" in content
        assert "REQ-p00001" in content
        assert "REQ-o00001" in content
        assert "REQ-d00001" in content
