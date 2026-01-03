"""
elspais.testing.result_parser - Test result file parser.

Parses JUnit XML and pytest JSON result files to extract test outcomes.
"""

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


class TestStatus(Enum):
    """Test execution status."""

    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"
    UNKNOWN = "unknown"


@dataclass
class TestResult:
    """
    Result of a single test case.

    Attributes:
        test_name: Name of the test function/method
        classname: Test class or module name
        status: Test execution status
        requirement_ids: Requirement IDs this test covers
        result_file: Path to the result file
        duration: Test duration in seconds (if available)
        message: Failure/error message (if applicable)
    """

    test_name: str
    classname: str
    status: TestStatus
    requirement_ids: List[str] = field(default_factory=list)
    result_file: Optional[Path] = None
    duration: Optional[float] = None
    message: Optional[str] = None


@dataclass
class ResultParseResult:
    """
    Result of parsing test result files.

    Attributes:
        results: List of all parsed test results
        files_parsed: List of successfully parsed files
        errors: List of parse errors
    """

    results: List[TestResult] = field(default_factory=list)
    files_parsed: List[Path] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


class ResultParser:
    """
    Parses test result files (JUnit XML, pytest JSON).

    Extracts test names, outcomes, and requirement references from
    test result files to correlate with test file scanning.
    """

    # Patterns for extracting requirement IDs from test names
    DEFAULT_REF_PATTERNS = [
        r"(?:REQ[-_])?([pod]\d{5})(?:[-_]([A-Z]))?",
    ]

    def __init__(self, reference_patterns: Optional[List[str]] = None) -> None:
        """
        Initialize the parser.

        Args:
            reference_patterns: Regex patterns to extract requirement IDs from test names
        """
        patterns = reference_patterns or self.DEFAULT_REF_PATTERNS
        self._patterns = [re.compile(p) for p in patterns]

    def parse_result_files(
        self,
        base_path: Path,
        result_file_patterns: List[str],
    ) -> ResultParseResult:
        """
        Parse all matching result files.

        Args:
            base_path: Project root path
            result_file_patterns: Glob patterns for result files

        Returns:
            ResultParseResult with all parsed test results
        """
        result = ResultParseResult()
        seen_files: Set[Path] = set()

        for pattern in result_file_patterns:
            for result_file in base_path.glob(pattern):
                if result_file in seen_files:
                    continue
                if not result_file.is_file():
                    continue
                seen_files.add(result_file)

                try:
                    if result_file.suffix == ".xml":
                        file_results = self._parse_junit_xml(result_file)
                    elif result_file.suffix == ".json":
                        file_results = self._parse_pytest_json(result_file)
                    else:
                        continue

                    result.results.extend(file_results)
                    result.files_parsed.append(result_file)
                except Exception as e:
                    result.errors.append(f"{result_file}: {e}")

        return result

    def _parse_junit_xml(self, file_path: Path) -> List[TestResult]:
        """
        Parse a JUnit XML result file.

        Args:
            file_path: Path to JUnit XML file

        Returns:
            List of TestResult objects
        """
        results: List[TestResult] = []

        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
        except ET.ParseError as e:
            raise ValueError(f"Invalid XML: {e}")

        # Handle both <testsuites> and <testsuite> as root
        if root.tag == "testsuites":
            testsuites = root.findall("testsuite")
        elif root.tag == "testsuite":
            testsuites = [root]
        else:
            return results

        for testsuite in testsuites:
            for testcase in testsuite.findall("testcase"):
                test_name = testcase.get("name", "")
                classname = testcase.get("classname", "")
                time_str = testcase.get("time")
                duration = float(time_str) if time_str else None

                # Determine status
                failure = testcase.find("failure")
                error = testcase.find("error")
                skipped = testcase.find("skipped")

                if failure is not None:
                    status = TestStatus.FAILED
                    message = failure.get("message") or failure.text
                elif error is not None:
                    status = TestStatus.ERROR
                    message = error.get("message") or error.text
                elif skipped is not None:
                    status = TestStatus.SKIPPED
                    message = skipped.get("message") or skipped.text
                else:
                    status = TestStatus.PASSED
                    message = None

                # Extract requirement IDs from test name
                req_ids = self._extract_requirement_ids(test_name, classname)

                results.append(TestResult(
                    test_name=test_name,
                    classname=classname,
                    status=status,
                    requirement_ids=req_ids,
                    result_file=file_path,
                    duration=duration,
                    message=message,
                ))

        return results

    def _parse_pytest_json(self, file_path: Path) -> List[TestResult]:
        """
        Parse a pytest JSON result file.

        Args:
            file_path: Path to pytest JSON file

        Returns:
            List of TestResult objects
        """
        results: List[TestResult] = []

        try:
            with open(file_path, encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}")

        # Handle pytest-json-report format
        tests = data.get("tests", [])
        for test in tests:
            nodeid = test.get("nodeid", "")
            outcome = test.get("outcome", "unknown")

            # Parse nodeid: "tests/test_foo.py::TestClass::test_method"
            parts = nodeid.split("::")
            test_name = parts[-1] if parts else nodeid
            classname = parts[-2] if len(parts) > 1 else ""

            # Map outcome to status
            status_map = {
                "passed": TestStatus.PASSED,
                "failed": TestStatus.FAILED,
                "error": TestStatus.ERROR,
                "skipped": TestStatus.SKIPPED,
            }
            status = status_map.get(outcome, TestStatus.UNKNOWN)

            # Get duration and message
            duration = test.get("duration")
            message = None
            call_data = test.get("call", {})
            if call_data and status in (TestStatus.FAILED, TestStatus.ERROR):
                message = call_data.get("longrepr")

            # Extract requirement IDs
            req_ids = self._extract_requirement_ids(test_name, classname)

            results.append(TestResult(
                test_name=test_name,
                classname=classname,
                status=status,
                requirement_ids=req_ids,
                result_file=file_path,
                duration=duration,
                message=message,
            ))

        return results

    def _extract_requirement_ids(self, test_name: str, classname: str) -> List[str]:
        """
        Extract requirement IDs from test name and classname.

        Args:
            test_name: Test function/method name
            classname: Test class or module name

        Returns:
            List of normalized requirement IDs (e.g., ["REQ-p00001"])
        """
        req_ids: List[str] = []
        search_text = f"{classname}::{test_name}"

        for pattern in self._patterns:
            for match in pattern.finditer(search_text):
                groups = match.groups()
                if not groups or not groups[0]:
                    continue
                type_id = groups[0]
                # Normalize to full requirement ID (ignore assertion label for ID)
                req_id = f"REQ-{type_id}"
                if req_id not in req_ids:
                    req_ids.append(req_id)

        return req_ids

    def parse_junit_xml(self, file_path: Path) -> List[TestResult]:
        """Public method to parse a JUnit XML file."""
        return self._parse_junit_xml(file_path)

    def parse_pytest_json(self, file_path: Path) -> List[TestResult]:
        """Public method to parse a pytest JSON file."""
        return self._parse_pytest_json(file_path)
