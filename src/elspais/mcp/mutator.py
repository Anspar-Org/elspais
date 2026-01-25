"""
elspais.mcp.mutator - Graph-to-filesystem sync operations.

Provides the GraphMutator class for reading and writing spec files
while preserving format and tracking line numbers for requirement
location.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from elspais.core.patterns import PatternConfig, PatternValidator


@dataclass
class RequirementLocation:
    """Location of a requirement within a spec file.

    Attributes:
        start_line: 1-indexed line number of the requirement header
        end_line: 1-indexed line number of the last line (inclusive)
        header_line: The requirement header line text
        has_end_marker: Whether the requirement has an *End* marker
        has_separator: Whether a --- separator follows the end marker
    """

    start_line: int
    end_line: int
    header_line: str
    has_end_marker: bool
    has_separator: bool


@dataclass
class FileContent:
    """Content of a spec file with line tracking.

    Attributes:
        path: Absolute path to the file
        text: Full file content as string
        lines: Content split into lines (0-indexed list)
    """

    path: Path
    text: str
    lines: list[str]


class GraphMutator:
    """
    Encapsulates graph-to-filesystem sync operations.

    Provides methods for reading and writing spec files while
    preserving format and tracking line numbers for requirement
    location.

    Attributes:
        working_dir: Root directory of the workspace
        pattern_config: Configuration for requirement ID patterns
    """

    # Regex patterns matching those in core/parser.py
    HEADER_PATTERN = re.compile(r"^#*\s*(?P<id>[A-Z]+-[A-Za-z0-9-]+):\s*(?P<title>.+)$")
    END_MARKER_PATTERN = re.compile(
        r"^\*End\*\s+\*[^*]+\*\s*(?:\|\s*\*\*Hash\*\*:\s*(?P<hash>[a-zA-Z0-9]+))?",
        re.MULTILINE,
    )

    def __init__(
        self,
        working_dir: Path,
        pattern_config: Optional[PatternConfig] = None,
    ):
        """
        Initialize the mutator.

        Args:
            working_dir: Root directory of the workspace
            pattern_config: Optional pattern configuration for ID validation.
                           If not provided, a default config is used.
        """
        self.working_dir = working_dir
        self.pattern_config = pattern_config or PatternConfig.from_dict({})
        self.validator = PatternValidator(self.pattern_config)

    def _read_spec_file(self, path: Path) -> FileContent:
        """
        Read a spec file and return its content with line tracking.

        Args:
            path: Path to the spec file (absolute or relative to working_dir)

        Returns:
            FileContent with path, text, and lines

        Raises:
            FileNotFoundError: If the file doesn't exist
            ValueError: If the path is outside the workspace
        """
        # Resolve path relative to working_dir if not absolute
        if not path.is_absolute():
            path = self.working_dir / path
        path = path.resolve()

        # Security check: ensure path is within working_dir
        try:
            path.relative_to(self.working_dir.resolve())
        except ValueError:
            raise ValueError(f"Path {path} is outside workspace {self.working_dir}")

        if not path.exists():
            raise FileNotFoundError(f"Spec file not found: {path}")

        text = path.read_text(encoding="utf-8")
        lines = text.split("\n")

        return FileContent(path=path, text=text, lines=lines)

    def _write_spec_file(self, path: Path, content: str) -> None:
        """
        Write content to a spec file, preserving format.

        Args:
            path: Path to the spec file (absolute or relative to working_dir)
            content: New file content to write

        Raises:
            ValueError: If the path is outside the workspace
        """
        # Resolve path relative to working_dir if not absolute
        if not path.is_absolute():
            path = self.working_dir / path
        path = path.resolve()

        # Security check: ensure path is within working_dir
        try:
            path.relative_to(self.working_dir.resolve())
        except ValueError:
            raise ValueError(f"Path {path} is outside workspace {self.working_dir}")

        # Ensure parent directory exists
        path.parent.mkdir(parents=True, exist_ok=True)

        path.write_text(content, encoding="utf-8")

    def _find_requirement_lines(
        self,
        content: FileContent,
        req_id: str,
    ) -> Optional[RequirementLocation]:
        """
        Find the line range for a requirement by ID.

        Locates the requirement in the file and returns its start and end
        line numbers (1-indexed), along with metadata about the block.

        Args:
            content: FileContent from _read_spec_file
            req_id: The requirement ID to find (e.g., "REQ-p00001")

        Returns:
            RequirementLocation if found, None if not found
        """
        lines = content.lines
        start_line: Optional[int] = None
        header_line: str = ""
        i = 0

        while i < len(lines):
            line = lines[i]

            # Look for requirement header
            header_match = self.HEADER_PATTERN.match(line)
            if header_match:
                found_id = header_match.group("id")

                if found_id == req_id:
                    start_line = i + 1  # 1-indexed
                    header_line = line
                    end_line = i + 1  # At minimum, ends at same line
                    has_end_marker = False
                    has_separator = False

                    # Find the end of this requirement
                    i += 1
                    while i < len(lines):
                        current_line = lines[i]

                        # Check for end marker
                        if self.END_MARKER_PATTERN.match(current_line):
                            end_line = i + 1  # 1-indexed
                            has_end_marker = True
                            # Check for separator line
                            if i + 1 < len(lines) and lines[i + 1].strip() == "---":
                                end_line = i + 2  # Include separator
                                has_separator = True
                            break

                        # Check for next requirement header (any valid header pattern)
                        # Note: We use a permissive check here rather than full ID validation
                        # because the mutator only needs to find where requirement blocks end
                        next_match = self.HEADER_PATTERN.match(current_line)
                        if next_match:
                            # End before next requirement (don't include it)
                            end_line = i  # Previous line (1-indexed)
                            break

                        end_line = i + 1  # Update end line as we go
                        i += 1

                    return RequirementLocation(
                        start_line=start_line,
                        end_line=end_line,
                        header_line=header_line,
                        has_end_marker=has_end_marker,
                        has_separator=has_separator,
                    )

            i += 1

        return None

    def get_requirement_text(
        self,
        content: FileContent,
        location: RequirementLocation,
    ) -> str:
        """
        Extract requirement text from a file using its location.

        Args:
            content: FileContent from _read_spec_file
            location: RequirementLocation from _find_requirement_lines

        Returns:
            The full requirement text including header and end marker
        """
        # Convert 1-indexed to 0-indexed for list access
        start_idx = location.start_line - 1
        end_idx = location.end_line  # end_line is inclusive, so use directly
        return "\n".join(content.lines[start_idx:end_idx])

    def replace_requirement_text(
        self,
        content: FileContent,
        location: RequirementLocation,
        new_text: str,
    ) -> str:
        """
        Replace requirement text in file content.

        Args:
            content: FileContent from _read_spec_file
            location: RequirementLocation of requirement to replace
            new_text: New text to replace the requirement with

        Returns:
            New file content with the requirement replaced
        """
        # Convert 1-indexed to 0-indexed for list access
        start_idx = location.start_line - 1
        end_idx = location.end_line  # end_line is inclusive

        # Split new_text into lines
        new_lines = new_text.split("\n")

        # Build new content: before + new + after
        result_lines = content.lines[:start_idx] + new_lines + content.lines[end_idx:]

        return "\n".join(result_lines)
