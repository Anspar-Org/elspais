"""
elspais.commands.edit - Edit requirements command.

Provides functionality to modify requirements in-place:
- Change Implements references
- Change Status
- Move requirements between files
- Batch operations via JSON
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


def run(args: argparse.Namespace) -> int:
    """Run the edit command."""
    from elspais.config.defaults import DEFAULT_CONFIG
    from elspais.config.loader import find_config_file, get_spec_directories, load_config

    # Load configuration
    config_path = args.config if hasattr(args, 'config') else None
    if config_path is None:
        config_path = find_config_file(Path.cwd())
    if config_path and config_path.exists():
        config = load_config(config_path)
    else:
        config = DEFAULT_CONFIG

    # Get spec directories
    spec_dir = args.spec_dir if hasattr(args, 'spec_dir') and args.spec_dir else None
    spec_dirs = get_spec_directories(spec_dir, config)
    if not spec_dirs:
        print("Error: No spec directories found", file=sys.stderr)
        return 1

    # Use first spec dir as base
    base_spec_dir = spec_dirs[0]

    dry_run = getattr(args, 'dry_run', False)

    validate_refs = getattr(args, 'validate_refs', False)

    # Handle batch mode
    if hasattr(args, 'from_json') and args.from_json:
        return run_batch_edit(args.from_json, base_spec_dir, dry_run, validate_refs)

    # Handle single edit mode
    if hasattr(args, 'req_id') and args.req_id:
        return run_single_edit(args, base_spec_dir, dry_run)

    print("Error: Must specify --req-id or --from-json", file=sys.stderr)
    return 1


def run_batch_edit(
    json_source: str, spec_dir: Path, dry_run: bool, validate_refs: bool = False
) -> int:
    """Run batch edit from JSON file or stdin."""
    # Load JSON
    if json_source == "-":
        changes = json.load(sys.stdin)
    else:
        json_path = Path(json_source)
        if not json_path.exists():
            print(f"Error: JSON file not found: {json_source}", file=sys.stderr)
            return 1
        changes = json.loads(json_path.read_text())

    if not isinstance(changes, list):
        print("Error: JSON must be a list of changes", file=sys.stderr)
        return 1

    results = batch_edit(spec_dir, changes, dry_run=dry_run, validate_refs=validate_refs)

    # Report results
    success_count = sum(1 for r in results if r.get("success"))
    error_count = len(results) - success_count

    if dry_run:
        print(f"[DRY RUN] Would apply {len(results)} changes")
    else:
        print(f"Applied {success_count} changes")

    if error_count > 0:
        print(f"Errors: {error_count}")
        for r in results:
            if not r.get("success"):
                print(f"  - {r.get('req_id', 'unknown')}: {r.get('error', 'unknown error')}")
        return 1

    return 0


def run_single_edit(args: argparse.Namespace, spec_dir: Path, dry_run: bool) -> int:
    """Run single requirement edit."""
    req_id = args.req_id

    # Find the requirement
    location = find_requirement_in_files(spec_dir, req_id)
    if not location:
        print(f"Error: Requirement {req_id} not found", file=sys.stderr)
        return 1

    file_path = location["file_path"]
    results = []

    # Apply implements change
    if hasattr(args, 'implements') and args.implements is not None:
        impl_list = [i.strip() for i in args.implements.split(",")]
        result = modify_implements(file_path, req_id, impl_list, dry_run=dry_run)
        results.append(("implements", result))

    # Apply status change
    if hasattr(args, 'status') and args.status:
        result = modify_status(file_path, req_id, args.status, dry_run=dry_run)
        results.append(("status", result))

    # Apply move
    if hasattr(args, 'move_to') and args.move_to:
        dest_path = spec_dir / args.move_to
        result = move_requirement(file_path, dest_path, req_id, dry_run=dry_run)
        results.append(("move", result))

    # Report
    for op_name, result in results:
        # Check for source_empty warning on move
        if op_name == "move" and result.get("source_empty") and not dry_run:
            print(f"INFO: Source file is now empty: {result.get('source_file')}")
        if result.get("success"):
            if dry_run:
                print(f"[DRY RUN] Would {op_name}: {req_id}")
            else:
                print(f"Updated {op_name}: {req_id}")
        else:
            print(f"Error in {op_name}: {result.get('error')}", file=sys.stderr)
            return 1

    return 0


def find_requirement_in_files(
    spec_dir: Path,
    req_id: str,
) -> Optional[Dict[str, Any]]:
    """
    Find a requirement in spec files.

    Args:
        spec_dir: Directory to search
        req_id: Requirement ID to find

    Returns:
        Dict with file_path, req_id, line_number, or None if not found
    """
    # Pattern to match requirement header
    pattern = re.compile(rf'^#\s*{re.escape(req_id)}:', re.MULTILINE)

    for md_file in spec_dir.rglob("*.md"):
        content = md_file.read_text()
        match = pattern.search(content)
        if match:
            # Count line number
            line_number = content[:match.start()].count('\n') + 1
            return {
                "file_path": md_file,
                "req_id": req_id,
                "line_number": line_number,
            }

    return None


def modify_implements(
    file_path: Path,
    req_id: str,
    new_implements: List[str],
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Modify the Implements field of a requirement.

    Args:
        file_path: Path to the spec file
        req_id: Requirement ID to modify
        new_implements: New list of implements references (empty = set to "-")
        dry_run: If True, don't actually modify the file

    Returns:
        Dict with success, old_implements, new_implements, error
    """
    content = file_path.read_text()

    # Find the requirement header
    req_pattern = re.compile(rf'^(#\s*{re.escape(req_id)}:[^\n]*\n)', re.MULTILINE)
    req_match = req_pattern.search(content)

    if not req_match:
        return {"success": False, "error": f"Requirement {req_id} not found in {file_path}"}

    # Find the **Implements**: field after the header
    start_pos = req_match.end()
    search_region = content[start_pos:start_pos + 500]

    impl_pattern = re.compile(r'(\*\*Implements\*\*:\s*)([^|\n]+)')
    impl_match = impl_pattern.search(search_region)

    if not impl_match:
        return {"success": False, "error": f"Could not find **Implements** for {req_id}"}

    # Extract old value
    old_value = impl_match.group(2).strip()
    old_implements = [v.strip() for v in old_value.split(",")] if old_value != "-" else []

    # Build new value
    if new_implements:
        new_value = ", ".join(new_implements)
    else:
        new_value = "-"

    # Calculate absolute positions
    abs_start = start_pos + impl_match.start()
    abs_end = start_pos + impl_match.end()

    old_line = impl_match.group(0)
    new_line = impl_match.group(1) + new_value

    if old_line == new_line:
        return {
            "success": True,
            "old_implements": old_implements,
            "new_implements": new_implements,
            "no_change": True,
            "dry_run": dry_run,
        }

    # Apply change
    new_content = content[:abs_start] + new_line + content[abs_end:]

    if not dry_run:
        file_path.write_text(new_content)

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
) -> Dict[str, Any]:
    """
    Modify the Status field of a requirement.

    Args:
        file_path: Path to the spec file
        req_id: Requirement ID to modify
        new_status: New status value
        dry_run: If True, don't actually modify the file

    Returns:
        Dict with success, old_status, new_status, error
    """
    content = file_path.read_text()

    # Find the requirement header
    req_pattern = re.compile(rf'^(#\s*{re.escape(req_id)}:[^\n]*\n)', re.MULTILINE)
    req_match = req_pattern.search(content)

    if not req_match:
        return {"success": False, "error": f"Requirement {req_id} not found in {file_path}"}

    # Find the **Status**: field after the header
    start_pos = req_match.end()
    search_region = content[start_pos:start_pos + 500]

    status_pattern = re.compile(r'(\*\*Status\*\*:\s*)(\w+)')
    status_match = status_pattern.search(search_region)

    if not status_match:
        return {"success": False, "error": f"Could not find **Status** for {req_id}"}

    old_status = status_match.group(2)

    if old_status == new_status:
        return {
            "success": True,
            "old_status": old_status,
            "new_status": new_status,
            "no_change": True,
            "dry_run": dry_run,
        }

    # Calculate absolute positions
    abs_start = start_pos + status_match.start()
    abs_end = start_pos + status_match.end()

    new_line = status_match.group(1) + new_status

    # Apply change
    new_content = content[:abs_start] + new_line + content[abs_end:]

    if not dry_run:
        file_path.write_text(new_content)

    return {
        "success": True,
        "old_status": old_status,
        "new_status": new_status,
        "dry_run": dry_run,
    }


def move_requirement(
    source_file: Path,
    dest_file: Path,
    req_id: str,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Move a requirement from one file to another.

    Args:
        source_file: Source spec file
        dest_file: Destination spec file
        req_id: Requirement ID to move
        dry_run: If True, don't actually modify files

    Returns:
        Dict with success, source_file, dest_file, error
    """
    source_content = source_file.read_text()

    # Find the requirement block
    # Pattern: # REQ-xxx: title ... *End* *title* | **Hash**: xxx\n---
    req_pattern = re.compile(
        rf'(^#\s*{re.escape(req_id)}:[^\n]*\n'
        rf'.*?'
        rf'\*End\*[^\n]*\n'
        rf'(?:---\n)?)',
        re.MULTILINE | re.DOTALL
    )

    req_match = req_pattern.search(source_content)

    if not req_match:
        return {"success": False, "error": f"Requirement {req_id} not found in {source_file}"}

    req_block = req_match.group(0)

    # Ensure block ends with separator
    if not req_block.endswith("---\n"):
        req_block = req_block.rstrip() + "\n---\n"

    # Remove from source
    new_source_content = source_content[:req_match.start()] + source_content[req_match.end():]
    # Clean up extra blank lines
    new_source_content = re.sub(r'\n{3,}', '\n\n', new_source_content)

    # Add to destination
    dest_content = dest_file.read_text() if dest_file.exists() else ""
    if dest_content and not dest_content.endswith("\n"):
        dest_content += "\n"
    if dest_content and not dest_content.endswith("\n\n"):
        dest_content += "\n"
    new_dest_content = dest_content + req_block

    # Check if source will be empty after move
    source_empty = len(new_source_content.strip()) == 0

    if not dry_run:
        source_file.write_text(new_source_content)
        dest_file.write_text(new_dest_content)

    return {
        "success": True,
        "source_file": str(source_file),
        "dest_file": str(dest_file),
        "source_empty": source_empty,
        "dry_run": dry_run,
    }


def collect_all_req_ids(spec_dir: Path) -> set:
    """
    Collect all requirement IDs from spec directory.

    Args:
        spec_dir: Directory to scan

    Returns:
        Set of requirement IDs found (short form, e.g., "p00001")
    """
    import re
    req_ids = set()
    pattern = re.compile(r'^#\s*(REQ-[A-Za-z0-9-]+):', re.MULTILINE)

    for md_file in spec_dir.rglob("*.md"):
        content = md_file.read_text()
        for match in pattern.finditer(content):
            full_id = match.group(1)
            # Extract short form (e.g., "p00001" from "REQ-p00001")
            if full_id.startswith("REQ-"):
                short_id = full_id[4:]  # Remove "REQ-" prefix
                req_ids.add(short_id)
            req_ids.add(full_id)  # Also add full form

    return req_ids


def batch_edit(
    spec_dir: Path,
    changes: List[Dict[str, Any]],
    dry_run: bool = False,
    validate_refs: bool = False,
) -> List[Dict[str, Any]]:
    """
    Apply batch edits from a list of change specifications.

    Args:
        spec_dir: Base spec directory
        changes: List of change dicts, each with req_id and one of:
                 - implements: List[str]
                 - status: str
                 - move_to: str (relative path)
        dry_run: If True, don't actually modify files
        validate_refs: If True, validate that implements references exist

    Returns:
        List of result dicts
    """
    results = []

    # Collect all req IDs if validation is enabled
    valid_refs: Optional[set] = None
    if validate_refs:
        valid_refs = collect_all_req_ids(spec_dir)

    for change in changes:
        req_id = change.get("req_id")
        if not req_id:
            results.append({"success": False, "error": "Missing req_id"})
            continue

        # Find the requirement
        location = find_requirement_in_files(spec_dir, req_id)
        if not location:
            results.append({
                "success": False,
                "req_id": req_id,
                "error": f"Requirement {req_id} not found",
            })
            continue

        file_path = location["file_path"]
        result: Dict[str, Any] = {"req_id": req_id, "success": True}

        # Validate implements references if enabled
        if validate_refs and valid_refs and "implements" in change:
            invalid_refs = []
            for ref in change["implements"]:
                # Check both short and full forms
                if ref not in valid_refs and f"REQ-{ref}" not in valid_refs:
                    invalid_refs.append(ref)
            if invalid_refs:
                result = {
                    "req_id": req_id,
                    "success": False,
                    "error": f"Invalid implements references: {', '.join(invalid_refs)}",
                }
                results.append(result)
                continue

        # Apply implements change
        if "implements" in change:
            impl_result = modify_implements(
                file_path, req_id, change["implements"], dry_run=dry_run
            )
            if not impl_result["success"]:
                result = impl_result
                result["req_id"] = req_id
                results.append(result)
                continue
            result["implements"] = impl_result

        # Apply status change
        if "status" in change:
            status_result = modify_status(
                file_path, req_id, change["status"], dry_run=dry_run
            )
            if not status_result["success"]:
                result = status_result
                result["req_id"] = req_id
                results.append(result)
                continue
            result["status"] = status_result

        # Apply move (must be last since it changes file location)
        if "move_to" in change:
            dest_path = spec_dir / change["move_to"]
            move_result = move_requirement(
                file_path, dest_path, req_id, dry_run=dry_run
            )
            if not move_result["success"]:
                result = move_result
                result["req_id"] = req_id
                results.append(result)
                continue
            result["move"] = move_result

        result["dry_run"] = dry_run
        results.append(result)

    return results
