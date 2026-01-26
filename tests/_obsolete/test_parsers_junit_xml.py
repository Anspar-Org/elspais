"""Tests for elspais.parsers.junit_xml module."""

import pytest
from pathlib import Path


class TestJUnitXMLParser:
    """Tests for JUnitXMLParser class."""

    @pytest.fixture
    def parser(self):
        """Create a JUnitXMLParser instance."""
        from elspais.parsers.junit_xml import JUnitXMLParser

        return JUnitXMLParser()

    @pytest.fixture
    def source(self):
        """Create a mock SourceLocation."""
        from elspais.core.graph import SourceLocation

        return SourceLocation(path="tests/results.xml", line=1)

    @pytest.fixture
    def schema(self):
        """Create a mock NodeTypeSchema."""
        from elspais.core.graph_schema import NodeTypeSchema

        return NodeTypeSchema(
            name="result",
            label_template="{status}: {name} ({duration}ms)",
        )

    def test_parse_simple_testsuite(self, parser, source, schema):
        """Test parsing a simple testsuite with passing tests."""
        xml_content = """<?xml version="1.0" encoding="utf-8"?>
        <testsuite name="test_module" tests="2" failures="0" errors="0">
            <testcase classname="test_module" name="test_one" time="0.001"/>
            <testcase classname="test_module" name="test_two" time="0.002"/>
        </testsuite>
        """
        nodes = parser.parse(xml_content, source, schema)

        assert len(nodes) == 2
        assert nodes[0].test_result.status == "passed"
        assert nodes[1].test_result.status == "passed"
        assert nodes[0].test_result.duration == 0.001
        assert nodes[1].test_result.duration == 0.002

    def test_parse_failed_test(self, parser, source, schema):
        """Test parsing a testsuite with a failed test."""
        xml_content = """<?xml version="1.0" encoding="utf-8"?>
        <testsuite name="test_module" tests="1" failures="1">
            <testcase classname="test_module" name="test_failing" time="0.5">
                <failure message="AssertionError: expected True">
                    Full traceback here
                </failure>
            </testcase>
        </testsuite>
        """
        nodes = parser.parse(xml_content, source, schema)

        assert len(nodes) == 1
        assert nodes[0].test_result.status == "failed"
        assert "AssertionError" in nodes[0].test_result.message

    def test_parse_error_test(self, parser, source, schema):
        """Test parsing a testsuite with an error."""
        xml_content = """<?xml version="1.0" encoding="utf-8"?>
        <testsuite name="test_module" tests="1" errors="1">
            <testcase classname="test_module" name="test_error" time="0.1">
                <error message="RuntimeError: something broke"/>
            </testcase>
        </testsuite>
        """
        nodes = parser.parse(xml_content, source, schema)

        assert len(nodes) == 1
        assert nodes[0].test_result.status == "error"
        assert "RuntimeError" in nodes[0].test_result.message

    def test_parse_skipped_test(self, parser, source, schema):
        """Test parsing a testsuite with a skipped test."""
        xml_content = """<?xml version="1.0" encoding="utf-8"?>
        <testsuite name="test_module" tests="1" skipped="1">
            <testcase classname="test_module" name="test_skipped" time="0">
                <skipped message="Not implemented yet"/>
            </testcase>
        </testsuite>
        """
        nodes = parser.parse(xml_content, source, schema)

        assert len(nodes) == 1
        assert nodes[0].test_result.status == "skipped"
        assert "Not implemented" in nodes[0].test_result.message

    def test_parse_extracts_requirement_ids(self, parser, source, schema):
        """Test that requirement IDs are extracted from test names."""
        xml_content = """<?xml version="1.0" encoding="utf-8"?>
        <testsuite name="test_module">
            <testcase classname="test_REQ_p00001" name="test_validates_REQ_p00001_A" time="0.01"/>
        </testsuite>
        """
        nodes = parser.parse(xml_content, source, schema)

        assert len(nodes) == 1
        # IDs should be normalized to use hyphens
        validates = nodes[0].metrics["_validates_targets"]
        assert "REQ-p00001" in validates or "REQ-p00001-A" in validates

    def test_parse_testsuites_wrapper(self, parser, source, schema):
        """Test parsing with <testsuites> wrapper element."""
        xml_content = """<?xml version="1.0" encoding="utf-8"?>
        <testsuites>
            <testsuite name="suite1" tests="1">
                <testcase classname="suite1" name="test1" time="0.1"/>
            </testsuite>
            <testsuite name="suite2" tests="1">
                <testcase classname="suite2" name="test2" time="0.2"/>
            </testsuite>
        </testsuites>
        """
        nodes = parser.parse(xml_content, source, schema)

        assert len(nodes) == 2
        assert nodes[0].metrics["test_class"] == "suite1"
        assert nodes[1].metrics["test_class"] == "suite2"

    def test_parse_invalid_xml(self, parser, source, schema):
        """Test parsing invalid XML returns empty list."""
        xml_content = "this is not valid xml <broken>"
        nodes = parser.parse(xml_content, source, schema)

        assert nodes == []

    def test_parse_invalid_time(self, parser, source, schema):
        """Test parsing with invalid time value defaults to 0."""
        xml_content = """<?xml version="1.0" encoding="utf-8"?>
        <testsuite name="test_module">
            <testcase classname="test_module" name="test_one" time="invalid"/>
        </testsuite>
        """
        nodes = parser.parse(xml_content, source, schema)

        assert len(nodes) == 1
        assert nodes[0].test_result.duration == 0.0

    def test_can_parse_junit_files(self, parser):
        """Test can_parse identifies JUnit XML files."""
        assert parser.can_parse(Path("junit-results.xml")) is True
        assert parser.can_parse(Path("test-results.xml")) is True
        assert parser.can_parse(Path("pytest_junit.xml")) is True

    def test_can_parse_rejects_non_junit(self, parser):
        """Test can_parse rejects non-JUnit files."""
        assert parser.can_parse(Path("config.xml")) is False
        assert parser.can_parse(Path("data.json")) is False
        assert parser.can_parse(Path("test.py")) is False

    def test_message_truncation(self, parser, source, schema):
        """Test that long messages are truncated to 200 chars."""
        long_message = "x" * 500
        xml_content = f"""<?xml version="1.0" encoding="utf-8"?>
        <testsuite name="test_module">
            <testcase classname="test_module" name="test_one" time="0.1">
                <failure message="{long_message}"/>
            </testcase>
        </testsuite>
        """
        nodes = parser.parse(xml_content, source, schema)

        assert len(nodes) == 1
        assert len(nodes[0].test_result.message) == 200


class TestCreateParser:
    """Tests for create_parser factory function."""

    def test_create_parser(self):
        """Test that create_parser returns a JUnitXMLParser."""
        from elspais.parsers.junit_xml import JUnitXMLParser, create_parser

        parser = create_parser()
        assert isinstance(parser, JUnitXMLParser)
