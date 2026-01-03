"""Tests for elspais.testing.scanner module."""

from pathlib import Path

import pytest

from elspais.testing.scanner import TestReference, TestScanResult, TestScanner


class TestTestScanner:
    """Tests for TestScanner class."""

    @pytest.fixture
    def scanner(self):
        """Create a TestScanner with default patterns."""
        return TestScanner()

    @pytest.fixture
    def fixtures_dir(self):
        """Return path to test fixtures directory."""
        return Path(__file__).parent / "fixtures"

    def test_scan_file_basic(self, scanner, fixtures_dir):
        """Test scanning a file with requirement references."""
        test_file = fixtures_dir / "sample_test.py"
        if not test_file.exists():
            pytest.skip("Fixture file not found")

        refs = scanner.scan_file(test_file)

        # Should find references to p00001, d00001, d00002, d00003, o00001
        req_ids = {r.requirement_id for r in refs}
        assert "REQ-p00001" in req_ids
        assert "REQ-d00001" in req_ids

    def test_scan_file_extracts_test_name(self, scanner, fixtures_dir):
        """Test that scanner extracts test function names."""
        test_file = fixtures_dir / "sample_test.py"
        if not test_file.exists():
            pytest.skip("Fixture file not found")

        refs = scanner.scan_file(test_file)

        # Find a reference that should have a test name
        p00001_refs = [r for r in refs if r.requirement_id == "REQ-p00001"]
        assert any(r.test_name is not None for r in p00001_refs)

    def test_scan_file_with_assertion_reference(self, scanner, fixtures_dir):
        """Test scanning files with assertion-level references."""
        test_file = fixtures_dir / "sample_test.py"
        if not test_file.exists():
            pytest.skip("Fixture file not found")

        refs = scanner.scan_file(test_file)

        # Should find REQ-p00001-A and REQ-p00001-B assertion refs
        # These should roll up to REQ-p00001
        p00001_refs = [r for r in refs if r.requirement_id == "REQ-p00001"]
        assert len(p00001_refs) >= 2

    def test_scan_nonexistent_file(self, scanner, tmp_path):
        """Test scanning a nonexistent file returns empty list."""
        refs = scanner.scan_file(tmp_path / "nonexistent.py")
        assert refs == []

    def test_scan_result_add_reference(self):
        """Test TestScanResult.add_reference aggregates correctly."""
        result = TestScanResult()

        ref1 = TestReference(
            requirement_id="REQ-p00001",
            assertion_label=None,
            test_file=Path("test.py"),
            line_number=10,
        )
        ref2 = TestReference(
            requirement_id="REQ-p00001",
            assertion_label="A",
            test_file=Path("test.py"),
            line_number=20,
        )

        result.add_reference(ref1)
        result.add_reference(ref2)

        assert "REQ-p00001" in result.references
        assert len(result.references["REQ-p00001"]) == 2

    def test_scan_directories(self, scanner, fixtures_dir):
        """Test scanning directories for test files."""
        result = scanner.scan_directories(
            base_path=fixtures_dir.parent,
            test_dirs=["fixtures"],
            file_patterns=["*_test.py", "sample_*.py"],
        )

        assert result.files_scanned >= 1
        assert len(result.references) > 0

    def test_custom_reference_patterns(self, fixtures_dir):
        """Test scanner with custom reference patterns."""
        # Custom pattern that only matches IMPLEMENTS comments
        scanner = TestScanner(reference_patterns=[
            r"IMPLEMENTS:\s*REQ-([pod]\d{5})",
        ])

        test_file = fixtures_dir / "sample_test.py"
        if not test_file.exists():
            pytest.skip("Fixture file not found")

        refs = scanner.scan_file(test_file)

        # Should only find refs from IMPLEMENTS comments
        assert len(refs) >= 1
