"""File mutation helpers for CLI commands.

Provides functions to safely modify spec files on disk:
- update_hash_in_file: Update the hash in a requirement's End marker
- add_status_to_file: Add a missing Status field to metadata
"""

from __future__ import annotations

import re
from pathlib import Path


def update_hash_in_file(
    file_path: Path,
    req_id: str,
    new_hash: str,
) -> bool:
    """Update the hash in a spec file for a requirement.

    Finds the end marker line: *End* *Title* | **Hash**: old_hash
    And updates to: *End* *Title* | **Hash**: new_hash

    Args:
        file_path: Path to the spec file.
        req_id: The requirement ID (e.g., 'REQ-p00001').
        new_hash: The new hash value to set.

    Returns:
        True if the hash was updated, False if the requirement was not found.
    """
    file_path = Path(file_path)
    content = file_path.read_text(encoding="utf-8")

    # Find the requirement block to locate its End marker
    # First find the header line: ## REQ-xxx: Title
    header_pattern = re.compile(
        rf"^(#+ {re.escape(req_id)}:\s*(.+?)\s*)$",
        re.MULTILINE,
    )
    header_match = header_pattern.search(content)
    if not header_match:
        return False

    # Now find the End marker after this header
    # Pattern: *End* *Title* | **Hash**: xxxxxxxx
    # The title in the End marker should match the requirement's title
    start_pos = header_match.end()

    # Look for the End marker pattern anywhere after the header
    # It can have various title formats, so we just look for *End* ... **Hash**:
    end_pattern = re.compile(
        r"(\*End\*\s+\*.+?\*\s*\|\s*\*\*Hash\*\*:\s*)([a-fA-F0-9_]+)",
    )

    # Search from the header position
    end_match = end_pattern.search(content, pos=start_pos)
    if not end_match:
        return False

    # Check if this End marker is still part of our requirement block
    # (i.e., no new requirement header between our header and this End marker)
    next_header_pattern = re.compile(r"^#+ [A-Z]+-", re.MULTILINE)
    next_header_match = next_header_pattern.search(content, pos=start_pos)

    if next_header_match and next_header_match.start() < end_match.start():
        # This End marker belongs to a different requirement
        return False

    # Replace just the hash value
    new_content = content[: end_match.start(2)] + new_hash + content[end_match.end(2) :]

    file_path.write_text(new_content, encoding="utf-8")
    return True


def add_status_to_file(
    file_path: Path,
    req_id: str,
    status: str,
) -> bool:
    """Add a Status field to a requirement's metadata line.

    Finds the metadata line: **Level**: XXX | **Implements**: YYY
    And adds Status: **Level**: XXX | **Status**: ZZZ | **Implements**: YYY

    Args:
        file_path: Path to the spec file.
        req_id: The requirement ID (e.g., 'REQ-p00001').
        status: The status value to add (e.g., 'Active').

    Returns:
        True if status was added, False if req not found or already has status.
    """
    file_path = Path(file_path)
    content = file_path.read_text(encoding="utf-8")

    # Find the requirement header
    header_pattern = re.compile(
        rf"^(#+ {re.escape(req_id)}:\s*.+?)$",
        re.MULTILINE,
    )
    header_match = header_pattern.search(content)
    if not header_match:
        return False

    start_pos = header_match.end()

    # Find the next requirement header or end of file to bound our search
    next_header_pattern = re.compile(r"^#+ [A-Z]+-", re.MULTILINE)
    next_header_match = next_header_pattern.search(content, pos=start_pos)
    end_pos = next_header_match.start() if next_header_match else len(content)

    # Search for metadata line within this requirement block
    block = content[start_pos:end_pos]

    # Check if status already exists
    if re.search(r"\*\*Status\*\*:", block):
        return False

    # Find the Level line: **Level**: XXX | ...
    level_pattern = re.compile(
        r"(\*\*Level\*\*:\s*\w+)(\s*\|)",
    )
    level_match = level_pattern.search(block)
    if not level_match:
        return False

    # Insert status after Level
    new_block = (
        block[: level_match.end(1)] + f" | **Status**: {status}" + block[level_match.start(2) :]
    )

    # Rebuild the full content
    new_content = content[:start_pos] + new_block + content[end_pos:]

    file_path.write_text(new_content, encoding="utf-8")
    return True
