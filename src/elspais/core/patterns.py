"""
elspais.core.patterns - Configurable requirement ID pattern matching.

Supports multiple ID formats:
- HHT style: REQ-p00001, REQ-CAL-d00001
- Type-prefix style: PRD-00001, OPS-00001, DEV-00001
- Jira style: PROJ-123
- Named: REQ-UserAuth
"""

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

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
        assertions: Optional assertion label format configuration
    """

    id_template: str
    prefix: str
    types: Dict[str, Dict[str, Any]]
    id_format: Dict[str, Any]
    associated: Optional[Dict[str, Any]] = None
    assertions: Optional[Dict[str, Any]] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PatternConfig":
        """Create PatternConfig from configuration dictionary."""
        return cls(
            id_template=data.get("id_template", "{prefix}-{type}{id}"),
            prefix=data.get("prefix", "REQ"),
            types=data.get("types", {}),
            id_format=data.get("id_format", {"style": "numeric", "digits": 5}),
            associated=data.get("associated"),
            assertions=data.get("assertions"),
        )

    def get_type_by_id(self, type_id: str) -> Optional[Dict[str, Any]]:
        """Get type configuration by type ID."""
        for config in self.types.values():
            if config.get("id") == type_id:
                return config
        return None

    def get_all_type_ids(self) -> List[str]:
        """Get list of all type IDs."""
        return [config.get("id", "") for config in self.types.values()]

    def get_assertion_label_pattern(self) -> str:
        """Get regex pattern for assertion labels based on configuration."""
        assertions = self.assertions or {}
        style = assertions.get("label_style", "uppercase")
        zero_pad = assertions.get("zero_pad", False)

        if style == "uppercase":
            return r"[A-Z]"
        elif style == "numeric":
            if zero_pad:
                return r"[0-9]{2}"
            return r"[0-9]{1,2}"
        elif style == "alphanumeric":
            return r"[0-9A-Z]"
        elif style == "numeric_1based":
            if zero_pad:
                return r"[0-9]{2}"
            return r"[1-9][0-9]?"
        else:
            return r"[A-Z]"

    def get_assertion_max_count(self) -> int:
        """Get maximum number of assertions allowed."""
        assertions = self.assertions or {}
        style = assertions.get("label_style", "uppercase")
        max_count = assertions.get("max_count")

        if max_count is not None:
            return int(max_count)

        # Default max based on style
        if style == "uppercase":
            return 26
        elif style == "numeric":
            return 100
        elif style == "alphanumeric":
            return 36
        elif style == "numeric_1based":
            return 99
        return 26


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
        self._regex_with_assertion = self._build_regex(include_assertion=True)
        self._assertion_label_regex = re.compile(
            f"^{self.config.get_assertion_label_pattern()}$"
        )

    def _build_regex(self, include_assertion: bool = False) -> re.Pattern:
        """Build regex pattern from configuration.

        Args:
            include_assertion: If True, include optional assertion suffix pattern
        """
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

        # Optionally add assertion suffix pattern
        if include_assertion:
            assertion_pattern = self.config.get_assertion_label_pattern()
            pattern = f"{pattern}(?:-(?P<assertion>{assertion_pattern}))?"

        return re.compile(f"^{pattern}$")

    def parse(self, id_string: str, allow_assertion: bool = False) -> Optional[ParsedRequirement]:
        """
        Parse a requirement ID string into components.

        Args:
            id_string: The requirement ID to parse (e.g., "REQ-p00001" or "REQ-p00001-A")
            allow_assertion: If True, allow and parse assertion suffix

        Returns:
            ParsedRequirement if valid, None if invalid
        """
        regex = self._regex_with_assertion if allow_assertion else self._regex
        match = regex.match(id_string)
        if not match:
            return None

        groups = match.groupdict()
        return ParsedRequirement(
            full_id=id_string,
            prefix=groups.get("prefix", ""),
            associated=groups.get("associated") or None,
            type_code=groups.get("type", ""),
            number=groups.get("id", ""),
            assertion=groups.get("assertion") or None,
        )

    def is_valid(self, id_string: str, allow_assertion: bool = False) -> bool:
        """
        Check if an ID string is valid.

        Args:
            id_string: The requirement ID to validate
            allow_assertion: If True, allow assertion suffix

        Returns:
            True if valid, False otherwise
        """
        return self.parse(id_string, allow_assertion=allow_assertion) is not None

    def is_valid_assertion_label(self, label: str) -> bool:
        """
        Check if an assertion label is valid.

        Args:
            label: The assertion label to validate (e.g., "A", "01")

        Returns:
            True if valid, False otherwise
        """
        return self._assertion_label_regex.match(label) is not None

    def format_assertion_label(self, index: int) -> str:
        """
        Format an assertion label from a zero-based index.

        Args:
            index: Zero-based index (0 = A or 00, 1 = B or 01, etc.)

        Returns:
            Formatted assertion label
        """
        assertions = self.config.assertions or {}
        style = assertions.get("label_style", "uppercase")
        zero_pad = assertions.get("zero_pad", False)

        if style == "uppercase":
            if index < 0 or index >= 26:
                raise ValueError(f"Index {index} out of range for uppercase labels (0-25)")
            return chr(ord("A") + index)
        elif style == "numeric":
            if zero_pad:
                return f"{index:02d}"
            return str(index)
        elif style == "alphanumeric":
            if index < 10:
                return str(index)
            elif index < 36:
                return chr(ord("A") + index - 10)
            else:
                raise ValueError(f"Index {index} out of range for alphanumeric labels (0-35)")
        elif style == "numeric_1based":
            if zero_pad:
                return f"{index + 1:02d}"
            return str(index + 1)
        else:
            return chr(ord("A") + index)

    def parse_assertion_label_index(self, label: str) -> int:
        """
        Parse an assertion label to get its zero-based index.

        Args:
            label: The assertion label (e.g., "A", "01", "B")

        Returns:
            Zero-based index
        """
        assertions = self.config.assertions or {}
        style = assertions.get("label_style", "uppercase")

        if style == "uppercase":
            if len(label) == 1 and label.isupper():
                return ord(label) - ord("A")
        elif style == "numeric":
            return int(label)
        elif style == "alphanumeric":
            if label.isdigit():
                return int(label)
            elif len(label) == 1 and label.isupper():
                return ord(label) - ord("A") + 10
        elif style == "numeric_1based":
            return int(label) - 1

        raise ValueError(f"Cannot parse assertion label: {label}")

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
