"""
elspais.commands.changed - Git-based change detection for requirements.

Detects changes to requirement files using git:
- Uncommitted changes (modified or new files)
- Changes vs main/master branch
- Moved requirements (comparing current location to committed state)
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

from elspais.config.defaults import DEFAULT_CONFIG
from elspais.config.loader import find_config_file, load_config
from elspais.core.git import (
    GitChangeInfo,
    MovedRequirement,
    detect_moved_requirements,
    filter_spec_files,
    get_current_req_locations,
    get_git_changes,
    get_repo_root,
)


def load_configuration(args: argparse.Namespace) -> Optional[Dict]:
    """Load configuration from file or use defaults."""
    config_path = getattr(args, "config", None)
    if config_path:
        pass  # Use provided path
    else:
        config_path = find_config_file(Path.cwd())

    if config_path and config_path.exists():
        try:
            return load_config(config_path)
        except Exception as e:
            print(f"Error loading config: {e}", file=sys.stderr)
            return None
    else:
        return DEFAULT_CONFIG


def run(args: argparse.Namespace) -> int:
    """Run the changed command."""
    # Get repository root
    repo_root = get_repo_root()
    if repo_root is None:
        print("Error: Not in a git repository")
        return 1

    # Load config to get spec directory
    config = load_configuration(args)
    if config is None:
        return 1

    spec_dir = config.get("directories", {}).get("spec", "spec")
    if isinstance(spec_dir, list):
        spec_dir = spec_dir[0] if spec_dir else "spec"

    base_branch = getattr(args, "base_branch", None) or "main"
    json_output = getattr(args, "json", False)
    show_all = getattr(args, "all", False)
    quiet = getattr(args, "quiet", False)

    # Get git change information
    changes = get_git_changes(repo_root, spec_dir, base_branch)

    # Filter to spec files only
    spec_modified = filter_spec_files(changes.modified_files, spec_dir)
    spec_untracked = filter_spec_files(changes.untracked_files, spec_dir)
    spec_branch = filter_spec_files(changes.branch_changed_files, spec_dir)

    # Detect moved requirements
    current_locations = get_current_req_locations(repo_root, spec_dir)
    moved = detect_moved_requirements(
        changes.committed_req_locations, current_locations
    )

    # Build result
    result = {
        "repo_root": str(repo_root),
        "spec_dir": spec_dir,
        "base_branch": base_branch,
        "uncommitted": {
            "modified": sorted(spec_modified),
            "untracked": sorted(spec_untracked),
            "count": len(spec_modified) + len(spec_untracked),
        },
        "branch_changed": {
            "files": sorted(spec_branch),
            "count": len(spec_branch),
        },
        "moved_requirements": [
            {
                "req_id": m.req_id,
                "old_path": m.old_path,
                "new_path": m.new_path,
            }
            for m in moved
        ],
    }

    # Include all files if --all flag is set
    if show_all:
        result["all_modified"] = sorted(changes.modified_files)
        result["all_untracked"] = sorted(changes.untracked_files)
        result["all_branch_changed"] = sorted(changes.branch_changed_files)

    if json_output:
        print(json.dumps(result, indent=2))
        return 0

    # Human-readable output
    has_changes = False

    if spec_modified or spec_untracked:
        has_changes = True
        if not quiet:
            uncommitted_count = len(spec_modified) + len(spec_untracked)
            print(f"Uncommitted spec changes: {uncommitted_count}")

            if spec_modified:
                print(f"  Modified ({len(spec_modified)}):")
                for f in sorted(spec_modified):
                    print(f"    M {f}")

            if spec_untracked:
                print(f"  New ({len(spec_untracked)}):")
                for f in sorted(spec_untracked):
                    print(f"    + {f}")
            print()

    if spec_branch:
        has_changes = True
        if not quiet:
            print(f"Changed vs {base_branch}: {len(spec_branch)}")
            for f in sorted(spec_branch):
                print(f"    {f}")
            print()

    if moved:
        has_changes = True
        if not quiet:
            print(f"Moved requirements: {len(moved)}")
            for m in moved:
                print(f"  REQ-{m.req_id}:")
                print(f"    from: {m.old_path}")
                print(f"    to:   {m.new_path}")
            print()

    if not has_changes:
        if not quiet:
            print("No uncommitted changes to spec files")
        return 0

    return 0
