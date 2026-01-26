"""Tests for CodeParser - Priority 70 code reference parser."""

import pytest

from elspais.arch3.Graph.MDparser import ParseContext
from elspais.arch3.Graph.MDparser.code import CodeParser


class TestCodeParserPriority:
    """Tests for CodeParser priority."""

    def test_priority_is_70(self):
        parser = CodeParser()
        assert parser.priority == 70


class TestCodeParserBasic:
    """Tests for basic code reference parsing."""

    def test_claims_implements_comment(self):
        parser = CodeParser()
        lines = [
            (1, "def authenticate():"),
            (2, "    # Implements: REQ-p00001-A"),
            (3, "    pass"),
        ]
        ctx = ParseContext(file_path="src/auth.py")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        assert results[0].content_type == "code_ref"
        assert results[0].start_line == 2
        assert "REQ-p00001-A" in results[0].parsed_data["implements"]

    def test_claims_validates_comment(self):
        parser = CodeParser()
        lines = [
            (1, "def test_auth():"),
            (2, "    # Validates: REQ-p00001"),
            (3, "    assert True"),
        ]
        ctx = ParseContext(file_path="tests/test_auth.py")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        assert results[0].parsed_data["validates"] == ["REQ-p00001"]

    def test_no_code_refs_returns_empty(self):
        parser = CodeParser()
        lines = [
            (1, "def regular_function():"),
            (2, "    # Just a regular comment"),
            (3, "    pass"),
        ]
        ctx = ParseContext(file_path="src/utils.py")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 0
