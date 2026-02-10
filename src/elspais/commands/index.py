# Implements: REQ-int-d00003 (CLI Extension)
# Implements: REQ-d00052-G
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
from elspais.graph.relations import EdgeKind


def run(args: argparse.Namespace) -> int:
    """Run the index command."""
    from elspais.config import get_config, get_spec_directories
    from elspais.graph.factory import build_graph

    spec_dir = getattr(args, "spec_dir", None)
    config_path = getattr(args, "config", None)
    mode = getattr(args, "mode", "combined")

    config = get_config(config_path)
    spec_dirs = get_spec_directories(spec_dir, config)

    scan_sponsors = mode != "core"

    graph = build_graph(
        config=config,
        spec_dirs=spec_dirs if spec_dir else None,
        config_path=config_path,
        scan_sponsors=scan_sponsors,
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
    index_req_ids = set(re.findall(r"REQ-[a-z0-9-]+", content, re.IGNORECASE))
    index_jny_ids = set(re.findall(r"JNY-[A-Za-z0-9-]+", content))

    # Get IDs from graph
    graph_req_ids = {node.id for node in graph.nodes_by_kind(NodeKind.REQUIREMENT)}
    graph_jny_ids = {node.id for node in graph.nodes_by_kind(NodeKind.USER_JOURNEY)}

    # Compare requirements
    missing_reqs = graph_req_ids - index_req_ids
    extra_reqs = index_req_ids - graph_req_ids

    # Compare journeys
    missing_jnys = graph_jny_ids - index_jny_ids
    extra_jnys = index_jny_ids - graph_jny_ids

    has_issues = False

    if missing_reqs:
        print(f"Missing requirements from INDEX.md ({len(missing_reqs)}):")
        for req_id in sorted(missing_reqs):
            print(f"  {req_id}")
        has_issues = True

    if extra_reqs:
        print(f"Extra requirements in INDEX.md ({len(extra_reqs)}):")
        for req_id in sorted(extra_reqs):
            print(f"  {req_id}")
        has_issues = True

    if missing_jnys:
        print(f"Missing journeys from INDEX.md ({len(missing_jnys)}):")
        for jny_id in sorted(missing_jnys):
            print(f"  {jny_id}")
        has_issues = True

    if extra_jnys:
        print(f"Extra journeys in INDEX.md ({len(extra_jnys)}):")
        for jny_id in sorted(extra_jnys):
            print(f"  {jny_id}")
        has_issues = True

    if not has_issues:
        req_n = len(graph_req_ids)
        jny_n = len(graph_jny_ids)
        print(f"INDEX.md is up to date ({req_n} requirements, {jny_n} journeys)")
        return 0

    return 1


def _format_table(headers: list[str], rows: list[list[str]]) -> list[str]:
    """Format a markdown table with properly padded columns.

    Computes max width for each column and pads all cells to align pipes.
    """
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(cell))

    def _pad_row(cells: list[str]) -> str:
        padded = " | ".join(cell.ljust(col_widths[i]) for i, cell in enumerate(cells))
        return f"| {padded} |"

    lines = [_pad_row(headers)]
    lines.append("| " + " | ".join("-" * w for w in col_widths) + " |")
    for row in rows:
        lines.append(_pad_row(row))
    return lines


def _make_relative(file_path: str, spec_dirs: list[Path]) -> str:
    """Make a file path relative to the first matching spec directory."""
    if not file_path:
        return ""
    for spec_dir in spec_dirs:
        try:
            return str(Path(file_path).relative_to(spec_dir))
        except ValueError:
            pass
    return str(file_path)


def _regenerate_index(graph: TraceGraph, spec_dirs: list[Path], args: argparse.Namespace) -> int:
    """Regenerate INDEX.md from graph requirements."""
    # Group by level
    by_level: dict[str, list] = {"PRD": [], "OPS": [], "DEV": [], "other": []}

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

        headers = ["ID", "Title", "File", "Hash"]
        rows = []
        for node in sorted(nodes, key=lambda n: n.id):
            file_path = _make_relative(node.source.path if node.source else "", spec_dirs)
            hash_val = node.hash or ""
            rows.append([node.id, node.get_label(), str(file_path), hash_val])

        lines.extend(_format_table(headers, rows))
        lines.append("")

    # User Journeys section
    journey_nodes = list(graph.nodes_by_kind(NodeKind.USER_JOURNEY))
    if journey_nodes:
        lines.append("## User Journeys (JNY)")
        lines.append("")

        headers = ["ID", "Title", "Actor", "File", "Addresses"]
        rows = []
        for node in sorted(journey_nodes, key=lambda n: n.id):
            actor = node.get_field("actor") or ""
            file_path = _make_relative(node.source.path if node.source else "", spec_dirs)
            addresses = sorted(
                e.source.id for e in node.iter_incoming_edges() if e.kind == EdgeKind.ADDRESSES
            )
            addr_str = ", ".join(addresses)
            rows.append([node.id, node.get_label(), actor, str(file_path), addr_str])

        lines.extend(_format_table(headers, rows))
        lines.append("")

    # Write to first spec dir
    output_path = spec_dirs[0] / "INDEX.md" if spec_dirs else Path("spec/INDEX.md")
    output_path.write_text("\n".join(lines), encoding="utf-8")

    req_count = sum(len(nodes) for nodes in by_level.values())
    jny_count = len(journey_nodes)
    print(f"Generated {output_path} ({req_count} requirements, {jny_count} journeys)")
    return 0
