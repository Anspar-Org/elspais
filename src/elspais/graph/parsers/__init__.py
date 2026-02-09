"""MDparser - Line-claiming parser system.

This module provides the infrastructure for parsing markdown spec files
using a priority-based line-claiming system. Parsers are registered with
priorities, and lines are claimed in priority order.

Exports:
- LineClaimingParser: Protocol for parser implementations
- ParseContext: Context passed to parsers
- ParsedContent: Result of parsing a claimed region
- ParserRegistry: Manages parser registration and orchestration
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class ParseContext:
    """Context passed to parsers during parsing.

    Attributes:
        file_path: Path to the file being parsed (relative to repo root).
        config: Configuration dictionary for pattern matching, etc.
    """

    file_path: str
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedContent:
    """Result of parsing a claimed region.

    Represents a contiguous block of lines claimed by a parser,
    with the parsed content and metadata.

    Attributes:
        content_type: Type of content (e.g., "requirement", "comment").
        start_line: First line number (1-indexed).
        end_line: Last line number (1-indexed, inclusive).
        raw_text: Original text of the claimed lines.
        parsed_data: Structured data extracted by the parser.
    """

    content_type: str
    start_line: int
    end_line: int
    raw_text: str
    parsed_data: dict[str, Any] = field(default_factory=dict)

    @property
    def line_count(self) -> int:
        """Number of lines in this content block."""
        return self.end_line - self.start_line + 1


@runtime_checkable
class LineClaimingParser(Protocol):
    """Protocol for line-claiming parsers.

    Parsers claim lines in priority order (lower = earlier). Each parser
    receives only the unclaimed lines and yields ParsedContent for any
    lines it claims.
    """

    @property
    def priority(self) -> int:
        """Priority for this parser (lower = earlier)."""
        ...

    def claim_and_parse(
        self,
        lines: list[tuple[int, str]],
        context: ParseContext,
    ) -> Iterator[ParsedContent]:
        """Claim and parse lines.

        Args:
            lines: List of (line_number, content) tuples for unclaimed lines.
            context: Parsing context with file info and config.

        Yields:
            ParsedContent for each claimed region.
        """
        ...


class ParserRegistry:
    """Registry for managing line-claiming parsers.

    Parsers are registered and then called in priority order during parsing.
    Each parser only sees lines not yet claimed by earlier parsers.
    """

    def __init__(self) -> None:
        self.parsers: list[LineClaimingParser] = []

    def register(self, parser: LineClaimingParser) -> None:
        """Register a parser.

        Args:
            parser: A parser implementing LineClaimingParser protocol.
        """
        self.parsers.append(parser)

    def get_ordered(self) -> list[LineClaimingParser]:
        """Get parsers sorted by priority (ascending).

        Returns:
            List of parsers in priority order.
        """
        return sorted(self.parsers, key=lambda p: p.priority)

    def parse_all(
        self,
        lines: list[tuple[int, str]],
        context: ParseContext,
    ) -> Iterator[ParsedContent]:
        """Parse lines using all registered parsers in priority order.

        Each parser receives only the lines not claimed by earlier parsers.

        Args:
            lines: List of (line_number, content) tuples.
            context: Parsing context.

        Yields:
            ParsedContent from all parsers.
        """
        # Track which line numbers have been claimed
        claimed_lines: set[int] = set()

        for parser in self.get_ordered():
            # Filter to only unclaimed lines
            unclaimed = [(ln, text) for ln, text in lines if ln not in claimed_lines]

            if not unclaimed:
                break

            # Let parser claim and parse
            for content in parser.claim_and_parse(unclaimed, context):
                # Mark lines as claimed
                for ln in range(content.start_line, content.end_line + 1):
                    claimed_lines.add(ln)
                yield content


__all__ = [
    "LineClaimingParser",
    "ParseContext",
    "ParsedContent",
    "ParserRegistry",
]
