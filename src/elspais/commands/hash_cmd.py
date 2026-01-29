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


def _verify_hashes(graph, args) -> int:
    """Verify all hashes match content."""
    from elspais.utilities.hasher import calculate_hash

    mismatches = []
    missing = []

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        stored_hash = node.hash
        if not stored_hash:
            missing.append(node.id)
            continue

        # Get body content from the node
        body = node.get_field("body", "")
        if body:
            computed = calculate_hash(body)
            if computed != stored_hash:
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
    """Update hashes (not yet implemented - requires file mutation)."""
    _ = getattr(args, "req_id", None)  # Reserved for future use
    _ = getattr(args, "dry_run", False)  # Reserved for future use

    print("Hash update requires file mutation which is not yet implemented.", file=sys.stderr)
    print("Use 'elspais validate --fix' for automated hash updates.", file=sys.stderr)
    return 1
