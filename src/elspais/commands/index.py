"""
elspais.commands.index - INDEX.md management command.
"""

import argparse
from pathlib import Path

from elspais.config.defaults import DEFAULT_CONFIG
from elspais.config.loader import find_config_file, get_spec_directories, load_config
from elspais.core.parser import RequirementParser
from elspais.core.patterns import PatternConfig


def run(args: argparse.Namespace) -> int:
    """Run the index command."""
    if not args.index_action:
        print("Usage: elspais index {validate|regenerate}")
        return 1

    if args.index_action == "validate":
        return run_validate(args)
    elif args.index_action == "regenerate":
        return run_regenerate(args)

    return 1


def run_validate(args: argparse.Namespace) -> int:
    """Validate INDEX.md accuracy."""
    config_path = args.config or find_config_file(Path.cwd())
    if config_path and config_path.exists():
        config = load_config(config_path)
    else:
        config = DEFAULT_CONFIG

    spec_dirs = get_spec_directories(args.spec_dir, config)
    if not spec_dirs:
        print("Error: No spec directories found")
        return 1

    spec_config = config.get("spec", {})
    # Use first spec directory for INDEX.md location
    index_file = spec_dirs[0] / spec_config.get("index_file", "INDEX.md")

    if not index_file.exists():
        print(f"INDEX.md not found: {index_file}")
        return 1

    # Parse all requirements
    pattern_config = PatternConfig.from_dict(config.get("patterns", {}))
    no_reference_values = spec_config.get("no_reference_values")
    skip_files = spec_config.get("skip_files", [])
    parser = RequirementParser(pattern_config, no_reference_values=no_reference_values)
    requirements = parser.parse_directories(spec_dirs, skip_files=skip_files)

    # Parse INDEX.md to find listed requirements
    index_content = index_file.read_text(encoding="utf-8")
    indexed_ids = set()

    import re
    for match in re.finditer(r"\|\s*([A-Z]+-(?:[A-Z]+-)?[a-zA-Z]?\d+)\s*\|", index_content):
        indexed_ids.add(match.group(1))

    # Compare
    actual_ids = set(requirements.keys())
    missing = actual_ids - indexed_ids
    extra = indexed_ids - actual_ids

    if missing:
        print(f"Missing from INDEX.md ({len(missing)}):")
        for req_id in sorted(missing):
            print(f"  - {req_id}")

    if extra:
        print(f"\nExtra in INDEX.md ({len(extra)}):")
        for req_id in sorted(extra):
            print(f"  - {req_id}")

    if not missing and not extra:
        print(f"✓ INDEX.md is accurate ({len(actual_ids)} requirements)")
        return 0

    return 1


def run_regenerate(args: argparse.Namespace) -> int:
    """Regenerate INDEX.md from requirements."""
    config_path = args.config or find_config_file(Path.cwd())
    if config_path and config_path.exists():
        config = load_config(config_path)
    else:
        config = DEFAULT_CONFIG

    spec_dirs = get_spec_directories(args.spec_dir, config)
    if not spec_dirs:
        print("Error: No spec directories found")
        return 1

    spec_config = config.get("spec", {})
    # Use first spec directory for INDEX.md location
    index_file = spec_dirs[0] / spec_config.get("index_file", "INDEX.md")

    # Parse all requirements
    pattern_config = PatternConfig.from_dict(config.get("patterns", {}))
    no_reference_values = spec_config.get("no_reference_values")
    skip_files = spec_config.get("skip_files", [])
    parser = RequirementParser(pattern_config, no_reference_values=no_reference_values)
    requirements = parser.parse_directories(spec_dirs, skip_files=skip_files)

    if not requirements:
        print("No requirements found")
        return 1

    # Generate INDEX.md
    content = generate_index(requirements, config)
    index_file.write_text(content, encoding="utf-8")

    print(f"Regenerated: {index_file}")
    print(f"  {len(requirements)} requirements indexed")

    return 0


def generate_index(requirements: dict, config: dict) -> str:
    """Generate INDEX.md content."""
    lines = [
        "# Requirements Index",
        "",
        "This file provides a complete index of all requirements.",
        "",
    ]

    # Group by type
    prd_reqs = {k: v for k, v in requirements.items() if v.level.upper() in ["PRD", "PRODUCT"]}
    ops_reqs = {k: v for k, v in requirements.items() if v.level.upper() in ["OPS", "OPERATIONS"]}
    dev_reqs = {k: v for k, v in requirements.items() if v.level.upper() in ["DEV", "DEVELOPMENT"]}

    for title, reqs in [
        ("Product Requirements (PRD)", prd_reqs),
        ("Operations Requirements (OPS)", ops_reqs),
        ("Development Requirements (DEV)", dev_reqs),
    ]:
        if not reqs:
            continue

        lines.append(f"## {title}")
        lines.append("")
        lines.append("| ID | Title | File | Hash |")
        lines.append("|---|---|---|---|")

        for req_id, req in sorted(reqs.items()):
            file_name = req.file_path.name if req.file_path else "-"
            hash_val = req.hash or "-"
            lines.append(f"| {req_id} | {req.title} | {file_name} | {hash_val} |")

        lines.append("")

    lines.extend([
        "---",
        "",
        "*Generated by elspais*",
    ])

    return "\n".join(lines)


