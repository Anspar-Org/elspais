"""
elspais.testing - Test mapping and coverage functionality.

This package provides test-to-requirement mapping and coverage analysis:
- TestingConfig: Configuration for test scanning
- TestScanner: Scans test files for requirement references
- ResultParser: Parses JUnit XML and pytest JSON results
- TestCoverageMapper: Orchestrates scanning and result mapping for coverage
"""

from elspais.testing.config import TestingConfig
from elspais.testing.mapper import RequirementTestData, TestCoverageMapper, TestMappingResult
from elspais.testing.result_parser import ResultParser, TestResult, TestStatus
from elspais.testing.scanner import TestReference, TestScanner, TestScanResult

__all__ = [
    "TestingConfig",
    "TestScanner",
    "TestScanResult",
    "TestReference",
    "ResultParser",
    "TestResult",
    "TestStatus",
    "TestCoverageMapper",
    "TestMappingResult",
    "RequirementTestData",
]
