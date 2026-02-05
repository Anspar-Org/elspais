# Implements: REQ-int-d00003 (CLI Extension)
"""
elspais.commands.hash_cmd - Manage requirement hashes.

Uses the graph-based system for hash verification and updates.
"""

from __future__ import annotations

import argparse
import sys

from elspais.graph import NodeKind


def run(args: argparse.Namespace) -> int:
    """Run the hash command.

    Subcommands:
    - verify: Check hashes match content
    - update: Recalculate and update hashes
    """
    from elspais.graph.factory import build_graph

    spec_dir = getattr(args, "spec_dir", None)
    config_path = getattr(args, "config", None)

    graph = build_graph(
        spec_dirs=[spec_dir] if spec_dir else None,
        config_path=config_path,
    )

    action = getattr(args, "hash_action", None)

    if action == "verify":
        return _verify_hashes(graph, args)
    elif action == "update":
        return _update_hashes(graph, args)
    else:
        print("Usage: elspais hash <verify|update>", file=sys.stderr)
        return 1


def _compute_hash_for_node(node, hash_mode: str) -> str | None:
    """Compute the content hash for a requirement node.

    Supports two modes (per spec/requirements-spec.md Hash Definition):
    - full-text: hash every line between header and footer (body_text)
    - normalized-text: hash normalized assertion text only

    Args:
        node: The requirement GraphNode.
        hash_mode: Hash calculation mode ("full-text" or "normalized-text").

    Returns:
        Computed hash string, or None if no hashable content.
    """
    from elspais.utilities.hasher import calculate_hash, compute_normalized_hash

    if hash_mode == "normalized-text":
        assertions = []
        for child in node.iter_children():
            if child.kind == NodeKind.ASSERTION:
                label = child.get_field("label", "")
                text = child.get_label() or ""
                if label and text:
                    assertions.append((label, text))
        if not assertions:
            return None
        return compute_normalized_hash(assertions)
    else:
        body = node.get_field("body_text", "")
        if not body:
            return None
        return calculate_hash(body)


def _verify_hashes(graph, args) -> int:
    """Verify all hashes match content."""
    hash_mode = getattr(graph, "hash_mode", "full-text")

    mismatches = []
    missing = []

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        stored_hash = node.hash
        if not stored_hash:
            missing.append(node.id)
            continue

        computed = _compute_hash_for_node(node, hash_mode)
        if computed and computed != stored_hash:
            mismatches.append(
                {
                    "id": node.id,
                    "stored": stored_hash,
                    "computed": computed,
                }
            )

    # Report results
    if not getattr(args, "quiet", False):
        if missing:
            print(f"Missing hashes: {len(missing)}")
            for req_id in missing[:10]:  # Show first 10
                print(f"  {req_id}")
            if len(missing) > 10:
                print(f"  ... and {len(missing) - 10} more")

        if mismatches:
            print(f"Hash mismatches: {len(mismatches)}")
            for m in mismatches[:10]:
                print(f"  {m['id']}: stored={m['stored']} computed={m['computed']}")
            if len(mismatches) > 10:
                print(f"  ... and {len(mismatches) - 10} more")

        if not missing and not mismatches:
            print("All hashes valid")

    return 1 if mismatches else 0


def _update_hashes(graph, args) -> int:
    """Update hashes in spec files.

    Finds requirements with mismatched hashes and updates them.
    Supports --dry-run to preview changes without applying them.
    Supports --req-id to update a specific requirement only.
    """
    from pathlib import Path

    from elspais.mcp.file_mutations import update_hash_in_file

    dry_run = getattr(args, "dry_run", False)
    target_req_id = getattr(args, "req_id", None)
    json_output = getattr(args, "json_output", False)
    hash_mode = getattr(graph, "hash_mode", "full-text")

    # Get repo root from graph or default to cwd
    repo_root = getattr(graph, "_repo_root", None) or Path.cwd()

    updates = []
    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        # Filter to specific requirement if requested
        if target_req_id and node.id != target_req_id:
            continue

        stored_hash = node.hash
        computed_hash = _compute_hash_for_node(node, hash_mode)

        # Skip if no hashable content
        if not computed_hash:
            continue

        # Check if hash needs updating
        if stored_hash != computed_hash:
            # Get file path from source location
            source = node.source
            if source is None:
                continue

            file_path = Path(repo_root) / source.path

            updates.append(
                {
                    "id": node.id,
                    "old_hash": stored_hash or "(none)",
                    "new_hash": computed_hash,
                    "file": str(file_path),
                }
            )

    # Handle dry run
    if dry_run:
        if json_output:
            import json

            print(json.dumps({"updates": updates, "count": len(updates)}, indent=2))
        else:
            if not updates:
                print("All hashes are up to date.")
            else:
                print(f"Would update {len(updates)} hash(es):")
                for u in updates:
                    print(f"  {u['id']}: {u['old_hash']} -> {u['new_hash']}")
        return 0

    # Apply updates
    updated_count = 0
    for u in updates:
        success = update_hash_in_file(
            file_path=Path(u["file"]),
            req_id=u["id"],
            new_hash=u["new_hash"],
        )
        if success:
            updated_count += 1
            if not json_output:
                print(f"Updated {u['id']}: {u['old_hash']} -> {u['new_hash']}")

    if json_output:
        import json

        print(json.dumps({"updated": updated_count, "total": len(updates)}, indent=2))
    else:
        if updated_count == 0:
            print("No hashes needed updating.")
        else:
            print(f"Updated {updated_count} hash(es).")

    return 0
