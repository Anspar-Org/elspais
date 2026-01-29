"""CodeParser - Priority 70 parser for code references.

Parses code comments containing requirement references.
Uses the shared reference_config infrastructure for configurable patterns.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator

from elspais.graph.parsers import ParseContext, ParsedContent
from elspais.utilities.reference_config import (
    ReferenceConfig,
    ReferenceResolver,
    build_block_header_pattern,
    build_block_ref_pattern,
    build_comment_pattern,
)

if TYPE_CHECKING:
    from elspais.utilities.patterns import PatternConfig


class CodeParser:
    """Parser for code reference comments.

    Priority: 70 (after requirements and journeys)

    Recognizes comments like:
    - # Implements: REQ-xxx
    - # Validates: REQ-xxx
    - // Implements: REQ-xxx (for JS/TS)
    - // IMPLEMENTS REQUIREMENTS: (multiline block header)
    - //   REQ-xxx: Description (multiline block item)

    Uses configurable patterns from ReferenceConfig for:
    - Comment styles (# // -- etc.)
    - Keywords (Implements, Validates, Tests, etc.)
    - Separator characters (- _ etc.)
    """

    priority = 70

    def __init__(
        self,
        pattern_config: PatternConfig | None = None,
        reference_resolver: ReferenceResolver | None = None,
    ) -> None:
        """Initialize CodeParser with optional configuration.

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
        # Try instance config first
        if self._pattern_config is not None:
            return self._pattern_config

        # Try context config
        if "pattern_config" in context.config:
            return context.config["pattern_config"]

        # Fall back to creating a default
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

        # Try context config
        if "reference_resolver" in context.config:
            resolver: ReferenceResolver = context.config["reference_resolver"]
            file_path = Path(context.file_path)
            repo_root = Path(context.config.get("repo_root", "."))
            return resolver.resolve(file_path, repo_root)

        # Fall back to default config
        return ReferenceConfig()

    def claim_and_parse(
        self,
        lines: list[tuple[int, str]],
        context: ParseContext,
    ) -> Iterator[ParsedContent]:
        """Claim and parse code reference comments.

        Args:
            lines: List of (line_number, content) tuples.
            context: Parsing context.

        Yields:
            ParsedContent for each code reference.
        """
        # Get configs for this file
        pattern_config = self._get_pattern_config(context)
        ref_config = self._get_reference_config(context, pattern_config)

        # Build patterns dynamically based on config
        implements_pattern = build_comment_pattern(pattern_config, ref_config, "implements")
        validates_pattern = build_comment_pattern(pattern_config, ref_config, "validates")
        block_header_pattern = build_block_header_pattern(ref_config, "implements")
        block_ref_pattern = build_block_ref_pattern(pattern_config, ref_config)

        i = 0
        while i < len(lines):
            ln, text = lines[i]

            # Check for single-line patterns first
            impl_match = implements_pattern.search(text)
            val_match = validates_pattern.search(text)

            if impl_match or val_match:
                parsed_data: dict[str, Any] = {
                    "implements": [],
                    "validates": [],
                }

                if impl_match:
                    refs = [r.strip() for r in impl_match.group("refs").split(",")]
                    parsed_data["implements"] = refs

                if val_match:
                    refs = [r.strip() for r in val_match.group("refs").split(",")]
                    parsed_data["validates"] = refs

                yield ParsedContent(
                    content_type="code_ref",
                    start_line=ln,
                    end_line=ln,
                    raw_text=text,
                    parsed_data=parsed_data,
                )
                i += 1
                continue

            # Check for multiline block header: // IMPLEMENTS REQUIREMENTS:
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
                        content_type="code_ref",
                        start_line=start_ln,
                        end_line=end_ln,
                        raw_text="\n".join(raw_lines),
                        parsed_data={
                            "implements": refs,
                            "validates": [],
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
                # Remove the comment marker and check if remainder is empty
                remainder = stripped[len(style) :].strip()
                # Also handle trailing comment markers (for decorative comments)
                remainder = remainder.rstrip("#/-").strip()
                if not remainder:
                    return True
        return False
