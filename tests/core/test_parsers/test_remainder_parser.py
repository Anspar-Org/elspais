"""Tests for RemainderParser - Priority 999 catch-all parser."""

import pytest

from elspais.graph.parsers import ParseContext
from elspais.graph.parsers.remainder import RemainderParser


class TestRemainderParserPriority:
    """Tests for RemainderParser priority."""

    def test_priority_is_999(self):
        parser = RemainderParser()
        assert parser.priority == 999


class TestRemainderParserBehavior:
    """Tests for RemainderParser line grouping."""

    def test_claims_all_remaining_lines(self):
        parser = RemainderParser()
        lines = [
            (1, "Line one"),
            (2, "Line two"),
            (3, "Line three"),
        ]
        ctx = ParseContext(file_path="test.md")

        results = list(parser.claim_and_parse(lines, ctx))

        # Should claim all lines as a single remainder block
        assert len(results) == 1
        assert results[0].content_type == "remainder"
        assert results[0].start_line == 1
        assert results[0].end_line == 3

    def test_groups_contiguous_lines(self):
        parser = RemainderParser()
        lines = [
            (1, "Line one"),
            (2, "Line two"),
            # Gap at line 3
            (4, "Line four"),
            (5, "Line five"),
        ]
        ctx = ParseContext(file_path="test.md")

        results = list(parser.claim_and_parse(lines, ctx))

        # Should create two groups due to gap
        assert len(results) == 2
        assert results[0].start_line == 1
        assert results[0].end_line == 2
        assert results[1].start_line == 4
        assert results[1].end_line == 5

    def test_empty_lines_returns_nothing(self):
        parser = RemainderParser()
        lines = []
        ctx = ParseContext(file_path="test.md")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 0

    def test_single_line(self):
        parser = RemainderParser()
        lines = [(5, "Only line")]
        ctx = ParseContext(file_path="test.md")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        assert results[0].start_line == 5
        assert results[0].end_line == 5

    def test_preserves_raw_text(self):
        parser = RemainderParser()
        lines = [
            (1, "First line"),
            (2, "Second line"),
        ]
        ctx = ParseContext(file_path="test.md")

        results = list(parser.claim_and_parse(lines, ctx))

        assert "First line" in results[0].raw_text
        assert "Second line" in results[0].raw_text

    def test_handles_blank_lines_in_content(self):
        parser = RemainderParser()
        lines = [
            (1, "Line one"),
            (2, ""),
            (3, "Line three"),
        ]
        ctx = ParseContext(file_path="test.md")

        results = list(parser.claim_and_parse(lines, ctx))

        # Blank lines shouldn't break grouping when contiguous
        assert len(results) == 1
        assert results[0].start_line == 1
        assert results[0].end_line == 3
