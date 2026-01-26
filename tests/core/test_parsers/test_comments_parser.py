"""Tests for CommentsParser - Priority 0 comment block parser."""

import pytest

from elspais.arch3.Graph.MDparser import ParseContext
from elspais.arch3.Graph.MDparser.comments import CommentsParser


class TestCommentsParserPriority:
    """Tests for CommentsParser priority."""

    def test_priority_is_zero(self):
        parser = CommentsParser()
        assert parser.priority == 0


class TestCommentsParserSingleLine:
    """Tests for single-line HTML comments."""

    def test_claims_single_line_comment(self):
        parser = CommentsParser()
        lines = [
            (1, "Some text"),
            (2, "<!-- This is a comment -->"),
            (3, "More text"),
        ]
        ctx = ParseContext(file_path="test.md")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        assert results[0].content_type == "comment"
        assert results[0].start_line == 2
        assert results[0].end_line == 2

    def test_claims_multiple_single_line_comments(self):
        parser = CommentsParser()
        lines = [
            (1, "<!-- First comment -->"),
            (2, "Some text"),
            (3, "<!-- Second comment -->"),
        ]
        ctx = ParseContext(file_path="test.md")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 2
        assert results[0].start_line == 1
        assert results[1].start_line == 3


class TestCommentsParserMultiLine:
    """Tests for multi-line HTML comment blocks."""

    def test_claims_multiline_comment(self, comment_block_lines):
        parser = CommentsParser()
        ctx = ParseContext(file_path="test.md")

        results = list(parser.claim_and_parse(comment_block_lines, ctx))

        # Should find single-line and multi-line comments
        assert len(results) == 2

        # Single-line comment
        single = [r for r in results if r.start_line == r.end_line]
        assert len(single) == 1
        assert single[0].start_line == 2

        # Multi-line comment
        multi = [r for r in results if r.start_line != r.end_line]
        assert len(multi) == 1
        assert multi[0].start_line == 4
        assert multi[0].end_line == 8

    def test_multiline_comment_raw_text(self):
        parser = CommentsParser()
        lines = [
            (1, "<!--"),
            (2, "Multi-line"),
            (3, "content"),
            (4, "-->"),
        ]
        ctx = ParseContext(file_path="test.md")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        assert "Multi-line" in results[0].raw_text
        assert "content" in results[0].raw_text


class TestCommentsParserEdgeCases:
    """Edge cases for comment parsing."""

    def test_no_comments_returns_empty(self):
        parser = CommentsParser()
        lines = [
            (1, "Just text"),
            (2, "More text"),
        ]
        ctx = ParseContext(file_path="test.md")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 0

    def test_unclosed_comment_not_claimed(self):
        parser = CommentsParser()
        lines = [
            (1, "<!--"),
            (2, "Unclosed comment"),
            # No closing -->
        ]
        ctx = ParseContext(file_path="test.md")

        results = list(parser.claim_and_parse(lines, ctx))

        # Unclosed comments should not be claimed (would break parsing)
        assert len(results) == 0

    def test_inline_comment_markers_not_confused(self):
        parser = CommentsParser()
        lines = [
            (1, "Use <!-- for comments and --> for closing"),
        ]
        ctx = ParseContext(file_path="test.md")

        # Line has both markers but isn't a proper comment
        # This is actually a valid single-line comment
        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1  # It's a valid comment
