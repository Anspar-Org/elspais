"""Tests for Heredocs Parser.

The heredocs parser recognizes embedded requirement definitions in test files
and claims them as plain-text blocks, preventing the requirement parser from
treating them as real requirements.
"""

import pytest

from elspais.arch3.Graph.MDparser.heredocs import HeredocsParser
from elspais.arch3.Graph.MDparser import ParseContext


class TestHeredocsParserBasic:
    """Basic tests for HeredocsParser."""

    def test_parser_has_low_priority(self):
        """Parser has priority 10 (runs before requirements)."""
        parser = HeredocsParser()
        assert parser.priority == 10

    def test_claims_triple_quoted_string_with_req(self):
        """Claims triple-quoted strings containing requirement patterns."""
        lines = [
            (1, 'TEST_REQ = """'),
            (2, "## REQ-t00001: Test Requirement"),
            (3, "**Level**: DEV | **Status**: Active"),
            (4, '"""'),
        ]
        context = ParseContext(
            file_path="tests/test_fixtures.py",
        )
        parser = HeredocsParser()

        results = list(parser.claim_and_parse(lines, context))

        # Should claim lines 1-4
        assert len(results) == 1
        assert results[0].start_line == 1
        assert results[0].end_line == 4
        assert results[0].content_type == "heredoc"

    def test_ignores_strings_without_req(self):
        """Does not claim strings that don't contain REQ patterns."""
        lines = [
            (1, 'NORMAL = """'),
            (2, "This is just a normal string"),
            (3, "without any requirement patterns"),
            (4, '"""'),
        ]
        context = ParseContext(
            file_path="tests/test_fixtures.py",
        )
        parser = HeredocsParser()

        results = list(parser.claim_and_parse(lines, context))

        # Should not claim any lines
        assert len(results) == 0

    def test_claims_single_quoted_heredoc(self):
        """Claims single-quoted heredoc strings with REQ patterns."""
        lines = [
            (1, "TEST_DATA = '''"),
            (2, "## REQ-p00001: Product Requirement"),
            (3, "This is test data"),
            (4, "'''"),
        ]
        context = ParseContext(
            file_path="tests/test_data.py",
        )
        parser = HeredocsParser()

        results = list(parser.claim_and_parse(lines, context))

        assert len(results) == 1
        assert results[0].content_type == "heredoc"


class TestHeredocsParserEdgeCases:
    """Edge case tests for HeredocsParser."""

    def test_claims_multiline_f_string(self):
        """Claims f-strings that contain REQ patterns."""
        lines = [
            (1, 'content = f"""'),
            (2, "REQ-x00001: Embedded requirement"),
            (3, '"""'),
        ]
        context = ParseContext(
            file_path="tests/test_gen.py",
        )
        parser = HeredocsParser()

        results = list(parser.claim_and_parse(lines, context))

        assert len(results) == 1

    def test_handles_multiple_heredocs(self):
        """Handles multiple heredoc blocks in same file."""
        lines = [
            (1, 'REQ1 = """'),
            (2, "REQ-a00001: First"),
            (3, '"""'),
            (4, ""),
            (5, 'REQ2 = """'),
            (6, "REQ-b00002: Second"),
            (7, '"""'),
        ]
        context = ParseContext(
            file_path="tests/test_multi.py",
        )
        parser = HeredocsParser()

        results = list(parser.claim_and_parse(lines, context))

        assert len(results) == 2
        assert results[0].start_line == 1
        assert results[0].end_line == 3
        assert results[1].start_line == 5
        assert results[1].end_line == 7

    def test_non_python_file_skipped(self):
        """Skips non-Python files."""
        lines = [
            (1, "REQ-x00001: Requirement"),
        ]
        context = ParseContext(
            file_path="spec/requirements.md",
        )
        parser = HeredocsParser()

        results = list(parser.claim_and_parse(lines, context))

        # Should not claim markdown file content
        assert len(results) == 0

    def test_preserves_raw_text(self):
        """Preserves the raw text content in the result."""
        lines = [
            (1, 'FIXTURE = """'),
            (2, "## REQ-t00001: Test Requirement"),
            (3, "Some body text"),
            (4, '"""'),
        ]
        context = ParseContext(
            file_path="tests/conftest.py",
        )
        parser = HeredocsParser()

        results = list(parser.claim_and_parse(lines, context))

        assert len(results) == 1
        # The raw_text should contain the heredoc content
        assert "REQ-t00001" in results[0].raw_text
        assert "Test Requirement" in results[0].raw_text


class TestHeredocsParserRubyStyle:
    """Tests for Ruby/Shell style heredocs."""

    def test_claims_shell_heredoc(self):
        """Claims shell-style heredocs with REQ patterns."""
        lines = [
            (1, "cat << 'EOF'"),
            (2, "## REQ-s00001: Shell Requirement"),
            (3, "Some content here"),
            (4, "EOF"),
        ]
        context = ParseContext(
            file_path="tests/test_script.sh",
        )
        parser = HeredocsParser()

        results = list(parser.claim_and_parse(lines, context))

        assert len(results) == 1
        assert results[0].content_type == "heredoc"

    def test_claims_shell_heredoc_double_quotes(self):
        """Claims shell heredocs with double quotes in marker."""
        lines = [
            (1, 'cat << "END"'),
            (2, "REQ-x00001: Some req"),
            (3, "END"),
        ]
        context = ParseContext(
            file_path="script.bash",
        )
        parser = HeredocsParser()

        results = list(parser.claim_and_parse(lines, context))

        assert len(results) == 1
