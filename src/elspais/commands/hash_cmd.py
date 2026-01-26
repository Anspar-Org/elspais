"""
elspais.commands.hash_cmd - Hash management command.

Verify and update requirement hashes.
"""

import argparse
import sys
from pathlib import Path

from elspais.config import (
    DEFAULT_CONFIG,
    find_config_file,
    get_spec_directories,
    load_config,
)
from elspais.models import Requirement
from elspais.utilities.hasher import calculate_hash, verify_hash
from elspais.loader import load_requirements_from_directories


def run(args: argparse.Namespace) -> int:
    """Run the hash command."""
    if not args.hash_action:
        print("Usage: elspais hash {verify|update}")
        return 1

    if args.hash_action == "verify":
        return run_verify(args)
    elif args.hash_action == "update":
        return run_update(args)

    return 1


def run_verify(args: argparse.Namespace) -> int:
    """Verify all requirement hashes."""
    config, requirements = load_requirements(args)
    if not requirements:
        return 1

    hash_length = config.get("validation", {}).get("hash_length", 8)
    algorithm = config.get("validation", {}).get("hash_algorithm", "sha256")

    mismatches = []
    missing = []

    for req_id, req in requirements.items():
        if not req.hash:
            missing.append(req_id)
        else:
            expected = calculate_hash(req.body, length=hash_length, algorithm=algorithm)
            if not verify_hash(req.body, req.hash, length=hash_length, algorithm=algorithm):
                mismatches.append((req_id, req.hash, expected))

    # Report results
    if missing:
        print(f"Missing hashes: {len(missing)}")
        for req_id in missing:
            print(f"  - {req_id}")

    if mismatches:
        print(f"\nHash mismatches: {len(mismatches)}")
        for req_id, current, expected in mismatches:
            print(f"  - {req_id}: {current} (expected: {expected})")

    if not missing and not mismatches:
        print(f"✓ All {len(requirements)} hashes verified")
        return 0

    return 1 if mismatches else 0


def run_update(args: argparse.Namespace) -> int:
    """Update requirement hashes."""
    config, requirements = load_requirements(args)
    if not requirements:
        return 1

    hash_length = config.get("validation", {}).get("hash_length", 8)
    algorithm = config.get("validation", {}).get("hash_algorithm", "sha256")

    # Filter to specific requirement if specified
    if args.req_id:
        if args.req_id not in requirements:
            print(f"Requirement not found: {args.req_id}")
            return 1
        requirements = {args.req_id: requirements[args.req_id]}

    updates = []

    for req_id, req in requirements.items():
        expected = calculate_hash(req.body, length=hash_length, algorithm=algorithm)
        if req.hash != expected:
            updates.append((req_id, req, expected))

    if not updates:
        print("All hashes are up to date")
        return 0

    # Show or apply updates
    if args.dry_run:
        print(f"Would update {len(updates)} hashes:")
        for req_id, req, new_hash in updates:
            old_hash = req.hash or "(none)"
            print(f"  {req_id}: {old_hash} -> {new_hash}")
    else:
        print(f"Updating {len(updates)} hashes...")
        for req_id, req, new_hash in updates:
            result = update_hash_in_file(req, new_hash)
            if result["updated"]:
                print(f"  ✓ {req_id}")
                old_hash = result["old_hash"] or "(none)"
                print(f"    [INFO] Hash: {old_hash} -> {result['new_hash']}")
                if result["title_fixed"]:
                    print(f"    [INFO] Title fixed: \"{result['old_title']}\" -> \"{req.title}\"")
            else:
                print(f"  ✗ {req_id}")
                print("    [WARN] Could not find End marker to update")

    return 0


def load_requirements(args: argparse.Namespace) -> tuple:
    """Load configuration and requirements."""
    config_path = args.config or find_config_file(Path.cwd())
    if config_path and config_path.exists():
        config = load_config(config_path)
    else:
        config = DEFAULT_CONFIG

    spec_dirs = get_spec_directories(args.spec_dir, config)
    if not spec_dirs:
        print("Error: No spec directories found", file=sys.stderr)
        return config, {}

    try:
        requirements = load_requirements_from_directories(spec_dirs, config)
    except Exception as e:
        print(f"Error parsing requirements: {e}", file=sys.stderr)
        return config, {}

    return config, requirements


def update_hash_in_file(req: Requirement, new_hash: str) -> dict:
    """Update the hash in the requirement's source file.

    Finds the End marker by the old hash value, then replaces the entire line
    with the correct title and new hash. This handles cases where the End
    marker title doesn't match the header title.

    Args:
        req: Requirement object with file_path, title, and hash
        new_hash: New hash value to write

    Returns:
        Dict with change info:
          - 'updated': bool - whether file was modified
          - 'old_hash': str - previous hash (or None)
          - 'new_hash': str - new hash value
          - 'title_fixed': bool - whether title was corrected
          - 'old_title': str - previous title (if different)
    """
    import re

    result = {
        "updated": False,
        "old_hash": req.hash,
        "new_hash": new_hash,
        "title_fixed": False,
        "old_title": None,
    }

    if not req.file_path:
        return result

    content = req.file_path.read_text(encoding="utf-8")
    new_end_line = f"*End* *{req.title}* | **Hash**: {new_hash}"

    if req.hash:
        # Strategy: Try title first (most specific), then hash if title not found
        # This handles both: (1) normal case, (2) mismatched title case

        # First try: match by correct title (handles case where titles match)
        pattern_by_title = (
            rf"^\*End\*\s+\*{re.escape(req.title)}\*\s*\|\s*\*\*Hash\*\*:\s*[a-fA-F0-9]+\s*$"
        )
        if re.search(pattern_by_title, content, re.MULTILINE):
            content, count = re.subn(pattern_by_title, new_end_line, content, flags=re.MULTILINE)
            if count > 0:
                result["updated"] = True
        else:
            # Second try: find by hash value (handles mismatched title)
            # Pattern: *End* *AnyTitle* | **Hash**: oldhash
            pattern_by_hash = (
                rf"^\*End\*\s+\*([^*]+)\*\s*\|\s*\*\*Hash\*\*:\s*{re.escape(req.hash)}\s*$"
            )
            match = re.search(pattern_by_hash, content, re.MULTILINE)

            if match:
                old_title = match.group(1)
                if old_title != req.title:
                    result["title_fixed"] = True
                    result["old_title"] = old_title

                # Replace entire line (only first match to avoid affecting other reqs)
                content = re.sub(
                    pattern_by_hash, new_end_line, content, count=1, flags=re.MULTILINE
                )
                result["updated"] = True
    else:
        # Add hash to end marker (no existing hash)
        # Pattern: *End* *Title* (without hash)
        pattern = rf"^(\*End\*\s+\*{re.escape(req.title)}\*)(?!\s*\|\s*\*\*Hash\*\*)\s*$"
        content, count = re.subn(pattern, new_end_line, content, flags=re.MULTILINE)
        if count > 0:
            result["updated"] = True

    if result["updated"]:
        req.file_path.write_text(content, encoding="utf-8")

    return result
