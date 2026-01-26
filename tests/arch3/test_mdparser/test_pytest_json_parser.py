"""Tests for Pytest JSON Parser."""

import pytest

from elspais.arch3.Graph.MDparser.results.pytest_json import PytestJSONParser


class TestPytestJSONParserBasic:
    """Basic tests for PytestJSONParser."""

    def test_parse_passing_test(self):
        """Parses a passing test case."""
        json_content = '''
{
  "tests": [
    {
      "nodeid": "tests/test_auth.py::test_login_REQ_p00001",
      "outcome": "passed",
      "duration": 0.123
    }
  ]
}
'''
        parser = PytestJSONParser()

        results = parser.parse(json_content, "test_results.json")

        assert len(results) == 1
        assert results[0]["status"] == "passed"
        assert results[0]["name"] == "test_login_REQ_p00001"
        assert "REQ-p00001" in results[0]["validates"]

    def test_parse_failing_test(self):
        """Parses a failing test case."""
        json_content = '''
{
  "tests": [
    {
      "nodeid": "tests/test_auth.py::test_fail",
      "outcome": "failed",
      "duration": 0.5,
      "call": {
        "longrepr": "AssertionError: Expected True"
      }
    }
  ]
}
'''
        parser = PytestJSONParser()

        results = parser.parse(json_content, "test_results.json")

        assert len(results) == 1
        assert results[0]["status"] == "failed"
        assert "AssertionError" in results[0]["message"]

    def test_parse_skipped_test(self):
        """Parses a skipped test case."""
        json_content = '''
{
  "tests": [
    {
      "nodeid": "tests/test_auth.py::test_skip",
      "outcome": "skipped",
      "duration": 0
    }
  ]
}
'''
        parser = PytestJSONParser()

        results = parser.parse(json_content, "test_results.json")

        assert len(results) == 1
        assert results[0]["status"] == "skipped"

    def test_parse_error_test(self):
        """Parses a test with error."""
        json_content = '''
{
  "tests": [
    {
      "nodeid": "tests/test_auth.py::test_error",
      "outcome": "error",
      "duration": 0.1,
      "setup": {
        "message": "ImportError: No module named foo"
      }
    }
  ]
}
'''
        parser = PytestJSONParser()

        results = parser.parse(json_content, "test_results.json")

        assert len(results) == 1
        assert results[0]["status"] == "error"

    def test_parse_multiple_tests(self):
        """Parses multiple test cases."""
        json_content = '''
{
  "tests": [
    {"nodeid": "test.py::test_a", "outcome": "passed", "duration": 0.1},
    {"nodeid": "test.py::test_b", "outcome": "passed", "duration": 0.2},
    {"nodeid": "test.py::test_c", "outcome": "passed", "duration": 0.3}
  ]
}
'''
        parser = PytestJSONParser()

        results = parser.parse(json_content, "test_results.json")

        assert len(results) == 3


class TestPytestJSONParserReqExtraction:
    """Tests for requirement ID extraction."""

    def test_extracts_req_from_name(self):
        """Extracts REQ ID from test name."""
        json_content = '''
{
  "tests": [
    {
      "nodeid": "test.py::test_REQ_p00001_login",
      "outcome": "passed",
      "duration": 0.1
    }
  ]
}
'''
        parser = PytestJSONParser()

        results = parser.parse(json_content, "results.json")

        assert "REQ-p00001" in results[0]["validates"]

    def test_extracts_multiple_reqs(self):
        """Extracts multiple REQ IDs from test name."""
        json_content = '''
{
  "tests": [
    {
      "nodeid": "test.py::test_REQ_p00001_and_REQ_o00002",
      "outcome": "passed",
      "duration": 0.1
    }
  ]
}
'''
        parser = PytestJSONParser()

        results = parser.parse(json_content, "results.json")

        assert "REQ-p00001" in results[0]["validates"]
        assert "REQ-o00002" in results[0]["validates"]

    def test_extracts_assertion_refs(self):
        """Extracts assertion references like REQ-p00001-A."""
        json_content = '''
{
  "tests": [
    {
      "nodeid": "test.py::test_REQ_p00001_A",
      "outcome": "passed",
      "duration": 0.1
    }
  ]
}
'''
        parser = PytestJSONParser()

        results = parser.parse(json_content, "results.json")

        assert "REQ-p00001-A" in results[0]["validates"]


class TestPytestJSONParserEdgeCases:
    """Edge case tests for PytestJSONParser."""

    def test_invalid_json_returns_empty(self):
        """Returns empty list for invalid JSON."""
        parser = PytestJSONParser()

        results = parser.parse("not valid json", "test.json")

        assert results == []

    def test_empty_tests_array(self):
        """Handles empty tests array."""
        json_content = '{"tests": []}'
        parser = PytestJSONParser()

        results = parser.parse(json_content, "test.json")

        assert results == []

    def test_xfailed_maps_to_skipped(self):
        """Maps xfailed (expected failure) to skipped."""
        json_content = '''
{
  "tests": [
    {
      "nodeid": "test.py::test_xfail",
      "outcome": "xfailed",
      "duration": 0.1
    }
  ]
}
'''
        parser = PytestJSONParser()

        results = parser.parse(json_content, "test.json")

        assert results[0]["status"] == "skipped"

    def test_xpassed_maps_to_passed(self):
        """Maps xpassed (unexpected pass) to passed."""
        json_content = '''
{
  "tests": [
    {
      "nodeid": "test.py::test_xpass",
      "outcome": "xpassed",
      "duration": 0.1
    }
  ]
}
'''
        parser = PytestJSONParser()

        results = parser.parse(json_content, "test.json")

        assert results[0]["status"] == "passed"

    def test_simple_list_format(self):
        """Handles simple list format."""
        json_content = '''
[
  {"name": "test_a", "status": "passed", "duration": 0.1},
  {"name": "test_b", "status": "failed", "duration": 0.2, "message": "Failed"}
]
'''
        parser = PytestJSONParser()

        results = parser.parse(json_content, "test.json")

        assert len(results) == 2
        assert results[0]["status"] == "passed"
        assert results[1]["status"] == "failed"

    def test_nodeid_with_class(self):
        """Handles nodeid with class name."""
        json_content = '''
{
  "tests": [
    {
      "nodeid": "tests/test_auth.py::TestLogin::test_valid_user",
      "outcome": "passed",
      "duration": 0.1
    }
  ]
}
'''
        parser = PytestJSONParser()

        results = parser.parse(json_content, "test.json")

        assert results[0]["name"] == "TestLogin::test_valid_user"
        assert results[0]["classname"] == "tests/test_auth.py"


class TestPytestJSONParserCanParse:
    """Tests for can_parse method."""

    def test_can_parse_pytest_json(self):
        """Returns True for pytest JSON files."""
        from pathlib import Path

        parser = PytestJSONParser()

        assert parser.can_parse(Path("pytest-results.json")) is True
        assert parser.can_parse(Path("test-results.json")) is True
        assert parser.can_parse(Path("results.json")) is True

    def test_cannot_parse_non_json(self):
        """Returns False for non-JSON files."""
        from pathlib import Path

        parser = PytestJSONParser()

        assert parser.can_parse(Path("results.xml")) is False
        assert parser.can_parse(Path("test.py")) is False
