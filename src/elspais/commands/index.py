# Implements: REQ-int-d00003 (CLI Extension)
"""
elspais.commands.index - INDEX.md management command.

Uses graph-based system:
- `elspais index validate` - Validate INDEX.md accuracy
- `elspais index regenerate` - Regenerate INDEX.md from requirements
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from elspais.graph.builder import TraceGraph

from elspais.graph import NodeKind


def run(args: argparse.Namespace) -> int:
    """Run the index command."""
    from elspais.config import get_config, get_spec_directories
    from elspais.graph.factory import build_graph

    spec_dir = getattr(args, "spec_dir", None)
    config_path = getattr(args, "config", None)

    config = get_config(config_path)
    spec_dirs = get_spec_directories(spec_dir, config)

    graph = build_graph(
        config=config,
        spec_dirs=spec_dirs if spec_dir else None,
        config_path=config_path,
    )

    action = getattr(args, "index_action", None)

    if action == "validate":
        return _validate_index(graph, spec_dirs, args)
    elif action == "regenerate":
        return _regenerate_index(graph, spec_dirs, args)
    else:
        print("Usage: elspais index <validate|regenerate>", file=sys.stderr)
        return 1


def _validate_index(graph: TraceGraph, spec_dirs: list[Path], args: argparse.Namespace) -> int:
    """Validate INDEX.md against graph requirements."""
    # Find INDEX.md
    index_path = None
    for spec_dir in spec_dirs:
        candidate = spec_dir / "INDEX.md"
        if candidate.exists():
            index_path = candidate
            break

    if not index_path:
        print("No INDEX.md found in spec directories.")
        print("Run 'elspais index regenerate' to create one.")
        return 1

    # Parse IDs from INDEX.md
    content = index_path.read_text()
    index_ids = set(re.findall(r"REQ-[a-z0-9-]+", content, re.IGNORECASE))

    # Get IDs from graph
    graph_ids = set()
    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        graph_ids.add(node.id)

    # Compare
    missing = graph_ids - index_ids
    extra = index_ids - graph_ids

    if missing:
        print(f"Missing from INDEX.md ({len(missing)}):")
        for req_id in sorted(missing):
            print(f"  {req_id}")

    if extra:
        print(f"Extra in INDEX.md ({len(extra)}):")
        for req_id in sorted(extra):
            print(f"  {req_id}")

    if not missing and not extra:
        print(f"INDEX.md is up to date ({len(graph_ids)} requirements)")
        return 0

    return 1 if missing or extra else 0


def _regenerate_index(graph: TraceGraph, spec_dirs: list[Path], args: argparse.Namespace) -> int:
    """Regenerate INDEX.md from graph requirements."""
    # Group by level
    by_level = {"PRD": [], "OPS": [], "DEV": [], "other": []}

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        level = (node.level or "").upper()
        if level in by_level:
            by_level[level].append(node)
        else:
            by_level["other"].append(node)

    # Generate markdown
    lines = ["# Requirements Index", ""]

    level_names = {
        "PRD": "Product Requirements (PRD)",
        "OPS": "Operations Requirements (OPS)",
        "DEV": "Development Requirements (DEV)",
        "other": "Other Requirements",
    }

    for level, title in level_names.items():
        nodes = by_level[level]
        if not nodes:
            continue

        lines.append(f"## {title}")
        lines.append("")
        lines.append("| ID | Title | File | Hash |")
        lines.append("|---|---|---|---|")

        for node in sorted(nodes, key=lambda n: n.id):
            file_path = node.source.path if node.source else ""
            # Make path relative
            if file_path:
                for spec_dir in spec_dirs:
                    try:
                        file_path = Path(file_path).relative_to(spec_dir)
                        break
                    except ValueError:
                        pass
            hash_val = node.hash or ""
            lines.append(f"| {node.id} | {node.get_label()} | {file_path} | {hash_val} |")

        lines.append("")

    # Write to first spec dir
    output_path = spec_dirs[0] / "INDEX.md" if spec_dirs else Path("spec/INDEX.md")
    output_path.write_text("\n".join(lines))

    req_count = sum(len(nodes) for nodes in by_level.values())
    print(f"Generated {output_path} ({req_count} requirements)")
    return 0
