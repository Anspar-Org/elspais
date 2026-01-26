"""Tests for elspais.testing.result_parser module."""

from pathlib import Path

import pytest

from elspais.testing.result_parser import ResultParser, TestResult, TestStatus


class TestResultParser:
    """Tests for ResultParser class."""

    @pytest.fixture
    def parser(self):
        """Create a ResultParser instance."""
        return ResultParser()

    @pytest.fixture
    def fixtures_dir(self):
        """Return path to test fixtures directory."""
        return Path(__file__).parent / "fixtures"

    def test_parse_junit_xml(self, parser, fixtures_dir):
        """Test parsing JUnit XML result file."""
        xml_file = fixtures_dir / "junit_results.xml"
        if not xml_file.exists():
            pytest.skip("Fixture file not found")

        results = parser.parse_junit_xml(xml_file)

        assert len(results) == 5
        # Check for specific test results
        test_names = {r.test_name for r in results}
        assert "test_REQ_p00001_user_authentication" in test_names

    def test_junit_xml_status_detection(self, parser, fixtures_dir):
        """Test that JUnit XML correctly detects test statuses."""
        xml_file = fixtures_dir / "junit_results.xml"
        if not xml_file.exists():
            pytest.skip("Fixture file not found")

        results = parser.parse_junit_xml(xml_file)

        # Find specific tests and check status
        passed_test = next(
            (r for r in results if r.test_name == "test_REQ_p00001_user_authentication"),
            None,
        )
        assert passed_test is not None
        assert passed_test.status == TestStatus.PASSED

        failed_test = next(
            (r for r in results if r.test_name == "test_REQ_p00001_B_stores_password_hash"),
            None,
        )
        assert failed_test is not None
        assert failed_test.status == TestStatus.FAILED
        assert failed_test.message is not None

        skipped_test = next(
            (r for r in results if r.test_name == "test_skipped_feature"),
            None,
        )
        assert skipped_test is not None
        assert skipped_test.status == TestStatus.SKIPPED

    def test_junit_xml_requirement_extraction(self, parser, fixtures_dir):
        """Test that requirement IDs are extracted from test names."""
        xml_file = fixtures_dir / "junit_results.xml"
        if not xml_file.exists():
            pytest.skip("Fixture file not found")

        results = parser.parse_junit_xml(xml_file)

        # Find test with requirement reference
        auth_test = next(
            (r for r in results if r.test_name == "test_REQ_p00001_user_authentication"),
            None,
        )
        assert auth_test is not None
        assert "REQ-p00001" in auth_test.requirement_ids

    def test_parse_pytest_json(self, parser, fixtures_dir):
        """Test parsing pytest JSON result file."""
        json_file = fixtures_dir / "pytest_results.json"
        if not json_file.exists():
            pytest.skip("Fixture file not found")

        results = parser.parse_pytest_json(json_file)

        assert len(results) == 5
        # Check for specific test results
        test_names = {r.test_name for r in results}
        assert "test_REQ_p00001_user_authentication" in test_names

    def test_pytest_json_status_detection(self, parser, fixtures_dir):
        """Test that pytest JSON correctly detects test statuses."""
        json_file = fixtures_dir / "pytest_results.json"
        if not json_file.exists():
            pytest.skip("Fixture file not found")

        results = parser.parse_pytest_json(json_file)

        passed_count = sum(1 for r in results if r.status == TestStatus.PASSED)
        failed_count = sum(1 for r in results if r.status == TestStatus.FAILED)
        skipped_count = sum(1 for r in results if r.status == TestStatus.SKIPPED)

        assert passed_count == 3
        assert failed_count == 1
        assert skipped_count == 1

    def test_parse_result_files(self, parser, fixtures_dir):
        """Test parsing multiple result files via pattern."""
        result = parser.parse_result_files(
            base_path=fixtures_dir,
            result_file_patterns=["*.xml", "*.json"],
        )

        assert len(result.files_parsed) == 2
        assert len(result.results) == 10  # 5 from XML + 5 from JSON
        assert len(result.errors) == 0

    def test_parse_invalid_xml(self, parser, tmp_path):
        """Test parsing invalid XML raises error."""
        bad_xml = tmp_path / "bad.xml"
        bad_xml.write_text("not valid xml <")

        with pytest.raises(ValueError, match="Invalid XML"):
            parser.parse_junit_xml(bad_xml)

    def test_parse_invalid_json(self, parser, tmp_path):
        """Test parsing invalid JSON raises error."""
        bad_json = tmp_path / "bad.json"
        bad_json.write_text("{not valid json")

        with pytest.raises(ValueError, match="Invalid JSON"):
            parser.parse_pytest_json(bad_json)
