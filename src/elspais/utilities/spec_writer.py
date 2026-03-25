# Implements: REQ-o00063-A, REQ-o00063-B, REQ-o00063-D, REQ-o00063-G, REQ-o00063-H, REQ-o00063-I
"""Spec file I/O — unified module for reading/writing spec files.

Consolidates all spec-file mutation helpers used by both the CLI
(``commands/edit.py``, ``commands/fix_cmd.py``) and the MCP server
(``mcp/server.py``).

Every file write uses ``encoding="utf-8"`` explicitly.

Public API
----------
- ``update_hash_in_file``      — update hash in a requirement's End marker
- ``add_status_to_file``       — add a missing Status field to metadata
- ``modify_implements``        — change the Implements field of a requirement
- ``modify_refines``           — change the Refines field of a requirement
- ``modify_status``            — change the Status field of a requirement
- ``modify_title``             — change the title of a requirement
- ``modify_assertion_text``    — change an assertion's text in a requirement
- ``add_assertion_to_file``    — add a new assertion to a requirement
- ``delete_assertion_from_file`` — remove an assertion from a requirement
- ``rename_assertion_in_file``  — rename an assertion label in a requirement
- ``move_requirement``         — move a requirement between spec files
- ``change_reference_type``    — change Implements/Refines in a spec file
- ``fix_reference_in_file``    — redirect a broken reference to a new target
- ``rename_requirement_id``    — rename a requirement ID in its header
- ``rename_references_in_file`` — update all references to an old ID in a file
- ``add_requirement_to_file``  — add a new requirement block to a spec file
- ``delete_requirement_from_file`` — remove a requirement block from a spec file
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


def _extract_prefix(req_id: str) -> str:
    """Extract the ID prefix from a requirement ID (e.g., 'REQ' from 'REQ-p00001')."""
    dash = req_id.find("-")
    return req_id[:dash] if dash > 0 else ""


def _find_end_marker(content: str, start_pos: int) -> re.Match | None:
    """Find an End marker with **Hash** after the given position.

    Matches: *End* *Title* | **Hash**: <any-value>
    Group 1 = prefix (everything before hash value)
    Group 2 = hash value
    """
    pattern = re.compile(rf"(\*End\*\s+\*.+?\*\s*\|\s*\*\*Hash\*\*:\s*)({HASH_VALUE_PATTERN})")
    return pattern.search(content, pos=start_pos)


def _find_next_req_header(content: str, start_pos: int, prefix: str) -> re.Match | None:
    """Find the next requirement header after the given position.

    Args:
        content: File content to search.
        start_pos: Position to start searching from.
        prefix: Requirement ID prefix (e.g., 'REQ'). Only matches headings
            starting with this prefix followed by a dash.
    """
    pattern = re.compile(rf"^#+ {re.escape(prefix)}-", re.MULTILINE)
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

    next_header_match = _find_next_req_header(content, start_pos, _extract_prefix(req_id))
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

    next_header_match = _find_next_req_header(content, start_pos, _extract_prefix(req_id))
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
    from elspais.graph.parsers.patterns import IMPLEMENTS_PATTERN

    content = file_path.read_text(encoding="utf-8")

    # Find the requirement header (any markdown header level)
    req_match = _find_req_header(content, req_id)

    if not req_match:
        return {"success": False, "error": f"Requirement {req_id} not found in {file_path}"}

    # Find the **Implements**: field after the header
    start_pos = req_match.end()
    search_region = content[start_pos : start_pos + 500]

    impl_match = IMPLEMENTS_PATTERN.search(search_region)

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


def modify_refines(
    file_path: Path,
    req_id: str,
    new_refines: list[str],
    dry_run: bool = False,
) -> dict[str, Any]:
    """Modify the Refines field of a requirement.

    If the field does not exist yet and new_refines is non-empty, inserts
    ``| **Refines**: ...`` into the metadata line.  If it exists and
    new_refines is empty, sets the value to ``-``.

    Args:
        file_path: Path to the spec file.
        req_id: Requirement ID to modify.
        new_refines: New list of refines references (empty = set to "-").
        dry_run: If True, don't actually modify the file.

    Returns:
        Dict with success, old_refines, new_refines, error.
    """
    from elspais.graph.parsers.patterns import REFINES_PATTERN

    content = file_path.read_text(encoding="utf-8")

    # Find the requirement header (any markdown header level)
    req_match = _find_req_header(content, req_id)

    if not req_match:
        return {"success": False, "error": f"Requirement {req_id} not found in {file_path}"}

    # Find the **Refines**: field after the header
    start_pos = req_match.end()
    search_region = content[start_pos : start_pos + 500]

    refines_match = REFINES_PATTERN.search(search_region)

    if refines_match:
        # Field exists — surgical replacement (same approach as modify_implements)
        old_value = refines_match.group("refines").strip()
        old_refines = [v.strip() for v in old_value.split(",")] if old_value != "-" else []

        new_value = ", ".join(new_refines) if new_refines else "-"

        abs_start = start_pos + refines_match.start("refines")
        abs_end = start_pos + refines_match.end("refines")

        if old_value == new_value:
            return {
                "success": True,
                "old_refines": old_refines,
                "new_refines": new_refines,
                "no_change": True,
                "dry_run": dry_run,
            }

        new_content = content[:abs_start] + new_value + content[abs_end:]
    else:
        # Field does not exist — need to insert it or treat as no-op
        old_refines = []

        if not new_refines:
            return {
                "success": True,
                "old_refines": [],
                "new_refines": [],
                "no_change": True,
                "dry_run": dry_run,
            }

        # Insert | **Refines**: value into the metadata line.
        # Find the metadata line (the line containing **Level**: after the header).
        meta_pattern = re.compile(r"^(\*\*Level\*\*:.+)$", re.MULTILINE)
        meta_match = meta_pattern.search(search_region)
        if not meta_match:
            return {
                "success": False,
                "error": f"Could not find metadata line for {req_id} to insert **Refines**",
            }

        new_value = ", ".join(new_refines)
        insert_text = f" | **Refines**: {new_value}"

        # Insert at end of the metadata line
        abs_insert = start_pos + meta_match.end(1)
        new_content = content[:abs_insert] + insert_text + content[abs_insert:]

    if not dry_run:
        file_path.write_text(new_content, encoding="utf-8")

    return {
        "success": True,
        "old_refines": old_refines,
        "new_refines": new_refines,
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
    from elspais.graph.parsers.patterns import ALT_STATUS_PATTERN

    content = file_path.read_text(encoding="utf-8")

    # Find the requirement header (any markdown header level)
    req_match = _find_req_header(content, req_id)

    if not req_match:
        return {"success": False, "error": f"Requirement {req_id} not found in {file_path}"}

    # Find the **Status**: field after the header
    start_pos = req_match.end()
    search_region = content[start_pos : start_pos + 500]

    status_match = ALT_STATUS_PATTERN.search(search_region)

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
# Title / assertion mutations (Phase 1: trace-edit)
# ---------------------------------------------------------------------------


def modify_title(
    file_path: Path,
    req_id: str,
    new_title: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Modify the title of a requirement.

    Finds the header line ``## REQ-xxx: Old Title`` and replaces the title
    portion while preserving the heading level and ID.

    Args:
        file_path: Path to the spec file.
        req_id: Requirement ID to modify.
        new_title: New title text.
        dry_run: If True, don't actually modify the file.

    Returns:
        Dict with success, old_title, new_title, dry_run, error.
    """
    content = file_path.read_text(encoding="utf-8")

    # Find the requirement header (any markdown header level)
    req_match = _find_req_header(content, req_id)

    if not req_match:
        return {"success": False, "error": f"Requirement {req_id} not found in {file_path}"}

    # Group 2 of _find_req_header is the title text
    old_title = req_match.group(2)

    if old_title == new_title:
        return {
            "success": True,
            "old_title": old_title,
            "new_title": new_title,
            "no_change": True,
            "dry_run": dry_run,
        }

    # Calculate absolute positions for group 2 (the title)
    abs_start = req_match.start(2)
    abs_end = req_match.end(2)

    # Apply change — replace just the title text
    new_content = content[:abs_start] + new_title + content[abs_end:]

    if not dry_run:
        file_path.write_text(new_content, encoding="utf-8")

    return {
        "success": True,
        "old_title": old_title,
        "new_title": new_title,
        "dry_run": dry_run,
    }


def modify_assertion_text(
    file_path: Path,
    req_id: str,
    label: str,
    new_text: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Modify an assertion's text within a requirement block.

    Finds the assertion line ``{label}. old text`` within the requirement
    and replaces the text portion.  Handles multi-line assertions where
    continuation lines are indented.

    Args:
        file_path: Path to the spec file.
        req_id: Requirement ID containing the assertion.
        label: Assertion label (e.g., 'A', 'B').
        new_text: New assertion text.
        dry_run: If True, don't actually modify the file.

    Returns:
        Dict with success, old_text, new_text, dry_run, error.
    """
    content = file_path.read_text(encoding="utf-8")

    # Find the requirement header
    req_match = _find_req_header(content, req_id)
    if not req_match:
        return {"success": False, "error": f"Requirement {req_id} not found in {file_path}"}

    start_pos = req_match.end()

    # Find the end of this requirement block
    next_header = _find_next_req_header(content, start_pos, _extract_prefix(req_id))
    end_pos = next_header.start() if next_header else len(content)

    block = content[start_pos:end_pos]

    # Find the assertion line within this block.
    # Pattern: start-of-line, optional whitespace, label, dot, space(s), text
    assertion_pattern = re.compile(
        rf"^(\s*{re.escape(label)}\.\s+)(.+)$",
        re.MULTILINE,
    )
    assertion_match = assertion_pattern.search(block)

    if not assertion_match:
        return {
            "success": False,
            "error": f"Assertion {label} not found in {req_id}",
        }

    # The text starts at group(2). We need to capture multi-line continuation
    # lines (indented lines that follow the assertion line).
    text_start = assertion_match.start(2)
    text_end = assertion_match.end(2)

    # Check for continuation lines: lines that start with whitespace and are
    # NOT a new assertion label or section boundary.
    # remaining starts with "\n..." because the regex match ends at end-of-line
    # before the newline character.  We split on "\n" and skip the first
    # empty element (the content before the first newline).
    remaining = block[assertion_match.end() :]
    continuation_pattern = re.compile(
        r"^(?P<cont>\s+\S.*)$",
        re.MULTILINE,
    )
    # A new assertion, section header, End marker, or blank line ends continuation
    boundary_pattern = re.compile(
        r"^(\s*[A-Z0-9]+\.\s|##\s|\*End\*|\s*$)",
        re.MULTILINE,
    )

    lines_after = remaining.split("\n")
    # Skip the first element — it is always empty (text before first \n)
    for line in lines_after[1:]:
        if not line:
            # Blank line ends continuation
            break
        if boundary_pattern.match(line) and not continuation_pattern.match(line):
            break
        cont_match = continuation_pattern.match(line)
        if cont_match:
            # +1 for the newline character between lines
            text_end += 1 + len(line)
        else:
            break

    old_text = block[text_start:text_end]

    if old_text == new_text:
        return {
            "success": True,
            "old_text": old_text,
            "new_text": new_text,
            "no_change": True,
            "dry_run": dry_run,
        }

    # Calculate absolute positions in the full content
    abs_text_start = start_pos + text_start
    abs_text_end = start_pos + text_end

    new_content = content[:abs_text_start] + new_text + content[abs_text_end:]

    if not dry_run:
        file_path.write_text(new_content, encoding="utf-8")

    return {
        "success": True,
        "old_text": old_text,
        "new_text": new_text,
        "dry_run": dry_run,
    }


def add_assertion_to_file(
    file_path: Path,
    req_id: str,
    label: str,
    text: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Add a new assertion to a requirement's Assertions section.

    Finds the ``## Assertions`` section within the requirement and inserts
    the new assertion after the last existing assertion line, maintaining
    consistent formatting.

    Args:
        file_path: Path to the spec file.
        req_id: Requirement ID to add the assertion to.
        label: Assertion label (e.g., 'G', 'H').
        text: Assertion text (the SHALL statement).
        dry_run: If True, don't actually modify the file.

    Returns:
        Dict with success, label, dry_run, error.
    """
    content = file_path.read_text(encoding="utf-8")

    # Find the requirement header
    req_match = _find_req_header(content, req_id)
    if not req_match:
        return {"success": False, "error": f"Requirement {req_id} not found in {file_path}"}

    start_pos = req_match.end()

    # Find the end of this requirement block
    next_header = _find_next_req_header(content, start_pos, _extract_prefix(req_id))
    end_pos = next_header.start() if next_header else len(content)

    block = content[start_pos:end_pos]

    # Find the ## Assertions section header
    assertions_header = re.compile(r"^##\s+Assertions\s*$", re.MULTILINE)
    header_match = assertions_header.search(block)
    if not header_match:
        return {
            "success": False,
            "error": f"No ## Assertions section found in {req_id}",
        }

    # Find existing assertion lines within this block (after the Assertions header)
    assertions_start = header_match.end()
    assertion_line_pattern = re.compile(r"^\s*[A-Z0-9]+\.\s+.+$", re.MULTILINE)

    # Find the last assertion line within this block
    last_assertion_end = None
    for m in assertion_line_pattern.finditer(block, assertions_start):
        # Check for multi-line continuations after this assertion
        candidate_end = m.end()
        remaining_after = block[candidate_end:]
        lines_after = remaining_after.split("\n")
        # Skip first element — empty string before the first \n
        for line in lines_after[1:]:
            if not line:
                break
            # Continuation lines: start with whitespace, contain non-space content
            if re.match(r"^\s+\S", line):
                candidate_end += 1 + len(line)
            else:
                break
        last_assertion_end = candidate_end

    if last_assertion_end is None:
        # No existing assertions — insert right after the Assertions header
        # with a blank line in between
        insert_pos = start_pos + assertions_start
        new_line = f"\n{label}. {text}"
    else:
        insert_pos = start_pos + last_assertion_end
        new_line = f"\n{label}. {text}"

    new_content = content[:insert_pos] + new_line + content[insert_pos:]

    if not dry_run:
        file_path.write_text(new_content, encoding="utf-8")

    return {
        "success": True,
        "label": label,
        "dry_run": dry_run,
    }


def delete_assertion_from_file(
    file_path: Path,
    req_id: str,
    label: str,
    renames: list[dict[str, str]] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Delete an assertion from a requirement's Assertions section.

    Removes the assertion line for ``label`` (including multi-line
    continuations).  When ``renames`` is provided, subsequent assertions
    are relabeled to compact the sequence (e.g., after deleting B,
    C→B, D→C).

    Args:
        file_path: Path to the spec file.
        req_id: Requirement ID containing the assertion.
        label: Assertion label to delete (e.g., 'B').
        renames: Optional list of ``{"old_label": "C", "new_label": "B"}``
            dicts describing compaction renames to apply after deletion.
        dry_run: If True, don't actually modify the file.

    Returns:
        Dict with success, deleted_label, dry_run, error.
    """
    content = file_path.read_text(encoding="utf-8")

    req_match = _find_req_header(content, req_id)
    if not req_match:
        return {"success": False, "error": f"Requirement {req_id} not found in {file_path}"}

    start_pos = req_match.end()
    next_header = _find_next_req_header(content, start_pos, _extract_prefix(req_id))
    end_pos = next_header.start() if next_header else len(content)

    block = content[start_pos:end_pos]

    # Find the assertion line
    assertion_pattern = re.compile(
        rf"^(\s*{re.escape(label)}\.\s+.+)$",
        re.MULTILINE,
    )
    assertion_match = assertion_pattern.search(block)
    if not assertion_match:
        return {"success": False, "error": f"Assertion {label} not found in {req_id}"}

    # Calculate the full extent including continuation lines
    line_start = assertion_match.start()
    line_end = assertion_match.end()

    remaining = block[line_end:]
    for line in remaining.split("\n")[1:]:
        if not line:
            break
        if re.match(r"^\s+\S", line):
            line_end += 1 + len(line)
        else:
            break

    # Include the preceding newline if present (to avoid blank line gaps)
    abs_line_start = start_pos + line_start
    abs_line_end = start_pos + line_end
    if abs_line_start > 0 and content[abs_line_start - 1] == "\n":
        abs_line_start -= 1

    new_content = content[:abs_line_start] + content[abs_line_end:]

    # Apply compaction renames if provided
    if renames:
        for rename in renames:
            old_lbl = rename.get("old_label", "")
            new_lbl = rename.get("new_label", "")
            if old_lbl and new_lbl:
                # Replace "{old_label}. " with "{new_label}. " within the req block
                rename_pattern = re.compile(
                    rf"^(\s*){re.escape(old_lbl)}(\.\s+)",
                    re.MULTILINE,
                )
                new_content = rename_pattern.sub(rf"\g<1>{new_lbl}\2", new_content, count=1)

    if not dry_run:
        file_path.write_text(new_content, encoding="utf-8")

    return {
        "success": True,
        "deleted_label": label,
        "dry_run": dry_run,
    }


def rename_assertion_in_file(
    file_path: Path,
    req_id: str,
    old_label: str,
    new_label: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Rename an assertion label within a requirement block.

    Changes ``{old_label}. text`` to ``{new_label}. text``.

    Args:
        file_path: Path to the spec file.
        req_id: Requirement ID containing the assertion.
        old_label: Current assertion label (e.g., 'A').
        new_label: New assertion label (e.g., 'D').
        dry_run: If True, don't actually modify the file.

    Returns:
        Dict with success, old_label, new_label, dry_run, error.
    """
    content = file_path.read_text(encoding="utf-8")

    req_match = _find_req_header(content, req_id)
    if not req_match:
        return {"success": False, "error": f"Requirement {req_id} not found in {file_path}"}

    start_pos = req_match.end()
    next_header = _find_next_req_header(content, start_pos, _extract_prefix(req_id))
    end_pos = next_header.start() if next_header else len(content)

    block = content[start_pos:end_pos]

    # Find the assertion line
    assertion_pattern = re.compile(
        rf"^(\s*){re.escape(old_label)}(\.\s+.+)$",
        re.MULTILINE,
    )
    assertion_match = assertion_pattern.search(block)
    if not assertion_match:
        return {"success": False, "error": f"Assertion {old_label} not found in {req_id}"}

    if old_label == new_label:
        return {
            "success": True,
            "old_label": old_label,
            "new_label": new_label,
            "no_change": True,
            "dry_run": dry_run,
        }

    # Replace just the label portion
    abs_label_start = start_pos + assertion_match.start() + len(assertion_match.group(1))
    abs_label_end = abs_label_start + len(old_label)

    new_content = content[:abs_label_start] + new_label + content[abs_label_end:]

    if not dry_run:
        file_path.write_text(new_content, encoding="utf-8")

    return {
        "success": True,
        "old_label": old_label,
        "new_label": new_label,
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
        rf"(^#+\s*{re.escape(req_id)}:[^\n]*\n" rf".*?" rf"^\*End\*[^\n]*\n" rf"(?:---\n)?)",
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


# ---------------------------------------------------------------------------
# Changelog entry helpers
# ---------------------------------------------------------------------------


def _format_changelog_entry(entry: dict[str, str]) -> str:
    """Format a changelog entry dict into a markdown line."""
    return (
        f"- {entry['date']} | {entry['hash']} | {entry['change_order']}"
        f" | {entry['author_name']} ({entry['author_id']}) | {entry['reason']}"
    )


def add_changelog_entry(
    file_path: Path,
    req_id: str,
    entry: dict[str, str],
) -> str | None:
    """Add a changelog entry to a requirement in a spec file.

    If a ## Changelog section exists, inserts the new entry at the top.
    If no ## Changelog section exists, creates one before the End marker.

    Args:
        file_path: Path to the spec file.
        req_id: The requirement ID (e.g., 'REQ-p00001').
        entry: Dict with keys: date, hash, change_order,
               author_name, author_id, reason.

    Returns:
        None on success, error string on failure.
    """
    file_path = Path(file_path)
    content = file_path.read_text(encoding="utf-8")

    header_match = _find_req_header(content, req_id)
    if not header_match:
        return f"Header for {req_id} not found in {file_path.name}"

    start_pos = header_match.end()

    end_match = _find_end_marker(content, start_pos)
    if not end_match:
        return f"No End marker found for {req_id} in {file_path.name}"

    entry_line = _format_changelog_entry(entry)

    # Look for existing ## Changelog section between header and end marker
    req_block = content[start_pos : end_match.start()]
    changelog_match = re.search(r"^## Changelog\s*$", req_block, re.MULTILINE)

    if changelog_match:
        # Insert after the ## Changelog heading (+ blank line)
        insert_pos = start_pos + changelog_match.end()
        # Find the first non-blank line after the heading
        after_heading = content[insert_pos:]
        # Skip blank lines after heading
        leading_blank = re.match(r"\n*", after_heading)
        skip = leading_blank.end() if leading_blank else 0
        insert_pos += skip
        new_content = content[:insert_pos] + entry_line + "\n" + content[insert_pos:]
    else:
        # Create ## Changelog section before End marker
        insert_pos = end_match.start()
        # Ensure proper spacing
        section = f"\n## Changelog\n\n{entry_line}\n\n"
        new_content = content[:insert_pos] + section + content[insert_pos:]

    file_path.write_text(new_content, encoding="utf-8")
    return None


def fix_reference_in_file(
    file_path: Path,
    req_id: str,
    old_target_id: str,
    new_target_id: str,
) -> dict[str, Any]:
    """Redirect a broken reference in a requirement's metadata.

    Replaces ``old_target_id`` with ``new_target_id`` within the
    ``**Implements**:`` or ``**Refines**:`` fields of the given
    requirement block.

    Args:
        file_path: Path to the spec file.
        req_id: Requirement ID containing the broken reference.
        old_target_id: The current (broken) target ID.
        new_target_id: The new target ID to point to.

    Returns:
        Dict with success, error.
    """
    content = file_path.read_text(encoding="utf-8")

    req_match = _find_req_header(content, req_id)
    if not req_match:
        return {"success": False, "error": f"Requirement {req_id} not found in {file_path}"}

    start_pos = req_match.end()
    next_header = _find_next_req_header(content, start_pos, _extract_prefix(req_id))
    end_pos = next_header.start() if next_header else len(content)

    block = content[start_pos:end_pos]

    if old_target_id not in block:
        return {
            "success": False,
            "error": f"Reference to {old_target_id} not found in {req_id}",
        }

    new_block = block.replace(old_target_id, new_target_id)
    new_content = content[:start_pos] + new_block + content[end_pos:]

    file_path.write_text(new_content, encoding="utf-8")

    return {"success": True}


def rename_requirement_id(
    file_path: Path,
    old_id: str,
    new_id: str,
) -> dict[str, Any]:
    """Rename a requirement ID in its header line.

    Changes ``## OLD_ID: Title`` to ``## NEW_ID: Title``.

    Args:
        file_path: Path to the spec file.
        old_id: Current requirement ID.
        new_id: New requirement ID.

    Returns:
        Dict with success, error.
    """
    content = file_path.read_text(encoding="utf-8")

    # Match the heading with the ID as a captured group
    pattern = re.compile(
        rf"^(#+\s+)({re.escape(old_id)})(:\s*.+)$",
        re.MULTILINE,
    )
    match = pattern.search(content)
    if not match:
        return {"success": False, "error": f"Requirement {old_id} not found in {file_path}"}

    # Replace just the ID portion (group 2)
    abs_start = match.start(2)
    abs_end = match.end(2)

    new_content = content[:abs_start] + new_id + content[abs_end:]

    file_path.write_text(new_content, encoding="utf-8")

    return {"success": True}


def rename_references_in_file(
    file_path: Path,
    old_id: str,
    new_id: str,
) -> dict[str, Any]:
    """Replace all references to an old requirement ID within a file.

    Scans the ``**Implements**:``, ``**Refines**:``, and
    ``**Satisfies**:`` fields for ``old_id`` and replaces with
    ``new_id``.  Uses a global replace within those metadata values
    since requirement IDs are fixed-width and don't appear as
    substrings of each other.

    Args:
        file_path: Path to the spec file.
        old_id: The old requirement ID to find.
        new_id: The new requirement ID to substitute.

    Returns:
        Dict with success, count (number of replacements), error.
    """
    content = file_path.read_text(encoding="utf-8")

    if old_id not in content:
        return {"success": True, "count": 0, "no_change": True}

    new_content = content.replace(old_id, new_id)
    count = content.count(old_id)

    file_path.write_text(new_content, encoding="utf-8")

    return {"success": True, "count": count}


def add_requirement_to_file(
    file_path: Path,
    req_id: str,
    title: str,
    level: str,
    status: str = "Draft",
    implements_list: list[str] | None = None,
    hash_value: str = "00000000",
) -> dict[str, Any]:
    """Append a new requirement block to a spec file.

    Creates a complete requirement block with metadata, empty
    Assertions section, and End marker, then appends it to the file.

    Args:
        file_path: Path to the spec file.
        req_id: Requirement ID (e.g., 'REQ-d00099').
        title: Requirement title text.
        level: Requirement level (e.g., 'DEV', 'OPS', 'PRD').
        status: Requirement status (default 'Draft').
        implements_list: Optional list of implements references.
        hash_value: Initial hash value.

    Returns:
        Dict with success, error.
    """
    impl_str = ", ".join(implements_list) if implements_list else "-"

    block = (
        f"\n## {req_id}: {title}\n"
        f"\n"
        f"**Level**: {level} | **Status**: {status} | **Implements**: {impl_str}\n"
        f"\n"
        f"## Assertions\n"
        f"\n"
        f"*End* *{title}* | **Hash**: {hash_value}\n"
        f"---\n"
    )

    if file_path.exists():
        content = file_path.read_text(encoding="utf-8")
        # Ensure a blank line before the new block
        if content and not content.endswith("\n\n"):
            if not content.endswith("\n"):
                content += "\n"
        new_content = content + block
    else:
        new_content = block.lstrip("\n")

    file_path.write_text(new_content, encoding="utf-8")

    return {"success": True}


def delete_requirement_from_file(
    file_path: Path,
    req_id: str,
) -> dict[str, Any]:
    """Remove a requirement block from a spec file.

    Finds the block from ``## REQ-xxx: Title`` through
    ``*End* *Title* | **Hash**: ...`` (and optional ``---`` separator)
    and removes it.

    Args:
        file_path: Path to the spec file.
        req_id: Requirement ID to remove.

    Returns:
        Dict with success, error.
    """
    content = file_path.read_text(encoding="utf-8")

    # Reuse the same pattern from move_requirement
    req_pattern = re.compile(
        rf"(^#+\s*{re.escape(req_id)}:[^\n]*\n" rf".*?" rf"^\*End\*[^\n]*\n" rf"(?:---\n)?)",
        re.MULTILINE | re.DOTALL,
    )

    req_match = req_pattern.search(content)
    if not req_match:
        return {"success": False, "error": f"Requirement {req_id} not found in {file_path}"}

    # Remove the block
    new_content = content[: req_match.start()] + content[req_match.end() :]

    # Clean up multiple blank lines
    new_content = BLANK_LINE_CLEANUP_RE.sub("\n\n", new_content)

    file_path.write_text(new_content, encoding="utf-8")

    return {"success": True}
