# Implements: REQ-int-d00003 (CLI Extension)
"""
elspais.commands.validate - Validate requirements format and relationships.

Uses the graph-based system for validation. Commands only work with graph data.
Supports --fix to auto-fix certain issues (hashes, status).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

from elspais.graph import NodeKind


def _get_requirement_body(node) -> str:
    """Extract hashable body content from a requirement node.

    The body is computed from assertion texts (the SHALL statements).
    """
    assertions = []
    for child in node.iter_children():
        if child.kind == NodeKind.ASSERTION:
            label = child.get_field("label", "")
            text = child.get_label() or ""
            if label and text:
                assertions.append(f"{label}. {text}")
    return "\n\n".join(assertions)


def run(args: argparse.Namespace) -> int:
    """Run the validate command.

    Uses graph factory to build TraceGraph, then validates requirements.
    Supports --fix to auto-fix certain issues.
    """
    from elspais.graph.factory import build_graph
    from elspais.utilities.hasher import calculate_hash

    spec_dir = getattr(args, "spec_dir", None)
    config_path = getattr(args, "config", None)
    fix_mode = getattr(args, "fix", False)
    dry_run = getattr(args, "dry_run", False)

    # Get repo root from spec_dir or cwd
    repo_root = Path(spec_dir).parent if spec_dir else Path.cwd()

    graph = build_graph(
        spec_dirs=[spec_dir] if spec_dir else None,
        config_path=config_path,
        repo_root=repo_root,
    )

    # Collect validation issues
    errors = []
    warnings = []
    fixable = []  # Issues that can be auto-fixed

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        # Check for orphan requirements (no parents except roots)
        if node.parent_count() == 0 and node.level not in ("PRD", "prd"):
            warnings.append(
                {
                    "rule": "hierarchy.orphan",
                    "id": node.id,
                    "message": f"Requirement {node.id} has no parent (orphan)",
                }
            )

        # Check for hash presence and correctness
        body = _get_requirement_body(node)
        if body:
            computed_hash = calculate_hash(body)
            stored_hash = node.hash

            if not stored_hash:
                # Missing hash - fixable
                issue = {
                    "rule": "hash.missing",
                    "id": node.id,
                    "message": f"Requirement {node.id} is missing a hash",
                    "fixable": True,
                    "fix_type": "hash",
                    "computed_hash": computed_hash,
                    "file": str(repo_root / node.source.path) if node.source else None,
                }
                warnings.append(issue)
                if issue["file"]:
                    fixable.append(issue)
            elif stored_hash != computed_hash:
                # Hash mismatch - fixable
                issue = {
                    "rule": "hash.mismatch",
                    "id": node.id,
                    "message": f"Requirement {node.id} hash mismatch: "
                    f"stored={stored_hash} computed={computed_hash}",
                    "fixable": True,
                    "fix_type": "hash",
                    "computed_hash": computed_hash,
                    "file": str(repo_root / node.source.path) if node.source else None,
                }
                warnings.append(issue)
                if issue["file"]:
                    fixable.append(issue)
        elif not node.hash:
            # No body and no hash
            warnings.append(
                {
                    "rule": "hash.missing",
                    "id": node.id,
                    "message": f"Requirement {node.id} is missing a hash",
                }
            )

    # Filter by skip rules
    skip_rules = getattr(args, "skip_rule", None) or []
    if skip_rules:
        import fnmatch

        errors = [e for e in errors if not any(fnmatch.fnmatch(e["rule"], p) for p in skip_rules)]
        warnings = [
            w for w in warnings if not any(fnmatch.fnmatch(w["rule"], p) for p in skip_rules)
        ]
        fixable = [f for f in fixable if not any(fnmatch.fnmatch(f["rule"], p) for p in skip_rules)]

    # Handle --fix mode
    fixed_count = 0
    if fix_mode and fixable:
        fixed_count = _apply_fixes(fixable, dry_run)

    # Count requirements
    req_count = sum(1 for _ in graph.nodes_by_kind(NodeKind.REQUIREMENT))

    # Output results
    if getattr(args, "json", False):
        result = {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "requirements_count": req_count,
            "fixed_count": fixed_count if fix_mode else 0,
        }
        print(json.dumps(result, indent=2))
    else:
        if not getattr(args, "quiet", False):
            print(f"Validated {req_count} requirements")

        # Show fix results
        if fix_mode:
            if dry_run:
                if fixable:
                    print(f"Would fix {len(fixable)} issue(s):")
                    for f in fixable:
                        print(f"  {f['id']}: {f['rule']}")
                else:
                    print("No fixable issues found.")
            else:
                if fixed_count > 0:
                    print(f"Fixed {fixed_count} issue(s)")

        for err in errors:
            print(f"ERROR [{err['rule']}] {err['id']}: {err['message']}", file=sys.stderr)

        # Only show unfixed warnings
        unfixed_warnings = [w for w in warnings if not w.get("fixable") or not fix_mode]
        for warn in unfixed_warnings:
            print(
                f"WARNING [{warn['rule']}] {warn['id']}: {warn['message']}",
                file=sys.stderr,
            )

        if errors:
            print(
                f"\n{len(errors)} errors, {len(unfixed_warnings)} warnings",
                file=sys.stderr,
            )
        elif unfixed_warnings:
            print(f"\n{len(unfixed_warnings)} warnings", file=sys.stderr)

    return 1 if errors else 0


def _apply_fixes(fixable: list[dict], dry_run: bool) -> int:
    """Apply fixes to spec files.

    Args:
        fixable: List of fixable issues with fix metadata.
        dry_run: If True, don't actually modify files.

    Returns:
        Number of issues fixed.
    """
    if dry_run:
        return 0

    from elspais.mcp.file_mutations import add_status_to_file, update_hash_in_file

    fixed = 0
    for issue in fixable:
        fix_type = issue.get("fix_type")
        file_path = issue.get("file")

        if not file_path:
            continue

        if fix_type == "hash":
            # Fix hash (missing or mismatch)
            success = update_hash_in_file(
                file_path=Path(file_path),
                req_id=issue["id"],
                new_hash=issue["computed_hash"],
            )
            if success:
                fixed += 1

        elif fix_type == "status":
            # Add missing status
            success = add_status_to_file(
                file_path=Path(file_path),
                req_id=issue["id"],
                status=issue.get("status", "Active"),
            )
            if success:
                fixed += 1

    return fixed
