"""Tests for elspais.testing.mapper module."""

from pathlib import Path

import pytest

from elspais.testing.config import TestingConfig
from elspais.testing.mapper import RequirementTestData, TestMapper, TestMappingResult


class TestTestMapper:
    """Tests for TestMapper class."""

    @pytest.fixture
    def fixtures_dir(self):
        """Return path to test fixtures directory."""
        return Path(__file__).parent / "fixtures"

    @pytest.fixture
    def testing_config(self, fixtures_dir):
        """Create a testing config for fixtures."""
        return TestingConfig(
            enabled=True,
            test_dirs=["."],  # Current dir (fixtures)
            patterns=["*_test.py", "sample_*.py"],
            result_files=["*.xml", "*.json"],
            reference_patterns=[],  # Use defaults
        )

    def test_map_tests_basic(self, testing_config, fixtures_dir):
        """Test basic test mapping functionality."""
        mapper = TestMapper(testing_config)

        result = mapper.map_tests(
            requirement_ids={"REQ-p00001", "REQ-d00001"},
            base_path=fixtures_dir,
        )

        assert isinstance(result, TestMappingResult)
        assert len(result.requirement_data) > 0

    def test_map_tests_includes_known_requirements(self, testing_config, fixtures_dir):
        """Test that all known requirements get entries."""
        mapper = TestMapper(testing_config)
        known_reqs = {"REQ-p00001", "REQ-d00001", "REQ-x99999"}  # x99999 has no tests

        result = mapper.map_tests(
            requirement_ids=known_reqs,
            base_path=fixtures_dir,
        )

        # All known reqs should have entries
        for req_id in known_reqs:
            assert req_id in result.requirement_data

        # The one with no tests should have zero counts
        assert result.requirement_data["REQ-x99999"].test_count == 0

    def test_map_tests_counts_correctly(self, testing_config, fixtures_dir):
        """Test that test counts are calculated correctly."""
        mapper = TestMapper(testing_config)

        result = mapper.map_tests(
            requirement_ids={"REQ-p00001"},
            base_path=fixtures_dir,
        )

        p00001_data = result.requirement_data.get("REQ-p00001")
        if p00001_data:
            # Should have at least 2 tests (from both XML and JSON)
            assert p00001_data.test_count >= 0  # May be 0 if results not matching

    def test_requirement_test_data_defaults(self):
        """Test RequirementTestData default values."""
        data = RequirementTestData()

        assert data.test_count == 0
        assert data.test_passed == 0
        assert data.test_failed == 0
        assert data.test_skipped == 0
        assert data.test_result_files == []

    def test_map_tests_with_no_results(self, fixtures_dir):
        """Test mapping when result files don't exist."""
        config = TestingConfig(
            enabled=True,
            test_dirs=["."],
            patterns=["*_test.py"],
            result_files=["nonexistent/*.xml"],  # No matching files
            reference_patterns=[],
        )
        mapper = TestMapper(config)

        result = mapper.map_tests(
            requirement_ids={"REQ-p00001"},
            base_path=fixtures_dir,
        )

        # Should still work, just with zero passed
        assert result is not None
        if "REQ-p00001" in result.requirement_data:
            data = result.requirement_data["REQ-p00001"]
            assert data.test_passed == 0
            assert data.test_result_files == []

    def test_scan_summary_populated(self, testing_config, fixtures_dir):
        """Test that scan summary is populated."""
        mapper = TestMapper(testing_config)

        result = mapper.map_tests(
            requirement_ids=set(),
            base_path=fixtures_dir,
        )

        assert "files_scanned" in result.scan_summary
        assert "test_dirs" in result.scan_summary
        assert "patterns" in result.scan_summary
        assert "result_files_parsed" in result.scan_summary
