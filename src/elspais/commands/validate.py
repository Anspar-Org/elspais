# Implements: REQ-int-d00003 (CLI Extension)
"""
elspais.commands.validate - Validate requirements format and relationships.

Uses the graph-based system for validation. Commands only work with graph data.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from elspais.graph.builder import TraceGraph

from elspais.graph import NodeKind


def run(args: argparse.Namespace) -> int:
    """Run the validate command.

    Uses graph factory to build TraceGraph, then validates requirements.
    """
    from elspais.graph.factory import build_graph

    spec_dir = getattr(args, "spec_dir", None)
    config_path = getattr(args, "config", None)

    graph = build_graph(
        spec_dirs=[spec_dir] if spec_dir else None,
        config_path=config_path,
    )

    # Collect validation issues
    errors = []
    warnings = []

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        # Check for orphan requirements (no parents except roots)
        if node.parent_count() == 0 and node.level not in ("PRD", "prd"):
            warnings.append({
                "rule": "hierarchy.orphan",
                "id": node.id,
                "message": f"Requirement {node.id} has no parent (orphan)",
            })

        # Check for hash presence
        if not node.hash:
            warnings.append({
                "rule": "hash.missing",
                "id": node.id,
                "message": f"Requirement {node.id} is missing a hash",
            })

    # Filter by skip rules
    skip_rules = getattr(args, "skip_rule", None) or []
    if skip_rules:
        import fnmatch
        errors = [e for e in errors if not any(fnmatch.fnmatch(e["rule"], p) for p in skip_rules)]
        warnings = [w for w in warnings if not any(fnmatch.fnmatch(w["rule"], p) for p in skip_rules)]

    # Count requirements
    req_count = sum(1 for _ in graph.nodes_by_kind(NodeKind.REQUIREMENT))

    # Output results
    if getattr(args, "json", False):
        result = {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "requirements_count": req_count,
        }
        print(json.dumps(result, indent=2))
    else:
        if not getattr(args, "quiet", False):
            print(f"Validated {req_count} requirements")

        for err in errors:
            print(f"ERROR [{err['rule']}] {err['id']}: {err['message']}", file=sys.stderr)

        for warn in warnings:
            print(f"WARNING [{warn['rule']}] {warn['id']}: {warn['message']}", file=sys.stderr)

        if errors:
            print(f"\n{len(errors)} errors, {len(warnings)} warnings", file=sys.stderr)
        elif warnings:
            print(f"\n{len(warnings)} warnings", file=sys.stderr)

    return 1 if errors else 0
