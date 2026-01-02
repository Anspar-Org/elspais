"""
elspais.commands.hash_cmd - Hash management command.

Verify and update requirement hashes.
"""

import argparse
import sys
from pathlib import Path

from elspais.config.defaults import DEFAULT_CONFIG
from elspais.config.loader import find_config_file, get_spec_directories, load_config
from elspais.core.hasher import calculate_hash, verify_hash
from elspais.core.models import Requirement
from elspais.core.parser import RequirementParser
from elspais.core.patterns import PatternConfig


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
            update_hash_in_file(req, new_hash)
            print(f"  ✓ {req_id}")

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

    pattern_config = PatternConfig.from_dict(config.get("patterns", {}))
    spec_config = config.get("spec", {})
    no_reference_values = spec_config.get("no_reference_values")
    skip_files = spec_config.get("skip_files", [])
    parser = RequirementParser(pattern_config, no_reference_values=no_reference_values)

    try:
        requirements = parser.parse_directories(spec_dirs, skip_files=skip_files)
    except Exception as e:
        print(f"Error parsing requirements: {e}", file=sys.stderr)
        return config, {}

    return config, requirements


def update_hash_in_file(req: Requirement, new_hash: str) -> None:
    """Update the hash in the requirement's source file.

    The replacement is scoped to the specific requirement's end marker
    (identified by title) to avoid accidentally updating other requirements
    in the same file that might have the same hash value.
    """
    if not req.file_path:
        return

    content = req.file_path.read_text(encoding="utf-8")

    import re

    if req.hash:
        # Replace existing hash - SCOPED to this requirement's end marker
        # Match: *End* *Title* | **Hash**: oldhash
        # Replace hash only for THIS requirement (identified by title)
        content = re.sub(
            rf"(\*End\*\s+\*{re.escape(req.title)}\*\s*\|\s*)\*\*Hash\*\*:\s*{re.escape(req.hash)}",
            rf"\1**Hash**: {new_hash}",
            content,
        )
    else:
        # Add hash to end marker
        # Pattern: *End* *Title* (without hash)
        # Add: | **Hash**: XXXX
        content = re.sub(
            rf"(\*End\*\s+\*{re.escape(req.title)}\*)(?!\s*\|\s*\*\*Hash\*\*)",
            rf"\1 | **Hash**: {new_hash}",
            content,
        )

    req.file_path.write_text(content, encoding="utf-8")
