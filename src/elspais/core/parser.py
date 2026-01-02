"""
elspais.core.parser - Requirement file parsing.

Parses Markdown files containing requirements in the standard format.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Union

from elspais.core.models import Assertion, Requirement
from elspais.core.patterns import PatternConfig, PatternValidator


class RequirementParser:
    """
    Parses requirement specifications from Markdown files.
    """

    # Regex patterns for parsing
    # Generic pattern to find potential requirement headers
    # Actual ID validation is done by PatternValidator
    HEADER_PATTERN = re.compile(
        r"^#*\s*(?P<id>[A-Z]+-[A-Za-z0-9-]+):\s*(?P<title>.+)$"
    )
    LEVEL_STATUS_PATTERN = re.compile(
        r"\*\*Level\*\*:\s*(?P<level>\w+)"
        r"(?:\s*\|\s*\*\*Implements\*\*:\s*(?P<implements>[^|]+))?"
        r"(?:\s*\|\s*\*\*Status\*\*:\s*(?P<status>\w+))?"
    )
    ALT_STATUS_PATTERN = re.compile(
        r"\*\*Status\*\*:\s*(?P<status>\w+)"
    )
    IMPLEMENTS_PATTERN = re.compile(
        r"\*\*Implements\*\*:\s*(?P<implements>[^|]+)"
    )
    END_MARKER_PATTERN = re.compile(
        r"^\*End\*\s+\*[^*]+\*\s*(?:\|\s*\*\*Hash\*\*:\s*(?P<hash>[a-zA-Z0-9]+))?",
        re.MULTILINE
    )
    RATIONALE_PATTERN = re.compile(
        r"\*\*Rationale\*\*:\s*(.+?)(?=\n\n|\n\*\*|\Z)", re.DOTALL
    )
    ACCEPTANCE_PATTERN = re.compile(
        r"\*\*Acceptance Criteria\*\*:\s*\n((?:\s*-\s*.+\n?)+)", re.MULTILINE
    )
    # Assertions section header (## Assertions or **Assertions**)
    ASSERTIONS_HEADER_PATTERN = re.compile(
        r"^##\s+Assertions\s*$", re.MULTILINE
    )
    # Individual assertion line: "A. The system SHALL..." or "01. ..." etc.
    # Captures: label (any alphanumeric), text (rest of line, may continue)
    ASSERTION_LINE_PATTERN = re.compile(
        r"^\s*([A-Z0-9]+)\.\s+(.+)$", re.MULTILINE
    )

    # Default values that mean "no references" in Implements field
    DEFAULT_NO_REFERENCE_VALUES = ["-", "null", "none", "x", "X", "N/A", "n/a"]

    # Default placeholder values that indicate a removed/deprecated assertion
    DEFAULT_PLACEHOLDER_VALUES = [
        "obsolete", "removed", "deprecated", "N/A", "n/a", "-", "reserved"
    ]

    def __init__(
        self,
        pattern_config: PatternConfig,
        no_reference_values: Optional[List[str]] = None,
        placeholder_values: Optional[List[str]] = None,
    ):
        """
        Initialize parser with pattern configuration.

        Args:
            pattern_config: Configuration for ID patterns
            no_reference_values: Values in Implements field that mean "no references"
            placeholder_values: Values that indicate removed/deprecated assertions
        """
        self.pattern_config = pattern_config
        self.validator = PatternValidator(pattern_config)
        self.no_reference_values = (
            no_reference_values
            if no_reference_values is not None
            else self.DEFAULT_NO_REFERENCE_VALUES
        )
        self.placeholder_values = (
            placeholder_values
            if placeholder_values is not None
            else self.DEFAULT_PLACEHOLDER_VALUES
        )

    def parse_text(
        self,
        text: str,
        file_path: Optional[Path] = None,
        subdir: str = "",
    ) -> Dict[str, Requirement]:
        """
        Parse requirements from text.

        Args:
            text: Markdown text containing requirements
            file_path: Optional source file path for location tracking
            subdir: Subdirectory within spec/ (e.g., "roadmap", "archive", "")

        Returns:
            Dictionary of requirement ID -> Requirement
        """
        requirements = {}
        lines = text.split("\n")

        i = 0
        while i < len(lines):
            line = lines[i]

            # Look for requirement header
            header_match = self.HEADER_PATTERN.match(line)
            if header_match:
                req_id = header_match.group("id")

                # Validate ID against configured pattern
                if not self.validator.is_valid(req_id):
                    i += 1
                    continue

                title = header_match.group("title").strip()
                start_line = i + 1  # 1-indexed

                # Find the end of this requirement
                req_lines = [line]
                i += 1
                while i < len(lines):
                    req_lines.append(lines[i])
                    # Check for end marker or next requirement
                    if self.END_MARKER_PATTERN.match(lines[i]):
                        i += 1
                        # Skip separator line if present
                        if i < len(lines) and lines[i].strip() == "---":
                            i += 1
                        break
                    # Check for next valid requirement header
                    next_match = self.HEADER_PATTERN.match(lines[i])
                    if next_match and self.validator.is_valid(next_match.group("id")):
                        # Hit next requirement without end marker
                        break
                    i += 1

                # Parse the requirement block
                req_text = "\n".join(req_lines)
                req = self._parse_requirement_block(
                    req_id, title, req_text, file_path, start_line, subdir
                )
                if req:
                    requirements[req_id] = req
            else:
                i += 1

        return requirements

    def parse_file(
        self,
        file_path: Path,
        subdir: str = "",
    ) -> Dict[str, Requirement]:
        """
        Parse requirements from a file.

        Args:
            file_path: Path to the Markdown file
            subdir: Subdirectory within spec/ (e.g., "roadmap", "archive", "")

        Returns:
            Dictionary of requirement ID -> Requirement
        """
        text = file_path.read_text(encoding="utf-8")
        return self.parse_text(text, file_path, subdir)

    def parse_directory(
        self,
        directory: Path,
        patterns: Optional[List[str]] = None,
        skip_files: Optional[List[str]] = None,
        subdir: str = "",
    ) -> Dict[str, Requirement]:
        """
        Parse all requirements from a directory.

        Args:
            directory: Path to the spec directory
            patterns: Optional glob patterns to match files
            skip_files: Optional list of filenames to skip
            subdir: Subdirectory within spec/ (e.g., "roadmap", "archive", "")

        Returns:
            Dictionary of requirement ID -> Requirement
        """
        if patterns is None:
            patterns = ["*.md"]

        if skip_files is None:
            skip_files = []

        requirements = {}
        for pattern in patterns:
            for file_path in directory.glob(pattern):
                if file_path.is_file() and file_path.name not in skip_files:
                    file_reqs = self.parse_file(file_path, subdir)
                    requirements.update(file_reqs)

        return requirements

    def parse_directories(
        self,
        directories: Union[str, Path, Sequence[Union[str, Path]]],
        base_path: Optional[Path] = None,
        patterns: Optional[List[str]] = None,
        skip_files: Optional[List[str]] = None,
    ) -> Dict[str, Requirement]:
        """
        Parse all requirements from one or more directories.

        Does NOT recursively search subdirectories - only the specified directories.

        Args:
            directories: Single directory path (str/Path) or list of directory paths
            base_path: Base path to resolve relative directories against
            patterns: Optional glob patterns to match files (default: ["*.md"])
            skip_files: Optional list of filenames to skip

        Returns:
            Dictionary of requirement ID -> Requirement
        """
        # Normalize to list
        if isinstance(directories, (str, Path)):
            dir_list = [directories]
        else:
            dir_list = list(directories)

        if base_path is None:
            base_path = Path.cwd()

        requirements = {}
        for dir_entry in dir_list:
            if Path(dir_entry).is_absolute():
                dir_path = Path(dir_entry)
            else:
                dir_path = base_path / dir_entry
            if dir_path.exists() and dir_path.is_dir():
                dir_reqs = self.parse_directory(
                    dir_path, patterns=patterns, skip_files=skip_files
                )
                requirements.update(dir_reqs)

        return requirements

    def parse_directory_with_subdirs(
        self,
        directory: Path,
        subdirs: Optional[List[str]] = None,
        patterns: Optional[List[str]] = None,
        skip_files: Optional[List[str]] = None,
    ) -> Dict[str, Requirement]:
        """
        Parse requirements from a directory and its subdirectories.

        Unlike parse_directory, this method:
        - Parses the root directory (with subdir="")
        - Parses each specified subdirectory (with subdir set to the subdir name)

        Args:
            directory: Path to the spec directory
            subdirs: List of subdirectory names to include (e.g., ["roadmap", "archive"])
            patterns: Optional glob patterns to match files
            skip_files: Optional list of filenames to skip

        Returns:
            Dictionary of requirement ID -> Requirement
        """
        if subdirs is None:
            subdirs = []

        requirements = {}

        # Parse root directory
        root_reqs = self.parse_directory(
            directory, patterns=patterns, skip_files=skip_files, subdir=""
        )
        requirements.update(root_reqs)

        # Parse each subdirectory
        for subdir_name in subdirs:
            subdir_path = directory / subdir_name
            if subdir_path.exists() and subdir_path.is_dir():
                subdir_reqs = self.parse_directory(
                    subdir_path, patterns=patterns, skip_files=skip_files, subdir=subdir_name
                )
                requirements.update(subdir_reqs)

        return requirements

    def _parse_requirement_block(
        self,
        req_id: str,
        title: str,
        text: str,
        file_path: Optional[Path],
        line_number: int,
        subdir: str = "",
    ) -> Optional[Requirement]:
        """
        Parse a single requirement block.

        Args:
            req_id: The requirement ID
            title: The requirement title
            text: The full requirement text block
            file_path: Source file path
            line_number: Starting line number
            subdir: Subdirectory within spec/ (e.g., "roadmap", "archive", "")

        Returns:
            Requirement object or None if parsing fails
        """
        # Extract level, status, and implements from header line
        level = "Unknown"
        status = "Unknown"
        implements_str = ""

        level_match = self.LEVEL_STATUS_PATTERN.search(text)
        if level_match:
            level = level_match.group("level") or "Unknown"
            implements_str = level_match.group("implements") or ""
            status = level_match.group("status") or "Unknown"

        # Try alternative status pattern
        if status == "Unknown":
            alt_status_match = self.ALT_STATUS_PATTERN.search(text)
            if alt_status_match:
                status = alt_status_match.group("status")

        # Try alternative implements pattern
        if not implements_str:
            impl_match = self.IMPLEMENTS_PATTERN.search(text)
            if impl_match:
                implements_str = impl_match.group("implements")

        # Parse implements list
        implements = self._parse_implements(implements_str)

        # Extract body (text between header and acceptance/end)
        body = self._extract_body(text)

        # Extract rationale
        rationale = None
        rationale_match = self.RATIONALE_PATTERN.search(text)
        if rationale_match:
            rationale = rationale_match.group(1).strip()

        # Extract acceptance criteria (legacy format)
        acceptance_criteria = []
        acceptance_match = self.ACCEPTANCE_PATTERN.search(text)
        if acceptance_match:
            criteria_text = acceptance_match.group(1)
            acceptance_criteria = [
                line.strip().lstrip("- ").strip()
                for line in criteria_text.split("\n")
                if line.strip().startswith("-")
            ]

        # Extract assertions (new format)
        assertions = self._extract_assertions(text)

        # Extract hash from end marker
        hash_value = None
        end_match = self.END_MARKER_PATTERN.search(text)
        if end_match:
            hash_value = end_match.group("hash")

        return Requirement(
            id=req_id,
            title=title,
            level=level,
            status=status,
            body=body,
            implements=implements,
            acceptance_criteria=acceptance_criteria,
            assertions=assertions,
            rationale=rationale,
            hash=hash_value,
            file_path=file_path,
            line_number=line_number,
            subdir=subdir,
        )

    def _parse_implements(self, implements_str: str) -> List[str]:
        """Parse comma-separated implements list.

        Returns empty list if the value is a "no reference" indicator.
        """
        if not implements_str:
            return []

        # Check if it's a "no reference" value
        stripped = implements_str.strip()
        if stripped in self.no_reference_values:
            return []

        parts = [p.strip() for p in implements_str.split(",")]
        # Filter out empty parts and no-reference values
        return [p for p in parts if p and p not in self.no_reference_values]

    def _extract_body(self, text: str) -> str:
        """Extract the main body text from requirement block.

        Matches hht-diary behavior: body is everything between the status line
        and the end marker, including Rationale and Acceptance Criteria sections.
        Trailing blank lines are removed for consistent hashing.
        """
        lines = text.split("\n")
        body_lines = []
        in_body = False

        for line in lines:
            # Skip header line and everything before status line
            if self.HEADER_PATTERN.match(line):
                continue

            # Status line marks the start - skip it but start collecting after
            if "**Level**" in line or "**Status**" in line:
                in_body = True
                continue

            # Stop at end marker
            if line.strip().startswith("*End*"):
                break

            if in_body:
                body_lines.append(line)

        # Remove trailing blank lines (matches hht-diary clean_requirement_body)
        while body_lines and not body_lines[-1].strip():
            body_lines.pop()

        # Strip trailing whitespace from result (hht-diary does this via .strip() on rationale)
        return "\n".join(body_lines).rstrip()

    def _extract_assertions(self, text: str) -> List[Assertion]:
        """Extract assertions from requirement text.

        Looks for `## Assertions` section and parses lines like:
        A. The system SHALL...
        B. The system SHALL NOT...

        Args:
            text: The requirement text block

        Returns:
            List of Assertion objects
        """
        assertions: List[Assertion] = []

        # Find the assertions section
        header_match = self.ASSERTIONS_HEADER_PATTERN.search(text)
        if not header_match:
            return assertions

        # Get text after the header until the next section or end marker
        start_pos = header_match.end()
        section_text = text[start_pos:]

        # Find the end of the assertions section (next ## header, Rationale, or End marker)
        end_patterns = [
            r"^##\s+",           # Next section header
            r"^\*End\*",         # End marker
            r"^---\s*$",         # Separator line
        ]
        end_pos = len(section_text)
        for pattern in end_patterns:
            match = re.search(pattern, section_text, re.MULTILINE)
            if match and match.start() < end_pos:
                end_pos = match.start()

        assertions_text = section_text[:end_pos]

        # Parse individual assertion lines
        for match in self.ASSERTION_LINE_PATTERN.finditer(assertions_text):
            label = match.group(1)
            assertion_text = match.group(2).strip()

            # Check if this is a placeholder
            is_placeholder = any(
                assertion_text.lower().startswith(pv.lower())
                for pv in self.placeholder_values
            )

            assertions.append(Assertion(
                label=label,
                text=assertion_text,
                is_placeholder=is_placeholder,
            ))

        return assertions
