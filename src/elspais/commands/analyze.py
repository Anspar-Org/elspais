"""
elspais.commands.analyze - Analyze requirements command.
"""

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional

from elspais.config.defaults import DEFAULT_CONFIG
from elspais.config.loader import find_config_file, get_spec_directories, load_config
from elspais.core.models import Requirement
from elspais.core.parser import RequirementParser
from elspais.core.patterns import PatternConfig


def run(args: argparse.Namespace) -> int:
    """Run the analyze command."""
    if not args.analyze_action:
        print("Usage: elspais analyze {hierarchy|orphans|coverage}")
        return 1

    if args.analyze_action == "hierarchy":
        return run_hierarchy(args)
    elif args.analyze_action == "orphans":
        return run_orphans(args)
    elif args.analyze_action == "coverage":
        return run_coverage(args)

    return 1


def run_hierarchy(args: argparse.Namespace) -> int:
    """Show requirement hierarchy tree."""
    requirements = load_requirements(args)
    if not requirements:
        return 1

    print("Requirement Hierarchy")
    print("=" * 60)

    # Find root requirements (PRD with no implements)
    roots = [
        req for req in requirements.values()
        if req.level.upper() in ["PRD", "PRODUCT"] and not req.implements
    ]

    if not roots:
        # Fall back to all PRD requirements
        roots = [
            req for req in requirements.values()
            if req.level.upper() in ["PRD", "PRODUCT"]
        ]

    printed = set()

    def print_tree(req: Requirement, indent: int = 0) -> None:
        if req.id in printed:
            return
        printed.add(req.id)

        prefix = "  " * indent
        status_icon = "✓" if req.status == "Active" else "○"
        print(f"{prefix}{status_icon} {req.id}: {req.title}")

        # Find children (requirements that implement this one)
        children = find_children(req.id, requirements)
        for child in children:
            print_tree(child, indent + 1)

    for root in sorted(roots, key=lambda r: r.id):
        print_tree(root)
        print()

    return 0


def run_orphans(args: argparse.Namespace) -> int:
    """Find orphaned requirements."""
    requirements = load_requirements(args)
    if not requirements:
        return 1

    orphans = []

    for req in requirements.values():
        # Skip PRD (they can be roots)
        if req.level.upper() in ["PRD", "PRODUCT"]:
            continue

        # Check if this requirement implements anything
        if not req.implements:
            orphans.append(req)
        else:
            # Check if all implements references are valid
            all_valid = True
            for impl_id in req.implements:
                if not find_requirement(impl_id, requirements):
                    all_valid = False
                    break
            if not all_valid:
                orphans.append(req)

    if orphans:
        print(f"Orphaned Requirements ({len(orphans)}):")
        print("-" * 40)
        for req in sorted(orphans, key=lambda r: r.id):
            impl_str = ", ".join(req.implements) if req.implements else "(none)"
            print(f"  {req.id}: {req.title}")
            print(f"    Level: {req.level} | Implements: {impl_str}")
            if req.file_path:
                print(f"    File: {req.file_path.name}:{req.line_number}")
            print()
    else:
        print("✓ No orphaned requirements found")

    return 0


def run_coverage(args: argparse.Namespace) -> int:
    """Show implementation coverage report."""
    requirements = load_requirements(args)
    if not requirements:
        return 1

    # Group by type
    prd_count = sum(1 for r in requirements.values() if r.level.upper() in ["PRD", "PRODUCT"])
    ops_count = sum(1 for r in requirements.values() if r.level.upper() in ["OPS", "OPERATIONS"])
    dev_count = sum(1 for r in requirements.values() if r.level.upper() in ["DEV", "DEVELOPMENT"])

    # Count PRD requirements that have implementations
    implemented_prd = set()
    for req in requirements.values():
        for impl_id in req.implements:
            # Resolve to full ID
            target = find_requirement(impl_id, requirements)
            if target and target.level.upper() in ["PRD", "PRODUCT"]:
                implemented_prd.add(target.id)

    print("Implementation Coverage Report")
    print("=" * 60)
    print()
    print(f"Total Requirements: {len(requirements)}")
    print(f"  PRD: {prd_count}")
    print(f"  OPS: {ops_count}")
    print(f"  DEV: {dev_count}")
    print()
    print("PRD Implementation Coverage:")
    print(f"  Implemented: {len(implemented_prd)}/{prd_count}")
    if prd_count > 0:
        pct = (len(implemented_prd) / prd_count) * 100
        print(f"  Coverage: {pct:.1f}%")

    # List unimplemented PRD
    unimplemented = [
        req for req in requirements.values()
        if req.level.upper() in ["PRD", "PRODUCT"] and req.id not in implemented_prd
    ]

    if unimplemented:
        print()
        print(f"Unimplemented PRD ({len(unimplemented)}):")
        for req in sorted(unimplemented, key=lambda r: r.id):
            print(f"  - {req.id}: {req.title}")

    return 0


def load_requirements(args: argparse.Namespace) -> Dict[str, Requirement]:
    """Load requirements from spec directories."""
    config_path = args.config or find_config_file(Path.cwd())
    if config_path and config_path.exists():
        config = load_config(config_path)
    else:
        config = DEFAULT_CONFIG

    spec_dirs = get_spec_directories(args.spec_dir, config)
    if not spec_dirs:
        print("Error: No spec directories found", file=sys.stderr)
        return {}

    pattern_config = PatternConfig.from_dict(config.get("patterns", {}))
    spec_config = config.get("spec", {})
    no_reference_values = spec_config.get("no_reference_values")
    skip_files = spec_config.get("skip_files", [])
    parser = RequirementParser(pattern_config, no_reference_values=no_reference_values)

    try:
        return parser.parse_directories(spec_dirs, skip_files=skip_files)
    except Exception as e:
        print(f"Error parsing requirements: {e}", file=sys.stderr)
        return {}


def find_children(req_id: str, requirements: Dict[str, Requirement]) -> List[Requirement]:
    """Find requirements that implement the given requirement."""
    children = []
    short_id = req_id.split("-")[-1] if "-" in req_id else req_id

    for other_req in requirements.values():
        for impl in other_req.implements:
            if impl == req_id or impl == short_id or impl.endswith(short_id):
                children.append(other_req)
                break

    return sorted(children, key=lambda r: r.id)


def find_requirement(impl_id: str, requirements: Dict[str, Requirement]) -> Optional[Requirement]:
    """Find a requirement by full or partial ID."""
    if impl_id in requirements:
        return requirements[impl_id]

    for req_id, req in requirements.items():
        if req_id.endswith(impl_id) or req_id.endswith(f"-{impl_id}"):
            return req

    return None
