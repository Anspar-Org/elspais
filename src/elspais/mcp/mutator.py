"""
elspais.mcp.mutator - Graph-to-filesystem sync operations.

Provides the GraphMutator class for reading and writing spec files
while preserving format and tracking line numbers for requirement
location.
"""

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional, Tuple

from elspais.core.patterns import PatternConfig, PatternValidator


class ReferenceType(Enum):
    """Type of reference relationship between requirements."""

    IMPLEMENTS = "implements"
    REFINES = "refines"


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
