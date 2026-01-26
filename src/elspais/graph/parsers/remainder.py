"""RemainderParser - Priority 999 catch-all parser.

Claims all remaining unclaimed lines after all other parsers have run.
Groups contiguous lines into remainder blocks.
"""

from __future__ import annotations

from typing import Iterator

from elspais.graph.parsers import ParseContext, ParsedContent


class RemainderParser:
    """Parser for unclaimed remainder content.

    Priority: 999 (lowest priority, runs last)

    Claims all remaining lines that no other parser claimed, grouping
    contiguous lines into blocks. This ensures every line in the file
    is assigned to exactly one ParsedContent.
    """

    priority = 999

    def claim_and_parse(
        self,
        lines: list[tuple[int, str]],
        context: ParseContext,
    ) -> Iterator[ParsedContent]:
        """Claim all remaining lines as remainder blocks.

        Groups contiguous lines (no gaps in line numbers) into single
        remainder blocks.

        Args:
            lines: List of (line_number, content) tuples.
            context: Parsing context.

        Yields:
            ParsedContent for each contiguous remainder block.
        """
        if not lines:
            return

        # Sort by line number
        sorted_lines = sorted(lines, key=lambda x: x[0])

        # Group contiguous lines
        groups: list[list[tuple[int, str]]] = []
        current_group: list[tuple[int, str]] = []

        for ln, text in sorted_lines:
            if not current_group:
                current_group.append((ln, text))
            elif ln == current_group[-1][0] + 1:
                # Contiguous
                current_group.append((ln, text))
            else:
                # Gap - start new group
                groups.append(current_group)
                current_group = [(ln, text)]

        if current_group:
            groups.append(current_group)

        # Yield each group as a remainder block
        for group in groups:
            start_line = group[0][0]
            end_line = group[-1][0]
            raw_text = "\n".join(text for _, text in group)

            yield ParsedContent(
                content_type="remainder",
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                parsed_data={},
            )
