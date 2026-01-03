"""
elspais.testing.mapper - Test-to-requirement mapping orchestration.

Coordinates test file scanning and result parsing to produce
per-requirement test coverage data.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from elspais.testing.config import TestingConfig
from elspais.testing.result_parser import ResultParser, TestResult, TestStatus
from elspais.testing.scanner import TestScanner


@dataclass
class RequirementTestData:
    """
    Test coverage data for a single requirement.

    Attributes:
        test_count: Total number of tests referencing this requirement
        test_passed: Number of passed tests
        test_failed: Number of failed tests
        test_skipped: Number of skipped tests
        test_result_files: Unique result file paths for this requirement
    """

    test_count: int = 0
    test_passed: int = 0
    test_failed: int = 0
    test_skipped: int = 0
    test_result_files: List[str] = field(default_factory=list)


@dataclass
class TestMappingResult:
    """
    Complete test mapping for all requirements.

    Attributes:
        requirement_data: Mapping of requirement IDs to test data
        scan_summary: Summary of scanning operation
        errors: List of errors encountered
    """

    requirement_data: Dict[str, RequirementTestData] = field(default_factory=dict)
    scan_summary: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)


class TestMapper:
    """
    Orchestrates test scanning and result mapping.

    Coordinates the TestScanner and ResultParser to produce
    per-requirement test coverage data for JSON output.
    """

    def __init__(self, config: TestingConfig) -> None:
        """
        Initialize the mapper.

        Args:
            config: Testing configuration
        """
        self.config = config
        self._scanner = TestScanner(config.reference_patterns or None)
        self._parser = ResultParser(config.reference_patterns or None)

    def map_tests(
        self,
        requirement_ids: Set[str],
        base_path: Path,
        ignore: Optional[List[str]] = None,
    ) -> TestMappingResult:
        """
        Map tests to requirements and gather coverage data.

        Args:
            requirement_ids: Set of known requirement IDs
            base_path: Project root path
            ignore: Directory names to ignore

        Returns:
            TestMappingResult with per-requirement test data
        """
        result = TestMappingResult()
        ignore_dirs = ignore or []

        # Step 1: Scan test files for requirement references
        scan_result = self._scanner.scan_directories(
            base_path=base_path,
            test_dirs=self.config.test_dirs,
            file_patterns=self.config.patterns,
            ignore=ignore_dirs,
        )

        result.scan_summary["files_scanned"] = scan_result.files_scanned
        result.scan_summary["test_dirs"] = self.config.test_dirs
        result.scan_summary["patterns"] = self.config.patterns
        result.errors.extend(scan_result.errors)

        # Step 2: Parse test result files
        parse_result = self._parser.parse_result_files(
            base_path=base_path,
            result_file_patterns=self.config.result_files,
        )

        result.scan_summary["result_files_parsed"] = len(parse_result.files_parsed)
        result.errors.extend(parse_result.errors)

        # Step 3: Build requirement ID to test results mapping
        req_to_results: Dict[str, List[TestResult]] = {}
        for test_result in parse_result.results:
            for req_id in test_result.requirement_ids:
                if req_id not in req_to_results:
                    req_to_results[req_id] = []
                req_to_results[req_id].append(test_result)

        # Step 4: Calculate per-requirement test data
        # Combine scan references with result data
        all_req_ids = set(scan_result.references.keys()) | set(req_to_results.keys())

        for req_id in all_req_ids:
            test_data = RequirementTestData()

            # Count from scan references (test files found)
            if req_id in scan_result.references:
                test_data.test_count = len(scan_result.references[req_id])

            # Count from results (if available)
            if req_id in req_to_results:
                results = req_to_results[req_id]
                # If we have results, use result count (more accurate)
                if not scan_result.references.get(req_id):
                    test_data.test_count = len(results)

                result_files: Set[str] = set()
                for tr in results:
                    if tr.status == TestStatus.PASSED:
                        test_data.test_passed += 1
                    elif tr.status == TestStatus.FAILED:
                        test_data.test_failed += 1
                    elif tr.status == TestStatus.ERROR:
                        test_data.test_failed += 1
                    elif tr.status == TestStatus.SKIPPED:
                        test_data.test_skipped += 1

                    if tr.result_file:
                        result_files.add(str(tr.result_file))

                test_data.test_result_files = sorted(result_files)

            result.requirement_data[req_id] = test_data

        # Ensure all known requirements have entries (even if zero)
        for req_id in requirement_ids:
            if req_id not in result.requirement_data:
                result.requirement_data[req_id] = RequirementTestData()

        return result
