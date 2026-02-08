"""Markdown-to-ANSI renderer for terminal documentation display.

Renders markdown files with ANSI color codes for terminal display.
Supports headings, code blocks, bold text, inline code, and command hints.
"""

from __future__ import annotations

import re
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class MarkdownRenderer:
    """Renders markdown content to ANSI-colored terminal output."""

    # ANSI escape codes
    BOLD = "\033[1m"
    DIM = "\033[2m"
    CYAN = "\033[36m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RESET = "\033[0m"

    def __init__(self, use_color: bool = True) -> None:
        """Initialize renderer with color settings.

        Args:
            use_color: Whether to emit ANSI color codes.
        """
        self.use_color = use_color

    def _c(self, code: str) -> str:
        """Return ANSI code if colors enabled, else empty string."""
        return code if self.use_color else ""

    def render(self, markdown: str) -> str:
        """Render markdown content to ANSI-colored output.

        Args:
            markdown: Raw markdown text.

        Returns:
            Formatted text with ANSI codes (if colors enabled).
        """
        lines = markdown.split("\n")
        output_lines: list[str] = []
        in_code_block = False
        code_lines: list[str] = []

        for line in lines:
            # Handle code block boundaries
            if line.strip().startswith("```"):
                if in_code_block:
                    # End code block - emit collected lines
                    output_lines.extend(self._render_code_block(code_lines))
                    code_lines = []
                    in_code_block = False
                else:
                    # Start code block
                    in_code_block = True
                continue

            if in_code_block:
                code_lines.append(line)
                continue

            # Process regular lines
            output_lines.append(self._render_line(line))

        # Handle unclosed code block
        if code_lines:
            output_lines.extend(self._render_code_block(code_lines))

        return "\n".join(output_lines)

    def _render_code_block(self, lines: list[str]) -> list[str]:
        """Render a fenced code block with dim formatting."""
        result = []
        for line in lines:
            # Indent code blocks by 2 spaces and dim them
            result.append(f"  {self._c(self.DIM)}{line}{self._c(self.RESET)}")
        return result

    def _render_line(self, line: str) -> str:
        """Render a single line of markdown."""
        stripped = line.strip()

        # Level 1 heading: # Title -> boxed heading
        if stripped.startswith("# ") and not stripped.startswith("## "):
            title = stripped[2:].strip()
            return self._render_heading(title)

        # Level 2 heading: ## Subheading -> green with underline
        if stripped.startswith("## "):
            title = stripped[3:].strip()
            return self._render_subheading(title)

        # Level 3+ headings: just bold
        if stripped.startswith("### "):
            title = stripped[4:].strip()
            return f"\n{self._c(self.BOLD)}{title}{self._c(self.RESET)}\n"

        # Regular line - apply inline formatting
        return self._render_inline(line)

    def _render_heading(self, title: str) -> str:
        """Render a level-1 heading with box borders."""
        border = "═" * 60
        return (
            f"\n{self._c(self.BOLD)}{self._c(self.CYAN)}{border}{self._c(self.RESET)}\n"
            f"{self._c(self.BOLD)}{title}{self._c(self.RESET)}\n"
            f"{self._c(self.BOLD)}{self._c(self.CYAN)}{border}{self._c(self.RESET)}\n"
        )

    def _render_subheading(self, title: str) -> str:
        """Render a level-2 heading with underline."""
        underline = "─" * 40
        return (
            f"\n{self._c(self.BOLD)}{self._c(self.GREEN)}{title}{self._c(self.RESET)}\n"
            f"{self._c(self.DIM)}{underline}{self._c(self.RESET)}\n"
        )

    def _render_inline(self, text: str) -> str:
        """Apply inline markdown formatting to text.

        Handles:
        - **bold** -> BOLD
        - `code` -> CYAN
        - $ command -> GREEN $ prefix with dim comment
        """
        result = text

        # Handle command lines: "$ command  # comment"
        # Match lines that have "$ " near the start (possibly indented)
        cmd_match = re.match(r"^(\s*)(\$)\s+(.*)$", result)
        if cmd_match:
            indent, dollar, rest = cmd_match.groups()
            # Split command from comment
            if "  #" in rest or "\t#" in rest:
                # Find the comment part
                comment_match = re.search(r"(\s{2,}#.*)$", rest)
                if comment_match:
                    comment = comment_match.group(1)
                    cmd_part = rest[: comment_match.start()]
                    result = (
                        f"{indent}{self._c(self.GREEN)}{dollar}{self._c(self.RESET)} "
                        f"{cmd_part}{self._c(self.DIM)}{comment}{self._c(self.RESET)}"
                    )
                else:
                    result = f"{indent}{self._c(self.GREEN)}{dollar}{self._c(self.RESET)} {rest}"
            else:
                result = f"{indent}{self._c(self.GREEN)}{dollar}{self._c(self.RESET)} {rest}"
            return result

        # Bold: **text** -> BOLD text RESET
        result = re.sub(
            r"\*\*([^*]+)\*\*",
            lambda m: f"{self._c(self.BOLD)}{m.group(1)}{self._c(self.RESET)}",
            result,
        )

        # Inline code: `text` -> CYAN text RESET
        result = re.sub(
            r"`([^`]+)`",
            lambda m: f"{self._c(self.CYAN)}{m.group(1)}{self._c(self.RESET)}",
            result,
        )

        return result


def render_markdown(markdown: str, use_color: bool | None = None) -> str:
    """Convenience function to render markdown to ANSI.

    Args:
        markdown: Raw markdown text.
        use_color: Whether to use ANSI colors. If None, auto-detect TTY.

    Returns:
        Formatted text suitable for terminal output.
    """
    if use_color is None:
        use_color = sys.stdout.isatty()
    renderer = MarkdownRenderer(use_color=use_color)
    return renderer.render(markdown)
