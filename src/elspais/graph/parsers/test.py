"""TestParser - Priority 80 parser for test references.

Parses test files for requirement references in test names and comments.
Uses the shared reference_config infrastructure for configurable patterns.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Iterator

from elspais.graph.parsers import ParseContext, ParsedContent
from elspais.utilities.reference_config import (
    ReferenceConfig,
    ReferenceResolver,
    _build_comment_prefix_pattern,
    build_block_header_pattern,
    build_block_ref_pattern,
)

if TYPE_CHECKING:
    from elspais.utilities.patterns import PatternConfig


class TestParser:
    """Parser for test references.

    Priority: 80 (after code references)

    Recognizes:
    - Test names with REQ references: test_foo_REQ_p00001
    - Comments with REQ references: # Tests REQ-xxx
    - Multiline block headers: -- TESTS REQUIREMENTS:
    - Multiline block items: --   REQ-xxx: Description

    Uses configurable patterns from ReferenceConfig for:
    - Comment styles (# // -- etc.)
    - Keywords (Tests, Validates, etc.)
    - Separator characters (- _ etc.)
    """

    priority = 80

    def __init__(
        self,
        pattern_config: PatternConfig | None = None,
        reference_resolver: ReferenceResolver | None = None,
    ) -> None:
        """Initialize TestParser with optional configuration.

        Args:
            pattern_config: Configuration for ID structure. If None, uses defaults.
            reference_resolver: Resolver for file-specific reference config. If None,
                               uses default ReferenceConfig.
        """
        self._pattern_config = pattern_config
        self._reference_resolver = reference_resolver

    def _get_pattern_config(self, context: ParseContext) -> PatternConfig:
        """Get pattern config from context or instance.

        Args:
            context: Parse context that may contain pattern config.

        Returns:
            PatternConfig to use for parsing.
        """
        if self._pattern_config is not None:
            return self._pattern_config

        if "pattern_config" in context.config:
            return context.config["pattern_config"]

        from elspais.utilities.patterns import PatternConfig

        return PatternConfig.from_dict(
            {
                "prefix": "REQ",
                "types": {
                    "prd": {"id": "p", "name": "PRD"},
                    "ops": {"id": "o", "name": "OPS"},
                    "dev": {"id": "d", "name": "DEV"},
                },
                "id_format": {"style": "numeric", "digits": 5},
            }
        )

    def _get_reference_config(
        self, context: ParseContext, pattern_config: PatternConfig
    ) -> ReferenceConfig:
        """Get reference config for the current file.

        Args:
            context: Parse context with file path.
            pattern_config: Pattern config (unused but available for consistency).

        Returns:
            ReferenceConfig for this file.
        """
        if self._reference_resolver is not None:
            file_path = Path(context.file_path)
            repo_root = Path(context.config.get("repo_root", "."))
            return self._reference_resolver.resolve(file_path, repo_root)

        if "reference_resolver" in context.config:
            resolver: ReferenceResolver = context.config["reference_resolver"]
            file_path = Path(context.file_path)
            repo_root = Path(context.config.get("repo_root", "."))
            return resolver.resolve(file_path, repo_root)

        return ReferenceConfig()

    def _build_test_name_pattern(
        self, pattern_config: PatternConfig, ref_config: ReferenceConfig
    ) -> re.Pattern[str]:
        """Build pattern for matching REQ references in test function names.

        Test names use underscores: def test_foo_REQ_p00001_A

        Args:
            pattern_config: Configuration for ID structure.
            ref_config: Configuration for reference matching.

        Returns:
            Compiled regex pattern for matching test name references.
        """
        prefix = pattern_config.prefix

        # Get type codes
        type_codes = pattern_config.get_all_type_ids()
        if type_codes:
            type_pattern = f"(?:{'|'.join(re.escape(t) for t in type_codes)})"
        else:
            type_pattern = r"[a-z]"

        # Get ID format
        id_format = pattern_config.id_format
        style = id_format.get("style", "numeric")
        digits = id_format.get("digits", 5)

        if style == "numeric":
            id_number_pattern = rf"\d{{{digits}}}"
        else:
            id_number_pattern = r"[A-Za-z0-9]+"

        # Assertion pattern (uppercase letters, can be multiple like A_B_C)
        # Add negative lookahead to prevent matching lowercase continuation
        assertion_pattern = r"(?:_[A-Z](?![a-z]))+"

        # Test names use underscores, so pattern uses _ for separators
        full_pattern = (
            rf"def\s+test_\w*"
            rf"(?P<ref>{re.escape(prefix)}_{type_pattern}{id_number_pattern}"
            rf"(?:{assertion_pattern})?)"
        )

        flags = 0 if ref_config.case_sensitive else re.IGNORECASE
        return re.compile(full_pattern, flags)

    def _build_test_comment_pattern(
        self, pattern_config: PatternConfig, ref_config: ReferenceConfig
    ) -> re.Pattern[str]:
        """Build pattern for matching REQ references in test comments.

        Test comments use "Tests" keyword WITHOUT colon: # Tests REQ-xxx
        This differs from CodeParser which uses "Validates:" WITH colon.

        Args:
            pattern_config: Configuration for ID structure.
            ref_config: Configuration for reference matching.

        Returns:
            Compiled regex pattern for matching test comment references.
        """
        # Build comment prefix pattern
        comment_pattern = _build_comment_prefix_pattern(ref_config.comment_styles)

        # Get validates keywords (includes "Tests")
        keywords = ref_config.keywords.get("validates", ["Validates", "Tests"])
        keyword_pattern = "|".join(re.escape(k) for k in keywords)

        # Build ID pattern
        prefix = pattern_config.prefix
        sep_chars = "".join(re.escape(s) for s in ref_config.separators)

        # Pattern for a single ID (may include assertion)
        single_id = rf"{re.escape(prefix)}[{sep_chars}][A-Za-z0-9{sep_chars}]+"

        # Full pattern: comment marker + keyword (NO colon) + space + refs
        # This matches: # Tests REQ-xxx or # Test REQ-xxx
        full_pattern = (
            rf"{comment_pattern}\s*"
            rf"(?:{keyword_pattern})s?\s+"  # keyword with optional 's', space (NO colon)
            rf"(?P<refs>{single_id}(?:\s*,?\s*{single_id})*)"
        )

        flags = 0 if ref_config.case_sensitive else re.IGNORECASE
        return re.compile(full_pattern, flags)

    def claim_and_parse(
        self,
        lines: list[tuple[int, str]],
        context: ParseContext,
    ) -> Iterator[ParsedContent]:
        """Claim and parse test references.

        Args:
            lines: List of (line_number, content) tuples.
            context: Parsing context.

        Yields:
            ParsedContent for each test reference.
        """
        pattern_config = self._get_pattern_config(context)
        ref_config = self._get_reference_config(context, pattern_config)

        # Build patterns dynamically based on config
        test_name_pattern = self._build_test_name_pattern(pattern_config, ref_config)
        comment_pattern = self._build_test_comment_pattern(pattern_config, ref_config)
        block_header_pattern = build_block_header_pattern(ref_config, "validates")
        block_ref_pattern = build_block_ref_pattern(pattern_config, ref_config)

        i = 0
        while i < len(lines):
            ln, text = lines[i]
            validates: list[str] = []

            # Check for REQ in test function name
            name_match = test_name_pattern.search(text)
            if name_match:
                # Convert REQ_p00001 to REQ-p00001
                ref = name_match.group("ref").replace("_", "-")
                validates.append(ref)

            # Check for REQ in comment (single-line)
            comment_match = comment_pattern.search(text)
            if comment_match:
                refs_str = comment_match.group("refs")
                # Extract individual REQ IDs from the refs string
                prefix = pattern_config.prefix
                for ref_match in re.finditer(
                    rf"{re.escape(prefix)}[-_][A-Za-z0-9\-_]+", refs_str, re.IGNORECASE
                ):
                    validates.append(ref_match.group(0).replace("_", "-"))

            if validates:
                yield ParsedContent(
                    content_type="test_ref",
                    start_line=ln,
                    end_line=ln,
                    raw_text=text,
                    parsed_data={
                        "validates": validates,
                    },
                )
                i += 1
                continue

            # Check for multiline block header: -- TESTS REQUIREMENTS:
            if block_header_pattern.search(text):
                refs: list[str] = []
                start_ln = ln
                end_ln = ln
                raw_lines = [text]
                i += 1

                # Collect REQ references from subsequent comment lines
                while i < len(lines):
                    next_ln, next_text = lines[i]
                    ref_match = block_ref_pattern.match(next_text)
                    if ref_match:
                        refs.append(ref_match.group("ref"))
                        end_ln = next_ln
                        raw_lines.append(next_text)
                        i += 1
                    elif self._is_empty_comment(next_text, ref_config.comment_styles):
                        # Empty comment line, skip
                        i += 1
                    else:
                        # Non-comment line or different content, stop
                        break

                if refs:
                    yield ParsedContent(
                        content_type="test_ref",
                        start_line=start_ln,
                        end_line=end_ln,
                        raw_text="\n".join(raw_lines),
                        parsed_data={
                            "validates": refs,
                        },
                    )
                continue

            i += 1

    def _is_empty_comment(self, text: str, comment_styles: list[str]) -> bool:
        """Check if a line is an empty comment.

        Args:
            text: Line text to check.
            comment_styles: List of comment style markers.

        Returns:
            True if line is an empty comment.
        """
        stripped = text.strip()
        for style in comment_styles:
            if stripped.startswith(style):
                remainder = stripped[len(style) :].strip()
                remainder = remainder.rstrip("#/-").strip()
                if not remainder:
                    return True
        return False
