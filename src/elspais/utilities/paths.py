"""Path manipulation utilities.

Centralizes path-string operations that have been inlined across the
codebase. Keep this module dependency-free and side-effect-free.
"""

# Implements: REQ-d00129-D
from __future__ import annotations

from pathlib import Path


def normalize_relative_path(p: str | Path) -> str:
    """Return ``p`` as a forward-slash-separated string.

    Used wherever stored relative paths must be compared or rendered in a
    platform-independent way. Backslashes from Windows-style inputs are
    rewritten to forward slashes; otherwise the string passes through.
    """
    return str(p).replace("\\", "/")
