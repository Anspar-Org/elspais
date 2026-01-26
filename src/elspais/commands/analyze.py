"""
elspais.commands.analyze - Analyze requirements command.

Uses TraceGraphBuilder for hierarchy analysis, replacing legacy hierarchy.py.
"""

import argparse
import sys
from pathlib import Path
from typing import Dict, Optional

from elspais.arch3 import (
    DEFAULT_CONFIG,
    NodeKind,
    Requirement,
    find_config_file,
    get_spec_directories,
    load_config,
    load_requirements_from_directories,
)
from elspais.arch3.Graph import GraphNode
from elspais.arch3.Graph.builder import GraphBuilder, TraceGraph


def run(args: argparse.Namespace) -> int:
    """Run the analyze command."""
    if not args.analyze_action:
        print("Usage: elspais analyze {hierarchy|orphans|coverage}")
        return 1

    if args.analyze_action == "hierarchy":
        return run_hierarchy(args)
    elif args.analyze_action == "orphans":
        return run_orphans(args)
    elif args.analyze_action == "coverage":
        return run_coverage(args)

    return 1


def run_hierarchy(args: argparse.Namespace) -> int:
    """Show requirement hierarchy tree using TraceGraph."""
    requirements, graph = load_requirements_with_graph(args)
    if not requirements or not graph:
        return 1

    print("Requirement Hierarchy")
    print("=" * 60)

    # Get root nodes from graph
    roots = [
        node
        for node in graph.roots
        if node.kind == NodeKind.REQUIREMENT
    ]

    if not roots:
        print("No root requirements found")
        return 0

    printed = set()

    def print_tree(node: GraphNode, indent: int = 0) -> None:
        if node.id in printed:
            return
        printed.add(node.id)

        prefix = "  " * indent
        req = node.requirement
        if req:
            status_icon = "✓" if req.status == "Active" else "○"
            print(f"{prefix}{status_icon} {req.id}: {req.title}")
        else:
            print(f"{prefix}○ {node.id}")

        # Find children from graph (requirements that implement this one)
        for child in node.children:
            if child.kind == NodeKind.REQUIREMENT:
                print_tree(child, indent + 1)

    for root in sorted(roots, key=lambda n: n.id):
        print_tree(root)
        print()

    return 0


def run_orphans(args: argparse.Namespace) -> int:
    """Find orphaned requirements using TraceGraph validation."""
    requirements, graph = load_requirements_with_graph(args)
    if not requirements or not graph:
        return 1

    # Build orphan list - non-root requirements with no parents
    orphans = []
    for node in graph.all_nodes():
        if node.kind != NodeKind.REQUIREMENT:
            continue

        # Skip root nodes (PRD level)
        if node in graph.roots:
            continue

        # Check if has no parents in the graph
        parent_reqs = [p for p in node.parents if p.kind == NodeKind.REQUIREMENT]
        if not parent_reqs:
            if node.requirement:
                orphans.append(node.requirement)

    if orphans:
        print(f"Orphaned Requirements ({len(orphans)}):")
        print("-" * 40)
        for req in sorted(orphans, key=lambda r: r.id):
            impl_str = ", ".join(req.implements) if req.implements else "(none)"
            print(f"  {req.id}: {req.title}")
            print(f"    Level: {req.level} | Implements: {impl_str}")
            if req.file_path:
                print(f"    File: {req.file_path.name}:{req.line_number}")
            print()
    else:
        print("✓ No orphaned requirements found")

    return 0


def run_coverage(args: argparse.Namespace) -> int:
    """Show implementation coverage report using TraceGraph."""
    requirements, graph = load_requirements_with_graph(args)
    if not requirements or not graph:
        return 1

    # Group by type
    prd_count = sum(1 for r in requirements.values() if r.level.upper() in ["PRD", "PRODUCT"])
    ops_count = sum(1 for r in requirements.values() if r.level.upper() in ["OPS", "OPERATIONS"])
    dev_count = sum(1 for r in requirements.values() if r.level.upper() in ["DEV", "DEVELOPMENT"])

    # Count PRD requirements that have implementations (children in the graph)
    implemented_prd = set()
    for node in graph.all_nodes():
        if node.kind != NodeKind.REQUIREMENT:
            continue
        if not node.requirement:
            continue
        if node.requirement.level.upper() not in ["PRD", "PRODUCT"]:
            continue

        # Check if this PRD has any REQ children (implementers)
        for child in node.children:
            if child.kind == NodeKind.REQUIREMENT:
                implemented_prd.add(node.id)
                break

    print("Implementation Coverage Report")
    print("=" * 60)
    print()
    print(f"Total Requirements: {len(requirements)}")
    print(f"  PRD: {prd_count}")
    print(f"  OPS: {ops_count}")
    print(f"  DEV: {dev_count}")
    print()
    print("PRD Implementation Coverage:")
    print(f"  Implemented: {len(implemented_prd)}/{prd_count}")
    if prd_count > 0:
        pct = (len(implemented_prd) / prd_count) * 100
        print(f"  Coverage: {pct:.1f}%")

    # List unimplemented PRD
    unimplemented = [
        req
        for req in requirements.values()
        if req.level.upper() in ["PRD", "PRODUCT"] and req.id not in implemented_prd
    ]

    if unimplemented:
        print()
        print(f"Unimplemented PRD ({len(unimplemented)}):")
        for req in sorted(unimplemented, key=lambda r: r.id):
            print(f"  - {req.id}: {req.title}")

    return 0


def load_requirements(args: argparse.Namespace) -> Dict[str, Requirement]:
    """Load requirements from spec directories."""
    requirements, _ = load_requirements_with_graph(args)
    return requirements


def load_requirements_with_graph(
    args: argparse.Namespace,
) -> tuple[Dict[str, Requirement], Optional[TraceGraph]]:
    """Load requirements and build TraceGraph from spec directories.

    Args:
        args: Command arguments with config and spec_dir options

    Returns:
        Tuple of (requirements dict, TraceGraph) or ({}, None) on error
    """
    config_path = args.config or find_config_file(Path.cwd())
    if config_path and config_path.exists():
        config = load_config(config_path)
    else:
        config = DEFAULT_CONFIG

    spec_dirs = get_spec_directories(args.spec_dir, config)
    if not spec_dirs:
        print("Error: No spec directories found", file=sys.stderr)
        return {}, None

    try:
        requirements = load_requirements_from_directories(spec_dirs, config)
        if not requirements:
            return {}, None

        # Build graph
        repo_root = spec_dirs[0].parent if spec_dirs[0].name == "spec" else Path.cwd()
        builder = GraphBuilder(repo_root=repo_root)
        builder.add_requirements(requirements)
        graph = builder.build()

        return requirements, graph
    except Exception as e:
        print(f"Error parsing requirements: {e}", file=sys.stderr)
        return {}, None
