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
    """

    priority = 70

    # Patterns for various comment styles
    IMPLEMENTS_PATTERN = re.compile(
        r"(?:#|//|--)\s*Implements:\s*(?P<refs>[A-Z]+-[A-Za-z0-9-]+(?:\s*,\s*[A-Z]+-[A-Za-z0-9-]+)*)"
    )
    VALIDATES_PATTERN = re.compile(
        r"(?:#|//|--)\s*Validates:\s*(?P<refs>[A-Z]+-[A-Za-z0-9-]+(?:\s*,\s*[A-Z]+-[A-Za-z0-9-]+)*)"
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
        for ln, text in lines:
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
