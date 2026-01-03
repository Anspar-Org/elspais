"""
elspais.testing.scanner - Test file scanner for requirement references.

Scans test files for requirement ID references (e.g., REQ-d00001, REQ-p00001-A)
in function names, docstrings, and comments.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set


@dataclass
class TestReference:
    """
    A reference from a test to a requirement.

    Attributes:
        requirement_id: Normalized requirement ID (e.g., "REQ-p00001")
        assertion_label: Assertion label if present (e.g., "A" for REQ-p00001-A)
        test_file: Path to the test file
        test_name: Name of the test function/method if extractable
        line_number: Line number where reference was found
    """

    requirement_id: str
    assertion_label: Optional[str]
    test_file: Path
    test_name: Optional[str] = None
    line_number: int = 0


@dataclass
class TestScanResult:
    """
    Result of scanning test files for requirement references.

    Attributes:
        references: Mapping of requirement IDs to their test references
        files_scanned: Number of test files scanned
        errors: List of errors encountered during scanning
    """

    references: Dict[str, List[TestReference]] = field(default_factory=dict)
    files_scanned: int = 0
    errors: List[str] = field(default_factory=list)

    def add_reference(self, ref: TestReference) -> None:
        """Add a test reference, rolling up assertion-level refs to parent."""
        # Roll up assertion-level references to the parent requirement
        req_id = ref.requirement_id
        if req_id not in self.references:
            self.references[req_id] = []
        self.references[req_id].append(ref)


class TestScanner:
    """
    Scans test files for requirement ID references.

    Uses configurable patterns to find requirement references in:
    - Test function/method names
    - Docstrings
    - Comments (IMPLEMENTS: patterns)
    """

    # Default patterns if none configured
    DEFAULT_PATTERNS = [
        # Test function names: test_REQ_p00001_something or test_p00001_something
        r"test_.*(?:REQ[-_])?([pod]\d{5})(?:[-_]([A-Z]))?",
        # IMPLEMENTS comments: IMPLEMENTS: REQ-p00001 or IMPLEMENTS: REQ-p00001-A
        r"(?:IMPLEMENTS|Implements|implements)[:\s]+(?:REQ[-_])?([pod]\d{5})(?:-([A-Z]))?",
        # Direct references: REQ-p00001 or REQ-p00001-A
        r"\bREQ[-_]([pod]\d{5})(?:-([A-Z]))?\b",
    ]

    def __init__(self, reference_patterns: Optional[List[str]] = None) -> None:
        """
        Initialize the scanner with reference patterns.

        Args:
            reference_patterns: Regex patterns for extracting requirement IDs.
                               Each pattern should have groups for (type+id) and
                               optionally (assertion_label).
        """
        patterns = reference_patterns or self.DEFAULT_PATTERNS
        self._patterns = [re.compile(p) for p in patterns]

    def scan_directories(
        self,
        base_path: Path,
        test_dirs: List[str],
        file_patterns: List[str],
        ignore: Optional[List[str]] = None,
    ) -> TestScanResult:
        """
        Scan test directories for requirement references.

        Args:
            base_path: Project root path
            test_dirs: Glob patterns for test directories (e.g., ["apps/**/test"])
            file_patterns: File patterns to match (e.g., ["*_test.py"])
            ignore: Directory names to ignore (e.g., ["node_modules"])

        Returns:
            TestScanResult with all found references
        """
        result = TestScanResult()
        ignore_set = set(ignore or [])
        seen_files: Set[Path] = set()

        for dir_pattern in test_dirs:
            # Handle special cases for directory patterns
            if dir_pattern in (".", ""):
                # Current directory
                dirs_to_scan = [base_path]
            else:
                # Resolve the directory pattern
                dirs_to_scan = list(base_path.glob(dir_pattern))

            for test_dir in dirs_to_scan:
                if not test_dir.is_dir():
                    continue
                if any(ig in test_dir.parts for ig in ignore_set):
                    continue

                # Find test files in this directory
                for file_pattern in file_patterns:
                    for test_file in test_dir.glob(file_pattern):
                        if test_file in seen_files:
                            continue
                        if not test_file.is_file():
                            continue
                        seen_files.add(test_file)

                        # Scan the file
                        file_refs = self._scan_file(test_file)
                        for ref in file_refs:
                            result.add_reference(ref)
                        result.files_scanned += 1

        return result

    def _scan_file(self, file_path: Path) -> List[TestReference]:
        """
        Scan a single test file for requirement references.

        Args:
            file_path: Path to the test file

        Returns:
            List of TestReference objects found in the file
        """
        references: List[TestReference] = []

        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return references

        lines = content.split("\n")
        current_test_name: Optional[str] = None

        for line_num, line in enumerate(lines, start=1):
            # Track current test function name
            test_match = re.match(r"\s*def\s+(test_\w+)", line)
            if test_match:
                current_test_name = test_match.group(1)

            # Look for requirement references
            for pattern in self._patterns:
                for match in pattern.finditer(line):
                    groups = match.groups()
                    if not groups or not groups[0]:
                        continue

                    # Extract requirement ID parts
                    type_id = groups[0]  # e.g., "p00001"
                    assertion_label = groups[1] if len(groups) > 1 else None

                    # Normalize to full requirement ID
                    req_id = f"REQ-{type_id}"

                    ref = TestReference(
                        requirement_id=req_id,
                        assertion_label=assertion_label,
                        test_file=file_path,
                        test_name=current_test_name,
                        line_number=line_num,
                    )
                    references.append(ref)

        return references

    def scan_file(self, file_path: Path) -> List[TestReference]:
        """
        Public method to scan a single file.

        Args:
            file_path: Path to the test file

        Returns:
            List of TestReference objects
        """
        return self._scan_file(file_path)
