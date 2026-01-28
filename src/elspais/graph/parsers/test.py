"""TestParser - Priority 80 parser for test references.

Parses test files for requirement references in test names and comments.
"""

from __future__ import annotations

import re
from typing import Iterator

from elspais.graph.parsers import ParseContext, ParsedContent


class TestParser:
    """Parser for test references.

    Priority: 80 (after code references)

    Recognizes:
    - Test names with REQ references: test_foo_REQ_p00001
    - Comments with REQ references: # Tests REQ-xxx
    - Multiline block headers: -- TESTS REQUIREMENTS:
    - Multiline block items: --   REQ-xxx: Description
    """

    priority = 80

    # Pattern for REQ in test name (underscores replaced with dashes)
    TEST_NAME_REQ_PATTERN = re.compile(
        r"def\s+test_\w*(?P<ref>REQ_[a-z]\d+)"
    )

    # Pattern for REQ reference in comments
    COMMENT_REQ_PATTERN = re.compile(
        r"(?:#|//|--)\s*Tests?\s+(?P<refs>REQ-[A-Za-z0-9-]+(?:\s*,?\s*REQ-[A-Za-z0-9-]+)*)"
    )

    # Multiline block headers (case-insensitive)
    TESTS_BLOCK_HEADER = re.compile(
        r"(?:#|//|--)\s*TESTS?\s+REQUIREMENTS?:?\s*$", re.IGNORECASE
    )

    # Multiline block item: --   REQ-xxx: Description  or  --   REQ-xxx
    BLOCK_REQ_PATTERN = re.compile(
        r"^\s*(?:#|//|--)\s+(?P<ref>REQ-[A-Za-z0-9-]+)"
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
        i = 0
        while i < len(lines):
            ln, text = lines[i]
            validates: list[str] = []

            # Check for REQ in test function name
            name_match = self.TEST_NAME_REQ_PATTERN.search(text)
            if name_match:
                # Convert REQ_p00001 to REQ-p00001
                ref = name_match.group("ref").replace("_", "-")
                validates.append(ref)

            # Check for REQ in comment (single-line)
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
                i += 1
                continue

            # Check for multiline block header: -- TESTS REQUIREMENTS:
            if self.TESTS_BLOCK_HEADER.search(text):
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
