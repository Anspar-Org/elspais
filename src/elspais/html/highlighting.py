# Implements: REQ-p00006-A
"""Syntax highlighting utilities for the file viewer.

Extracts Pygments-based highlighting into reusable functions shared by
both the static HTML generator (view mode) and the Flask server (edit mode).

Gracefully degrades to plain HTML-escaped text when Pygments is unavailable.
"""

from __future__ import annotations

import html as _html

MAX_FILE_SIZE = 512_000  # 500 KB limit


def highlight_file_content(file_path: str, raw_content: str) -> dict:
    """Highlight file content using Pygments, with graceful fallback.

    Args:
        file_path: File name or path (used for lexer detection).
        raw_content: Raw text content of the file.

    Returns:
        Dictionary with keys:
        - ``lines``: list of HTML strings (one per line, Pygments-highlighted)
        - ``language``: detected language name (lowercase)
        - ``raw``: the original raw content
    """
    raw_lines = raw_content.split("\n")

    try:
        from pygments import highlight as pygments_highlight
        from pygments.formatters import HtmlFormatter
        from pygments.lexers import TextLexer, get_lexer_for_filename

        formatter = HtmlFormatter(nowrap=True)

        try:
            lexer = get_lexer_for_filename(file_path)
            language = lexer.name.lower()
        except Exception:
            lexer = TextLexer()
            language = "text"

        # Highlight the full content, then split by line.
        # This preserves multi-line token state (e.g., docstrings).
        full_highlighted = pygments_highlight(raw_content, lexer, formatter)
        highlighted_lines: list[str] = full_highlighted.split("\n")

        # Pygments may add a trailing empty string after final \n
        if highlighted_lines and highlighted_lines[-1] == "":
            highlighted_lines.pop()

    except ImportError:
        # No Pygments available — use HTML-escaped plain text
        highlighted_lines = [_html.escape(line) for line in raw_lines]
        language = "text"

        # Remove trailing empty line to match raw_lines when content ends with \n
        if highlighted_lines and raw_content.endswith("\n"):
            highlighted_lines.pop()

    return {
        "lines": highlighted_lines,
        "language": language,
        "raw": raw_content,
    }


def get_pygments_css(style: str = "default", scope: str = ".highlight") -> str:
    """Generate scoped Pygments CSS for syntax highlighting.

    Args:
        style: Pygments style name (e.g., ``"default"``, ``"monokai"``).
        scope: CSS selector to scope the rules under.

    Returns:
        CSS rules as a string, or empty string if Pygments is unavailable.
    """
    try:
        from pygments.formatters import HtmlFormatter

        formatter = HtmlFormatter(style=style)
        return formatter.get_style_defs(scope)
    except ImportError:
        return ""
