"""Tests for diff generation module.

Validates: REQ-p00001-B
"""

import pytest

from elspais.trace_view.diff import (
    DiffHunk,
    DiffResult,
    _parse_range,
    _parse_unified_diff,
    diff_to_html,
)


class TestDiffResult:
    """Tests for DiffResult dataclass."""

    def test_has_changes_with_hunks(self):
        """Test has_changes returns True when hunks exist."""
        result = DiffResult(
            file_path="test.md",
            hunks=[DiffHunk(1, 1, 1, 1, [])],
        )
        assert result.has_changes is True

    def test_has_changes_new_file(self):
        """Test has_changes returns True for new files."""
        result = DiffResult(file_path="test.md", is_new_file=True)
        assert result.has_changes is True

    def test_has_changes_deleted_file(self):
        """Test has_changes returns True for deleted files."""
        result = DiffResult(file_path="test.md", is_deleted=True)
        assert result.has_changes is True

    def test_has_changes_no_changes(self):
        """Test has_changes returns False when no changes."""
        result = DiffResult(file_path="test.md")
        assert result.has_changes is False


class TestParseRange:
    """Tests for _parse_range helper."""

    def test_parse_range_with_count(self):
        """Test parsing range with comma."""
        start, count = _parse_range("10,5")
        assert start == 10
        assert count == 5

    def test_parse_range_single(self):
        """Test parsing range without comma."""
        start, count = _parse_range("42")
        assert start == 42
        assert count == 1


class TestParseUnifiedDiff:
    """Tests for _parse_unified_diff."""

    def test_parse_simple_diff(self):
        """Test parsing a simple unified diff."""
        diff_lines = [
            "--- a/test.md",
            "+++ b/test.md",
            "@@ -1,3 +1,3 @@",
            " line1",
            "-old line",
            "+new line",
            " line3",
        ]
        hunks = _parse_unified_diff(diff_lines)

        assert len(hunks) == 1
        assert hunks[0].old_start == 1
        assert hunks[0].old_count == 3
        assert hunks[0].new_start == 1
        assert hunks[0].new_count == 3
        assert len(hunks[0].lines) == 4
        assert hunks[0].lines[0] == (" ", "line1")
        assert hunks[0].lines[1] == ("-", "old line")
        assert hunks[0].lines[2] == ("+", "new line")
        assert hunks[0].lines[3] == (" ", "line3")

    def test_parse_multiple_hunks(self):
        """Test parsing diff with multiple hunks."""
        diff_lines = [
            "--- a/test.md",
            "+++ b/test.md",
            "@@ -1,2 +1,2 @@",
            "-old1",
            "+new1",
            "@@ -10,2 +10,2 @@",
            "-old2",
            "+new2",
        ]
        hunks = _parse_unified_diff(diff_lines)

        assert len(hunks) == 2
        assert hunks[0].old_start == 1
        assert hunks[1].old_start == 10


class TestDiffToHtml:
    """Tests for diff_to_html rendering."""

    def test_render_error(self):
        """Test rendering error message."""
        result = DiffResult(file_path="test.md", error="Something went wrong")
        html = diff_to_html(result)
        assert "diff-error" in html
        assert "Something went wrong" in html

    def test_render_no_changes(self):
        """Test rendering no changes message."""
        result = DiffResult(file_path="test.md")
        html = diff_to_html(result)
        assert "diff-no-changes" in html
        assert "No changes detected" in html

    def test_render_new_file(self):
        """Test rendering new file."""
        result = DiffResult(
            file_path="test.md",
            is_new_file=True,
            hunks=[DiffHunk(0, 0, 1, 1, [("+", "new content")])],
        )
        html = diff_to_html(result)
        assert "diff-new-file" in html
        assert "New file" in html

    def test_render_with_hunks(self):
        """Test rendering actual diff hunks."""
        result = DiffResult(
            file_path="test.md",
            hunks=[
                DiffHunk(
                    old_start=1,
                    old_count=2,
                    new_start=1,
                    new_count=2,
                    lines=[
                        ("-", "old line"),
                        ("+", "new line"),
                    ],
                )
            ],
        )
        html = diff_to_html(result)
        assert "diff-container" in html
        assert "diff-hunk" in html
        assert "diff-removed" in html
        assert "diff-added" in html
        assert "old line" in html
        assert "new line" in html

    def test_html_escaping(self):
        """Test that HTML is properly escaped."""
        result = DiffResult(
            file_path="test.md",
            hunks=[
                DiffHunk(
                    old_start=1,
                    old_count=1,
                    new_start=1,
                    new_count=1,
                    lines=[("+", "<script>alert('xss')</script>")],
                )
            ],
        )
        html = diff_to_html(result)
        assert "&lt;script&gt;" in html
        assert "<script>" not in html
