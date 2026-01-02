"""
elspais.core.models - Core data models for requirements.

Provides dataclasses for representing requirements, parsed IDs,
and requirement types.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class RequirementType:
    """
    Represents a requirement type (PRD, OPS, DEV, etc.).

    Attributes:
        id: The type identifier used in requirement IDs (e.g., "p", "PRD")
        name: Human-readable name (e.g., "Product Requirement")
        level: Hierarchy level (1=highest/parent, higher numbers=children)
    """

    id: str
    name: str = ""
    level: int = 1


@dataclass
class Assertion:
    """
    Represents a single assertion within a requirement.

    Assertions are the unit of verification - each defines one testable
    obligation using SHALL/SHALL NOT language.

    Attributes:
        label: The assertion label (e.g., "A", "B", "01", "0A")
        text: The assertion text (e.g., "The system SHALL...")
        is_placeholder: True if text indicates removed/deprecated assertion
    """

    label: str
    text: str
    is_placeholder: bool = False

    @property
    def full_id(self) -> str:
        """Return the assertion ID suffix (e.g., "-A")."""
        return f"-{self.label}"

    def __str__(self) -> str:
        return f"{self.label}. {self.text}"


@dataclass
class ParsedRequirement:
    """
    Represents a parsed requirement ID broken into components.

    Attributes:
        full_id: The complete requirement ID (e.g., "REQ-CAL-p00001" or "REQ-p00001-A")
        prefix: The ID prefix (e.g., "REQ")
        associated: Optional associated repo namespace (e.g., "CAL")
        type_code: The requirement type code (e.g., "p")
        number: The ID number or name (e.g., "00001")
        assertion: Optional assertion label (e.g., "A", "01")
    """

    full_id: str
    prefix: str
    associated: Optional[str]
    type_code: str
    number: str
    assertion: Optional[str] = None

    @property
    def base_id(self) -> str:
        """Return the requirement ID without assertion suffix."""
        if self.assertion:
            return self.full_id.rsplit("-", 1)[0]
        return self.full_id


@dataclass
class Requirement:
    """
    Represents a complete requirement specification.

    Attributes:
        id: Unique requirement identifier (e.g., "REQ-p00001")
        title: Requirement title
        level: Requirement level/type name (e.g., "PRD", "DEV")
        status: Current status (e.g., "Active", "Draft")
        body: Main requirement text
        implements: List of requirement IDs this requirement implements
        acceptance_criteria: List of acceptance criteria (legacy format)
        assertions: List of Assertion objects (new format)
        rationale: Optional rationale text
        hash: Content hash for change detection
        file_path: Source file path
        line_number: Line number in source file
        tags: Optional list of tags
    """

    id: str
    title: str
    level: str
    status: str
    body: str
    implements: List[str] = field(default_factory=list)
    acceptance_criteria: List[str] = field(default_factory=list)
    assertions: List["Assertion"] = field(default_factory=list)
    rationale: Optional[str] = None
    hash: Optional[str] = None
    file_path: Optional[Path] = None
    line_number: Optional[int] = None
    tags: List[str] = field(default_factory=list)
    subdir: str = ""  # Subdirectory within spec/, e.g., "roadmap", "archive", ""

    @property
    def type_code(self) -> str:
        """
        Extract the type code from the requirement ID.

        For REQ-p00001, returns "p".
        For REQ-CAL-d00001, returns "d".
        For PRD-00001, returns "PRD".
        """
        # Try to extract type code from ID
        # Pattern: after last separator, before numbers
        match = re.search(r"-([a-zA-Z]+)\d", self.id)
        if match:
            return match.group(1)

        # Pattern: type at start (e.g., PRD-00001)
        match = re.match(r"([A-Z]+)-\d", self.id)
        if match:
            return match.group(1)

        return ""

    @property
    def number(self) -> int:
        """
        Extract the numeric ID from the requirement ID.

        For REQ-p00001, returns 1.
        For REQ-d00042, returns 42.
        """
        match = re.search(r"(\d+)$", self.id)
        if match:
            return int(match.group(1))
        return 0

    @property
    def associated(self) -> Optional[str]:
        """
        Extract the associated repo code from the requirement ID.

        For REQ-CAL-d00001, returns "CAL".
        For REQ-p00001, returns None.
        """
        # Pattern: REQ-XXX- where XXX is 2-4 uppercase letters
        match = re.search(r"^[A-Z]+-([A-Z]{2,4})-", self.id)
        if match:
            return match.group(1)
        return None

    @property
    def is_roadmap(self) -> bool:
        """
        Check if this requirement is from the roadmap subdirectory.

        Returns True if subdir is "roadmap", False otherwise.
        This is a convenience property for backward compatibility.
        """
        return self.subdir == "roadmap"

    @property
    def spec_path(self) -> str:
        """
        Return the spec-relative file path as a string.

        For requirements in spec/prd-core.md, returns "spec/prd-core.md".
        For requirements in spec/roadmap/prd-future.md, returns "spec/roadmap/prd-future.md".
        """
        if self.file_path:
            return str(self.file_path)
        return ""

    def location(self) -> str:
        """Return file:line location string."""
        if self.file_path and self.line_number:
            return f"{self.file_path}:{self.line_number}"
        elif self.file_path:
            return str(self.file_path)
        return "unknown"

    def get_assertion(self, label: str) -> Optional["Assertion"]:
        """Get an assertion by its label."""
        for assertion in self.assertions:
            if assertion.label == label:
                return assertion
        return None

    def assertion_id(self, label: str) -> str:
        """Return the full assertion ID (e.g., 'REQ-p00001-A')."""
        return f"{self.id}-{label}"

    def __str__(self) -> str:
        return f"{self.id}: {self.title}"

    def __repr__(self) -> str:
        return f"Requirement(id={self.id!r}, title={self.title!r}, level={self.level!r})"


@dataclass
class ContentRule:
    """
    Represents a content rule file for semantic validation guidance.

    Content rules are markdown files that provide guidance to AI agents
    and humans when authoring requirements. They can include YAML frontmatter
    for metadata.

    Attributes:
        file_path: Path to the content rule file
        title: Human-readable title (from frontmatter or filename)
        content: Full markdown content (excluding frontmatter)
        type: Rule type - "guidance", "specification", or "template"
        applies_to: List of what this rule applies to (e.g., ["requirements", "assertions"])
    """

    file_path: Path
    title: str
    content: str
    type: str = "guidance"
    applies_to: List[str] = field(default_factory=list)


@dataclass
class ParseWarning:
    """
    Parser-level warning about a requirement.

    Warnings indicate issues found during parsing that don't prevent
    the requirement from being parsed, but may indicate problems.

    Attributes:
        requirement_id: The requirement ID this warning relates to
        message: Human-readable warning message
        file_path: Source file path (optional)
        line_number: Line number in source file (optional)
    """

    requirement_id: str
    message: str
    file_path: Optional[Path] = None
    line_number: Optional[int] = None

    def __str__(self) -> str:
        location = ""
        if self.file_path:
            location = f" at {self.file_path}"
            if self.line_number:
                location = f" at {self.file_path}:{self.line_number}"
        return f"[{self.requirement_id}] {self.message}{location}"


@dataclass
class ParseResult:
    """
    Result of parsing requirements from text or files.

    Contains both the successfully parsed requirements and any
    warnings generated during parsing.

    Attributes:
        requirements: Dictionary of requirement ID to Requirement
        warnings: List of parser warnings
    """

    requirements: Dict[str, "Requirement"]
    warnings: List[ParseWarning] = field(default_factory=list)

    def __getitem__(self, key: str) -> "Requirement":
        """Get a requirement by ID."""
        return self.requirements[key]

    def __contains__(self, key: str) -> bool:
        """Check if a requirement ID exists."""
        return key in self.requirements

    def __len__(self) -> int:
        """Return the number of requirements."""
        return len(self.requirements)

    def __iter__(self):
        """Iterate over requirement IDs."""
        return iter(self.requirements)

    def items(self):
        """Return items like a dict."""
        return self.requirements.items()

    def keys(self):
        """Return keys like a dict."""
        return self.requirements.keys()

    def values(self):
        """Return values like a dict."""
        return self.requirements.values()

    def get(self, key: str, default=None) -> Optional["Requirement"]:
        """Get a requirement by ID with default."""
        return self.requirements.get(key, default)
