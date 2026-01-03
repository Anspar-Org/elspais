"""
elspais.testing - Test mapping and coverage functionality.

This package provides test-to-requirement mapping and coverage analysis:
- TestingConfig: Configuration for test scanning
- TestScanner: Scans test files for requirement references
- ResultParser: Parses JUnit XML and pytest JSON results
- TestMapper: Orchestrates scanning and result mapping
"""

from elspais.testing.config import TestingConfig
from elspais.testing.mapper import RequirementTestData, TestMapper, TestMappingResult
from elspais.testing.result_parser import ResultParser, TestResult, TestStatus
from elspais.testing.scanner import TestReference, TestScanResult, TestScanner

__all__ = [
    "TestingConfig",
    "TestScanner",
    "TestScanResult",
    "TestReference",
    "ResultParser",
    "TestResult",
    "TestStatus",
    "TestMapper",
    "TestMappingResult",
    "RequirementTestData",
]
