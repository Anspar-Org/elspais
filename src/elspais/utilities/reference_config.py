"""Unified reference configuration for all parsers.

This module provides configurable reference pattern matching used by:
- CodeParser: # Implements: REQ-xxx
- TestParser: def test_REQ_xxx() and # Tests: REQ-xxx
- JUnitXMLParser: test names containing REQ-xxx
- PytestJSONParser: test names containing REQ-xxx

The configuration supports:
- Default patterns applied to all files
- File-type specific overrides (*.py, *.java, etc.)
- Directory-based overrides (tests/legacy/**)
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from elspais.utilities.patterns import PatternConfig


@dataclass
class ReferenceConfig:
    """Configuration for reference pattern matching.

    Used by all parsers: TestParser, CodeParser, JUnitXMLParser, PytestJSONParser.

    Attributes:
        separators: Separator characters to accept between ID components (default: ["-", "_"])
        case_sensitive: Whether matching is case-sensitive (default: False)
        prefix_optional: Whether the prefix (e.g., "REQ") is required (default: False)
        comment_styles: Recognized comment markers (default: ["#", "//", "--"])
        keywords: Keywords for different reference types
    """

    separators: list[str] = field(default_factory=lambda: ["-", "_"])
    case_sensitive: bool = False
    prefix_optional: bool = False
    comment_styles: list[str] = field(default_factory=lambda: ["#", "//", "--"])
    keywords: dict[str, list[str]] = field(
        default_factory=lambda: {
            "implements": ["Implements", "IMPLEMENTS"],
            "validates": ["Validates", "Tests", "VALIDATES", "TESTS"],
            "refines": ["Refines", "REFINES"],
        }
    )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReferenceConfig:
        """Create ReferenceConfig from configuration dictionary.

        Args:
            data: Dictionary with optional keys: separators, case_sensitive,
                  prefix_optional, comment_styles, keywords

        Returns:
            ReferenceConfig instance with values from dict or defaults
        """
        return cls(
            separators=data.get("separators", ["-", "_"]),
            case_sensitive=data.get("case_sensitive", False),
            prefix_optional=data.get("prefix_optional", False),
            comment_styles=data.get("comment_styles", ["#", "//", "--"]),
            keywords=data.get(
                "keywords",
                {
                    "implements": ["Implements", "IMPLEMENTS"],
                    "validates": ["Validates", "Tests", "VALIDATES", "TESTS"],
                    "refines": ["Refines", "REFINES"],
                },
            ),
        )

    def merge_with(self, override: ReferenceOverride) -> ReferenceConfig:
        """Create a new config by merging this config with an override.

        Only non-None values from the override are applied.

        Args:
            override: ReferenceOverride with values to apply

        Returns:
            New ReferenceConfig with merged values
        """
        # Start with current values
        merged_keywords = dict(self.keywords)

        # Merge keywords if override has them
        if override.keywords is not None:
            merged_keywords.update(override.keywords)

        return ReferenceConfig(
            separators=override.separators if override.separators is not None else self.separators,
            case_sensitive=(
                override.case_sensitive
                if override.case_sensitive is not None
                else self.case_sensitive
            ),
            prefix_optional=(
                override.prefix_optional
                if override.prefix_optional is not None
                else self.prefix_optional
            ),
            comment_styles=(
                override.comment_styles
                if override.comment_styles is not None
                else self.comment_styles
            ),
            keywords=merged_keywords,
        )


@dataclass
class ReferenceOverride:
    """Override rule for specific file types or directories.

    Attributes:
        match: Glob pattern to match files (e.g., "*.py", "tests/legacy/**")
        separators: Override separator characters (None = use default)
        case_sensitive: Override case sensitivity (None = use default)
        prefix_optional: Override prefix requirement (None = use default)
        comment_styles: Override comment styles (None = use default)
        keywords: Override keywords dict (None = use default)
    """

    match: str
    separators: list[str] | None = None
    case_sensitive: bool | None = None
    prefix_optional: bool | None = None
    comment_styles: list[str] | None = None
    keywords: dict[str, list[str]] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReferenceOverride:
        """Create ReferenceOverride from configuration dictionary.

        Args:
            data: Dictionary with 'match' (required) and optional override keys

        Returns:
            ReferenceOverride instance

        Raises:
            ValueError: If 'match' key is missing
        """
        if "match" not in data:
            raise ValueError("ReferenceOverride requires 'match' pattern")

        return cls(
            match=data["match"],
            separators=data.get("separators"),
            case_sensitive=data.get("case_sensitive"),
            prefix_optional=data.get("prefix_optional"),
            comment_styles=data.get("comment_styles"),
            keywords=data.get("keywords"),
        )

    def applies_to(self, file_path: Path, base_path: Path) -> bool:
        """Check if this override applies to the given file.

        Args:
            file_path: Absolute path to the file being checked
            base_path: Base path (repo root) for relative matching

        Returns:
            True if the match pattern matches the file
        """
        # Get relative path for matching
        try:
            rel_path = file_path.relative_to(base_path)
        except ValueError:
            # file_path is not under base_path, use filename only
            rel_path = Path(file_path.name)

        # Convert to string for fnmatch
        rel_str = str(rel_path)

        # Handle both forward and backward slashes on Windows
        rel_str_normalized = rel_str.replace("\\", "/")

        # Check if pattern matches
        # fnmatch doesn't handle ** well, so we need special handling
        pattern = self.match

        if "**" in pattern:
            # For ** patterns, we need recursive matching
            # Split pattern into parts and match recursively
            return self._match_recursive(rel_str_normalized, pattern)
        else:
            # Simple glob - check both full path and just filename
            if fnmatch.fnmatch(rel_str_normalized, pattern):
                return True
            # Also try matching just the filename for patterns like "*.py"
            if fnmatch.fnmatch(file_path.name, pattern):
                return True
            return False

    def _match_recursive(self, path: str, pattern: str) -> bool:
        """Match a path against a pattern containing **.

        Args:
            path: Normalized file path (forward slashes)
            pattern: Glob pattern with ** for recursive matching

        Returns:
            True if pattern matches path
        """
        # Split on **
        parts = pattern.split("**")

        if len(parts) == 2:
            # Pattern like "tests/**" or "**/test.py" or "tests/**/fixtures"
            prefix, suffix = parts

            # Remove leading/trailing slashes from parts
            prefix = prefix.rstrip("/")
            suffix = suffix.lstrip("/")

            if prefix and suffix:
                # Pattern like "tests/**/fixtures/*.py"
                # Path must start with prefix and end matching suffix
                if not path.startswith(prefix + "/") and path != prefix:
                    return False
                # Get the part after prefix
                remaining = path[len(prefix) :].lstrip("/")
                # Check if any suffix of remaining matches the suffix pattern
                parts_list = remaining.split("/")
                for i in range(len(parts_list)):
                    candidate = "/".join(parts_list[i:])
                    if fnmatch.fnmatch(candidate, suffix):
                        return True
                return False
            elif prefix:
                # Pattern like "tests/**" - match anything under tests/
                return path.startswith(prefix + "/") or path == prefix
            elif suffix:
                # Pattern like "**/test.py" - match file anywhere
                # Check if path ends with suffix or matches suffix directly
                if fnmatch.fnmatch(path, suffix):
                    return True
                # Check if any path component matches
                for i in range(len(path.split("/"))):
                    candidate = "/".join(path.split("/")[i:])
                    if fnmatch.fnmatch(candidate, suffix):
                        return True
                return False
            else:
                # Just "**" - matches everything
                return True

        # Multiple ** in pattern - complex case, fall back to basic matching
        return fnmatch.fnmatch(path, pattern)


class ReferenceResolver:
    """Resolves which reference config to use for a given file.

    This is the SINGLE entry point for all parsers to get their configuration.
    It applies defaults and matching overrides in order.

    Example:
        resolver = ReferenceResolver(defaults, overrides)
        config = resolver.resolve(Path("tests/test_auth.py"), repo_root)
        # config now has merged defaults + any matching overrides
    """

    def __init__(self, defaults: ReferenceConfig, overrides: list[ReferenceOverride] | None = None):
        """Initialize the resolver.

        Args:
            defaults: Default configuration to use
            overrides: Optional list of override rules (applied in order)
        """
        self.defaults = defaults
        self.overrides = overrides or []

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> ReferenceResolver:
        """Create ReferenceResolver from the references config section.

        Args:
            config: The 'references' section from elspais config

        Returns:
            Configured ReferenceResolver
        """
        defaults_dict = config.get("defaults", {})
        overrides_list = config.get("overrides", [])

        defaults = ReferenceConfig.from_dict(defaults_dict)
        overrides = [ReferenceOverride.from_dict(o) for o in overrides_list]

        return cls(defaults, overrides)

    def resolve(self, file_path: Path, base_path: Path) -> ReferenceConfig:
        """Return merged config for file (defaults + matching overrides).

        Overrides are applied in order, so later matching overrides
        take precedence over earlier ones.

        Args:
            file_path: Path to the file being processed
            base_path: Base path (repo root) for relative matching

        Returns:
            ReferenceConfig with all applicable overrides merged
        """
        result = self.defaults

        for override in self.overrides:
            if override.applies_to(file_path, base_path):
                result = result.merge_with(override)

        return result


# =============================================================================
# Pattern Builder Functions
# =============================================================================


def build_id_pattern(
    pattern_config: PatternConfig,
    ref_config: ReferenceConfig,
    include_assertion: bool = True,
) -> re.Pattern[str]:
    """Build regex pattern for matching requirement IDs.

    Creates a pattern that matches requirement IDs based on the configured
    PatternConfig (for ID structure) and ReferenceConfig (for separators, etc.)

    Args:
        pattern_config: Configuration for ID structure (prefix, types, format)
        ref_config: Configuration for reference matching (separators, case sensitivity)
        include_assertion: Whether to include optional assertion suffix

    Returns:
        Compiled regex pattern for matching requirement IDs
    """
    # Get prefix from pattern_config
    prefix = pattern_config.prefix

    # Build separator pattern from ref_config
    sep_pattern = _build_separator_pattern(ref_config.separators)

    # Get type codes from pattern_config
    type_codes = pattern_config.get_all_type_ids()
    if type_codes:
        type_pattern = f"(?:{'|'.join(re.escape(t) for t in type_codes)})"
    else:
        type_pattern = r"[a-z]"  # Default: single lowercase letter

    # Get ID format
    id_format = pattern_config.id_format
    style = id_format.get("style", "numeric")
    digits = id_format.get("digits", 5)

    if style == "numeric":
        id_number_pattern = rf"\d{{{digits}}}"
    else:
        id_number_pattern = r"[A-Za-z0-9]+"

    # Build assertion pattern if needed
    assertion_pattern = ""
    if include_assertion:
        # Assertion labels are typically uppercase letters, possibly multiple
        assertion_label = pattern_config.get_assertion_label_pattern()
        if assertion_label:
            # Make assertion optional with separator
            assertion_pattern = rf"(?:{sep_pattern}(?P<assertion>{assertion_label}))?"
        else:
            # Default: single uppercase letter
            assertion_pattern = rf"(?:{sep_pattern}(?P<assertion>[A-Z]))?"

    # Build the full pattern
    if ref_config.prefix_optional:
        prefix_pattern = rf"(?:{re.escape(prefix)}{sep_pattern})?"
    else:
        prefix_pattern = rf"{re.escape(prefix)}{sep_pattern}"

    full_pattern = (
        rf"(?P<full_id>{prefix_pattern}"
        rf"(?P<type>{type_pattern})"
        rf"(?P<number>{id_number_pattern})"
        rf"{assertion_pattern})"
    )

    flags = 0 if ref_config.case_sensitive else re.IGNORECASE
    return re.compile(full_pattern, flags)


def build_comment_pattern(
    pattern_config: PatternConfig,
    ref_config: ReferenceConfig,
    keyword_type: str = "implements",
) -> re.Pattern[str]:
    """Build pattern for matching reference comments.

    Creates a pattern for single-line comments like:
    - # Implements: REQ-p00001
    - // Validates: REQ-p00002, REQ-p00003

    Args:
        pattern_config: Configuration for ID structure
        ref_config: Configuration for comment styles and keywords
        keyword_type: Type of keyword to match ("implements", "validates", "refines")

    Returns:
        Compiled regex pattern for matching reference comments
    """
    # Build comment prefix pattern
    comment_pattern = _build_comment_prefix_pattern(ref_config.comment_styles)

    # Get keywords for the type
    keywords = ref_config.keywords.get(keyword_type, [keyword_type.capitalize()])
    keyword_pattern = "|".join(re.escape(k) for k in keywords)

    # Build ID pattern (simplified for comment matching - captures multiple)
    prefix = pattern_config.prefix
    sep_pattern = _build_separator_pattern(ref_config.separators)

    # Pattern for a single ID (may include assertion)
    single_id = (
        rf"{re.escape(prefix)}{sep_pattern}[A-Za-z0-9{re.escape(''.join(ref_config.separators))}]+"
    )

    # Full pattern: comment marker + keyword: + refs
    full_pattern = (
        rf"{comment_pattern}\s*"
        rf"(?:{keyword_pattern}):\s*"
        rf"(?P<refs>{single_id}(?:\s*,\s*{single_id})*)"
    )

    flags = 0 if ref_config.case_sensitive else re.IGNORECASE
    return re.compile(full_pattern, flags)


def build_block_header_pattern(
    ref_config: ReferenceConfig,
    keyword_type: str = "implements",
) -> re.Pattern[str]:
    """Build pattern for multi-line block headers.

    Creates a pattern for block-style references like:
    - # IMPLEMENTS REQUIREMENTS:
    - // TESTS REQUIREMENTS:

    Args:
        ref_config: Configuration for comment styles and keywords
        keyword_type: Type of keyword to match

    Returns:
        Compiled regex pattern for matching block headers
    """
    # Build comment prefix pattern
    comment_pattern = _build_comment_prefix_pattern(ref_config.comment_styles)

    # Get keywords and make variations
    keywords = ref_config.keywords.get(keyword_type, [keyword_type.capitalize()])

    # Add uppercase versions if not already present
    all_keywords = set(keywords)
    for k in keywords:
        all_keywords.add(k.upper())

    keyword_pattern = "|".join(re.escape(k) for k in all_keywords)

    # Block header pattern
    full_pattern = rf"{comment_pattern}\s*(?:{keyword_pattern})\s+REQUIREMENTS?:?\s*$"

    return re.compile(full_pattern, re.IGNORECASE)


def build_block_ref_pattern(
    pattern_config: PatternConfig,
    ref_config: ReferenceConfig,
) -> re.Pattern[str]:
    """Build pattern for references within a block.

    Creates a pattern for individual refs in a block like:
    - #   REQ-p00001
    - //  REQ-p00002-A

    Args:
        pattern_config: Configuration for ID structure
        ref_config: Configuration for comment styles

    Returns:
        Compiled regex pattern for matching block references
    """
    # Build comment prefix pattern
    comment_pattern = _build_comment_prefix_pattern(ref_config.comment_styles)

    # Build ID pattern
    prefix = pattern_config.prefix
    sep_pattern = _build_separator_pattern(ref_config.separators)

    # Pattern for ID (may include assertion)
    id_pattern = (
        rf"{re.escape(prefix)}{sep_pattern}[A-Za-z0-9{re.escape(''.join(ref_config.separators))}]+"
    )

    full_pattern = rf"^\s*{comment_pattern}\s+(?P<ref>{id_pattern})"

    flags = 0 if ref_config.case_sensitive else re.IGNORECASE
    return re.compile(full_pattern, flags)


def extract_ids_from_text(
    text: str,
    pattern_config: PatternConfig,
    ref_config: ReferenceConfig,
) -> list[str]:
    """Extract all requirement/assertion IDs from text.

    Finds all IDs matching the configured pattern in the given text.

    Args:
        text: Text to search for IDs
        pattern_config: Configuration for ID structure
        ref_config: Configuration for reference matching

    Returns:
        List of extracted ID strings (normalized)
    """
    pattern = build_id_pattern(pattern_config, ref_config, include_assertion=True)

    ids = []
    for match in pattern.finditer(text):
        match.group("full_id")
        normalized = normalize_extracted_id(match, pattern_config, ref_config)
        if normalized:
            ids.append(normalized)

    return ids


def normalize_extracted_id(
    match: re.Match[str],
    pattern_config: PatternConfig,
    ref_config: ReferenceConfig,
) -> str:
    """Normalize extracted ID to canonical format.

    Converts matched ID to the standard format defined by pattern_config.

    Args:
        match: Regex match object with named groups
        pattern_config: Configuration for ID structure
        ref_config: Configuration for separators

    Returns:
        Normalized ID string in canonical format
    """
    # Get matched components
    try:
        type_code = match.group("type")
        number = match.group("number")
    except (IndexError, AttributeError):
        # If groups don't exist, return the full match
        return match.group(0)

    # Build canonical ID using pattern_config
    prefix = pattern_config.prefix
    canonical_sep = "-"  # Standard separator for canonical format

    # Base ID
    canonical = f"{prefix}{canonical_sep}{type_code}{number}"

    # Add assertion if present
    try:
        assertion = match.group("assertion")
        if assertion:
            canonical = f"{canonical}{canonical_sep}{assertion.upper()}"
    except (IndexError, AttributeError):
        pass

    return canonical


# =============================================================================
# Helper Functions
# =============================================================================


def _build_separator_pattern(separators: list[str]) -> str:
    """Build regex pattern for matching any of the given separators.

    Args:
        separators: List of separator characters

    Returns:
        Regex pattern matching any separator
    """
    if not separators:
        return "-"
    if len(separators) == 1:
        return re.escape(separators[0])
    return f"[{''.join(re.escape(s) for s in separators)}]"


def _build_comment_prefix_pattern(comment_styles: list[str]) -> str:
    """Build regex pattern for matching comment prefixes.

    Args:
        comment_styles: List of comment style markers

    Returns:
        Regex pattern matching any comment prefix
    """
    if not comment_styles:
        return r"(?:#|//|--)"

    patterns = []
    for style in comment_styles:
        patterns.append(re.escape(style))

    return f"(?:{'|'.join(patterns)})"
