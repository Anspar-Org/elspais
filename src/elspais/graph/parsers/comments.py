"""CommentsParser - Priority 0 parser for HTML comment blocks.

Claims HTML comments (single-line and multi-line) before any other parser
can process them. This prevents comment content from being interpreted
as requirements or other content types.
"""

from __future__ import annotations

import re
from typing import Iterator

from elspais.arch3.Graph.MDparser import ParseContext, ParsedContent


class CommentsParser:
    """Parser for HTML comment blocks.

    Priority: 0 (highest priority, runs first)

    Handles:
    - Single-line comments: <!-- comment -->
    - Multi-line comments: <!-- ... -->
    """

    priority = 0

    # Pattern for single-line comment
    SINGLE_LINE_PATTERN = re.compile(r"<!--.*-->")

    # Pattern for comment start
    COMMENT_START = re.compile(r"<!--")

    # Pattern for comment end
    COMMENT_END = re.compile(r"-->")

    def claim_and_parse(
        self,
        lines: list[tuple[int, str]],
        context: ParseContext,
    ) -> Iterator[ParsedContent]:
        """Claim and parse HTML comment blocks.

        Args:
            lines: List of (line_number, content) tuples.
            context: Parsing context.

        Yields:
            ParsedContent for each comment block.
        """
        # Build a dict for quick line lookup
        line_map = {ln: text for ln, text in lines}
        line_numbers = sorted(line_map.keys())

        claimed: set[int] = set()
        i = 0

        while i < len(line_numbers):
            ln = line_numbers[i]
            if ln in claimed:
                i += 1
                continue

            text = line_map[ln]

            # Check for single-line comment
            if self.SINGLE_LINE_PATTERN.search(text):
                claimed.add(ln)
                yield ParsedContent(
                    content_type="comment",
                    start_line=ln,
                    end_line=ln,
                    raw_text=text,
                    parsed_data={"comment_type": "single_line"},
                )
                i += 1
                continue

            # Check for multi-line comment start
            if self.COMMENT_START.search(text) and not self.COMMENT_END.search(text):
                # Find the closing -->
                start_ln = ln
                end_ln = None
                collected_lines = [text]

                for j in range(i + 1, len(line_numbers)):
                    next_ln = line_numbers[j]
                    # Only consider contiguous lines
                    if next_ln != line_numbers[j - 1] + 1:
                        # Gap in line numbers, can't be same comment
                        break
                    next_text = line_map[next_ln]
                    collected_lines.append(next_text)
                    if self.COMMENT_END.search(next_text):
                        end_ln = next_ln
                        break

                if end_ln is not None:
                    # Found closing, claim all lines
                    for claim_ln in range(start_ln, end_ln + 1):
                        if claim_ln in line_map:
                            claimed.add(claim_ln)

                    yield ParsedContent(
                        content_type="comment",
                        start_line=start_ln,
                        end_line=end_ln,
                        raw_text="\n".join(collected_lines),
                        parsed_data={"comment_type": "multi_line"},
                    )

            i += 1
