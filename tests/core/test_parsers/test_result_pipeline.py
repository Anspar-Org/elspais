# Validates REQ-d00054
"""Tests for result parser claim_and_parse() pipeline integration.

Validates that JUnitXMLParser and PytestJSONParser correctly implement
the LineClaimingParser protocol via claim_and_parse(), returning
ParsedContent objects with content_type="test_result".
"""

from __future__ import annotations

from elspais.graph.parsers import ParseContext, ParsedContent
from elspais.graph.parsers.results.junit_xml import JUnitXMLParser
from elspais.graph.parsers.results.pytest_json import PytestJSONParser


class TestJUnitXMLParserPriority:
    """Tests for JUnitXMLParser priority."""

    def test_REQ_d00054_priority_is_90(self):
        """JUnitXMLParser has priority 90."""
        parser = JUnitXMLParser()
        assert parser.priority == 90


class TestPytestJSONParserPriority:
    """Tests for PytestJSONParser priority."""

    def test_REQ_d00054_priority_is_90(self):
        """PytestJSONParser has priority 90."""
        parser = PytestJSONParser()
        assert parser.priority == 90


class TestJUnitXMLClaimAndParse:
    """Tests for JUnitXMLParser.claim_and_parse()."""

    def test_REQ_d00054_returns_parsed_content_with_test_result_type(self):
        """claim_and_parse yields ParsedContent with content_type='test_result'."""
        xml = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<testsuite tests="1">\n'
            '  <testcase classname="tests.test_example.TestFoo"'
            ' name="test_REQ_d00054_bar" time="0.01"/>\n'
            "</testsuite>"
        )
        lines = [(i + 1, line) for i, line in enumerate(xml.split("\n"))]
        context = ParseContext(file_path="results/junit.xml")
        parser = JUnitXMLParser()

        results = list(parser.claim_and_parse(lines, context))

        assert len(results) == 1
        assert isinstance(results[0], ParsedContent)
        assert results[0].content_type == "test_result"

    def test_REQ_d00054_parsed_data_contains_expected_keys(self):
        """Parsed data dict contains standard test result keys."""
        xml = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<testsuite tests="1">\n'
            '  <testcase classname="tests.test_check.TestCheck"'
            ' name="test_REQ_d00054_pass" time="0.05"/>\n'
            "</testsuite>"
        )
        lines = [(i + 1, line) for i, line in enumerate(xml.split("\n"))]
        context = ParseContext(file_path="results/junit.xml")
        parser = JUnitXMLParser()

        results = list(parser.claim_and_parse(lines, context))

        data = results[0].parsed_data
        assert "id" in data
        assert "name" in data
        assert "classname" in data
        assert "status" in data
        assert "duration" in data
        assert "validates" in data
        assert "test_id" in data
        assert data["name"] == "test_REQ_d00054_pass"
        assert data["classname"] == "tests.test_check.TestCheck"
        assert data["status"] == "passed"
        assert data["duration"] == 0.05

    def test_REQ_d00054_multiple_testcases_yield_multiple_results(self):
        """Multiple testcases in XML produce multiple ParsedContent objects."""
        xml = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<testsuite tests="2">\n'
            '  <testcase classname="tests.test_a" name="test_one" time="0.01"/>\n'
            '  <testcase classname="tests.test_a" name="test_two" time="0.02"/>\n'
            "</testsuite>"
        )
        lines = [(i + 1, line) for i, line in enumerate(xml.split("\n"))]
        context = ParseContext(file_path="results/junit.xml")
        parser = JUnitXMLParser()

        results = list(parser.claim_and_parse(lines, context))

        assert len(results) == 2
        assert all(r.content_type == "test_result" for r in results)

    def test_REQ_d00054_failed_testcase_reports_failure_status(self):
        """A failed testcase has status='failed' in parsed data."""
        xml = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<testsuite tests="1">\n'
            '  <testcase classname="tests.test_b" name="test_fail" time="0.01">\n'
            '    <failure message="assert False"/>\n'
            "  </testcase>\n"
            "</testsuite>"
        )
        lines = [(i + 1, line) for i, line in enumerate(xml.split("\n"))]
        context = ParseContext(file_path="results/junit.xml")
        parser = JUnitXMLParser()

        results = list(parser.claim_and_parse(lines, context))

        assert len(results) == 1
        assert results[0].parsed_data["status"] == "failed"
        assert results[0].parsed_data["message"] == "assert False"

    def test_REQ_d00054_empty_xml_yields_no_results(self):
        """Invalid/empty XML content produces no ParsedContent."""
        lines = [(1, "not xml at all")]
        context = ParseContext(file_path="results/junit.xml")
        parser = JUnitXMLParser()

        results = list(parser.claim_and_parse(lines, context))

        assert results == []


class TestPytestJSONClaimAndParse:
    """Tests for PytestJSONParser.claim_and_parse()."""

    def test_REQ_d00054_returns_parsed_content_with_test_result_type(self):
        """claim_and_parse yields ParsedContent with content_type='test_result'."""
        json_content = (
            '{"tests": [{"nodeid": "tests/test_foo.py::test_REQ_d00054_bar",'
            ' "outcome": "passed", "duration": 0.01}]}'
        )
        lines = [(1, json_content)]
        context = ParseContext(file_path="results/pytest.json")
        parser = PytestJSONParser()

        results = list(parser.claim_and_parse(lines, context))

        assert len(results) == 1
        assert isinstance(results[0], ParsedContent)
        assert results[0].content_type == "test_result"

    def test_REQ_d00054_parsed_data_contains_expected_keys(self):
        """Parsed data dict contains standard test result keys."""
        json_content = (
            '{"tests": [{"nodeid": "tests/test_check.py::TestCheck::test_REQ_d00054_pass",'
            ' "outcome": "passed", "duration": 0.05}]}'
        )
        lines = [(1, json_content)]
        context = ParseContext(file_path="results/pytest.json")
        parser = PytestJSONParser()

        results = list(parser.claim_and_parse(lines, context))

        data = results[0].parsed_data
        assert "id" in data
        assert "name" in data
        assert "classname" in data
        assert "status" in data
        assert "duration" in data
        assert "validates" in data
        assert "test_id" in data
        assert data["status"] == "passed"
        assert data["duration"] == 0.05

    def test_REQ_d00054_multiple_tests_yield_multiple_results(self):
        """Multiple tests in JSON produce multiple ParsedContent objects."""
        json_content = (
            '{"tests": ['
            '{"nodeid": "tests/test_a.py::test_one", "outcome": "passed", "duration": 0.01},'
            '{"nodeid": "tests/test_a.py::test_two", "outcome": "failed", "duration": 0.02}'
            "]}"
        )
        lines = [(1, json_content)]
        context = ParseContext(file_path="results/pytest.json")
        parser = PytestJSONParser()

        results = list(parser.claim_and_parse(lines, context))

        assert len(results) == 2
        assert all(r.content_type == "test_result" for r in results)

    def test_REQ_d00054_failed_test_reports_failure_status(self):
        """A failed test has status='failed' in parsed data."""
        json_content = (
            '{"tests": [{"nodeid": "tests/test_b.py::test_fail",'
            ' "outcome": "failed", "duration": 0.01,'
            ' "call": {"longrepr": "AssertionError: bad"}}]}'
        )
        lines = [(1, json_content)]
        context = ParseContext(file_path="results/pytest.json")
        parser = PytestJSONParser()

        results = list(parser.claim_and_parse(lines, context))

        assert len(results) == 1
        assert results[0].parsed_data["status"] == "failed"
        assert "AssertionError" in results[0].parsed_data["message"]

    def test_REQ_d00054_invalid_json_yields_no_results(self):
        """Invalid JSON content produces no ParsedContent."""
        lines = [(1, "not json {{{")]
        context = ParseContext(file_path="results/pytest.json")
        parser = PytestJSONParser()

        results = list(parser.claim_and_parse(lines, context))

        assert results == []

    def test_REQ_d00054_simple_list_format(self):
        """Simple list format with classname/name produces results."""
        json_content = (
            '[{"classname": "tests.test_foo.TestBar", "name": "test_baz",'
            ' "status": "passed", "duration": 0.03}]'
        )
        lines = [(1, json_content)]
        context = ParseContext(file_path="results/pytest.json")
        parser = PytestJSONParser()

        results = list(parser.claim_and_parse(lines, context))

        assert len(results) == 1
        assert results[0].content_type == "test_result"
        assert results[0].parsed_data["name"] == "test_baz"
        assert results[0].parsed_data["status"] == "passed"
