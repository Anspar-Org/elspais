# Implements: REQ-p00001-C, REQ-p00004-A, REQ-p00004-B
"""
elspais.commands.changed - Git-based change detection for requirements.

Detects changes to requirement files using git:
- Uncommitted changes (modified or new files)
- Changes vs main/master branch
- Moved requirements (comparing current location to committed state)
"""
from __future__ import annotations

import argparse
import json

from elspais.config.schema import ElspaisConfig
from elspais.utilities.git import (
    detect_moved_requirements,
    filter_spec_files,
    get_git_changes,
    get_repo_root,
    get_req_locations_from_graph,
)

_SCHEMA_FIELDS = {f.alias or name for name, f in ElspaisConfig.model_fields.items()} | set(
    ElspaisConfig.model_fields.keys()
)


def _validate_config(config: dict) -> ElspaisConfig:
    """Validate a config dict into ElspaisConfig, stripping non-schema keys."""

    filtered = {k: v for k, v in config.items() if k in _SCHEMA_FIELDS}
    assoc = filtered.get("associates")
    if isinstance(assoc, dict) and "paths" in assoc:
        del filtered["associates"]
    proj = filtered.get("project", {})
    if isinstance(proj, dict) and proj.get("type") == "associated":
        if "core" not in filtered or not filtered["core"]:
            filtered["core"] = {"path": "."}
    return ElspaisConfig.model_validate(filtered)


def load_configuration(args: argparse.Namespace) -> dict | None:
    """Load configuration from file or use defaults.

    Note: This is a wrapper for get_config() that returns Optional[Dict]
    for backward compatibility. New code should use get_config() directly.
    """
    from elspais.config import get_config

    return get_config(
        config_path=getattr(args, "config", None),
    )


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

    typed_config = _validate_config(config)
    _dirs_spec = typed_config.directories.spec
    if _dirs_spec is not None:
        spec_dir = (
            _dirs_spec[0]
            if isinstance(_dirs_spec, list) and _dirs_spec
            else (_dirs_spec if isinstance(_dirs_spec, str) else "spec")
        )
    else:
        spec_dir = typed_config.spec.directories[0] if typed_config.spec.directories else "spec"

    base_branch = getattr(args, "base_branch", None) or "main"
    json_output = getattr(args, "format", "text") == "json"
    show_all = getattr(args, "all", False)
    quiet = getattr(args, "quiet", False)

    # Get git change information
    changes = get_git_changes(repo_root, spec_dir, base_branch)

    # Filter to spec files only
    spec_modified = filter_spec_files(changes.modified_files, spec_dir)
    spec_untracked = filter_spec_files(changes.untracked_files, spec_dir)
    spec_branch = filter_spec_files(changes.branch_changed_files, spec_dir)

    # Detect moved requirements using graph-based approach
    current_locations = get_req_locations_from_graph(repo_root)
    moved = detect_moved_requirements(changes.committed_req_locations, current_locations)

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
