"""Tests for JUnit XML Parser."""

from elspais.graph.parsers.results.junit_xml import JUnitXMLParser


class TestJUnitXMLParserBasic:
    """Basic tests for JUnitXMLParser."""

    def test_parse_passing_test(self):
        """Parses a passing test case."""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="TestAuth" tests="1">
  <testcase classname="tests.test_auth" name="test_login_REQ_p00001" time="0.123"/>
</testsuite>"""
        parser = JUnitXMLParser()

        results = parser.parse(xml, "test_results.xml")

        assert len(results) == 1
        assert results[0]["status"] == "passed"
        assert results[0]["name"] == "test_login_REQ_p00001"
        assert "REQ-p00001" in results[0]["validates"]

    def test_parse_failing_test(self):
        """Parses a failing test case."""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="TestAuth" tests="1">
  <testcase classname="tests.test_auth" name="test_fail" time="0.5">
    <failure message="AssertionError: Expected True"/>
  </testcase>
</testsuite>"""
        parser = JUnitXMLParser()

        results = parser.parse(xml, "test_results.xml")

        assert len(results) == 1
        assert results[0]["status"] == "failed"
        assert "AssertionError" in results[0]["message"]

    def test_parse_skipped_test(self):
        """Parses a skipped test case."""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="TestAuth" tests="1">
  <testcase classname="tests.test_auth" name="test_skip" time="0">
    <skipped message="Not implemented yet"/>
  </testcase>
</testsuite>"""
        parser = JUnitXMLParser()

        results = parser.parse(xml, "test_results.xml")

        assert len(results) == 1
        assert results[0]["status"] == "skipped"

    def test_parse_error_test(self):
        """Parses a test with error."""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="TestAuth" tests="1">
  <testcase classname="tests.test_auth" name="test_error" time="0.1">
    <error message="ImportError: No module named foo"/>
  </testcase>
</testsuite>"""
        parser = JUnitXMLParser()

        results = parser.parse(xml, "test_results.xml")

        assert len(results) == 1
        assert results[0]["status"] == "error"

    def test_parse_multiple_tests(self):
        """Parses multiple test cases."""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="TestAuth" tests="3">
  <testcase classname="tests.test_auth" name="test_a" time="0.1"/>
  <testcase classname="tests.test_auth" name="test_b" time="0.2"/>
  <testcase classname="tests.test_auth" name="test_c" time="0.3"/>
</testsuite>"""
        parser = JUnitXMLParser()

        results = parser.parse(xml, "test_results.xml")

        assert len(results) == 3


class TestJUnitXMLParserReqExtraction:
    """Tests for requirement ID extraction."""

    def test_extracts_req_from_name(self):
        """Extracts REQ ID from test name."""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="Test" tests="1">
  <testcase classname="test" name="test_REQ_p00001_login" time="0.1"/>
</testsuite>"""
        parser = JUnitXMLParser()

        results = parser.parse(xml, "results.xml")

        assert "REQ-p00001" in results[0]["validates"]

    def test_extracts_multiple_reqs(self):
        """Extracts multiple REQ IDs from test name."""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="Test" tests="1">
  <testcase classname="test" name="test_REQ_p00001_and_REQ_o00002" time="0.1"/>
</testsuite>"""
        parser = JUnitXMLParser()

        results = parser.parse(xml, "results.xml")

        assert "REQ-p00001" in results[0]["validates"]
        assert "REQ-o00002" in results[0]["validates"]

    def test_extracts_assertion_refs(self):
        """Extracts assertion references like REQ-p00001-A."""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="Test" tests="1">
  <testcase classname="test" name="test_REQ_p00001_A" time="0.1"/>
</testsuite>"""
        parser = JUnitXMLParser()

        results = parser.parse(xml, "results.xml")

        assert "REQ-p00001-A" in results[0]["validates"]

    def test_generates_test_id(self):
        """Generates stable test_id from classname and name."""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="Test" tests="1">
  <testcase classname="tests.test_auth.TestLogin" name="test_user_can_login" time="0.1"/>
</testsuite>"""
        parser = JUnitXMLParser()

        results = parser.parse(xml, "results.xml")

        assert results[0]["test_id"] == "test:tests/test_auth.py::TestLogin::test_user_can_login"

    def test_generates_test_id_without_classname(self):
        """Generates test_id even without classname."""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="Test" tests="1">
  <testcase name="test_something" time="0.1"/>
</testsuite>"""
        parser = JUnitXMLParser()

        results = parser.parse(xml, "results.xml")

        # Without classname, module path is empty
        assert results[0]["test_id"] == "test:::test_something"


class TestJUnitXMLParserEdgeCases:
    """Edge case tests for JUnitXMLParser."""

    def test_invalid_xml_returns_empty(self):
        """Returns empty list for invalid XML."""
        parser = JUnitXMLParser()

        results = parser.parse("not valid xml", "test.xml")

        assert results == []

    def test_empty_testsuite(self):
        """Handles empty testsuite."""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="Empty" tests="0">
</testsuite>"""
        parser = JUnitXMLParser()

        results = parser.parse(xml, "test.xml")

        assert results == []

    def test_testsuites_wrapper(self):
        """Handles testsuites wrapper element."""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<testsuites>
  <testsuite name="Suite1" tests="1">
    <testcase classname="test" name="test_a" time="0.1"/>
  </testsuite>
  <testsuite name="Suite2" tests="1">
    <testcase classname="test" name="test_b" time="0.2"/>
  </testsuite>
</testsuites>"""
        parser = JUnitXMLParser()

        results = parser.parse(xml, "test.xml")

        assert len(results) == 2


class TestJUnitXMLParserCanParse:
    """Tests for can_parse method."""

    def test_can_parse_junit_xml(self):
        """Returns True for JUnit XML files."""
        from pathlib import Path

        parser = JUnitXMLParser()

        assert parser.can_parse(Path("junit-results.xml")) is True
        assert parser.can_parse(Path("test-results.xml")) is True
        assert parser.can_parse(Path("results.xml")) is True

    def test_cannot_parse_non_xml(self):
        """Returns False for non-XML files."""
        from pathlib import Path

        parser = JUnitXMLParser()

        assert parser.can_parse(Path("results.json")) is False
        assert parser.can_parse(Path("test.py")) is False


class TestJUnitXMLParserCustomConfig:
    """Tests for JUnitXMLParser with custom configuration.

    REQ-d00102-A: Parser accepts custom PatternConfig for non-standard prefixes.
    REQ-d00102-B: Parser instantiation with PatternConfig and ReferenceResolver.
    REQ-d00102-C: Parser extracts custom prefix IDs from test names.
    """

    def test_REQ_d00102_A_custom_prefix_spec(self):
        """REQ-d00102-A: Parser with custom prefix 'SPEC' extracts correct IDs."""
        from elspais.utilities.patterns import PatternConfig

        pattern_config = PatternConfig.from_dict(
            {
                "prefix": "SPEC",
                "types": {
                    "prd": {"id": "p", "name": "PRD"},
                    "ops": {"id": "o", "name": "OPS"},
                    "dev": {"id": "d", "name": "DEV"},
                },
                "id_format": {"style": "numeric", "digits": 5},
            }
        )
        parser = JUnitXMLParser(pattern_config=pattern_config)

        xml = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="TestCustom" tests="1">
  <testcase classname="tests.test_custom" name="test_spec_SPEC_p00102" time="0.1"/>
</testsuite>"""

        results = parser.parse(xml, "results.xml")

        assert len(results) == 1
        assert "SPEC-p00102" in results[0]["validates"]

    def test_REQ_d00102_B_instantiation_with_pattern_config_and_resolver(self):
        """REQ-d00102-B: Parser instantiation with PatternConfig and ReferenceResolver."""
        from pathlib import Path

        from elspais.utilities.patterns import PatternConfig
        from elspais.utilities.reference_config import (
            ReferenceConfig,
            ReferenceResolver,
        )

        pattern_config = PatternConfig.from_dict(
            {
                "prefix": "REQ",
                "types": {
                    "prd": {"id": "p", "name": "PRD"},
                    "ops": {"id": "o", "name": "OPS"},
                    "dev": {"id": "d", "name": "DEV"},
                },
                "id_format": {"style": "numeric", "digits": 5},
            }
        )

        ref_config = ReferenceConfig(
            separators=["-", "_"],
            case_sensitive=False,
        )
        resolver = ReferenceResolver(ref_config)
        base_path = Path(".")

        # Verify instantiation succeeds with all parameters
        parser = JUnitXMLParser(
            pattern_config=pattern_config,
            reference_resolver=resolver,
            base_path=base_path,
        )

        assert parser._pattern_config == pattern_config
        assert parser._reference_resolver == resolver
        assert parser._base_path == base_path

    def test_REQ_d00102_C_extracts_custom_prefix_ids(self):
        """REQ-d00102-C: Parser extracts custom prefix IDs from test names."""
        from elspais.utilities.patterns import PatternConfig

        pattern_config = PatternConfig.from_dict(
            {
                "prefix": "TASK",
                "types": {
                    "prd": {"id": "p", "name": "PRD"},
                    "ops": {"id": "o", "name": "OPS"},
                    "dev": {"id": "d", "name": "DEV"},
                },
                "id_format": {"style": "numeric", "digits": 5},
            }
        )
        parser = JUnitXMLParser(pattern_config=pattern_config)

        xml = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="TestTask" tests="1">
  <testcase classname="tests.test_task" name="test_TASK_d00102_implementation" time="0.2"/>
</testsuite>"""

        results = parser.parse(xml, "results.xml")

        assert len(results) == 1
        assert "TASK-d00102" in results[0]["validates"]
