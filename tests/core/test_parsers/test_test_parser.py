"""Tests for TestParser - Priority 80 test reference parser."""

import pytest

from elspais.graph.parsers import ParseContext
from elspais.graph.parsers.test import TestParser


class TestTestParserPriority:
    """Tests for TestParser priority."""

    def test_priority_is_80(self):
        parser = TestParser()
        assert parser.priority == 80


class TestTestParserBasic:
    """Tests for basic test reference parsing."""

    def test_claims_test_with_req_reference(self):
        parser = TestParser()
        lines = [
            (1, "def test_user_auth_REQ_p00001():"),
            (2, "    assert True"),
        ]
        ctx = ParseContext(file_path="tests/test_auth.py")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        assert results[0].content_type == "test_ref"
        assert "REQ-p00001" in results[0].parsed_data["validates"]

    def test_claims_test_with_inline_marker(self):
        parser = TestParser()
        lines = [
            (1, "def test_something():"),
            (2, "    # Tests REQ-p00001"),
            (3, "    assert True"),
        ]
        ctx = ParseContext(file_path="tests/test_auth.py")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 1
        assert "REQ-p00001" in results[0].parsed_data["validates"]

    def test_no_test_refs_returns_empty(self):
        parser = TestParser()
        lines = [
            (1, "def test_unrelated():"),
            (2, "    assert 1 + 1 == 2"),
        ]
        ctx = ParseContext(file_path="tests/test_math.py")

        results = list(parser.claim_and_parse(lines, ctx))

        assert len(results) == 0
