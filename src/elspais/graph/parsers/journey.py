# Implements: REQ-o00050-C
"""JourneyParser - Priority 60 parser for user journey blocks.

Parses user journey specifications from markdown.
"""

from __future__ import annotations

import re
from typing import Any, Iterator

from elspais.graph.parsers import ParseContext, ParsedContent


class JourneyParser:
    """Parser for user journey blocks.

    Priority: 60 (after requirements)

    Parses user journeys in format:
    - Header: ## JNY-xxx-NN: Title
    - Actor/Goal fields
    - Steps section
    - End marker
    """

    priority = 60

    # Journey ID pattern: JNY-{Descriptor}-{number}
    HEADER_PATTERN = re.compile(r"^#*\s*(?P<id>JNY-[A-Za-z0-9-]+):\s*(?P<title>.+)$")
    ACTOR_PATTERN = re.compile(r"\*\*Actor\*\*:\s*(?P<actor>.+?)(?:\n|$)")
    GOAL_PATTERN = re.compile(r"\*\*Goal\*\*:\s*(?P<goal>.+?)(?:\n|$)")
    ADDRESSES_PATTERN = re.compile(r"^Addresses:\s*(?P<addresses>.+?)$", re.MULTILINE)
    END_MARKER_PATTERN = re.compile(r"^\*End\*\s+\*JNY-[^*]+\*", re.MULTILINE)

    def claim_and_parse(
        self,
        lines: list[tuple[int, str]],
        context: ParseContext,
    ) -> Iterator[ParsedContent]:
        """Claim and parse user journey blocks.

        Args:
            lines: List of (line_number, content) tuples.
            context: Parsing context.

        Yields:
            ParsedContent for each journey block.
        """
        line_map = dict(lines)
        line_numbers = sorted(line_map.keys())

        if not line_numbers:
            return

        claimed: set[int] = set()
        i = 0

        while i < len(line_numbers):
            ln = line_numbers[i]
            if ln in claimed:
                i += 1
                continue

            text = line_map[ln]

            header_match = self.HEADER_PATTERN.match(text)
            if header_match:
                journey_id = header_match.group("id")
                title = header_match.group("title").strip()
                start_line = ln

                # Find end of journey
                journey_lines = [(ln, text)]
                end_line = ln
                j = i + 1

                while j < len(line_numbers):
                    next_ln = line_numbers[j]
                    next_text = line_map[next_ln]
                    journey_lines.append((next_ln, next_text))
                    end_line = next_ln

                    if self.END_MARKER_PATTERN.match(next_text):
                        j += 1
                        break

                    # Next journey header
                    if self.HEADER_PATTERN.match(next_text):
                        journey_lines.pop()
                        end_line = line_numbers[j - 1] if j > i + 1 else ln
                        break

                    j += 1

                # Claim lines
                for claim_ln, _ in journey_lines:
                    claimed.add(claim_ln)

                raw_text = "\n".join(t for _, t in journey_lines)
                parsed_data = self._parse_journey(journey_id, title, raw_text)

                yield ParsedContent(
                    content_type="journey",
                    start_line=start_line,
                    end_line=end_line,
                    raw_text=raw_text,
                    parsed_data=parsed_data,
                )

                while i < len(line_numbers) and line_numbers[i] in claimed:
                    i += 1
            else:
                i += 1

    def _parse_journey(self, journey_id: str, title: str, text: str) -> dict[str, Any]:
        """Parse journey fields from text block."""
        data: dict[str, Any] = {
            "id": journey_id,
            "title": title,
            "actor": None,
            "goal": None,
            "addresses": [],
        }

        actor_match = self.ACTOR_PATTERN.search(text)
        if actor_match:
            data["actor"] = actor_match.group("actor").strip()

        goal_match = self.GOAL_PATTERN.search(text)
        if goal_match:
            data["goal"] = goal_match.group("goal").strip()

        addresses_match = self.ADDRESSES_PATTERN.search(text)
        if addresses_match:
            refs_str = addresses_match.group("addresses")
            data["addresses"] = [ref.strip() for ref in refs_str.split(",") if ref.strip()]

        return data
