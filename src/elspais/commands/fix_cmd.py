# Implements: REQ-p00004-A
"""
elspais.commands.fix_cmd - Auto-fix spec file issues.

Delegates to ``validate.run()`` with ``fix=True``.  For targeted
single-requirement hash updates, uses shared utilities directly.
``validate`` only reports issues; ``fix`` only fixes them.
"""

from __future__ import annotations

import argparse
import sys


def run(args: argparse.Namespace) -> int:
    """Run the fix command.

    - fix (no req_id): validate --fix for all fixable issues
    - fix REQ-xxx:     targeted hash update for a single requirement
    """
    target_req_id = getattr(args, "req_id", None)

    if target_req_id:
        return _fix_single(args, target_req_id)

    from elspais.commands import validate

    return validate.run(_make_validate_args(args))


def _make_validate_args(args: argparse.Namespace) -> argparse.Namespace:
    """Build a validate-compatible args namespace from fix args."""
    return argparse.Namespace(
        # Shared CLI args
        spec_dir=getattr(args, "spec_dir", None),
        config=getattr(args, "config", None),
        canonical_root=getattr(args, "canonical_root", None),
        quiet=getattr(args, "quiet", False),
        verbose=getattr(args, "verbose", False),
        # Validate mode
        mode=getattr(args, "mode", "combined"),
        json=False,
        export=False,
        skip_rule=None,
        # Fix mode — always on
        fix=True,
        dry_run=getattr(args, "dry_run", False),
    )


def _fix_single(args: argparse.Namespace, req_id: str) -> int:
    """Fix hash for a single requirement using shared utilities."""
    from pathlib import Path

    from elspais.commands.validate import compute_hash_for_node
    from elspais.graph import NodeKind
    from elspais.graph.factory import build_graph
    from elspais.mcp.file_mutations import update_hash_in_file

    spec_dir = getattr(args, "spec_dir", None)
    config_path = getattr(args, "config", None)
    canonical_root = getattr(args, "canonical_root", None)
    dry_run = getattr(args, "dry_run", False)
    repo_root = Path(spec_dir).parent if spec_dir else Path.cwd()

    graph = build_graph(
        spec_dirs=[spec_dir] if spec_dir else None,
        config_path=config_path,
        repo_root=repo_root,
        scan_code=False,
        scan_tests=False,
        canonical_root=canonical_root,
    )

    hash_mode = getattr(graph, "hash_mode", "full-text")

    # Find the target node
    node = None
    for n in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        if n.id == req_id:
            node = n
            break

    if node is None:
        print(f"Error: Requirement {req_id} not found", file=sys.stderr)
        return 1

    computed = compute_hash_for_node(node, hash_mode)
    if not computed:
        print(f"No hashable content for {req_id}")
        return 0

    stored = node.hash
    if stored == computed:
        print(f"{req_id} hash is already up to date")
        return 0

    if dry_run:
        print(f"Would update {req_id}: {stored or '(none)'} -> {computed}")
        return 0

    source = node.source
    if source is None:
        print(f"Error: No source file for {req_id}", file=sys.stderr)
        return 1

    file_path = repo_root / source.path
    error = update_hash_in_file(file_path=file_path, req_id=req_id, new_hash=computed)
    if error is None:
        print(f"Updated {req_id}: {stored or '(none)'} -> {computed}")
        return 0
    else:
        print(f"Error: {error}", file=sys.stderr)
        return 1
