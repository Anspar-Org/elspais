# Validates REQ-d00054
"""Tests for the parse stage of the result pipeline.

JUnitXMLParser and PytestJSONParser read an artifact into result records.
A record carries what the producer wrote plus its position in the artifact;
ingestion turns each record into a RESULT node.
"""

from __future__ import annotations

from elspais.graph.parsers.results.junit_xml import JUnitXMLParser
from elspais.graph.parsers.results.pytest_json import PytestJSONParser


class TestJUnitXMLParseStage:
    """Tests for the records JUnitXMLParser.parse() produces."""

    # Verifies: REQ-d00054
    def test_REQ_d00054_one_testcase_yields_one_record(self):
        """A testcase yields one result record."""
        xml = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<testsuite tests="1">\n'
            '  <testcase classname="tests.test_example.TestFoo"'
            ' name="test_REQ_d00054_bar" time="0.01"/>\n'
            "</testsuite>"
        )
        parser = JUnitXMLParser()

        results = parser.parse(xml, "results/junit.xml")

        assert len(results) == 1
        assert results[0]["name"] == "test_REQ_d00054_bar"

    # Verifies: REQ-d00054
    def test_REQ_d00054_parsed_data_contains_expected_keys(self):
        """A record carries exactly the standard test result keys."""
        xml = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<testsuite tests="1">\n'
            '  <testcase classname="tests.test_check.TestCheck"'
            ' name="test_REQ_d00054_pass" time="0.05"/>\n'
            "</testsuite>"
        )
        parser = JUnitXMLParser()

        results = parser.parse(xml, "results/junit.xml")

        data = results[0]
        assert set(data) == {
            "ordinal",
            "name",
            "classname",
            "status",
            "duration",
            "message",
            "source_path",
            "test_id",
            "line",
            "result_file",
            "result_line",
            "suite_hostname",
        }
        assert data["name"] == "test_REQ_d00054_pass"
        assert data["classname"] == "tests.test_check.TestCheck"
        assert data["status"] == "passed"
        assert data["duration"] == 0.05

    # Verifies: REQ-d00054
    def test_REQ_d00054_multiple_testcases_yield_multiple_results(self):
        """Multiple testcases in XML produce one record each, numbered in order."""
        xml = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<testsuite tests="2">\n'
            '  <testcase classname="tests.test_a" name="test_one" time="0.01"/>\n'
            '  <testcase classname="tests.test_a" name="test_two" time="0.02"/>\n'
            "</testsuite>"
        )
        parser = JUnitXMLParser()

        results = parser.parse(xml, "results/junit.xml")

        assert len(results) == 2
        assert [r["ordinal"] for r in results] == [1, 2]

    # Verifies: REQ-d00054
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
        parser = JUnitXMLParser()

        results = parser.parse(xml, "results/junit.xml")

        assert len(results) == 1
        assert results[0]["status"] == "failed"
        assert results[0]["message"] == "assert False"

    # Verifies: REQ-d00054
    def test_REQ_d00054_empty_xml_yields_no_results(self):
        """Invalid/empty XML content produces no records."""
        parser = JUnitXMLParser()

        results = parser.parse("not xml at all", "results/junit.xml")

        assert results == []


class TestPytestJSONParseStage:
    """Tests for the records PytestJSONParser.parse() produces."""

    # Verifies: REQ-d00054
    def test_REQ_d00054_one_testcase_yields_one_record(self):
        """A testcase yields one result record."""
        json_content = (
            '{"tests": [{"nodeid": "tests/test_foo.py::test_REQ_d00054_bar",'
            ' "outcome": "passed", "duration": 0.01}]}'
        )
        parser = PytestJSONParser()

        results = parser.parse(json_content, "results/pytest.json")

        assert len(results) == 1
        assert results[0]["name"] == "test_REQ_d00054_bar"

    # Verifies: REQ-d00054
    def test_REQ_d00054_parsed_data_contains_expected_keys(self):
        """A record carries exactly the standard test result keys."""
        json_content = (
            '{"tests": [{"nodeid": "tests/test_check.py::TestCheck::test_REQ_d00054_pass",'
            ' "outcome": "passed", "duration": 0.05}]}'
        )
        parser = PytestJSONParser()

        results = parser.parse(json_content, "results/pytest.json")

        data = results[0]
        assert set(data) == {
            "ordinal",
            "name",
            "classname",
            "status",
            "duration",
            "message",
            "source_path",
            "test_id",
            "result_file",
            "result_line",
        }
        assert data["status"] == "passed"
        assert data["duration"] == 0.05

    # Verifies: REQ-d00054
    def test_REQ_d00054_multiple_tests_yield_multiple_results(self):
        """Multiple tests in JSON produce one record each, numbered in order."""
        json_content = (
            '{"tests": ['
            '{"nodeid": "tests/test_a.py::test_one", "outcome": "passed", "duration": 0.01},'
            '{"nodeid": "tests/test_a.py::test_two", "outcome": "failed", "duration": 0.02}'
            "]}"
        )
        parser = PytestJSONParser()

        results = parser.parse(json_content, "results/pytest.json")

        assert len(results) == 2
        assert [r["ordinal"] for r in results] == [1, 2]

    # Verifies: REQ-d00054
    def test_REQ_d00054_failed_test_reports_failure_status(self):
        """A failed test has status='failed' in parsed data."""
        json_content = (
            '{"tests": [{"nodeid": "tests/test_b.py::test_fail",'
            ' "outcome": "failed", "duration": 0.01,'
            ' "call": {"longrepr": "AssertionError: bad"}}]}'
        )
        parser = PytestJSONParser()

        results = parser.parse(json_content, "results/pytest.json")

        assert len(results) == 1
        assert results[0]["status"] == "failed"
        assert "AssertionError" in results[0]["message"]

    # Verifies: REQ-d00054
    def test_REQ_d00054_invalid_json_yields_no_results(self):
        """Invalid JSON content produces no records."""
        parser = PytestJSONParser()

        results = parser.parse("not json {{{", "results/pytest.json")

        assert results == []

    # Verifies: REQ-d00054
    def test_REQ_d00054_simple_list_format(self):
        """Simple list format with classname/name produces results."""
        json_content = (
            '[{"classname": "tests.test_foo.TestBar", "name": "test_baz",'
            ' "status": "passed", "duration": 0.03}]'
        )
        parser = PytestJSONParser()

        results = parser.parse(json_content, "results/pytest.json")

        assert len(results) == 1
        assert results[0]["name"] == "test_baz"
        assert results[0]["status"] == "passed"
