"""
elspais.mcp.mutator - Spec file mutation operations.

Provides the SpecFileMutator class for reading and writing spec files
while preserving format and tracking line numbers for requirement
location.
"""

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional, Tuple

from elspais.utilities.patterns import PatternConfig, PatternValidator


class ReferenceType(Enum):
    """Type of reference relationship between requirements."""

    IMPLEMENTS = "implements"
    REFINES = "refines"


@dataclass
class RequirementMove:
    """Result of a requirement move operation.

    Attributes:
        success: Whether the move was successful
        req_id: The requirement ID that was moved
        source_file: Path to the file the requirement was moved from
        target_file: Path to the file the requirement was moved to
        position: Where the requirement was inserted ("start", "end", "after")
        after_id: If position="after", the requirement ID it was placed after
        message: Description of the result or error
    """

    success: bool
    req_id: str
    source_file: Optional[Path]
    target_file: Optional[Path]
    position: str
    after_id: Optional[str]
    message: str


@dataclass
class FileDeletionAnalysis:
    """Result of analyzing a file for deletion.

    Attributes:
        can_delete: Whether the file can be safely deleted
        file_path: Path to the analyzed file
        remaining_requirements: List of requirement IDs still in the file
        non_requirement_content: Content that is not part of requirements
        has_non_requirement_content: Whether there is content to preserve
        message: Description of the analysis result
    """

    can_delete: bool
    file_path: Path
    remaining_requirements: List[str]
    non_requirement_content: str
    has_non_requirement_content: bool
    message: str


@dataclass
class FileDeletionResult:
    """Result of a file deletion operation.

    Attributes:
        success: Whether the deletion was successful
        file_path: Path to the deleted file
        content_extracted: Whether content was extracted before deletion
        content_target: Path where content was extracted (if any)
        message: Description of the result or error
    """

    success: bool
    file_path: Path
    content_extracted: bool
    content_target: Optional[Path]
    message: str


@dataclass
class ReferenceSpecialization:
    """Result of a reference specialization operation.

    Attributes:
        success: Whether the specialization was successful
        source_id: The requirement ID that was modified
        target_id: The original requirement reference (e.g., REQ-p00001)
        assertions: The assertions that were specialized to
        old_reference: The original reference string
        new_reference: The new specialized reference string
        file_path: Path to the modified file
        message: Description of the result or error
    """

    success: bool
    source_id: str
    target_id: str
    assertions: List[str]
    old_reference: str
    new_reference: str
    file_path: Optional[Path]
    message: str


@dataclass
class ReferenceChange:
    """Result of a reference type change operation.

    Attributes:
        success: Whether the change was successful
        source_id: The requirement ID that was modified
        target_id: The referenced requirement ID
        old_type: The original reference type
        new_type: The new reference type
        file_path: Path to the modified file
        message: Description of the result or error
    """

    success: bool
    source_id: str
    target_id: str
    old_type: Optional[ReferenceType]
    new_type: ReferenceType
    file_path: Optional[Path]
    message: str


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


class SpecFileMutator:
    """
    Encapsulates spec file mutation operations.

    Provides methods for reading and writing spec files while
    preserving format and tracking line numbers for requirement
    location.

    Attributes:
        working_dir: Root directory of the workspace
        pattern_config: Configuration for requirement ID patterns
    """

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

    # Regex patterns for reference parsing (matching core/parser.py)
    IMPLEMENTS_PATTERN = re.compile(r"\*\*Implements\*\*:\s*(?P<refs>[^|\n]+)")
    REFINES_PATTERN = re.compile(r"\*\*Refines\*\*:\s*(?P<refs>[^|\n]+)")
    METADATA_LINE_PATTERN = re.compile(r"^\*\*Level\*\*:")

    # No-reference marker values (from core/parser.py)
    NO_REFERENCE_VALUES = frozenset(["-", "null", "none", "x", "X", "N/A", "n/a"])

    def _find_metadata_line(
        self,
        req_text: str,
    ) -> Tuple[Optional[int], Optional[str]]:
        """
        Find the metadata line in a requirement block.

        The metadata line contains **Level**, **Status**, and reference fields.

        Args:
            req_text: The requirement text block

        Returns:
            Tuple of (line_index, line_text) or (None, None) if not found.
            Line index is 0-indexed relative to req_text.
        """
        lines = req_text.split("\n")
        for i, line in enumerate(lines):
            if self.METADATA_LINE_PATTERN.match(line):
                return i, line
        return None, None

    def _parse_reference_list(self, refs_str: str) -> List[str]:
        """
        Parse a comma-separated reference string into a list.

        Args:
            refs_str: Comma-separated references (e.g., "REQ-p00001, REQ-p00002")

        Returns:
            List of individual reference IDs (excluding no-reference markers)
        """
        refs = []
        for ref in refs_str.split(","):
            ref = ref.strip()
            if ref and ref not in self.NO_REFERENCE_VALUES:
                refs.append(ref)
        return refs

    def _find_reference_in_line(
        self,
        line: str,
        target_id: str,
    ) -> Tuple[Optional[ReferenceType], List[str]]:
        """
        Find which reference field contains the target ID.

        Args:
            line: The metadata line
            target_id: The reference ID to find

        Returns:
            Tuple of (reference_type, all_refs_in_field) or (None, []) if not found.
            reference_type is IMPLEMENTS or REFINES, all_refs_in_field is the
            list of all references in that field.
        """
        # Check Implements field
        impl_match = self.IMPLEMENTS_PATTERN.search(line)
        if impl_match:
            refs = self._parse_reference_list(impl_match.group("refs"))
            if target_id in refs:
                return ReferenceType.IMPLEMENTS, refs

        # Check Refines field
        ref_match = self.REFINES_PATTERN.search(line)
        if ref_match:
            refs = self._parse_reference_list(ref_match.group("refs"))
            if target_id in refs:
                return ReferenceType.REFINES, refs

        return None, []

    def _build_refs_string(self, refs: List[str]) -> str:
        """
        Build a comma-separated reference string from a list.

        Args:
            refs: List of reference IDs

        Returns:
            Comma-separated string or "-" if empty
        """
        if not refs:
            return "-"
        return ", ".join(refs)

    def _update_metadata_line(
        self,
        line: str,
        target_id: str,
        old_type: ReferenceType,
        new_type: ReferenceType,
    ) -> str:
        """
        Update the metadata line to change a reference from one type to another.

        Args:
            line: The original metadata line
            target_id: The reference ID to move
            old_type: Current type (IMPLEMENTS or REFINES)
            new_type: New type to change to

        Returns:
            Updated metadata line
        """
        if old_type == new_type:
            return line

        # Parse current references
        impl_match = self.IMPLEMENTS_PATTERN.search(line)
        ref_match = self.REFINES_PATTERN.search(line)

        impl_refs = (
            self._parse_reference_list(impl_match.group("refs"))
            if impl_match
            else []
        )
        refines_refs = (
            self._parse_reference_list(ref_match.group("refs"))
            if ref_match
            else []
        )

        # Move reference from old to new type
        if old_type == ReferenceType.IMPLEMENTS:
            impl_refs = [r for r in impl_refs if r != target_id]
            refines_refs.append(target_id)
        else:  # old_type == ReferenceType.REFINES
            refines_refs = [r for r in refines_refs if r != target_id]
            impl_refs.append(target_id)

        # Rebuild the line
        result = line

        # Update or add Implements field
        new_impl_str = self._build_refs_string(impl_refs)
        if impl_match:
            # Replace existing Implements field
            old_impl = impl_match.group(0)
            result = result.replace(old_impl, f"**Implements**: {new_impl_str}")
        elif impl_refs:
            # Need to add Implements field - insert before Status or at end
            status_match = re.search(r"\s*\|\s*\*\*Status\*\*:", result)
            if status_match:
                result = (
                    result[: status_match.start()]
                    + f" | **Implements**: {new_impl_str}"
                    + result[status_match.start() :]
                )
            else:
                result = result.rstrip() + f" | **Implements**: {new_impl_str}"

        # Update or add Refines field
        new_refines_str = self._build_refs_string(refines_refs)
        if ref_match:
            # Replace existing Refines field
            old_refines = ref_match.group(0)
            result = result.replace(old_refines, f"**Refines**: {new_refines_str}")
        elif refines_refs:
            # Need to add Refines field - insert before Status or at end
            # Re-search in updated result
            status_match = re.search(r"\s*\|\s*\*\*Status\*\*:", result)
            if status_match:
                result = (
                    result[: status_match.start()]
                    + f" | **Refines**: {new_refines_str}"
                    + result[status_match.start() :]
                )
            else:
                result = result.rstrip() + f" | **Refines**: {new_refines_str}"

        # Remove empty fields (containing only "-")
        result = re.sub(r"\s*\|\s*\*\*Implements\*\*:\s*-\s*(?=\||$)", "", result)
        result = re.sub(r"\s*\|\s*\*\*Refines\*\*:\s*-\s*(?=\||$)", "", result)

        return result

    def change_reference_type(
        self,
        source_id: str,
        target_id: str,
        new_type: ReferenceType,
        file_path: Path,
    ) -> ReferenceChange:
        """
        Change a reference from Implements to Refines or vice versa.

        This method reads the spec file, finds the requirement, locates the
        reference in the metadata line, and updates it to the new type.

        Args:
            source_id: The requirement ID that contains the reference
            target_id: The referenced requirement ID to change
            new_type: The new reference type (IMPLEMENTS or REFINES)
            file_path: Path to the spec file containing the source requirement

        Returns:
            ReferenceChange with the result of the operation
        """
        try:
            # Read the spec file
            content = self._read_spec_file(file_path)

            # Find the requirement location
            location = self._find_requirement_lines(content, source_id)
            if location is None:
                return ReferenceChange(
                    success=False,
                    source_id=source_id,
                    target_id=target_id,
                    old_type=None,
                    new_type=new_type,
                    file_path=file_path,
                    message=f"Requirement {source_id} not found in {file_path}",
                )

            # Extract requirement text
            req_text = self.get_requirement_text(content, location)

            # Find the metadata line
            meta_idx, meta_line = self._find_metadata_line(req_text)
            if meta_line is None:
                return ReferenceChange(
                    success=False,
                    source_id=source_id,
                    target_id=target_id,
                    old_type=None,
                    new_type=new_type,
                    file_path=file_path,
                    message=f"Metadata line not found in requirement {source_id}",
                )

            # Find the reference in the line
            old_type, refs = self._find_reference_in_line(meta_line, target_id)
            if old_type is None:
                return ReferenceChange(
                    success=False,
                    source_id=source_id,
                    target_id=target_id,
                    old_type=None,
                    new_type=new_type,
                    file_path=file_path,
                    message=f"Reference to {target_id} not found in {source_id}",
                )

            # Check if already the correct type
            if old_type == new_type:
                return ReferenceChange(
                    success=True,
                    source_id=source_id,
                    target_id=target_id,
                    old_type=old_type,
                    new_type=new_type,
                    file_path=file_path,
                    message=f"Reference already has type {new_type.value}",
                )

            # Update the metadata line
            new_meta_line = self._update_metadata_line(
                meta_line, target_id, old_type, new_type
            )

            # Replace the line in requirement text
            req_lines = req_text.split("\n")
            req_lines[meta_idx] = new_meta_line
            new_req_text = "\n".join(req_lines)

            # Replace requirement in file content
            new_content = self.replace_requirement_text(content, location, new_req_text)

            # Write back to file
            self._write_spec_file(file_path, new_content)

            return ReferenceChange(
                success=True,
                source_id=source_id,
                target_id=target_id,
                old_type=old_type,
                new_type=new_type,
                file_path=file_path,
                message=f"Changed reference from {old_type.value} to {new_type.value}",
            )

        except FileNotFoundError as e:
            return ReferenceChange(
                success=False,
                source_id=source_id,
                target_id=target_id,
                old_type=None,
                new_type=new_type,
                file_path=file_path,
                message=str(e),
            )
        except ValueError as e:
            return ReferenceChange(
                success=False,
                source_id=source_id,
                target_id=target_id,
                old_type=None,
                new_type=new_type,
                file_path=file_path,
                message=str(e),
            )

    def _build_multi_assertion_ref(self, target_id: str, assertions: List[str]) -> str:
        """
        Build a multi-assertion reference string.

        Combines the target ID with assertion labels using the multi-assertion
        syntax: REQ-p00001-A-B-C

        Args:
            target_id: The base requirement ID (e.g., "REQ-p00001")
            assertions: List of assertion labels (e.g., ["A", "B", "C"])

        Returns:
            Multi-assertion reference string (e.g., "REQ-p00001-A-B-C")
        """
        if not assertions:
            return target_id
        return f"{target_id}-{'-'.join(assertions)}"

    def _update_reference_in_line(
        self,
        line: str,
        target_id: str,
        new_reference: str,
        ref_type: ReferenceType,
    ) -> str:
        """
        Update a specific reference in the metadata line.

        Args:
            line: The metadata line containing the reference
            target_id: The reference to replace
            new_reference: The new reference string
            ref_type: The type of reference field (IMPLEMENTS or REFINES)

        Returns:
            Updated metadata line with the reference replaced
        """
        if ref_type == ReferenceType.IMPLEMENTS:
            pattern = self.IMPLEMENTS_PATTERN
            field_name = "Implements"
        else:
            pattern = self.REFINES_PATTERN
            field_name = "Refines"

        match = pattern.search(line)
        if not match:
            return line

        refs_str = match.group("refs")
        refs = self._parse_reference_list(refs_str)

        # Replace the target_id with new_reference
        new_refs = []
        for ref in refs:
            if ref == target_id:
                new_refs.append(new_reference)
            else:
                new_refs.append(ref)

        new_refs_str = self._build_refs_string(new_refs)
        old_field = match.group(0)
        new_field = f"**{field_name}**: {new_refs_str}"

        return line.replace(old_field, new_field)

    def specialize_reference(
        self,
        source_id: str,
        target_id: str,
        assertions: List[str],
        file_path: Path,
    ) -> ReferenceSpecialization:
        """
        Specialize a requirement reference to specific assertions.

        Converts a reference from REQ→REQ form to REQ→Assertion form using
        the multi-assertion syntax (e.g., REQ-p00001-A-B-C).

        For example, converting:
            Implements: REQ-p00001
        to:
            Implements: REQ-p00001-A-B-C

        Args:
            source_id: The requirement ID that contains the reference
            target_id: The referenced requirement ID to specialize
            assertions: List of assertion labels to specialize to (e.g., ["A", "B"])
            file_path: Path to the spec file containing the source requirement

        Returns:
            ReferenceSpecialization with the result of the operation
        """
        # Validate assertions
        if not assertions:
            return ReferenceSpecialization(
                success=False,
                source_id=source_id,
                target_id=target_id,
                assertions=assertions,
                old_reference=target_id,
                new_reference="",
                file_path=file_path,
                message="No assertions specified for specialization",
            )

        # Validate assertion labels (should be single letters or numbers)
        for label in assertions:
            if not (
                (len(label) == 1 and label.isupper() and label.isalpha())
                or (len(label) <= 2 and label.isdigit())
            ):
                return ReferenceSpecialization(
                    success=False,
                    source_id=source_id,
                    target_id=target_id,
                    assertions=assertions,
                    old_reference=target_id,
                    new_reference="",
                    file_path=file_path,
                    message=f"Invalid assertion label: {label}. Must be a single uppercase letter (A-Z) or 1-2 digit number.",
                )

        new_reference = self._build_multi_assertion_ref(target_id, assertions)

        try:
            # Read the spec file
            content = self._read_spec_file(file_path)

            # Find the requirement location
            location = self._find_requirement_lines(content, source_id)
            if location is None:
                return ReferenceSpecialization(
                    success=False,
                    source_id=source_id,
                    target_id=target_id,
                    assertions=assertions,
                    old_reference=target_id,
                    new_reference=new_reference,
                    file_path=file_path,
                    message=f"Requirement {source_id} not found in {file_path}",
                )

            # Extract requirement text
            req_text = self.get_requirement_text(content, location)

            # Find the metadata line
            meta_idx, meta_line = self._find_metadata_line(req_text)
            if meta_line is None:
                return ReferenceSpecialization(
                    success=False,
                    source_id=source_id,
                    target_id=target_id,
                    assertions=assertions,
                    old_reference=target_id,
                    new_reference=new_reference,
                    file_path=file_path,
                    message=f"Metadata line not found in requirement {source_id}",
                )

            # Find the reference in the line
            ref_type, refs = self._find_reference_in_line(meta_line, target_id)
            if ref_type is None:
                return ReferenceSpecialization(
                    success=False,
                    source_id=source_id,
                    target_id=target_id,
                    assertions=assertions,
                    old_reference=target_id,
                    new_reference=new_reference,
                    file_path=file_path,
                    message=f"Reference to {target_id} not found in {source_id}",
                )

            # Check if already specialized (contains assertion suffix)
            # A specialized reference would be like REQ-p00001-A or REQ-p00001-A-B
            if target_id.count("-") > 1:
                # Check if last part looks like assertion
                parts = target_id.rsplit("-", 1)
                if len(parts) == 2:
                    suffix = parts[1]
                    if (len(suffix) == 1 and suffix.isupper()) or suffix.isdigit():
                        return ReferenceSpecialization(
                            success=False,
                            source_id=source_id,
                            target_id=target_id,
                            assertions=assertions,
                            old_reference=target_id,
                            new_reference=new_reference,
                            file_path=file_path,
                            message=f"Reference {target_id} appears to already be specialized",
                        )

            # Update the metadata line
            new_meta_line = self._update_reference_in_line(
                meta_line, target_id, new_reference, ref_type
            )

            # Replace the line in requirement text
            req_lines = req_text.split("\n")
            req_lines[meta_idx] = new_meta_line
            new_req_text = "\n".join(req_lines)

            # Replace requirement in file content
            new_content = self.replace_requirement_text(content, location, new_req_text)

            # Write back to file
            self._write_spec_file(file_path, new_content)

            return ReferenceSpecialization(
                success=True,
                source_id=source_id,
                target_id=target_id,
                assertions=assertions,
                old_reference=target_id,
                new_reference=new_reference,
                file_path=file_path,
                message=f"Specialized reference from {target_id} to {new_reference}",
            )

        except FileNotFoundError as e:
            return ReferenceSpecialization(
                success=False,
                source_id=source_id,
                target_id=target_id,
                assertions=assertions,
                old_reference=target_id,
                new_reference=new_reference,
                file_path=file_path,
                message=str(e),
            )
        except ValueError as e:
            return ReferenceSpecialization(
                success=False,
                source_id=source_id,
                target_id=target_id,
                assertions=assertions,
                old_reference=target_id,
                new_reference=new_reference,
                file_path=file_path,
                message=str(e),
            )

    def _find_insertion_point(
        self,
        content: FileContent,
        position: str,
        after_id: Optional[str] = None,
    ) -> Tuple[int, str]:
        """
        Find the line index for inserting a requirement.

        Args:
            content: FileContent of target file
            position: "start", "end", or "after"
            after_id: Required if position="after", the requirement ID to insert after

        Returns:
            Tuple of (line_index_0based, prefix_text)
            - line_index is where to insert (0-indexed)
            - prefix_text is any whitespace/newlines to prepend

        Raises:
            ValueError: If position="after" but after_id not found
        """
        lines = content.lines

        if not lines or (len(lines) == 1 and not lines[0].strip()):
            # Empty file
            return 0, ""

        if position == "start":
            # Find first requirement header, or start after preamble
            for i, line in enumerate(lines):
                if self.HEADER_PATTERN.match(line):
                    # Insert before the first requirement
                    return i, ""
            # No requirements found, insert at end
            return len(lines), "\n"

        elif position == "end":
            # Find last line of content, insert after it
            # Strip trailing empty lines for calculation
            last_content_idx = len(lines) - 1
            while last_content_idx >= 0 and not lines[last_content_idx].strip():
                last_content_idx -= 1

            if last_content_idx < 0:
                # All empty lines
                return 0, ""

            # Insert after the last content line
            return last_content_idx + 1, "\n"

        elif position == "after":
            if not after_id:
                raise ValueError("after_id is required when position is 'after'")

            # Find the requirement to insert after
            location = self._find_requirement_lines(content, after_id)
            if location is None:
                raise ValueError(f"Requirement {after_id} not found in target file")

            # Insert after the requirement's end line (0-indexed is end_line)
            return location.end_line, "\n"

        else:
            raise ValueError(f"Invalid position: {position}. Must be 'start', 'end', or 'after'")

    def _normalize_requirement_for_insertion(self, req_text: str) -> str:
        """
        Normalize requirement text for insertion into a file.

        Ensures:
        - No leading whitespace
        - Ends with newline
        - Has --- separator at end

        Returns:
            Normalized requirement text ready for insertion
        """
        text = req_text.strip()

        # Ensure separator at end
        if not text.endswith("---"):
            text = text + "\n\n---"

        return text

    def _remove_requirement_from_content(
        self,
        content: FileContent,
        location: RequirementLocation,
    ) -> str:
        """
        Remove a requirement from file content, cleaning up whitespace.

        Args:
            content: FileContent from _read_spec_file
            location: RequirementLocation of requirement to remove

        Returns:
            New file content with requirement removed
        """
        lines = content.lines
        start_idx = location.start_line - 1  # Convert to 0-indexed
        end_idx = location.end_line  # end_line is inclusive, so this is correct for slicing

        # Build new content without the requirement
        before = lines[:start_idx]
        after = lines[end_idx:]

        # Clean up extra blank lines at junction
        # Remove trailing blank lines from 'before'
        while before and not before[-1].strip():
            before.pop()

        # Remove leading blank lines from 'after'
        while after and not after[0].strip():
            after.pop(0)

        # Join with appropriate separation
        if before and after:
            # Add a blank line between remaining content
            result = before + [""] + after
        elif before:
            result = before
        elif after:
            result = after
        else:
            result = []

        return "\n".join(result)

    def move_requirement(
        self,
        req_id: str,
        source_file: Path,
        target_file: Path,
        position: str = "end",
        after_id: Optional[str] = None,
    ) -> RequirementMove:
        """
        Move a requirement from one file to another.

        Args:
            req_id: The requirement ID to move (e.g., "REQ-p00001")
            source_file: Path to the file containing the requirement
            target_file: Path to the destination file
            position: Where to insert - "start", "end", or "after"
            after_id: If position="after", the requirement ID to insert after

        Returns:
            RequirementMove with the result of the operation
        """
        # Validate inputs
        if position == "after" and not after_id:
            return RequirementMove(
                success=False,
                req_id=req_id,
                source_file=source_file,
                target_file=target_file,
                position=position,
                after_id=after_id,
                message="after_id is required when position is 'after'",
            )

        if position not in ("start", "end", "after"):
            return RequirementMove(
                success=False,
                req_id=req_id,
                source_file=source_file,
                target_file=target_file,
                position=position,
                after_id=after_id,
                message=f"Invalid position: {position}. Must be 'start', 'end', or 'after'",
            )

        try:
            # Resolve paths
            src_resolved = (
                source_file.resolve()
                if source_file.is_absolute()
                else (self.working_dir / source_file).resolve()
            )
            tgt_resolved = (
                target_file.resolve()
                if target_file.is_absolute()
                else (self.working_dir / target_file).resolve()
            )

            # Check if source and target are the same file
            if src_resolved == tgt_resolved:
                return RequirementMove(
                    success=False,
                    req_id=req_id,
                    source_file=source_file,
                    target_file=target_file,
                    position=position,
                    after_id=after_id,
                    message="Source and target files are the same. Use a different operation for reordering within a file.",
                )

            # Read source file
            source_content = self._read_spec_file(source_file)

            # Find requirement in source
            location = self._find_requirement_lines(source_content, req_id)
            if location is None:
                return RequirementMove(
                    success=False,
                    req_id=req_id,
                    source_file=source_file,
                    target_file=target_file,
                    position=position,
                    after_id=after_id,
                    message=f"Requirement {req_id} not found in {source_file}",
                )

            # Extract requirement text
            req_text = self.get_requirement_text(source_content, location)

            # Handle target file
            try:
                target_content = self._read_spec_file(target_file)
            except FileNotFoundError:
                # Create new file with empty content
                target_content = FileContent(
                    path=tgt_resolved,
                    text="",
                    lines=[],
                )

            # Find insertion point (validate after_id if needed)
            try:
                insert_idx, prefix = self._find_insertion_point(
                    target_content, position, after_id
                )
            except ValueError as e:
                return RequirementMove(
                    success=False,
                    req_id=req_id,
                    source_file=source_file,
                    target_file=target_file,
                    position=position,
                    after_id=after_id,
                    message=str(e),
                )

            # Normalize requirement text for insertion
            normalized_req = self._normalize_requirement_for_insertion(req_text)

            # Build new target content
            target_lines = target_content.lines.copy()
            req_lines = normalized_req.split("\n")

            # Insert requirement at the target location
            if prefix:
                # Add blank line before if prefix indicates we need separation
                new_target_lines = (
                    target_lines[:insert_idx] + [""] + req_lines + target_lines[insert_idx:]
                )
            else:
                new_target_lines = (
                    target_lines[:insert_idx] + req_lines + target_lines[insert_idx:]
                )

            # Clean up any double blank lines
            cleaned_target_lines = []
            prev_blank = False
            for line in new_target_lines:
                is_blank = not line.strip()
                if is_blank and prev_blank:
                    continue  # Skip consecutive blank lines
                cleaned_target_lines.append(line)
                prev_blank = is_blank

            new_target_content = "\n".join(cleaned_target_lines)

            # Build new source content (remove requirement)
            new_source_content = self._remove_requirement_from_content(
                source_content, location
            )

            # Write target file first (if this fails, source is unchanged)
            self._write_spec_file(target_file, new_target_content)

            # Write source file
            self._write_spec_file(source_file, new_source_content)

            return RequirementMove(
                success=True,
                req_id=req_id,
                source_file=source_file,
                target_file=target_file,
                position=position,
                after_id=after_id,
                message=f"Moved {req_id} from {source_file.name} to {target_file.name}",
            )

        except FileNotFoundError as e:
            return RequirementMove(
                success=False,
                req_id=req_id,
                source_file=source_file,
                target_file=target_file,
                position=position,
                after_id=after_id,
                message=str(e),
            )
        except ValueError as e:
            return RequirementMove(
                success=False,
                req_id=req_id,
                source_file=source_file,
                target_file=target_file,
                position=position,
                after_id=after_id,
                message=str(e),
            )

    def _find_all_requirements(
        self,
        content: FileContent,
    ) -> List[RequirementLocation]:
        """
        Find all requirements in a file.

        Args:
            content: FileContent from _read_spec_file

        Returns:
            List of RequirementLocation for each requirement found
        """
        locations = []
        lines = content.lines
        i = 0

        while i < len(lines):
            line = lines[i]

            # Look for requirement header
            header_match = self.HEADER_PATTERN.match(line)
            if header_match:
                req_id = header_match.group("id")
                start_line = i + 1  # 1-indexed
                header_line = line
                end_line = i + 1
                has_end_marker = False
                has_separator = False

                # Find the end of this requirement
                j = i + 1
                while j < len(lines):
                    current_line = lines[j]

                    # Check for end marker
                    if self.END_MARKER_PATTERN.match(current_line):
                        end_line = j + 1  # 1-indexed
                        has_end_marker = True
                        # Check for separator line
                        if j + 1 < len(lines) and lines[j + 1].strip() == "---":
                            end_line = j + 2
                            has_separator = True
                        break

                    # Check for next requirement header
                    next_match = self.HEADER_PATTERN.match(current_line)
                    if next_match:
                        end_line = j  # Previous line (1-indexed)
                        break

                    end_line = j + 1
                    j += 1

                locations.append(RequirementLocation(
                    start_line=start_line,
                    end_line=end_line,
                    header_line=header_line,
                    has_end_marker=has_end_marker,
                    has_separator=has_separator,
                ))

                # Continue from after this requirement
                i = end_line - 1  # -1 because we'll increment at end of loop

            i += 1

        return locations

    def _extract_non_requirement_content(
        self,
        content: FileContent,
        locations: List[RequirementLocation],
    ) -> str:
        """
        Extract content that is not part of any requirement.

        Args:
            content: FileContent from _read_spec_file
            locations: List of RequirementLocation for all requirements

        Returns:
            Non-requirement content as a string
        """
        if not locations:
            # No requirements, entire file is non-requirement content
            return content.text

        lines = content.lines
        non_req_lines = []

        # Sort locations by start_line
        sorted_locations = sorted(locations, key=lambda loc: loc.start_line)

        # Content before first requirement
        first_start = sorted_locations[0].start_line - 1  # Convert to 0-indexed
        if first_start > 0:
            for line in lines[:first_start]:
                if line.strip():  # Only include non-empty lines
                    non_req_lines.append(line)

        # Content after last requirement
        last_end = sorted_locations[-1].end_line  # Already correct for slicing
        if last_end < len(lines):
            for line in lines[last_end:]:
                if line.strip():  # Only include non-empty lines
                    non_req_lines.append(line)

        return "\n".join(non_req_lines)

    def analyze_file_for_deletion(
        self,
        file_path: Path,
    ) -> FileDeletionAnalysis:
        """
        Analyze a spec file to determine if it can be safely deleted.

        Checks for remaining requirements and non-requirement content that
        might need to be preserved before deletion.

        Args:
            file_path: Path to the spec file to analyze

        Returns:
            FileDeletionAnalysis with deletion readiness status
        """
        try:
            content = self._read_spec_file(file_path)
            locations = self._find_all_requirements(content)

            # Extract requirement IDs
            remaining_reqs = []
            for loc in locations:
                match = self.HEADER_PATTERN.match(loc.header_line)
                if match:
                    remaining_reqs.append(match.group("id"))

            # Extract non-requirement content
            non_req_content = self._extract_non_requirement_content(content, locations)
            has_non_req = bool(non_req_content.strip())

            can_delete = len(remaining_reqs) == 0

            if remaining_reqs:
                message = f"File contains {len(remaining_reqs)} requirement(s): {', '.join(remaining_reqs)}"
            elif has_non_req:
                message = "File has no requirements but contains non-requirement content that should be preserved"
            else:
                message = "File can be safely deleted (no requirements or content)"

            return FileDeletionAnalysis(
                can_delete=can_delete,
                file_path=file_path,
                remaining_requirements=remaining_reqs,
                non_requirement_content=non_req_content,
                has_non_requirement_content=has_non_req,
                message=message,
            )

        except FileNotFoundError:
            return FileDeletionAnalysis(
                can_delete=False,
                file_path=file_path,
                remaining_requirements=[],
                non_requirement_content="",
                has_non_requirement_content=False,
                message=f"File not found: {file_path}",
            )
        except ValueError as e:
            return FileDeletionAnalysis(
                can_delete=False,
                file_path=file_path,
                remaining_requirements=[],
                non_requirement_content="",
                has_non_requirement_content=False,
                message=str(e),
            )

    def delete_spec_file(
        self,
        file_path: Path,
        force: bool = False,
        extract_content_to: Optional[Path] = None,
    ) -> FileDeletionResult:
        """
        Delete a spec file, optionally extracting non-requirement content.

        By default, refuses to delete files with remaining requirements.
        Use force=True to delete anyway (requirements will be lost).

        Args:
            file_path: Path to the spec file to delete
            force: If True, delete even if requirements remain
            extract_content_to: If provided, extract non-requirement content
                               to this file before deletion

        Returns:
            FileDeletionResult with the operation status
        """
        # First analyze the file
        analysis = self.analyze_file_for_deletion(file_path)

        if not analysis.can_delete and not force:
            return FileDeletionResult(
                success=False,
                file_path=file_path,
                content_extracted=False,
                content_target=None,
                message=f"Cannot delete: {analysis.message}. Use force=True to delete anyway.",
            )

        try:
            # Resolve path
            if not file_path.is_absolute():
                file_path = self.working_dir / file_path
            file_path = file_path.resolve()

            # Security check
            try:
                file_path.relative_to(self.working_dir.resolve())
            except ValueError:
                return FileDeletionResult(
                    success=False,
                    file_path=file_path,
                    content_extracted=False,
                    content_target=None,
                    message=f"Path {file_path} is outside workspace",
                )

            # Extract content if requested and there's content to extract
            content_extracted = False
            if extract_content_to and analysis.has_non_requirement_content:
                self._write_spec_file(extract_content_to, analysis.non_requirement_content)
                content_extracted = True

            # Delete the file
            if file_path.exists():
                file_path.unlink()

            message = f"Deleted {file_path.name}"
            if content_extracted:
                message += f" (content extracted to {extract_content_to})"
            if force and analysis.remaining_requirements:
                message += f" (forced, lost {len(analysis.remaining_requirements)} requirement(s))"

            return FileDeletionResult(
                success=True,
                file_path=file_path,
                content_extracted=content_extracted,
                content_target=extract_content_to if content_extracted else None,
                message=message,
            )

        except OSError as e:
            return FileDeletionResult(
                success=False,
                file_path=file_path,
                content_extracted=False,
                content_target=None,
                message=f"Failed to delete file: {e}",
            )
