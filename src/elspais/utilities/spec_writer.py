# Implements: REQ-o00063-A, REQ-o00063-B, REQ-o00063-D
"""Spec file I/O — unified module for reading/writing spec files.

Consolidates all spec-file mutation helpers used by both the CLI
(``commands/edit.py``, ``commands/hash_cmd.py``) and the MCP server
(``mcp/server.py``).

Every file write uses ``encoding="utf-8"`` explicitly.

Public API
----------
- ``update_hash_in_file``  — update hash in a requirement's End marker
- ``add_status_to_file``   — add a missing Status field to metadata
- ``modify_implements``    — change the Implements field of a requirement
- ``modify_status``        — change the Status field of a requirement
- ``move_requirement``     — move a requirement between spec files
- ``change_reference_type``— change Implements/Refines in a spec file
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from elspais.utilities.hasher import HASH_VALUE_PATTERN
from elspais.utilities.patterns import BLANK_LINE_CLEANUP_RE
from elspais.utilities.patterns import find_req_header as _find_req_header

# ---------------------------------------------------------------------------
# Internal helpers for locating requirement blocks
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Hash / Status helpers (originally in mcp/file_mutations.py)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Implements / Status modification (originally in commands/edit.py)
# ---------------------------------------------------------------------------


def modify_implements(
    file_path: Path,
    req_id: str,
    new_implements: list[str],
    dry_run: bool = False,
) -> dict[str, Any]:
    """Modify the Implements field of a requirement.

    Args:
        file_path: Path to the spec file.
        req_id: Requirement ID to modify.
        new_implements: New list of implements references (empty = set to "-").
        dry_run: If True, don't actually modify the file.

    Returns:
        Dict with success, old_implements, new_implements, error.
    """
    from elspais.graph.parsers.requirement import RequirementParser

    content = file_path.read_text(encoding="utf-8")

    # Find the requirement header (any markdown header level)
    req_match = _find_req_header(content, req_id)

    if not req_match:
        return {"success": False, "error": f"Requirement {req_id} not found in {file_path}"}

    # Find the **Implements**: field after the header
    start_pos = req_match.end()
    search_region = content[start_pos : start_pos + 500]

    impl_match = RequirementParser.IMPLEMENTS_PATTERN.search(search_region)

    if not impl_match:
        return {"success": False, "error": f"Could not find **Implements** for {req_id}"}

    # Extract old value
    old_value = impl_match.group("implements").strip()
    old_implements = [v.strip() for v in old_value.split(",")] if old_value != "-" else []

    # Build new value
    if new_implements:
        new_value = ", ".join(new_implements)
    else:
        new_value = "-"

    # Calculate absolute positions using the named group bounds
    abs_start = start_pos + impl_match.start("implements")
    abs_end = start_pos + impl_match.end("implements")

    if old_value == new_value:
        return {
            "success": True,
            "old_implements": old_implements,
            "new_implements": new_implements,
            "no_change": True,
            "dry_run": dry_run,
        }

    # Apply change — replace just the implements value
    new_content = content[:abs_start] + new_value + content[abs_end:]

    if not dry_run:
        file_path.write_text(new_content, encoding="utf-8")

    return {
        "success": True,
        "old_implements": old_implements,
        "new_implements": new_implements,
        "dry_run": dry_run,
    }


def modify_status(
    file_path: Path,
    req_id: str,
    new_status: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Modify the Status field of a requirement.

    Args:
        file_path: Path to the spec file.
        req_id: Requirement ID to modify.
        new_status: New status value.
        dry_run: If True, don't actually modify the file.

    Returns:
        Dict with success, old_status, new_status, error.
    """
    from elspais.graph.parsers.requirement import RequirementParser

    content = file_path.read_text(encoding="utf-8")

    # Find the requirement header (any markdown header level)
    req_match = _find_req_header(content, req_id)

    if not req_match:
        return {"success": False, "error": f"Requirement {req_id} not found in {file_path}"}

    # Find the **Status**: field after the header
    start_pos = req_match.end()
    search_region = content[start_pos : start_pos + 500]

    status_match = RequirementParser.ALT_STATUS_PATTERN.search(search_region)

    if not status_match:
        return {"success": False, "error": f"Could not find **Status** for {req_id}"}

    old_status = status_match.group("status")

    if old_status == new_status:
        return {
            "success": True,
            "old_status": old_status,
            "new_status": new_status,
            "no_change": True,
            "dry_run": dry_run,
        }

    # Calculate absolute positions using the named group bounds
    abs_start = start_pos + status_match.start("status")
    abs_end = start_pos + status_match.end("status")

    # Apply change — replace just the status value
    new_content = content[:abs_start] + new_status + content[abs_end:]

    if not dry_run:
        file_path.write_text(new_content, encoding="utf-8")

    return {
        "success": True,
        "old_status": old_status,
        "new_status": new_status,
        "dry_run": dry_run,
    }


# ---------------------------------------------------------------------------
# Move requirement (consolidated from edit.py + server.py)
# ---------------------------------------------------------------------------


def move_requirement(
    source_file: Path,
    dest_file: Path,
    req_id: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Move a requirement from one file to another.

    Args:
        source_file: Source spec file.
        dest_file: Destination spec file.
        req_id: Requirement ID to move.
        dry_run: If True, don't actually modify files.

    Returns:
        Dict with success, source_file, dest_file, error.
    """
    source_content = source_file.read_text(encoding="utf-8")

    # Find the requirement block
    # Pattern: ## REQ-xxx: title ... *End* *title* | **Hash**: xxx\n---
    req_pattern = re.compile(
        rf"(^#+\s*{re.escape(req_id)}:[^\n]*\n" rf".*?" rf"\*End\*[^\n]*\n" rf"(?:---\n)?)",
        re.MULTILINE | re.DOTALL,
    )

    req_match = req_pattern.search(source_content)

    if not req_match:
        return {"success": False, "error": f"Requirement {req_id} not found in {source_file}"}

    req_block = req_match.group(0)

    # Ensure block ends with separator
    if not req_block.endswith("---\n"):
        req_block = req_block.rstrip() + "\n---\n"

    # Remove from source
    new_source_content = source_content[: req_match.start()] + source_content[req_match.end() :]
    # Clean up extra blank lines
    new_source_content = BLANK_LINE_CLEANUP_RE.sub("\n\n", new_source_content)

    # Add to destination
    dest_content = dest_file.read_text(encoding="utf-8") if dest_file.exists() else ""
    if dest_content and not dest_content.endswith("\n"):
        dest_content += "\n"
    if dest_content and not dest_content.endswith("\n\n"):
        dest_content += "\n"
    new_dest_content = dest_content + req_block

    # Check if source will be empty after move
    source_empty = len(new_source_content.strip()) == 0

    if not dry_run:
        source_file.write_text(new_source_content, encoding="utf-8")
        dest_file.write_text(new_dest_content, encoding="utf-8")

    return {
        "success": True,
        "source_file": str(source_file),
        "dest_file": str(dest_file),
        "source_empty": source_empty,
        "dry_run": dry_run,
    }


# ---------------------------------------------------------------------------
# Change reference type (originally in mcp/server.py)
# ---------------------------------------------------------------------------


def change_reference_type(
    file_path: Path,
    req_id: str,
    target_id: str,
    new_type: str,
) -> dict[str, Any]:
    """Change a reference type in a spec file (Implements -> Refines or vice versa).

    Args:
        file_path: Path to the spec file containing *req_id*.
        req_id: ID of the requirement to modify (for error messages).
        target_id: ID of the target requirement being referenced.
        new_type: New reference type ('IMPLEMENTS' or 'REFINES').

    Returns:
        Dict with success status and optional error.
    """
    # Normalize type
    new_type_lower = new_type.lower()
    if new_type_lower not in ("implements", "refines"):
        return {"success": False, "error": f"Invalid reference type: {new_type}"}

    content = file_path.read_text(encoding="utf-8")

    # Find and replace the reference pattern
    # Match patterns like: **Implements**: REQ-p00001 or **Refines**: REQ-p00001
    old_patterns = [
        f"**Implements**: {target_id}",
        f"**Refines**: {target_id}",
        f"Implements: {target_id}",
        f"Refines: {target_id}",
    ]

    # Capitalize for display
    new_type_display = new_type_lower.capitalize()
    new_text = f"**{new_type_display}**: {target_id}"

    modified = False
    for pattern in old_patterns:
        if pattern in content:
            content = content.replace(pattern, new_text)
            modified = True
            break

    if not modified:
        return {"success": False, "error": f"Reference to {target_id} not found in {req_id}"}

    # Write the modified content
    file_path.write_text(content, encoding="utf-8")

    return {"success": True}
