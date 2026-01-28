"""CodeParser - Priority 70 parser for code references.

Parses code comments containing requirement references.
"""

from __future__ import annotations

import re
from typing import Any, Iterator

from elspais.graph.parsers import ParseContext, ParsedContent


class CodeParser:
    """Parser for code reference comments.

    Priority: 70 (after requirements and journeys)

    Recognizes comments like:
    - # Implements: REQ-xxx
    - # Validates: REQ-xxx
    - // Implements: REQ-xxx (for JS/TS)
    - // IMPLEMENTS REQUIREMENTS: (multiline block header)
    - //   REQ-xxx: Description (multiline block item)
    """

    priority = 70

    # Patterns for various comment styles
    # Single-line format: // Implements: REQ-xxx, REQ-yyy
    IMPLEMENTS_PATTERN = re.compile(
        r"(?:#|//|--)\s*Implements:\s*(?P<refs>[A-Z]+-[A-Za-z0-9-]+(?:\s*,\s*[A-Z]+-[A-Za-z0-9-]+)*)"
    )
    VALIDATES_PATTERN = re.compile(
        r"(?:#|//|--)\s*Validates:\s*(?P<refs>[A-Z]+-[A-Za-z0-9-]+(?:\s*,\s*[A-Z]+-[A-Za-z0-9-]+)*)"
    )

    # Multiline block headers (case-insensitive)
    IMPLEMENTS_BLOCK_HEADER = re.compile(
        r"(?:#|//|--)\s*IMPLEMENTS\s+REQUIREMENTS?:?\s*$", re.IGNORECASE
    )

    # Multiline block item: //   REQ-xxx: Description  or  //   REQ-xxx
    BLOCK_REQ_PATTERN = re.compile(
        r"^\s*(?:#|//|--)\s+(?P<ref>REQ-[A-Za-z0-9-]+)"
    )

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
        i = 0
        while i < len(lines):
            ln, text = lines[i]

            # Check for single-line patterns first
            impl_match = self.IMPLEMENTS_PATTERN.search(text)
            val_match = self.VALIDATES_PATTERN.search(text)

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
            if self.IMPLEMENTS_BLOCK_HEADER.search(text):
                refs: list[str] = []
                start_ln = ln
                end_ln = ln
                raw_lines = [text]
                i += 1

                # Collect REQ references from subsequent comment lines
                while i < len(lines):
                    next_ln, next_text = lines[i]
                    ref_match = self.BLOCK_REQ_PATTERN.match(next_text)
                    if ref_match:
                        refs.append(ref_match.group("ref"))
                        end_ln = next_ln
                        raw_lines.append(next_text)
                        i += 1
                    elif next_text.strip().startswith(("#", "//", "--")) and not next_text.strip().rstrip("#/-").strip():
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
