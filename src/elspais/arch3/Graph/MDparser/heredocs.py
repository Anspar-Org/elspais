"""Heredocs parser for embedded requirement definitions.

This parser recognizes embedded requirement definitions in test files
(Python triple-quoted strings, shell heredocs) and claims them as
plain-text blocks, preventing the requirement parser from treating
them as real requirements.

If the text needs to be parsed later, it can be sent to the deserializer
as that can process arbitrary blocks of text.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Iterator

from elspais.arch3.Graph.MDparser import ParsedContent

if TYPE_CHECKING:
    from elspais.arch3.Graph.MDparser import ParseContext


def _get_file_type(file_path: str) -> str:
    """Determine file type from path.

    Args:
        file_path: Path to the file.

    Returns:
        File type: 'python', 'shell', or 'other'.
    """
    suffix = Path(file_path).suffix.lower()
    name = Path(file_path).name.lower()

    if suffix == ".py":
        return "python"
    elif suffix in (".sh", ".bash", ".zsh", ".ksh"):
        return "shell"
    elif name.endswith(".sh") or name.endswith(".bash"):
        return "shell"
    else:
        return "other"


class HeredocsParser:
    """Parser for heredoc/multiline string blocks containing requirement patterns.

    Priority: 10 (runs before requirement parser at 50)

    Claims Python triple-quoted strings and shell heredocs that contain
    REQ-xxx patterns, marking them as heredoc content type.
    """

    # Priority 10 - runs early to claim heredocs before requirement parser
    priority: int = 10

    # Pattern to detect requirement IDs
    REQ_PATTERN = re.compile(r"REQ[-_][A-Za-z]?\d+", re.IGNORECASE)

    # Python triple-quote start patterns
    PYTHON_HEREDOC_START = re.compile(
        r'^[a-zA-Z_][a-zA-Z0-9_]*\s*=\s*[fFrRbBuU]?'  # var = [prefix]
        r'("""|\'\'\')',  # triple quote
        re.MULTILINE,
    )

    # Shell heredoc start pattern: << 'EOF' or << "EOF" or << EOF
    SHELL_HEREDOC_START = re.compile(
        r"<<\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?",
        re.MULTILINE,
    )

    def claim_and_parse(
        self,
        lines: list[tuple[int, str]],
        context: ParseContext,
    ) -> Iterator[ParsedContent]:
        """Claim heredoc blocks containing requirement patterns.

        Args:
            lines: List of (line_number, content) tuples.
            context: Parse context with file information.

        Yields:
            ParsedContent for each claimed heredoc block.
        """
        file_type = _get_file_type(context.file_path)

        if file_type == "python":
            yield from self._parse_python_heredocs(lines, context)
        elif file_type == "shell":
            yield from self._parse_shell_heredocs(lines, context)
        # Skip markdown, spec files, etc.

    def _parse_python_heredocs(
        self,
        lines: list[tuple[int, str]],
        context: ParseContext,
    ) -> Iterator[ParsedContent]:
        """Parse Python triple-quoted strings containing REQ patterns.

        Args:
            lines: List of (line_number, content) tuples.
            context: Parse context.

        Yields:
            ParsedContent for each heredoc block.
        """
        i = 0
        while i < len(lines):
            line_num, content = lines[i]

            # Check for triple-quote start
            match = self.PYTHON_HEREDOC_START.match(content)
            if match:
                quote_char = match.group(1)  # """ or '''

                # Find the end of the heredoc
                heredoc_lines = [content]
                end_idx = i

                # Check if it's a one-liner
                rest = content[match.end() :]
                if quote_char in rest:
                    # Single line heredoc - check for REQ pattern
                    if self.REQ_PATTERN.search(content):
                        yield ParsedContent(
                            content_type="heredoc",
                            start_line=line_num,
                            end_line=line_num,
                            raw_text=content,
                            parsed_data={"quote_style": quote_char},
                        )
                    i += 1
                    continue

                # Multi-line heredoc
                for j in range(i + 1, len(lines)):
                    end_line_num, end_content = lines[j]
                    heredoc_lines.append(end_content)
                    if quote_char in end_content:
                        end_idx = j
                        break
                else:
                    # No closing quote found - skip
                    i += 1
                    continue

                # Check if heredoc contains REQ pattern
                full_text = "\n".join(heredoc_lines)
                if self.REQ_PATTERN.search(full_text):
                    yield ParsedContent(
                        content_type="heredoc",
                        start_line=line_num,
                        end_line=lines[end_idx][0],
                        raw_text=full_text,
                        parsed_data={"quote_style": quote_char},
                    )
                    i = end_idx + 1
                    continue

            i += 1

    def _parse_shell_heredocs(
        self,
        lines: list[tuple[int, str]],
        context: ParseContext,
    ) -> Iterator[ParsedContent]:
        """Parse shell-style heredocs containing REQ patterns.

        Args:
            lines: List of (line_number, content) tuples.
            context: Parse context.

        Yields:
            ParsedContent for each heredoc block.
        """
        i = 0
        while i < len(lines):
            line_num, content = lines[i]

            # Check for shell heredoc start
            match = self.SHELL_HEREDOC_START.search(content)
            if match:
                delimiter = match.group(1)  # e.g., EOF, END

                # Find the end delimiter
                heredoc_lines = [content]
                end_idx = i

                for j in range(i + 1, len(lines)):
                    end_line_num, end_content = lines[j]
                    heredoc_lines.append(end_content)
                    if end_content.strip() == delimiter:
                        end_idx = j
                        break
                else:
                    # No closing delimiter found - skip
                    i += 1
                    continue

                # Check if heredoc contains REQ pattern
                full_text = "\n".join(heredoc_lines)
                if self.REQ_PATTERN.search(full_text):
                    yield ParsedContent(
                        content_type="heredoc",
                        start_line=line_num,
                        end_line=lines[end_idx][0],
                        raw_text=full_text,
                        parsed_data={"delimiter": delimiter},
                    )
                    i = end_idx + 1
                    continue

            i += 1


def create_parser() -> HeredocsParser:
    """Factory function to create a HeredocsParser.

    Returns:
        New HeredocsParser instance.
    """
    return HeredocsParser()
