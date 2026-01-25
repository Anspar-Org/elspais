"""Tests for elspais.parsers.pytest_json module."""

import pytest
from pathlib import Path


class TestPytestJSONParser:
    """Tests for PytestJSONParser class."""

    @pytest.fixture
    def parser(self):
        """Create a PytestJSONParser instance."""
        from elspais.parsers.pytest_json import PytestJSONParser

        return PytestJSONParser()

    @pytest.fixture
    def source(self):
        """Create a mock SourceLocation."""
        from elspais.core.graph import SourceLocation

        return SourceLocation(path="tests/results.json", line=1)

    @pytest.fixture
    def schema(self):
        """Create a mock NodeTypeSchema."""
        from elspais.core.graph_schema import NodeTypeSchema

        return NodeTypeSchema(
            name="result",
            label_template="{status}: {name} ({duration}ms)",
        )

    def test_parse_pytest_json_report_format(self, parser, source, schema):
        """Test parsing pytest-json-report format."""
        import json

        content = json.dumps({
            "tests": [
                {
                    "nodeid": "tests/test_foo.py::test_one",
                    "outcome": "passed",
                    "duration": 0.001,
                },
                {
                    "nodeid": "tests/test_foo.py::test_two",
                    "outcome": "passed",
                    "duration": 0.002,
                },
            ]
        })
        nodes = parser.parse(content, source, schema)

        assert len(nodes) == 2
        assert nodes[0].test_result.status == "passed"
        assert nodes[1].test_result.status == "passed"

    def test_parse_failed_test(self, parser, source, schema):
        """Test parsing a failed test with longrepr."""
        import json

        content = json.dumps({
            "tests": [
                {
                    "nodeid": "tests/test_foo.py::test_failing",
                    "outcome": "failed",
                    "duration": 0.5,
                    "call": {
                        "longrepr": "AssertionError: expected True but got False",
                    },
                },
            ]
        })
        nodes = parser.parse(content, source, schema)

        assert len(nodes) == 1
        assert nodes[0].test_result.status == "failed"
        assert "AssertionError" in nodes[0].test_result.message

    def test_parse_skipped_test(self, parser, source, schema):
        """Test parsing a skipped test."""
        import json

        content = json.dumps({
            "tests": [
                {
                    "nodeid": "tests/test_foo.py::test_skipped",
                    "outcome": "skipped",
                    "duration": 0,
                },
            ]
        })
        nodes = parser.parse(content, source, schema)

        assert len(nodes) == 1
        assert nodes[0].test_result.status == "skipped"

    def test_parse_extracts_requirement_ids(self, parser, source, schema):
        """Test that requirement IDs are extracted from test names."""
        import json

        content = json.dumps({
            "tests": [
                {
                    "nodeid": "tests/test_REQ_p00001.py::test_validates_REQ_p00001",
                    "outcome": "passed",
                    "duration": 0.01,
                },
            ]
        })
        nodes = parser.parse(content, source, schema)

        assert len(nodes) == 1
        validates = nodes[0].metrics["_validates_targets"]
        # IDs normalized to use hyphens
        assert any("REQ-p00001" in v for v in validates)

    def test_parse_wrapped_report_format(self, parser, source, schema):
        """Test parsing report wrapped in 'report' key."""
        import json

        content = json.dumps({
            "report": {
                "tests": [
                    {
                        "nodeid": "tests/test_foo.py::test_one",
                        "outcome": "passed",
                        "duration": 0.1,
                    },
                ]
            }
        })
        nodes = parser.parse(content, source, schema)

        assert len(nodes) == 1
        assert nodes[0].test_result.status == "passed"

    def test_parse_array_format(self, parser, source, schema):
        """Test parsing when JSON is just an array of tests."""
        import json

        content = json.dumps([
            {"name": "test_one", "outcome": "passed", "duration": 0.1},
            {"name": "test_two", "outcome": "failed", "duration": 0.2},
        ])
        nodes = parser.parse(content, source, schema)

        assert len(nodes) == 2
        assert nodes[0].test_result.status == "passed"
        assert nodes[1].test_result.status == "failed"

    def test_parse_invalid_json(self, parser, source, schema):
        """Test parsing invalid JSON returns empty list."""
        content = "this is not valid json {{"
        nodes = parser.parse(content, source, schema)

        assert nodes == []

    def test_normalize_status_variants(self, parser):
        """Test status normalization handles various formats."""
        assert parser._normalize_status("passed") == "passed"
        assert parser._normalize_status("PASSED") == "passed"
        assert parser._normalize_status("pass") == "passed"
        assert parser._normalize_status("success") == "passed"

        assert parser._normalize_status("failed") == "failed"
        assert parser._normalize_status("fail") == "failed"
        assert parser._normalize_status("failure") == "failed"

        assert parser._normalize_status("skipped") == "skipped"
        assert parser._normalize_status("xfail") == "skipped"
        assert parser._normalize_status("xpass") == "skipped"

        assert parser._normalize_status("error") == "error"
        assert parser._normalize_status("broken") == "error"

    def test_parse_nodeid_variants(self, parser):
        """Test nodeid parsing handles various formats."""
        # File::Class::Method
        classname, testname = parser._parse_nodeid(
            "tests/test_foo.py::TestClass::test_method"
        )
        assert classname == "TestClass"
        assert testname == "test_method"

        # File::Method (no class)
        classname, testname = parser._parse_nodeid("tests/test_foo.py::test_func")
        assert classname is None
        assert testname == "test_func"

        # Just a name
        classname, testname = parser._parse_nodeid("test_simple")
        assert classname is None
        assert testname == "test_simple"

    def test_can_parse_pytest_files(self, parser):
        """Test can_parse identifies pytest JSON files."""
        assert parser.can_parse(Path("pytest-results.json")) is True
        assert parser.can_parse(Path("test-results.json")) is True
        assert parser.can_parse(Path("result.json")) is True

    def test_can_parse_rejects_non_pytest(self, parser):
        """Test can_parse rejects non-pytest files."""
        assert parser.can_parse(Path("config.json")) is False
        assert parser.can_parse(Path("data.xml")) is False
        assert parser.can_parse(Path("test.py")) is False

    def test_message_truncation(self, parser, source, schema):
        """Test that long messages are truncated to 200 chars."""
        import json

        long_message = "x" * 500
        content = json.dumps({
            "tests": [
                {
                    "nodeid": "tests/test_foo.py::test_one",
                    "outcome": "failed",
                    "duration": 0.1,
                    "longrepr": long_message,
                },
            ]
        })
        nodes = parser.parse(content, source, schema)

        assert len(nodes) == 1
        assert len(nodes[0].test_result.message) == 200

    def test_extract_message_from_call_crash(self, parser, source, schema):
        """Test message extraction from call.crash field."""
        import json

        content = json.dumps({
            "tests": [
                {
                    "nodeid": "tests/test_foo.py::test_one",
                    "outcome": "error",
                    "duration": 0.1,
                    "call": {"crash": "Segfault at 0x1234"},
                },
            ]
        })
        nodes = parser.parse(content, source, schema)

        assert len(nodes) == 1
        assert "Segfault" in nodes[0].test_result.message


class TestCreateParser:
    """Tests for create_parser factory function."""

    def test_create_parser(self):
        """Test that create_parser returns a PytestJSONParser."""
        from elspais.parsers.pytest_json import PytestJSONParser, create_parser

        parser = create_parser()
        assert isinstance(parser, PytestJSONParser)
