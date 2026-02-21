# Implements: REQ-p00005-C
"""
elspais.commands.associate_cmd - Manage associate repository links.

Provides subcommands to link, unlink, list, and auto-discover
associate repositories.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import tomlkit

from elspais.associates import Associate, discover_associate_from_path
from elspais.config import find_config_file, parse_toml_document


def run(args: argparse.Namespace) -> int:
    """Run the associate command.

    Dispatches to the appropriate subcommand based on args.

    Args:
        args: Parsed command line arguments.

    Returns:
        Exit code (0 for success, non-zero for failure).
    """
    if getattr(args, "list", False):
        return cmd_list(args)
    elif getattr(args, "unlink", None):
        return cmd_unlink(args)
    elif getattr(args, "all", False):
        return cmd_all(args)
    elif getattr(args, "path", None):
        return cmd_link(args)
    else:
        print("Usage: elspais associate <path>", file=sys.stderr)
        print("       elspais associate --all", file=sys.stderr)
        print("       elspais associate --list", file=sys.stderr)
        print("       elspais associate --unlink <name>", file=sys.stderr)
        return 1


def cmd_link(args: argparse.Namespace) -> int:
    """Link a single associate repository.

    If path is a directory, validates it has an associate config.
    If path is a name (no slashes), scans sibling directories.

    Args:
        args: Parsed arguments with .path set.

    Returns:
        Exit code.
    """
    path_str = args.path
    repo_path = Path(path_str)

    # If it looks like a name (no path separators), search siblings
    if not repo_path.is_absolute() and "/" not in path_str and "\\" not in path_str:
        resolved = _find_by_name(path_str, args)
        if resolved is None:
            print(
                f"Error: Could not find associate '{path_str}' in sibling directories.",
                file=sys.stderr,
            )
            return 1
        repo_path = resolved

    repo_path = repo_path.resolve()

    # Validate it is an associate repo
    result = discover_associate_from_path(repo_path)
    if isinstance(result, str):
        print(f"Error: {result}", file=sys.stderr)
        return 1

    # Write to .elspais.local.toml
    config_dir = _get_config_dir(args)
    if config_dir is None:
        print("Error: No configuration directory found.", file=sys.stderr)
        return 1

    canonical_root = getattr(args, "canonical_root", None)
    cr = Path(canonical_root) if canonical_root else None
    already_linked = _add_path_to_local_config(config_dir, str(repo_path), cr)
    if already_linked:
        print(f"Already linked: {result.name} ({result.code}) at {repo_path}")
        return 0

    print(f"Linked {result.name} ({result.code}) at {repo_path}")
    return 0


def cmd_all(args: argparse.Namespace) -> int:
    """Auto-discover and link all associate repos in sibling directories.

    Scans canonical_root.parent (or config_dir.parent) for directories
    containing .elspais.toml with project.type = 'associated'.

    Args:
        args: Parsed arguments.

    Returns:
        Exit code.
    """
    scan_base = _get_scan_base(args)
    if scan_base is None:
        print("Error: Cannot determine parent directory to scan.", file=sys.stderr)
        return 1

    config_dir = _get_config_dir(args)
    if config_dir is None:
        print("Error: No configuration directory found.", file=sys.stderr)
        return 1

    found: list[tuple[Path, Associate]] = []

    for child in sorted(scan_base.iterdir()):
        if not child.is_dir():
            continue
        # Skip the current repo
        if config_dir and child.resolve() == config_dir.resolve():
            continue
        result = discover_associate_from_path(child)
        if isinstance(result, Associate):
            found.append((child.resolve(), result))

    if not found:
        print("No associate repositories found in sibling directories.")
        return 0

    canonical_root = getattr(args, "canonical_root", None)
    cr = Path(canonical_root) if canonical_root else None
    linked_count = 0
    for repo_path, assoc in found:
        already_linked = _add_path_to_local_config(config_dir, str(repo_path), cr)
        status = "already linked" if already_linked else "linked"
        print(f"  Found: {repo_path} ({assoc.code}) [{status}]")
        if not already_linked:
            linked_count += 1

    print(f"Linked {linked_count} associate(s)")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    """List current associate links and their status.

    Reads [associates].paths from merged config and checks each path.

    Args:
        args: Parsed arguments.

    Returns:
        Exit code.
    """
    from elspais.config import get_config

    config_path = _get_config_path(args)
    config = get_config(config_path=config_path, quiet=True)

    paths = config.get("associates", {}).get("paths", [])

    if not paths:
        print("No associates linked.")
        print("Use 'elspais associate <path>' or 'elspais associate --all' to link.")
        return 0

    # Resolve relative paths from canonical_root (worktree support)
    canonical_root = getattr(args, "canonical_root", None)

    print(f"{'Name':<20} {'Prefix':<10} {'Status':<12} Path")
    print("-" * 72)

    for path_str in paths:
        repo_path = Path(path_str)
        if not repo_path.is_absolute() and canonical_root:
            repo_path = Path(canonical_root) / repo_path
        if not repo_path.exists():
            name = repo_path.name
            print(f"{name:<20} {'?':<10} {'NOT FOUND':<12} {path_str}")
            continue

        result = discover_associate_from_path(repo_path)
        if isinstance(result, str):
            name = repo_path.name
            print(f"{name:<20} {'?':<10} {'BROKEN':<12} {path_str}")
        else:
            spec_dir = repo_path / result.spec_path
            status = "OK" if spec_dir.exists() else "NO SPEC"
            print(f"{result.name:<20} {result.code:<10} {status:<12} {path_str}")

    return 0


def cmd_unlink(args: argparse.Namespace) -> int:
    """Remove an associate link by name.

    Finds the matching entry in .elspais.local.toml and removes it.

    Args:
        args: Parsed arguments with .unlink set to the name.

    Returns:
        Exit code.
    """
    name = args.unlink
    config_dir = _get_config_dir(args)
    if config_dir is None:
        print("Error: No configuration directory found.", file=sys.stderr)
        return 1

    local_path = config_dir / ".elspais.local.toml"
    if not local_path.exists():
        print(f"Error: No associate '{name}' found (no local config).", file=sys.stderr)
        return 1

    doc = parse_toml_document(local_path.read_text(encoding="utf-8"))
    associates = doc.get("associates", {})
    paths = associates.get("paths", [])

    if not paths:
        print(f"Error: No associate '{name}' found.", file=sys.stderr)
        return 1

    # Find the path matching the name using multiple strategies:
    # 1. Exact path match, 2. Directory basename, 3. Project name, 4. Prefix code
    canonical_root = getattr(args, "canonical_root", None)
    found_idx = None
    found_path = None

    # Strategy 1: exact path match
    for idx, path_str in enumerate(paths):
        if path_str == name:
            found_idx = idx
            found_path = path_str
            break

    # Strategy 2: directory basename match
    if found_idx is None:
        for idx, path_str in enumerate(paths):
            if Path(path_str).name == name:
                found_idx = idx
                found_path = path_str
                break

    # Strategy 3: path component substring (e.g., "callisto" in "callisto-worktrees/branch")
    if found_idx is None:
        for idx, path_str in enumerate(paths):
            if any(name in part for part in Path(path_str).parts):
                found_idx = idx
                found_path = path_str
                break

    # Strategy 4 & 5: project name or prefix code (requires reading config)
    if found_idx is None:
        name_lower = name.lower()
        for idx, path_str in enumerate(paths):
            repo_path = Path(path_str)
            if not repo_path.is_absolute() and canonical_root:
                repo_path = Path(canonical_root) / repo_path
            result = discover_associate_from_path(repo_path)
            if isinstance(result, Associate) and (
                result.name == name or result.code.lower() == name_lower
            ):
                found_idx = idx
                found_path = path_str
                break

    if found_idx is None:
        print(f"Error: No associate '{name}' found in linked paths.", file=sys.stderr)
        return 1

    # Remove the entry
    del paths[found_idx]
    # Write back
    local_path.write_text(tomlkit.dumps(doc), encoding="utf-8")

    print(f"Unlinked {name} (was {found_path})")
    return 0


# --- Private helpers ---


def _get_config_path(args: argparse.Namespace) -> Path | None:
    """Get config file path from args or by discovery."""
    if hasattr(args, "config") and args.config:
        return args.config
    return find_config_file(Path.cwd())


def _get_config_dir(args: argparse.Namespace) -> Path | None:
    """Get the directory containing the config file."""
    config_path = _get_config_path(args)
    if config_path and config_path.exists():
        return config_path.parent
    return None


def _get_scan_base(args: argparse.Namespace) -> Path | None:
    """Get the base directory to scan for associates.

    Uses canonical_root.parent if available, otherwise config_dir.parent.
    """
    canonical_root = getattr(args, "canonical_root", None)
    if canonical_root:
        return Path(canonical_root).parent

    config_dir = _get_config_dir(args)
    if config_dir:
        return config_dir.parent

    return None


def _find_by_name(name: str, args: argparse.Namespace) -> Path | None:
    """Search sibling directories for an associate by name.

    Args:
        name: Directory name or project name to find.
        args: Parsed arguments for context.

    Returns:
        Resolved Path if found, None otherwise.
    """
    scan_base = _get_scan_base(args)
    if scan_base is None:
        return None

    # Direct directory match
    candidate = scan_base / name
    if candidate.is_dir():
        result = discover_associate_from_path(candidate)
        if isinstance(result, Associate):
            return candidate

    # Scan all siblings for matching project.name
    for child in scan_base.iterdir():
        if not child.is_dir():
            continue
        result = discover_associate_from_path(child)
        if isinstance(result, Associate) and result.name == name:
            return child

    return None


def _add_path_to_local_config(
    config_dir: Path, repo_path: str, canonical_root: Path | None = None
) -> bool:
    """Add a path to [associates].paths in .elspais.local.toml.

    Creates the file and section if they don't exist.
    Returns True if the path was already present (no change made).

    Args:
        config_dir: Directory containing the config files.
        repo_path: Absolute path string to add.
        canonical_root: Canonical repo root for resolving existing relative paths.

    Returns:
        True if already linked, False if newly added.
    """
    local_path = config_dir / ".elspais.local.toml"

    if local_path.exists():
        doc = parse_toml_document(local_path.read_text(encoding="utf-8"))
    else:
        doc = tomlkit.document()

    # Ensure [associates] section exists
    if "associates" not in doc:
        doc.add("associates", tomlkit.table())

    associates = doc["associates"]

    # Ensure paths array exists
    if "paths" not in associates:
        associates["paths"] = tomlkit.array()

    paths = associates["paths"]

    # Check for duplicates (resolve existing paths to catch relative/absolute matches)
    resolved_new = Path(repo_path).resolve()
    for existing in paths:
        existing_path = Path(existing)
        if not existing_path.is_absolute() and canonical_root:
            existing_resolved = (canonical_root / existing_path).resolve()
        else:
            existing_resolved = existing_path.resolve()
        if existing_resolved == resolved_new:
            return True

    # Append new path
    paths.append(repo_path)

    # Write back
    local_path.write_text(tomlkit.dumps(doc), encoding="utf-8")
    return False
