# Implements: REQ-int-d00003 (CLI Extension)
"""
elspais.commands.analyze - Analyze requirements command.

Uses graph-based system for analysis:
- `elspais analyze hierarchy` - Display requirement hierarchy tree
- `elspais analyze orphans` - Find orphaned requirements
- `elspais analyze coverage` - Show implementation coverage report
"""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from elspais.graph.builder import TraceGraph

from elspais.graph import GraphNode, NodeKind


def run(args: argparse.Namespace) -> int:
    """Run the analyze command."""
    from elspais.graph.factory import build_graph

    spec_dir = getattr(args, "spec_dir", None)
    config_path = getattr(args, "config", None)

    graph = build_graph(
        spec_dirs=[spec_dir] if spec_dir else None,
        config_path=config_path,
    )

    action = getattr(args, "analyze_action", None)

    if action == "hierarchy":
        return _analyze_hierarchy(graph, args)
    elif action == "orphans":
        return _analyze_orphans(graph, args)
    elif action == "coverage":
        return _analyze_coverage(graph, args)
    else:
        print("Usage: elspais analyze <hierarchy|orphans|coverage>", file=sys.stderr)
        return 1


def _analyze_hierarchy(graph: TraceGraph, args: argparse.Namespace) -> int:
    """Display requirement hierarchy tree."""
    print("Requirement Hierarchy")
    print("=" * 60)

    # Find root requirements (PRD level or no parents)
    roots = []
    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        level = (node.level or "").upper()
        if level == "PRD" or node.parent_count() == 0:
            # Check if this has no parent requirements
            has_req_parent = False
            for parent in node.iter_parents():
                if parent.kind == NodeKind.REQUIREMENT:
                    has_req_parent = True
                    break
            if not has_req_parent:
                roots.append(node)

    for root in sorted(roots, key=lambda n: n.id):
        _print_tree(root, indent=0)

    return 0


def _print_tree(node: GraphNode, indent: int) -> None:
    """Recursively print node and children."""
    prefix = "  " * indent
    status_icon = "[x]" if (node.status or "").lower() == "active" else "[ ]"
    level = node.level or "?"
    print(f"{prefix}{status_icon} {node.id} ({level}) - {node.get_label()}")

    # Get child requirements
    children = []
    for child in node.iter_children():
        if child.kind == NodeKind.REQUIREMENT:
            children.append(child)

    for child in sorted(children, key=lambda n: n.id):
        _print_tree(child, indent + 1)


def _analyze_orphans(graph: TraceGraph, args: argparse.Namespace) -> int:
    """Find orphaned nodes across all kinds.

    Uses graph.orphaned_nodes() which returns all parentless nodes
    that have no meaningful (non-satellite) children.
    """
    by_kind: dict[str, list] = {}

    for node in graph.orphaned_nodes():
        kind_name = node.kind.value
        if kind_name not in by_kind:
            by_kind[kind_name] = []
        by_kind[kind_name].append(node)

    total = sum(len(nodes) for nodes in by_kind.values())

    if total:
        print(f"Found {total} orphaned nodes:")
        for kind_name in sorted(by_kind):
            nodes = by_kind[kind_name]
            print(f"\n  {kind_name} ({len(nodes)}):")
            for node in sorted(nodes, key=lambda n: n.id):
                loc = f"{node.source.path}:{node.source.line}" if node.source else "unknown"
                detail = f" ({node.level or '?'})" if node.kind == NodeKind.REQUIREMENT else ""
                print(f"    {node.id}{detail} - {node.get_label()}")
                print(f"      Location: {loc}")
    else:
        print("No orphaned nodes found.")

    return 1 if total else 0


def _analyze_coverage(graph: TraceGraph, args: argparse.Namespace) -> int:
    """Show implementation coverage report."""
    from elspais.graph.annotators import group_by_level

    # Group requirements by level using shared utility
    by_level = group_by_level(graph)

    print("Requirements by Level")
    print("=" * 40)
    for level, nodes in by_level.items():
        if nodes:
            print(f"  {level}: {len(nodes)}")

    # PRD implementation coverage
    prd_nodes = by_level["PRD"]
    if prd_nodes:
        print()
        print("PRD Implementation Coverage")
        print("-" * 40)

        implemented = []
        unimplemented = []

        for prd in prd_nodes:
            has_children = False
            for child in prd.iter_children():
                if child.kind == NodeKind.REQUIREMENT:
                    has_children = True
                    break
            if has_children:
                implemented.append(prd)
            else:
                unimplemented.append(prd)

        pct = len(implemented) / len(prd_nodes) * 100 if prd_nodes else 0
        print(f"  Implemented: {len(implemented)}/{len(prd_nodes)} ({pct:.1f}%)")

        if unimplemented:
            print()
            print("  Unimplemented PRD requirements:")
            for node in sorted(unimplemented, key=lambda n: n.id):
                print(f"    {node.id} - {node.get_label()}")

    return 0
