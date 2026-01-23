"""Code reference parser for implementation files.

This parser extracts requirement references from code comments
(e.g., "# Implements: REQ-d00001") and produces TraceNode instances.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from elspais.core.tree import CodeReference, SourceLocation, TraceNode
    from elspais.core.tree_schema import NodeTypeSchema


class CodeParser:
    """Parser for code files with requirement references.

    Extracts references from comments like:
    - # Implements: REQ-d00001
    - // Implements: REQ-d00001
    - /* Implements: REQ-d00001 */
    """

    # Patterns for different comment styles
    IMPLEMENTS_PATTERNS = [
        # Python/Ruby/Shell style
        re.compile(r"#\s*Implements:\s*([\w,\s-]+)", re.IGNORECASE),
        # C/JS/Java style single line
        re.compile(r"//\s*Implements:\s*([\w,\s-]+)", re.IGNORECASE),
        # C/JS/Java style block
        re.compile(r"/\*\s*Implements:\s*([\w,\s-]+)\s*\*/", re.IGNORECASE),
        # HTML/XML style
        re.compile(r"<!--\s*Implements:\s*([\w,\s-]+)\s*-->", re.IGNORECASE),
    ]

    # Pattern for extracting requirement IDs
    REQ_ID_PATTERN = re.compile(r"REQ-[\w-]+|[A-Z]+-\d+", re.IGNORECASE)

    # File extensions we can parse
    SUPPORTED_EXTENSIONS: set[str] = {
        ".py",
        ".js",
        ".ts",
        ".tsx",
        ".jsx",
        ".java",
        ".c",
        ".cpp",
        ".h",
        ".hpp",
        ".cs",
        ".go",
        ".rs",
        ".rb",
        ".php",
        ".swift",
        ".kt",
        ".scala",
        ".sh",
        ".bash",
        ".html",
        ".css",
        ".scss",
        ".less",
        ".sql",
        ".yml",
        ".yaml",
        ".toml",
    }

    def parse(
        self,
        content: str,
        source: SourceLocation,
        schema: NodeTypeSchema,
    ) -> list[TraceNode]:
        """Parse code content and return nodes.

        Args:
            content: File content to parse.
            source: Source location for the file.
            schema: Schema for this node type.

        Returns:
            List of parsed TraceNodes for code references.
        """
        from elspais.core.tree import CodeReference, NodeKind, SourceLocation, TraceNode

        nodes: list[TraceNode] = []
        lines = content.split("\n")

        for line_num, line in enumerate(lines, start=1):
            for pattern in self.IMPLEMENTS_PATTERNS:
                match = pattern.search(line)
                if match:
                    refs_text = match.group(1)
                    # Extract individual requirement IDs
                    req_ids = self.REQ_ID_PATTERN.findall(refs_text)

                    for req_id in req_ids:
                        # Try to find the symbol (function/class) this is in
                        symbol = self._find_symbol(lines, line_num - 1)

                        code_ref = CodeReference(
                            file_path=source.path,
                            line=line_num,
                            symbol=symbol,
                        )

                        node_id = f"{source.path}:{line_num}:{req_id}"
                        node = TraceNode(
                            id=node_id,
                            kind=NodeKind.CODE,
                            label=self._format_label(code_ref, schema.label_template),
                            source=SourceLocation(
                                path=source.path,
                                line=line_num,
                                repo=source.repo,
                            ),
                            code_ref=code_ref,
                        )
                        # Store the referenced requirement ID for linking
                        node.metrics["_validates_targets"] = [req_id.upper()]
                        nodes.append(node)

        return nodes

    def can_parse(self, file_path: Path) -> bool:
        """Check if this parser can handle the given file.

        Args:
            file_path: Path to the file.

        Returns:
            True for supported code file extensions.
        """
        return file_path.suffix.lower() in self.SUPPORTED_EXTENSIONS

    def _find_symbol(self, lines: list[str], line_index: int) -> str | None:
        """Find the enclosing symbol (function/class) for a line.

        Searches backwards from the given line to find the nearest
        function or class definition.

        Args:
            lines: All lines in the file.
            line_index: 0-based index of the current line.

        Returns:
            Symbol name if found, None otherwise.
        """
        # Patterns for common language constructs
        patterns = [
            # Python
            re.compile(r"^\s*(?:async\s+)?def\s+(\w+)"),
            re.compile(r"^\s*class\s+(\w+)"),
            # JavaScript/TypeScript
            re.compile(r"^\s*(?:async\s+)?function\s+(\w+)"),
            re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*="),
            re.compile(r"^\s*(?:export\s+)?class\s+(\w+)"),
            # Java/C#
            re.compile(
                r"^\s*(?:public|private|protected)?\s*(?:static\s+)?(?:void|int|String|\w+)\s+(\w+)\s*\("
            ),
            # Go
            re.compile(r"^\s*func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)"),
            # Rust
            re.compile(r"^\s*(?:pub\s+)?(?:async\s+)?fn\s+(\w+)"),
        ]

        # Search backwards
        for i in range(line_index, -1, -1):
            line = lines[i]
            for pattern in patterns:
                match = pattern.match(line)
                if match:
                    return match.group(1)

        return None

    def _format_label(self, code_ref: CodeReference, template: str) -> str:
        """Format a label using the template.

        Args:
            code_ref: CodeReference to format.
            template: Label template with {placeholders}.

        Returns:
            Formatted label string.
        """
        try:
            return template.format(
                file_path=code_ref.file_path,
                line=code_ref.line,
                symbol=code_ref.symbol or "<unknown>",
            )
        except (KeyError, AttributeError):
            if code_ref.symbol:
                return f"{code_ref.symbol} ({code_ref.file_path}:{code_ref.line})"
            return f"{code_ref.file_path}:{code_ref.line}"


def create_parser() -> CodeParser:
    """Factory function to create a CodeParser.

    Returns:
        New CodeParser instance.
    """
    return CodeParser()
