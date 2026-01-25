"""Requirement parser for spec files.

This parser wraps the existing core.parser.RequirementParser to produce
TraceNode instances for the traceability tree.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from elspais.core.models import Requirement
    from elspais.core.graph import SourceLocation, TraceNode
    from elspais.core.graph_schema import NodeTypeSchema


class RequirementParser:
    """Parser for requirement spec files.

    Wraps the existing RequirementParser to produce TraceNode instances.
    """

    def __init__(self) -> None:
        """Initialize the parser."""
        self._pattern_config: object | None = None

    def parse(
        self,
        content: str,
        source: SourceLocation,
        schema: NodeTypeSchema,
    ) -> list[TraceNode]:
        """Parse requirement content and return nodes.

        Args:
            content: File content to parse.
            source: Source location for the file.
            schema: Schema for this node type.

        Returns:
            List of parsed TraceNodes (requirements and their assertions).
        """
        from elspais.core.graph import NodeKind, SourceLocation, TraceNode

        nodes: list[TraceNode] = []

        # Parse requirements using the core parser
        requirements = self._parse_content(content, source.path)

        for req_id, req in requirements.items():
            # Create requirement node
            req_node = TraceNode(
                id=req_id,
                kind=NodeKind.REQUIREMENT,
                label=self._format_label(req, schema.label_template),
                source=SourceLocation(
                    path=source.path,
                    line=req.line_number or source.line,
                    repo=source.repo,
                ),
                requirement=req,
            )
            nodes.append(req_node)

            # Add assertion children
            for assertion in req.assertions:
                assertion_id = f"{req_id}-{assertion.label}"
                assertion_node = TraceNode(
                    id=assertion_id,
                    kind=NodeKind.ASSERTION,
                    label=f"{assertion.label}. {assertion.text[:50]}...",
                    source=req_node.source,
                    assertion=assertion,
                )
                req_node.children.append(assertion_node)
                assertion_node.parents.append(req_node)
                nodes.append(assertion_node)

        return nodes

    def can_parse(self, file_path: Path) -> bool:
        """Check if this parser can handle the given file.

        Args:
            file_path: Path to the file.

        Returns:
            True for Markdown files in spec directories.
        """
        # Parse markdown files
        if file_path.suffix.lower() not in (".md", ".markdown"):
            return False

        # Check if in a spec directory
        path_str = str(file_path).lower()
        return "spec" in path_str or "requirements" in path_str

    def _parse_content(self, content: str, file_path: str) -> dict[str, Requirement]:
        """Parse content using the core parser.

        Args:
            content: File content.
            file_path: Path to the file.

        Returns:
            Dictionary of requirement ID to Requirement.
        """
        from elspais.core.parser import RequirementParser as CoreParser
        from elspais.core.patterns import PatternConfig

        # Use default pattern config if not set
        if self._pattern_config is None:
            self._pattern_config = PatternConfig.from_dict({})

        parser = CoreParser(self._pattern_config)

        # Parse the content
        # The core parser expects to read from files, so we use parse_file_content
        try:
            result = parser.parse_file_content(content, Path(file_path))
            return dict(result)
        except Exception:
            return {}

    def _format_label(self, req: Requirement, template: str) -> str:
        """Format a label using the template.

        Args:
            req: Requirement to format.
            template: Label template with {placeholders}.

        Returns:
            Formatted label string.
        """
        try:
            return template.format(
                id=req.id,
                title=req.title,
                level=req.level,
                status=req.status,
            )
        except (KeyError, AttributeError):
            return f"{req.id}: {req.title}"

    def set_pattern_config(self, config: object) -> None:
        """Set the pattern configuration.

        Args:
            config: PatternConfig instance.
        """
        self._pattern_config = config


def create_parser() -> RequirementParser:
    """Factory function to create a RequirementParser.

    Returns:
        New RequirementParser instance.
    """
    return RequirementParser()
