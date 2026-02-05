# Implements: REQ-o00063-A, REQ-o00063-B, REQ-o00063-D
"""File mutation helpers for CLI commands.

Provides functions to safely modify spec files on disk:
- update_hash_in_file: Update the hash in a requirement's End marker
- add_status_to_file: Add a missing Status field to metadata
"""

from __future__ import annotations

import re
from pathlib import Path

from elspais.utilities.hasher import HASH_VALUE_PATTERN
from elspais.utilities.patterns import find_req_header as _find_req_header

# --- Shared helpers for locating requirement blocks in spec files ---


def _find_end_marker(content: str, start_pos: int) -> re.Match | None:
    """Find an End marker with **Hash** after the given position.

    Matches: *End* *Title* | **Hash**: <any-value>
    Group 1 = prefix (everything before hash value)
    Group 2 = hash value
    """
    pattern = re.compile(rf"(\*End\*\s+\*.+?\*\s*\|\s*\*\*Hash\*\*:\s*)({HASH_VALUE_PATTERN})")
    return pattern.search(content, pos=start_pos)


def _find_next_req_header(content: str, start_pos: int) -> re.Match | None:
    """Find the next requirement header after the given position."""
    pattern = re.compile(r"^#+ [A-Z]+-", re.MULTILINE)
    return pattern.search(content, pos=start_pos)


# --- Public API ---


def update_hash_in_file(
    file_path: Path,
    req_id: str,
    new_hash: str,
) -> str | None:
    """Update the hash in a spec file for a requirement.

    Finds the end marker line: *End* *Title* | **Hash**: old_hash
    And updates to: *End* *Title* | **Hash**: new_hash

    Args:
        file_path: Path to the spec file.
        req_id: The requirement ID (e.g., 'REQ-p00001').
        new_hash: The new hash value to set.

    Returns:
        None if the hash was updated successfully.
        A descriptive error string if the update failed.
    """
    file_path = Path(file_path)
    content = file_path.read_text(encoding="utf-8")

    header_match = _find_req_header(content, req_id)
    if not header_match:
        return f"Header for {req_id} not found in {file_path.name}"

    start_pos = header_match.end()

    end_match = _find_end_marker(content, start_pos)
    if not end_match:
        return f"No End marker with **Hash** found for {req_id} in {file_path.name}"

    next_header_match = _find_next_req_header(content, start_pos)
    if next_header_match and next_header_match.start() < end_match.start():
        return f"End marker for {req_id} belongs to a different requirement in {file_path.name}"

    # Replace just the hash value
    new_content = content[: end_match.start(2)] + new_hash + content[end_match.end(2) :]

    file_path.write_text(new_content, encoding="utf-8")
    return None


def add_status_to_file(
    file_path: Path,
    req_id: str,
    status: str,
) -> str | None:
    """Add a Status field to a requirement's metadata line.

    Finds the metadata line: **Level**: XXX | **Implements**: YYY
    And adds Status: **Level**: XXX | **Status**: ZZZ | **Implements**: YYY

    Args:
        file_path: Path to the spec file.
        req_id: The requirement ID (e.g., 'REQ-p00001').
        status: The status value to add (e.g., 'Active').

    Returns:
        None if status was added successfully.
        A descriptive error string if the update failed.
    """
    file_path = Path(file_path)
    content = file_path.read_text(encoding="utf-8")

    header_match = _find_req_header(content, req_id)
    if not header_match:
        return f"Header for {req_id} not found in {file_path.name}"

    start_pos = header_match.end()

    next_header_match = _find_next_req_header(content, start_pos)
    end_pos = next_header_match.start() if next_header_match else len(content)

    # Search for metadata line within this requirement block
    block = content[start_pos:end_pos]

    # Check if status already exists
    if re.search(r"\*\*Status\*\*:", block):
        return f"{req_id} already has a Status field in {file_path.name}"

    # Find the Level line: **Level**: XXX | ...
    level_pattern = re.compile(
        r"(\*\*Level\*\*:\s*\w+)(\s*\|)",
    )
    level_match = level_pattern.search(block)
    if not level_match:
        return f"No **Level** metadata line found for {req_id} in {file_path.name}"

    # Insert status after Level
    new_block = (
        block[: level_match.end(1)] + f" | **Status**: {status}" + block[level_match.start(2) :]
    )

    # Rebuild the full content
    new_content = content[:start_pos] + new_block + content[end_pos:]

    file_path.write_text(new_content, encoding="utf-8")
    return None
