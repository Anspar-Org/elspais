"""
elspais.core.parser - Requirement file parsing.

Parses Markdown files containing requirements in the standard format.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Union

from elspais.core.graph import FileNode, FileRegion
from elspais.core.models import (
    Assertion,
    ParseResult,
    ParseWarning,
    Requirement,
    StructuredParseResult,
)
from elspais.core.patterns import PatternConfig, PatternValidator


class RequirementParser:
    """
    Parses requirement specifications from Markdown files.
    """

    # Regex patterns for parsing
    # Generic pattern to find potential requirement headers
    # Actual ID validation is done by PatternValidator
    HEADER_PATTERN = re.compile(r"^#*\s*(?P<id>[A-Z]+-[A-Za-z0-9-]+):\s*(?P<title>.+)$")
    LEVEL_STATUS_PATTERN = re.compile(
        r"\*\*Level\*\*:\s*(?P<level>\w+)"
        r"(?:\s*\|\s*\*\*Implements\*\*:\s*(?P<implements>[^|\n]+))?"
        r"(?:\s*\|\s*\*\*Status\*\*:\s*(?P<status>\w+))?"
    )
    ALT_STATUS_PATTERN = re.compile(r"\*\*Status\*\*:\s*(?P<status>\w+)")
    IMPLEMENTS_PATTERN = re.compile(r"\*\*Implements\*\*:\s*(?P<implements>[^|\n]+)")
    REFINES_PATTERN = re.compile(r"\*\*Refines\*\*:\s*(?P<refines>[^|\n]+)")
    END_MARKER_PATTERN = re.compile(
        r"^\*End\*\s+\*[^*]+\*\s*(?:\|\s*\*\*Hash\*\*:\s*(?P<hash>[a-zA-Z0-9]+))?", re.MULTILINE
    )
    RATIONALE_PATTERN = re.compile(r"\*\*Rationale\*\*:\s*(.+?)(?=\n\n|\n\*\*|\Z)", re.DOTALL)
    ACCEPTANCE_PATTERN = re.compile(
        r"\*\*Acceptance Criteria\*\*:\s*\n((?:\s*-\s*.+\n?)+)", re.MULTILINE
    )
    # Assertions section header (## Assertions or **Assertions**)
    ASSERTIONS_HEADER_PATTERN = re.compile(r"^##\s+Assertions\s*$", re.MULTILINE)
    # Individual assertion line: "A. The system SHALL..." or "01. ..." etc.
    # Captures: label (any alphanumeric), text (rest of line, may continue)
    ASSERTION_LINE_PATTERN = re.compile(r"^\s*([A-Z0-9]+)\.\s+(.+)$", re.MULTILINE)

    # Default values that mean "no references" in Implements field
    DEFAULT_NO_REFERENCE_VALUES = ["-", "null", "none", "x", "X", "N/A", "n/a"]

    # Default placeholder values that indicate a removed/deprecated assertion
    DEFAULT_PLACEHOLDER_VALUES = [
        "obsolete",
        "removed",
        "deprecated",
        "N/A",
        "n/a",
        "-",
        "reserved",
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
    ) -> ParseResult:
        """
        Parse requirements from text.

        Args:
            text: Markdown text containing requirements
            file_path: Optional source file path for location tracking
            subdir: Subdirectory within spec/ (e.g., "roadmap", "archive", "")

        Returns:
            ParseResult with requirements dict and warnings list
        """
        requirements: Dict[str, Requirement] = {}
        warnings: List[ParseWarning] = []
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
                req, block_warnings = self._parse_requirement_block(
                    req_id, title, req_text, file_path, start_line, subdir
                )
                warnings.extend(block_warnings)
                if req:
                    # Check for duplicate ID
                    if req_id in requirements:
                        # Keep both: original stays, duplicate gets __conflict suffix
                        conflict_key, conflict_req, warning = self._make_conflict_entry(
                            req, req_id, requirements[req_id], file_path, start_line
                        )
                        requirements[conflict_key] = conflict_req
                        warnings.append(warning)
                    else:
                        requirements[req_id] = req
            else:
                i += 1

        return ParseResult(requirements=requirements, warnings=warnings)

    def parse_file(
        self,
        file_path: Path,
        subdir: str = "",
    ) -> ParseResult:
        """
        Parse requirements from a file.

        Args:
            file_path: Path to the Markdown file
            subdir: Subdirectory within spec/ (e.g., "roadmap", "archive", "")

        Returns:
            ParseResult with requirements dict and warnings list
        """
        text = file_path.read_text(encoding="utf-8")
        return self.parse_text(text, file_path, subdir)

    def parse_file_with_structure(
        self,
        file_path: Path,
        repo_root: Optional[Path] = None,
        subdir: str = "",
        preserve_lines: bool = False,
    ) -> StructuredParseResult:
        """
        Parse requirements from a file AND preserve file structure.

        Used for lossless file reconstruction. Captures requirements,
        warnings, AND the file structure (regions, ordering) needed
        to reconstruct the original file.

        Args:
            file_path: Path to the Markdown file
            repo_root: Repository root for relative path calculation
            subdir: Subdirectory within spec/ (e.g., "roadmap", "archive", "")
            preserve_lines: If True, store original_lines in FileNode (uses more memory)

        Returns:
            StructuredParseResult with requirements, warnings, and FileNode
        """
        text = file_path.read_text(encoding="utf-8")
        lines = text.split("\n")

        requirements: Dict[str, Requirement] = {}
        warnings: List[ParseWarning] = []
        regions: List[FileRegion] = []
        requirement_order: List[str] = []

        # Calculate relative file path
        if repo_root:
            rel_path = str(file_path.relative_to(repo_root))
        else:
            rel_path = str(file_path)

        # Track line boundaries
        i = 0
        last_req_end_line = 0  # Line after last requirement (0 means no reqs yet)

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

                # Capture region before this requirement
                if last_req_end_line == 0:
                    # First requirement - capture preamble
                    if i > 0:
                        regions.append(FileRegion(
                            region_type="preamble",
                            start_line=1,
                            end_line=i,
                            content="\n".join(lines[:i]),
                        ))
                else:
                    # Inter-requirement region
                    if i > last_req_end_line:
                        regions.append(FileRegion(
                            region_type="inter_requirement",
                            start_line=last_req_end_line + 1,
                            end_line=i,
                            content="\n".join(lines[last_req_end_line:i]),
                        ))

                title = header_match.group("title").strip()
                start_line = i + 1  # 1-indexed

                # Find the end of this requirement
                req_lines = [line]
                i += 1
                while i < len(lines):
                    req_lines.append(lines[i])
                    # Check for end marker or next requirement
                    if self.END_MARKER_PATTERN.match(lines[i]):
                        last_req_end_line = i + 1
                        i += 1
                        # Skip separator line if present
                        if i < len(lines) and lines[i].strip() == "---":
                            req_lines.append(lines[i])
                            last_req_end_line = i + 1
                            i += 1
                        break
                    # Check for next valid requirement header
                    next_match = self.HEADER_PATTERN.match(lines[i])
                    if next_match and self.validator.is_valid(next_match.group("id")):
                        # Hit next requirement without end marker
                        last_req_end_line = i
                        break
                    i += 1
                else:
                    # Reached end of file without end marker
                    last_req_end_line = len(lines)

                # Parse the requirement block
                req_text = "\n".join(req_lines)
                req, block_warnings = self._parse_requirement_block(
                    req_id, title, req_text, file_path, start_line, subdir
                )
                warnings.extend(block_warnings)
                if req:
                    # Check for duplicate ID
                    if req_id in requirements:
                        # Keep both: original stays, duplicate gets __conflict suffix
                        conflict_key, conflict_req, warning = self._make_conflict_entry(
                            req, req_id, requirements[req_id], file_path, start_line
                        )
                        requirements[conflict_key] = conflict_req
                        warnings.append(warning)
                    else:
                        requirements[req_id] = req
                    requirement_order.append(req_id)
            else:
                i += 1

        # Capture postamble (content after last requirement)
        if last_req_end_line > 0 and last_req_end_line < len(lines):
            regions.append(FileRegion(
                region_type="postamble",
                start_line=last_req_end_line + 1,
                end_line=len(lines),
                content="\n".join(lines[last_req_end_line:]),
            ))
        elif last_req_end_line == 0 and lines:
            # No requirements found - entire file is "preamble"
            regions.append(FileRegion(
                region_type="preamble",
                start_line=1,
                end_line=len(lines),
                content="\n".join(lines),
            ))

        # Create FileNode
        file_node = FileNode(
            file_path=rel_path,
            requirements=requirement_order,
            regions=regions,
            original_lines=lines if preserve_lines else None,
        )

        return StructuredParseResult(
            requirements=requirements,
            warnings=warnings,
            file_node=file_node,
        )

    def parse_directory(
        self,
        directory: Path,
        patterns: Optional[List[str]] = None,
        skip_files: Optional[List[str]] = None,
        skip_dirs: Optional[List[str]] = None,
        subdir: str = "",
        recursive: bool = False,
    ) -> ParseResult:
        """
        Parse all requirements from a directory.

        Args:
            directory: Path to the spec directory
            patterns: Optional glob patterns to match files
            skip_files: Optional list of filenames to skip
            skip_dirs: Optional list of directory names to skip (e.g., ["roadmap", "archive"])
            subdir: Subdirectory within spec/ (e.g., "roadmap", "archive", "")
                    Ignored when recursive=True (computed from file path).
            recursive: If True, recursively search subdirectories using rglob.
                      The subdir for each file is computed from its relative path.

        Returns:
            ParseResult with requirements dict and warnings list
        """
        if patterns is None:
            patterns = ["*.md"]

        if skip_files is None:
            skip_files = []

        if skip_dirs is None:
            skip_dirs = []

        requirements: Dict[str, Requirement] = {}
        warnings: List[ParseWarning] = []

        for pattern in patterns:
            # Use rglob for recursive search, glob for non-recursive
            if recursive:
                file_iter = directory.rglob(pattern)
            else:
                file_iter = directory.glob(pattern)

            for file_path in file_iter:
                if not file_path.is_file():
                    continue
                if file_path.name in skip_files:
                    continue

                # Check skip_dirs - filter out files in skipped directories
                if skip_dirs:
                    rel_path = file_path.relative_to(directory)
                    if any(skip_dir in rel_path.parts for skip_dir in skip_dirs):
                        continue

                # Compute subdir from relative path when recursive
                if recursive:
                    rel_path = file_path.relative_to(directory)
                    file_subdir = str(rel_path.parent) if rel_path.parent != Path(".") else ""
                else:
                    file_subdir = subdir

                result = self.parse_file(file_path, file_subdir)
                # Merge requirements, checking for cross-file duplicates
                for req_id, req in result.requirements.items():
                    if req_id in requirements:
                        # Keep both: original stays, duplicate gets __conflict suffix
                        conflict_key, conflict_req, warning = self._make_conflict_entry(
                            req, req_id, requirements[req_id], file_path, req.line_number
                        )
                        requirements[conflict_key] = conflict_req
                        warnings.append(warning)
                    else:
                        requirements[req_id] = req
                warnings.extend(result.warnings)

        return ParseResult(requirements=requirements, warnings=warnings)

    def parse_directories(
        self,
        directories: Union[str, Path, Sequence[Union[str, Path]]],
        base_path: Optional[Path] = None,
        patterns: Optional[List[str]] = None,
        skip_files: Optional[List[str]] = None,
        skip_dirs: Optional[List[str]] = None,
        recursive: bool = False,
    ) -> ParseResult:
        """
        Parse all requirements from one or more directories.

        Args:
            directories: Single directory path (str/Path) or list of directory paths
            base_path: Base path to resolve relative directories against
            patterns: Optional glob patterns to match files (default: ["*.md"])
            skip_files: Optional list of filenames to skip
            skip_dirs: Optional list of directory names to skip (e.g., ["roadmap", "archive"])
            recursive: If True, search subdirectories recursively (default: False)

        Returns:
            ParseResult with requirements dict and warnings list
        """
        # Normalize to list
        if isinstance(directories, (str, Path)):
            dir_list = [directories]
        else:
            dir_list = list(directories)

        if base_path is None:
            base_path = Path.cwd()

        requirements: Dict[str, Requirement] = {}
        warnings: List[ParseWarning] = []

        for dir_entry in dir_list:
            if Path(dir_entry).is_absolute():
                dir_path = Path(dir_entry)
            else:
                dir_path = base_path / dir_entry
            if dir_path.exists() and dir_path.is_dir():
                result = self.parse_directory(
                    dir_path,
                    patterns=patterns,
                    skip_files=skip_files,
                    skip_dirs=skip_dirs,
                    recursive=recursive,
                )
                # Merge requirements, checking for cross-directory duplicates
                for req_id, req in result.requirements.items():
                    if req_id in requirements:
                        # Keep both: original stays, duplicate gets __conflict suffix
                        conflict_key, conflict_req, warning = self._make_conflict_entry(
                            req, req_id, requirements[req_id], req.file_path, req.line_number
                        )
                        requirements[conflict_key] = conflict_req
                        warnings.append(warning)
                    else:
                        requirements[req_id] = req
                warnings.extend(result.warnings)

        return ParseResult(requirements=requirements, warnings=warnings)

    def parse_directory_with_subdirs(
        self,
        directory: Path,
        subdirs: Optional[List[str]] = None,
        patterns: Optional[List[str]] = None,
        skip_files: Optional[List[str]] = None,
    ) -> ParseResult:
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
            ParseResult with requirements dict and warnings list
        """
        if subdirs is None:
            subdirs = []

        requirements: Dict[str, Requirement] = {}
        warnings: List[ParseWarning] = []

        # Parse root directory
        root_result = self.parse_directory(
            directory, patterns=patterns, skip_files=skip_files, subdir=""
        )
        requirements.update(root_result.requirements)
        warnings.extend(root_result.warnings)

        # Parse each subdirectory
        for subdir_name in subdirs:
            subdir_path = directory / subdir_name
            if subdir_path.exists() and subdir_path.is_dir():
                subdir_result = self.parse_directory(
                    subdir_path, patterns=patterns, skip_files=skip_files, subdir=subdir_name
                )
                # Merge requirements, checking for cross-subdir duplicates
                for req_id, req in subdir_result.requirements.items():
                    if req_id in requirements:
                        # Keep both: original stays, duplicate gets __conflict suffix
                        conflict_key, conflict_req, warning = self._make_conflict_entry(
                            req, req_id, requirements[req_id], req.file_path, req.line_number
                        )
                        requirements[conflict_key] = conflict_req
                        warnings.append(warning)
                    else:
                        requirements[req_id] = req
                warnings.extend(subdir_result.warnings)

        return ParseResult(requirements=requirements, warnings=warnings)

    def _make_conflict_entry(
        self,
        duplicate_req: Requirement,
        original_id: str,
        original_req: Requirement,
        file_path: Optional[Path],
        line_number: Optional[int],
    ) -> tuple:
        """
        Create a conflict entry for a duplicate requirement.

        When a requirement ID already exists, this creates a modified version
        of the duplicate with:
        - Key suffix `__conflict` for storage
        - `is_conflict=True` flag
        - `conflict_with` set to the original ID
        - `implements=[]` (treated as orphaned)

        Args:
            duplicate_req: The duplicate requirement that was found
            original_id: The ID that is duplicated
            original_req: The original requirement that was first
            file_path: File path for the warning
            line_number: Line number for the warning

        Returns:
            Tuple of (conflict_key, modified_requirement, ParseWarning)
        """
        conflict_key = f"{original_id}__conflict"

        # Modify the duplicate requirement
        duplicate_req.is_conflict = True
        duplicate_req.conflict_with = original_id
        duplicate_req.implements = []  # Treat as orphaned

        warning = ParseWarning(
            requirement_id=original_id,
            message=(
                f"Duplicate ID found "
                f"(first occurrence in {original_req.file_path}:{original_req.line_number})"
            ),
            file_path=file_path,
            line_number=line_number,
        )

        return conflict_key, duplicate_req, warning

    def _parse_requirement_block(
        self,
        req_id: str,
        title: str,
        text: str,
        file_path: Optional[Path],
        line_number: int,
        subdir: str = "",
    ) -> tuple:
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
            Tuple of (Requirement or None, List[ParseWarning])
        """
        block_warnings: List[ParseWarning] = []

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

        # Parse refines field
        refines_str = ""
        refines_match = self.REFINES_PATTERN.search(text)
        if refines_match:
            refines_str = refines_match.group("refines")

        # Parse implements list, validate references, and expand multi-assertion syntax
        implements = self._parse_implements(implements_str)
        implements = self._expand_multi_assertion_refs(implements)
        for ref in implements:
            if not self.validator.is_valid(ref, allow_assertion=True):
                block_warnings.append(
                    ParseWarning(
                        requirement_id=req_id,
                        message=f"Invalid implements reference: {ref}",
                        file_path=file_path,
                        line_number=line_number,
                    )
                )

        # Parse refines list, validate references, and expand multi-assertion syntax
        refines = self._parse_implements(refines_str)
        refines = self._expand_multi_assertion_refs(refines)
        for ref in refines:
            if not self.validator.is_valid(ref, allow_assertion=True):
                block_warnings.append(
                    ParseWarning(
                        requirement_id=req_id,
                        message=f"Invalid refines reference: {ref}",
                        file_path=file_path,
                        line_number=line_number,
                    )
                )

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

        # Extract assertions (new format) and validate labels
        assertions = self._extract_assertions(text)
        for assertion in assertions:
            if not self._is_valid_assertion_label(assertion.label):
                block_warnings.append(
                    ParseWarning(
                        requirement_id=req_id,
                        message=f"Invalid assertion label format: {assertion.label}",
                        file_path=file_path,
                        line_number=line_number,
                    )
                )

        # Extract hash from end marker
        hash_value = None
        end_match = self.END_MARKER_PATTERN.search(text)
        if end_match:
            hash_value = end_match.group("hash")

        req = Requirement(
            id=req_id,
            title=title,
            level=level,
            status=status,
            body=body,
            implements=implements,
            refines=refines,
            acceptance_criteria=acceptance_criteria,
            assertions=assertions,
            rationale=rationale,
            hash=hash_value,
            file_path=file_path,
            line_number=line_number,
            subdir=subdir,
        )
        return req, block_warnings

    def _is_valid_assertion_label(self, label: str) -> bool:
        """Check if an assertion label matches expected format.

        Default expectation is uppercase letters A-Z.
        """
        # Check against configured assertion label pattern if available
        assertion_config = getattr(self.pattern_config, "assertions", None)
        if assertion_config:
            label_style = assertion_config.get("label_style", "uppercase")
            if label_style == "uppercase":
                return bool(re.match(r"^[A-Z]$", label))
            elif label_style == "numeric":
                return bool(re.match(r"^\d+$", label))
            elif label_style == "alphanumeric":
                return bool(re.match(r"^[A-Z0-9]+$", label))
        # Default: uppercase single letter
        return bool(re.match(r"^[A-Z]$", label))

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

    def _expand_multi_assertion_refs(self, refs: List[str]) -> List[str]:
        """Expand multi-assertion syntax to individual assertion refs.

        Handles formats like:
        - "REQ-p00001-A-B-C" -> ["REQ-p00001-A", "REQ-p00001-B", "REQ-p00001-C"]
        - "REQ-p00001-A" -> ["REQ-p00001-A"]
        - "REQ-p00001" -> ["REQ-p00001"]

        Args:
            refs: List of potentially multi-assertion references.

        Returns:
            List with multi-assertion refs expanded.
        """
        result = []
        # Pattern to detect multi-assertion: REQ-xxx-A-B-C or REQ-xxx-01-02-03
        # Group 1: base requirement ID (e.g., REQ-p00001)
        # Group 2: assertion labels (e.g., -A-B-C or -01-02-03)
        multi_assertion_pattern = re.compile(
            r"^([A-Z]+-[A-Za-z0-9-]+?)(-[A-Z](?:-[A-Z])+|-\d+(?:-\d+)+)$"
        )

        for ref in refs:
            match = multi_assertion_pattern.match(ref)
            if match:
                base_id = match.group(1)
                labels_str = match.group(2)
                # Split labels (e.g., "-A-B-C" -> ["A", "B", "C"])
                labels = [lbl for lbl in labels_str.split("-") if lbl]
                for label in labels:
                    result.append(f"{base_id}-{label}")
            else:
                result.append(ref)

        return result

    def _extract_body(self, text: str) -> str:
        """Extract the main body text from requirement block.

        Body is everything between the header (and optional metadata line)
        and the end marker, including Rationale and Acceptance Criteria sections.
        Trailing blank lines are removed for consistent hashing.
        """
        lines = text.split("\n")
        body_lines = []
        found_header = False
        in_body = False

        for line in lines:
            # Skip header line
            if self.HEADER_PATTERN.match(line):
                found_header = True
                continue

            if found_header and not in_body:
                # Metadata line - skip it but mark body start
                if "**Level**" in line or "**Status**" in line:
                    in_body = True
                    continue
                # First non-blank content line starts body (when no metadata)
                elif line.strip():
                    in_body = True
                    # Don't continue - include this line in body

            # Stop at end marker
            if line.strip().startswith("*End*"):
                break

            if in_body:
                body_lines.append(line)

        # Remove trailing blank lines (matches hht-diary clean_requirement_body)
        while body_lines and not body_lines[-1].strip():
            body_lines.pop()

        # Strip trailing whitespace from result
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
            r"^##\s+",  # Next section header
            r"^\*End\*",  # End marker
            r"^---\s*$",  # Separator line
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
                assertion_text.lower().startswith(pv.lower()) for pv in self.placeholder_values
            )

            assertions.append(
                Assertion(
                    label=label,
                    text=assertion_text,
                    is_placeholder=is_placeholder,
                )
            )

        return assertions
