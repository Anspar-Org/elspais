"""Diff generation for requirement changes.

Provides utilities for generating unified diffs between committed
and working copy versions of requirement files.
"""

from __future__ import annotations

import difflib
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class DiffHunk:
    """A single hunk from a unified diff."""

    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: list[tuple[str, str]]  # (type, content) where type is '+', '-', ' '


@dataclass
class DiffResult:
    """Result of a diff operation."""

    file_path: str
    old_content: Optional[str] = None
    new_content: Optional[str] = None
    hunks: list[DiffHunk] = field(default_factory=list)
    is_new_file: bool = False
    is_deleted: bool = False
    error: Optional[str] = None

    @property
    def has_changes(self) -> bool:
        """Check if there are actual changes."""
        return bool(self.hunks) or self.is_new_file or self.is_deleted


def get_committed_content(file_path: Path, repo_root: Path) -> Optional[str]:
    """Get file content from the last commit (HEAD).

    Args:
        file_path: Path to the file (absolute or relative to repo_root).
        repo_root: Repository root directory.

    Returns:
        File content from HEAD, or None if file doesn't exist in HEAD.
    """
    try:
        # Get relative path from repo root
        if file_path.is_absolute():
            rel_path = file_path.relative_to(repo_root)
        else:
            rel_path = file_path

        result = subprocess.run(
            ["git", "show", f"HEAD:{rel_path}"],
            capture_output=True,
            text=True,
            cwd=repo_root,
        )
        if result.returncode == 0:
            return result.stdout
        return None
    except (subprocess.SubprocessError, ValueError):
        return None


def generate_diff(
    file_path: Path,
    repo_root: Path,
    context_lines: int = 3,
) -> DiffResult:
    """Generate a unified diff for a file.

    Compares the file's current content with its committed (HEAD) version.

    Args:
        file_path: Path to the file.
        repo_root: Repository root directory.
        context_lines: Number of context lines around changes.

    Returns:
        DiffResult with hunks representing the changes.
    """
    result = DiffResult(file_path=str(file_path))

    # Get current content
    try:
        if file_path.exists():
            result.new_content = file_path.read_text(encoding="utf-8")
        else:
            result.is_deleted = True
            result.new_content = None
    except (OSError, UnicodeDecodeError) as e:
        result.error = f"Error reading current file: {e}"
        return result

    # Get committed content
    result.old_content = get_committed_content(file_path, repo_root)

    if result.old_content is None and result.new_content is not None:
        result.is_new_file = True
        # For new files, create a single hunk with all lines as additions
        lines = result.new_content.splitlines(keepends=True)
        if lines:
            result.hunks.append(
                DiffHunk(
                    old_start=0,
                    old_count=0,
                    new_start=1,
                    new_count=len(lines),
                    lines=[("+", line.rstrip("\n\r")) for line in lines],
                )
            )
        return result

    if result.old_content is None:
        result.error = "Cannot retrieve committed version"
        return result

    if result.new_content is None:
        # Deleted file - all lines are removals
        lines = result.old_content.splitlines(keepends=True)
        if lines:
            result.hunks.append(
                DiffHunk(
                    old_start=1,
                    old_count=len(lines),
                    new_start=0,
                    new_count=0,
                    lines=[("-", line.rstrip("\n\r")) for line in lines],
                )
            )
        return result

    # Generate unified diff
    old_lines = result.old_content.splitlines(keepends=True)
    new_lines = result.new_content.splitlines(keepends=True)

    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        lineterm="",
        n=context_lines,
    )

    # Parse the diff output into hunks
    result.hunks = _parse_unified_diff(list(diff))

    return result


def _parse_unified_diff(diff_lines: list[str]) -> list[DiffHunk]:
    """Parse unified diff output into DiffHunk objects.

    Args:
        diff_lines: Lines from difflib.unified_diff().

    Returns:
        List of DiffHunk objects.
    """
    hunks: list[DiffHunk] = []
    current_hunk: Optional[DiffHunk] = None

    for line in diff_lines:
        # Skip header lines
        if line.startswith("---") or line.startswith("+++"):
            continue

        # Hunk header: @@ -start,count +start,count @@
        if line.startswith("@@"):
            if current_hunk is not None:
                hunks.append(current_hunk)

            # Parse hunk header
            parts = line.split("@@")
            if len(parts) >= 2:
                ranges = parts[1].strip().split()
                old_range = ranges[0][1:] if ranges else "0,0"  # Remove leading -
                new_range = ranges[1][1:] if len(ranges) > 1 else "0,0"  # Remove +

                old_start, old_count = _parse_range(old_range)
                new_start, new_count = _parse_range(new_range)

                current_hunk = DiffHunk(
                    old_start=old_start,
                    old_count=old_count,
                    new_start=new_start,
                    new_count=new_count,
                    lines=[],
                )
            continue

        # Content lines
        if current_hunk is not None:
            if line.startswith("+"):
                current_hunk.lines.append(("+", line[1:].rstrip("\n\r")))
            elif line.startswith("-"):
                current_hunk.lines.append(("-", line[1:].rstrip("\n\r")))
            else:
                # Context line (starts with space)
                content = line[1:] if line.startswith(" ") else line
                current_hunk.lines.append((" ", content.rstrip("\n\r")))

    if current_hunk is not None:
        hunks.append(current_hunk)

    return hunks


def _parse_range(range_str: str) -> tuple[int, int]:
    """Parse a diff range string like '10,5' into (start, count).

    Args:
        range_str: Range string (e.g., "10,5" or "10").

    Returns:
        Tuple of (start_line, line_count).
    """
    if "," in range_str:
        parts = range_str.split(",")
        return int(parts[0]), int(parts[1])
    else:
        return int(range_str), 1


def diff_to_html(diff_result: DiffResult) -> str:
    """Convert a DiffResult to HTML for display.

    Args:
        diff_result: The diff result to render.

    Returns:
        HTML string with styled diff output.
    """
    if diff_result.error:
        return f'<div class="diff-error">{diff_result.error}</div>'

    if not diff_result.has_changes:
        return '<div class="diff-no-changes">No changes detected</div>'

    lines = ['<div class="diff-container">']

    if diff_result.is_new_file:
        lines.append('<div class="diff-header diff-new-file">New file</div>')
    elif diff_result.is_deleted:
        lines.append('<div class="diff-header diff-deleted-file">Deleted file</div>')

    for hunk in diff_result.hunks:
        lines.append('<div class="diff-hunk">')
        lines.append(
            f'<div class="diff-hunk-header">@@ -{hunk.old_start},{hunk.old_count} '
            f'+{hunk.new_start},{hunk.new_count} @@</div>'
        )

        for line_type, content in hunk.lines:
            if line_type == "+":
                css_class = "diff-added"
                prefix = "+"
            elif line_type == "-":
                css_class = "diff-removed"
                prefix = "-"
            else:
                css_class = "diff-context"
                prefix = " "

            # Escape HTML
            safe_content = (
                content.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            lines.append(
                f'<div class="diff-line {css_class}">'
                f'<span class="diff-prefix">{prefix}</span>'
                f'<span class="diff-content">{safe_content}</span>'
                f"</div>"
            )

        lines.append("</div>")  # .diff-hunk

    lines.append("</div>")  # .diff-container
    return "\n".join(lines)
