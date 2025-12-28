"""
elspais.core.patterns - Configurable requirement ID pattern matching.

Supports multiple ID formats:
- HHT style: REQ-p00001, REQ-CAL-d00001
- Type-prefix style: PRD-00001, OPS-00001, DEV-00001
- Jira style: PROJ-123
- Named: REQ-UserAuth
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

from elspais.core.models import ParsedRequirement


@dataclass
class PatternConfig:
    """
    Configuration for requirement ID patterns.

    Attributes:
        id_template: Template string with tokens {prefix}, {associated}, {type}, {id}
        prefix: Base prefix (e.g., "REQ")
        types: Dictionary of type definitions
        id_format: ID format configuration (style, digits, etc.)
        associated: Optional associated repo namespace configuration
    """

    id_template: str
    prefix: str
    types: Dict[str, Dict[str, Any]]
    id_format: Dict[str, Any]
    associated: Optional[Dict[str, Any]] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PatternConfig":
        """Create PatternConfig from configuration dictionary."""
        return cls(
            id_template=data.get("id_template", "{prefix}-{type}{id}"),
            prefix=data.get("prefix", "REQ"),
            types=data.get("types", {}),
            id_format=data.get("id_format", {"style": "numeric", "digits": 5}),
            associated=data.get("associated"),
        )

    def get_type_by_id(self, type_id: str) -> Optional[Dict[str, Any]]:
        """Get type configuration by type ID."""
        for name, config in self.types.items():
            if config.get("id") == type_id:
                return config
        return None

    def get_all_type_ids(self) -> List[str]:
        """Get list of all type IDs."""
        return [config.get("id", "") for config in self.types.values()]


class PatternValidator:
    """
    Validates and parses requirement IDs against configured patterns.
    """

    def __init__(self, config: PatternConfig):
        """
        Initialize pattern validator.

        Args:
            config: Pattern configuration
        """
        self.config = config
        self._regex = self._build_regex()

    def _build_regex(self) -> re.Pattern:
        """Build regex pattern from configuration."""
        template = self.config.id_template

        # Build type alternatives
        type_ids = self.config.get_all_type_ids()
        type_pattern = "|".join(re.escape(t) for t in type_ids if t)

        # Build ID pattern based on format
        id_format = self.config.id_format
        style = id_format.get("style", "numeric")

        if style == "numeric":
            digits = int(id_format.get("digits", 5))
            leading_zeros = id_format.get("leading_zeros", True)
            if digits > 0 and leading_zeros:
                id_pattern = f"\\d{{{digits}}}"
            elif digits > 0:
                id_pattern = f"\\d{{1,{digits}}}"
            else:
                id_pattern = "\\d+"
        elif style == "named":
            pattern = id_format.get("pattern", "[A-Za-z][A-Za-z0-9]+")
            id_pattern = pattern
        elif style == "alphanumeric":
            pattern = id_format.get("pattern", "[A-Z0-9]+")
            id_pattern = pattern
        else:
            id_pattern = "[A-Za-z0-9]+"

        # Build associated pattern if enabled
        associated_config = self.config.associated or {}
        if associated_config.get("enabled"):
            length = associated_config.get("length", 3)
            sep = re.escape(associated_config.get("separator", "-"))
            if length:
                associated_pattern = f"(?P<associated>[A-Z]{{{length}}}){sep}"
            else:
                associated_pattern = f"(?P<associated>[A-Z]+){sep}"
        else:
            associated_pattern = "(?P<associated>)"

        # Build full regex from template
        # Replace tokens with regex groups
        pattern = template
        pattern = pattern.replace("{prefix}", f"(?P<prefix>{re.escape(self.config.prefix)})")

        # Handle associated - it's optional
        if "{associated}" in pattern:
            pattern = pattern.replace("{associated}", f"(?:{associated_pattern})?")
        else:
            pattern = pattern.replace("{associated}", "")

        if type_pattern:
            pattern = pattern.replace("{type}", f"(?P<type>{type_pattern})")
        else:
            pattern = pattern.replace("{type}", "(?P<type>)")

        pattern = pattern.replace("{id}", f"(?P<id>{id_pattern})")

        return re.compile(f"^{pattern}$")

    def parse(self, id_string: str) -> Optional[ParsedRequirement]:
        """
        Parse a requirement ID string into components.

        Args:
            id_string: The requirement ID to parse (e.g., "REQ-p00001")

        Returns:
            ParsedRequirement if valid, None if invalid
        """
        match = self._regex.match(id_string)
        if not match:
            return None

        groups = match.groupdict()
        return ParsedRequirement(
            full_id=id_string,
            prefix=groups.get("prefix", ""),
            associated=groups.get("associated") or None,
            type_code=groups.get("type", ""),
            number=groups.get("id", ""),
        )

    def is_valid(self, id_string: str) -> bool:
        """
        Check if an ID string is valid.

        Args:
            id_string: The requirement ID to validate

        Returns:
            True if valid, False otherwise
        """
        return self.parse(id_string) is not None

    def format(
        self, type_code: str, number: int, associated: Optional[str] = None
    ) -> str:
        """
        Format a requirement ID from components.

        Args:
            type_code: The requirement type code (e.g., "p")
            number: The requirement number
            associated: Optional associated repo code

        Returns:
            Formatted requirement ID string
        """
        template = self.config.id_template
        id_format = self.config.id_format

        # Format number
        style = id_format.get("style", "numeric")
        if style == "numeric":
            digits = int(id_format.get("digits", 5))
            leading_zeros = id_format.get("leading_zeros", True)
            if digits > 0 and leading_zeros:
                formatted_number = str(number).zfill(digits)
            else:
                formatted_number = str(number)
        else:
            formatted_number = str(number)

        # Build result
        result = template
        result = result.replace("{prefix}", self.config.prefix)

        # Handle associated
        if associated and "{associated}" in result:
            associated_config = self.config.associated or {}
            sep = associated_config.get("separator", "-")
            result = result.replace("{associated}", f"{associated}{sep}")
        else:
            result = result.replace("{associated}", "")

        result = result.replace("{type}", type_code)
        result = result.replace("{id}", formatted_number)

        return result

    def extract_implements_ids(self, implements_str: str) -> List[str]:
        """
        Extract requirement IDs from an Implements field value.

        Handles formats like:
        - "p00001"
        - "p00001, o00002"
        - "REQ-p00001, REQ-o00002"
        - "CAL-p00001"

        Args:
            implements_str: The Implements field value

        Returns:
            List of normalized requirement IDs
        """
        if not implements_str:
            return []

        # Split by comma
        parts = [p.strip() for p in implements_str.split(",")]
        result = []

        for part in parts:
            if not part:
                continue

            # Check if it's a full ID
            if self.is_valid(part):
                result.append(part)
            else:
                # It might be a shortened ID like "p00001" or "CAL-p00001"
                # Just keep the raw value for later resolution
                result.append(part)

        return result
