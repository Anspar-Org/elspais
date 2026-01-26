"""TestParser - Priority 80 parser for test references.

Parses test files for requirement references in test names and comments.
"""

from __future__ import annotations

import re
from typing import Any, Iterator

from elspais.graph.parsers import ParseContext, ParsedContent


class TestParser:
    """Parser for test references.

    Priority: 80 (after code references)

    Recognizes:
    - Test names with REQ references: test_foo_REQ_p00001
    - Comments with REQ references: # Tests REQ-xxx
    """

    priority = 80

    # Pattern for REQ in test name (underscores replaced with dashes)
    TEST_NAME_REQ_PATTERN = re.compile(
        r"def\s+test_\w*(?P<ref>REQ_[a-z]\d+)"
    )

    # Pattern for REQ reference in comments
    COMMENT_REQ_PATTERN = re.compile(
        r"(?:#|//)\s*Tests?\s+(?P<refs>REQ-[A-Za-z0-9-]+(?:\s*,?\s*REQ-[A-Za-z0-9-]+)*)"
    )

    # General REQ pattern in any line
    GENERAL_REQ_PATTERN = re.compile(r"REQ-[a-z]\d+", re.IGNORECASE)

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
        for ln, text in lines:
            validates: list[str] = []

            # Check for REQ in test function name
            name_match = self.TEST_NAME_REQ_PATTERN.search(text)
            if name_match:
                # Convert REQ_p00001 to REQ-p00001
                ref = name_match.group("ref").replace("_", "-")
                validates.append(ref)

            # Check for REQ in comment
            comment_match = self.COMMENT_REQ_PATTERN.search(text)
            if comment_match:
                refs_str = comment_match.group("refs")
                refs = re.findall(r"REQ-[A-Za-z0-9-]+", refs_str)
                validates.extend(refs)

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
