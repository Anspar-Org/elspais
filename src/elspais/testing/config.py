"""
elspais.testing.config - Configuration for test mapping and coverage.

Provides TestingConfig dataclass for configuring test file scanning
and result file parsing.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class TestingConfig:
    """
    Configuration for test mapping and coverage features.

    Attributes:
        enabled: Whether test mapping is enabled (default: False)
        test_dirs: Glob patterns for test directories to scan
        patterns: File patterns to match test files (e.g., "*_test.py")
        result_files: Glob patterns for test result files (JUnit XML, pytest JSON)
        reference_patterns: Regex patterns to extract requirement IDs from tests
    """

    enabled: bool = False
    test_dirs: List[str] = field(default_factory=list)
    patterns: List[str] = field(default_factory=list)
    result_files: List[str] = field(default_factory=list)
    reference_patterns: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TestingConfig":
        """
        Create TestingConfig from configuration dictionary.

        Args:
            data: Dictionary from [testing] config section

        Returns:
            TestingConfig instance with values from data or defaults
        """
        return cls(
            enabled=data.get("enabled", False),
            test_dirs=data.get("test_dirs", []),
            patterns=data.get("patterns", []),
            result_files=data.get("result_files", []),
            reference_patterns=data.get("reference_patterns", []),
        )
