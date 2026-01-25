"""User Journey parser for spec files.

This parser extracts User Journey definitions from Markdown files
and produces TraceNode instances.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from elspais.core.graph import SourceLocation, TraceNode, UserJourney
    from elspais.core.graph_schema import NodeTypeSchema


class JourneyParser:
    """Parser for User Journey spec files.

    User Journeys are non-normative context providers with format:
    JNY-{Descriptor}-{number} (e.g., JNY-Spec-Author-01)
    """

    # Pattern for journey headers
    JOURNEY_PATTERN = re.compile(
        r"^#+\s+(JNY-[\w-]+):\s*(.+)$",
        re.MULTILINE,
    )

    # Patterns for journey fields
    ACTOR_PATTERN = re.compile(r"\*\*Actor\*\*:\s*(.+?)(?:\n|$)", re.IGNORECASE)
    GOAL_PATTERN = re.compile(r"\*\*Goal\*\*:\s*(.+?)(?:\n|$)", re.IGNORECASE)
    CONTEXT_PATTERN = re.compile(r"\*\*Context\*\*:\s*(.+?)(?:\n|$)", re.IGNORECASE)
    OUTCOME_PATTERN = re.compile(r"\*\*Expected\s+Outcome\*\*:\s*(.+?)(?:\n|$)", re.IGNORECASE)

    def parse(
        self,
        content: str,
        source: SourceLocation,
        schema: NodeTypeSchema,
    ) -> list[TraceNode]:
        """Parse journey content and return nodes.

        Args:
            content: File content to parse.
            source: Source location for the file.
            schema: Schema for this node type.

        Returns:
            List of parsed TraceNodes for user journeys.
        """
        from elspais.core.graph import NodeKind, SourceLocation, TraceNode, UserJourney

        nodes: list[TraceNode] = []
        content.split("\n")

        # Find all journey headers
        for match in self.JOURNEY_PATTERN.finditer(content):
            journey_id = match.group(1)
            title = match.group(2).strip()

            # Find line number
            line_start = content[: match.start()].count("\n") + 1

            # Extract the journey block (until next header or end)
            block_start = match.end()
            block_end = len(content)

            # Find next header
            next_header = re.search(r"^#+\s+", content[block_start:], re.MULTILINE)
            if next_header:
                block_end = block_start + next_header.start()

            block = content[match.start() : block_end]

            # Parse fields
            actor = self._extract_field(block, self.ACTOR_PATTERN) or "Unknown"
            goal = self._extract_field(block, self.GOAL_PATTERN) or title
            context = self._extract_field(block, self.CONTEXT_PATTERN)
            outcome = self._extract_field(block, self.OUTCOME_PATTERN)
            steps = self._extract_steps(block)

            journey = UserJourney(
                id=journey_id,
                actor=actor,
                goal=goal,
                context=context,
                steps=steps,
                expected_outcome=outcome,
                file_path=source.path,
                line_number=line_start,
            )

            node = TraceNode(
                id=journey_id,
                kind=NodeKind.USER_JOURNEY,
                label=self._format_label(journey, schema.label_template),
                source=SourceLocation(
                    path=source.path,
                    line=line_start,
                    repo=source.repo,
                ),
                journey=journey,
            )
            nodes.append(node)

        return nodes

    def can_parse(self, file_path: Path) -> bool:
        """Check if this parser can handle the given file.

        Args:
            file_path: Path to the file.

        Returns:
            True for Markdown files that might contain journeys.
        """
        if file_path.suffix.lower() not in (".md", ".markdown"):
            return False

        # Check for journey-related naming
        name = file_path.stem.lower()
        return "journey" in name or "jny" in name

    def _extract_field(self, block: str, pattern: re.Pattern) -> str | None:
        """Extract a field value from a block.

        Args:
            block: Text block to search.
            pattern: Regex pattern with one group.

        Returns:
            Extracted value or None.
        """
        match = pattern.search(block)
        return match.group(1).strip() if match else None

    def _extract_steps(self, block: str) -> list[str]:
        """Extract ordered steps from a block.

        Looks for numbered or bulleted lists after "Steps:" header.

        Args:
            block: Text block to search.

        Returns:
            List of step descriptions.
        """
        steps: list[str] = []

        # Find Steps section
        steps_match = re.search(
            r"\*\*Steps\*\*:?\s*\n((?:\s*[-*\d.]+\s+.+\n?)+)",
            block,
            re.IGNORECASE,
        )
        if steps_match:
            steps_block = steps_match.group(1)
            # Extract each list item
            for line in steps_block.split("\n"):
                line = line.strip()
                if line:
                    # Remove list markers
                    step = re.sub(r"^[-*\d.]+\s*", "", line)
                    if step:
                        steps.append(step)

        return steps

    def _format_label(self, journey: UserJourney, template: str) -> str:
        """Format a label using the template.

        Args:
            journey: UserJourney to format.
            template: Label template with {placeholders}.

        Returns:
            Formatted label string.
        """
        try:
            return template.format(
                id=journey.id,
                goal=journey.goal[:50] if journey.goal else "",
                actor=journey.actor,
            )
        except (KeyError, AttributeError):
            return f"{journey.id}: {journey.goal}"


def create_parser() -> JourneyParser:
    """Factory function to create a JourneyParser.

    Returns:
        New JourneyParser instance.
    """
    return JourneyParser()
