"""Shared helper functions for parsers."""

from __future__ import annotations


def is_empty_comment(text: str, comment_styles: list[str]) -> bool:
    """Check if a line is an empty comment.

    An empty comment is a line that starts with a comment marker but has
    no meaningful content after it. This includes decorative comment lines
    like "# ----" or "// ======".

    Args:
        text: Line text to check.
        comment_styles: List of comment style markers (e.g., ["#", "//"]).

    Returns:
        True if line is an empty comment.
    """
    stripped = text.strip()
    for style in comment_styles:
        if stripped.startswith(style):
            # Remove the comment marker and check if remainder is empty
            remainder = stripped[len(style) :].strip()
            # Also handle trailing comment markers (for decorative comments)
            remainder = remainder.rstrip("#/-").strip()
            if not remainder:
                return True
    return False
