"""
elspais.trace_view.generators.markdown - Markdown generation.

Provides functions to generate markdown traceability matrices from TraceGraph.
"""

import sys
from datetime import datetime
from typing import Dict, List, Optional

from elspais.core.graph import NodeKind, TraceGraph, TraceNode


def generate_legend_markdown() -> str:
    """Generate markdown legend section.

    Returns:
        Markdown string with legend explaining symbols
    """
    return """## Legend

**Requirement Status:**
- Active requirement
- Draft requirement
- Deprecated requirement

**Traceability:**
- Has implementation file(s)
- No implementation found

**Interactive (HTML only):**
- Expandable (has child requirements)
- Collapsed (click to expand)
"""


def generate_markdown_from_graph(
    graph: TraceGraph,
    base_path: str = "",
) -> str:
    """Generate markdown traceability matrix from TraceGraph.

    Args:
        graph: The TraceGraph to render
        base_path: Base path for links (e.g., '../' for files in subdirectory)

    Returns:
        Complete markdown traceability matrix
    """
    lines = []
    lines.append("# Requirements Traceability Matrix")

    # Count requirements
    req_nodes = [n for n in graph.all_nodes() if n.kind == NodeKind.REQUIREMENT]
    lines.append(f"\n**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**Total Requirements**: {len(req_nodes)}\n")

    # Summary by level
    by_level = _count_by_level(graph)
    lines.append("## Summary\n")
    lines.append(f"- **PRD Requirements**: {by_level['active']['PRD']}")
    lines.append(f"- **OPS Requirements**: {by_level['active']['OPS']}")
    lines.append(f"- **DEV Requirements**: {by_level['active']['DEV']}\n")

    # Add legend
    lines.append(generate_legend_markdown())

    # Full traceability tree
    lines.append("## Traceability Tree\n")

    # Start with roots (top-level requirements)
    for root in graph.roots:
        if root.kind == NodeKind.REQUIREMENT:
            lines.append(
                _format_req_tree_md(root, indent=0, ancestor_path=[], base_path=base_path)
            )

    # Orphaned requirements (those with broken parent links)
    orphaned = _find_orphaned_requirements(graph)
    if orphaned:
        lines.append("\n## Orphaned Requirements\n")
        lines.append("*(Requirements not linked from any parent)*\n")
        for node in orphaned:
            req = node.requirement
            if req:
                display_filename = node.metrics.get("display_filename", "")
                lines.append(f"- **{node.id}**: {req.title} ({req.level}) - {display_filename}")

    return "\n".join(lines)


def _count_by_level(graph: TraceGraph) -> Dict[str, Dict[str, int]]:
    """Count requirements by level, both including and excluding Deprecated.

    Args:
        graph: The TraceGraph to count

    Returns:
        Dict with 'active' (excludes Deprecated) and 'all' (includes Deprecated) counts
    """
    counts = {
        "active": {"PRD": 0, "OPS": 0, "DEV": 0},
        "all": {"PRD": 0, "OPS": 0, "DEV": 0},
    }
    for node in graph.all_nodes():
        if node.kind != NodeKind.REQUIREMENT:
            continue
        req = node.requirement
        if not req:
            continue
        level = req.level
        counts["all"][level] = counts["all"].get(level, 0) + 1
        if req.status != "Deprecated":
            counts["active"][level] = counts["active"].get(level, 0) + 1
    return counts


def _find_orphaned_requirements(graph: TraceGraph) -> List[TraceNode]:
    """Find non-PRD requirements with no parents.

    Args:
        graph: The TraceGraph to search

    Returns:
        List of orphaned requirement nodes
    """
    orphaned = []
    for node in graph.all_nodes():
        if node.kind != NodeKind.REQUIREMENT:
            continue
        req = node.requirement
        if not req:
            continue
        # PRD requirements are top-level, not orphans
        if req.level == "PRD":
            continue
        # Requirements with no parents are orphans
        if not node.parents:
            orphaned.append(node)
    return sorted(orphaned, key=lambda n: n.id)


def _format_req_tree_md(
    node: TraceNode,
    indent: int,
    ancestor_path: Optional[List[str]] = None,
    base_path: str = "",
) -> str:
    """Format requirement node and its children as markdown tree.

    Args:
        node: The requirement node to format
        indent: Current indentation level
        ancestor_path: List of requirement IDs in the current traversal path (for cycle detection)
        base_path: Base path for links

    Returns:
        Formatted markdown string
    """
    if ancestor_path is None:
        ancestor_path = []

    req = node.requirement
    if not req:
        return ""

    # Cycle detection: check if this requirement is already in our traversal path
    if node.id in ancestor_path:
        cycle_path = ancestor_path + [node.id]
        cycle_str = " -> ".join(cycle_path)
        print(f"Warning: CYCLE DETECTED: {cycle_str}", file=sys.stderr)
        return "  " * indent + f"- **CYCLE DETECTED**: {node.id} (path: {cycle_str})"

    # Safety depth limit
    MAX_DEPTH = 50
    if indent > MAX_DEPTH:
        print(f"Warning: MAX DEPTH ({MAX_DEPTH}) exceeded at {node.id}", file=sys.stderr)
        return "  " * indent + f"- **MAX DEPTH EXCEEDED**: {node.id}"

    lines = []
    prefix = "  " * indent

    # Format current requirement
    status_indicator = {
        "Active": "[Active]",
        "Draft": "[Draft]",
        "Deprecated": "[Deprecated]",
    }
    indicator = status_indicator.get(req.status, "[?]")

    # Get display info from metrics
    display_filename = node.metrics.get("display_filename", "")
    is_roadmap = node.metrics.get("is_roadmap", False)
    external_spec_path = node.metrics.get("external_spec_path")
    line_number = node.source.line if node.source else 0

    # Create link to source file with REQ anchor
    if external_spec_path:
        req_link = f"[{node.id}](file://{external_spec_path}#{node.id})"
    else:
        spec_subpath = "spec/roadmap" if is_roadmap else "spec"
        file_name = node.metrics.get("file_name", f"{display_filename}.md")
        req_link = f"[{node.id}]({base_path}{spec_subpath}/{file_name}#{node.id})"

    lines.append(
        f"{prefix}- {indicator} **{req_link}**: {req.title}\n"
        f"{prefix}  - Level: {req.level} | Status: {req.status}\n"
        f"{prefix}  - File: {display_filename}:{line_number}"
    )

    # Format implementation files as nested list with clickable links
    impl_files = node.metrics.get("implementation_files", [])
    if impl_files:
        lines.append(f"{prefix}  - **Implemented in**:")
        for file_path, line_num in impl_files:
            link = f"[{file_path}:{line_num}]({base_path}{file_path}#L{line_num})"
            lines.append(f"{prefix}    - {link}")

    # Find and format children (REQUIREMENT children only)
    children = [c for c in node.children if c.kind == NodeKind.REQUIREMENT]
    children.sort(key=lambda n: n.id)

    if children:
        # Add current req to path before recursing into children
        current_path = ancestor_path + [node.id]
        for child in children:
            lines.append(
                _format_req_tree_md(child, indent + 1, current_path, base_path)
            )

    return "\n".join(lines)


# Keep the old function name for compatibility during transition
def generate_markdown(requirements, base_path: str = "") -> str:
    """Legacy function signature - should not be called.

    This exists only for backward compatibility. The codebase should use
    generate_markdown_from_graph() instead.
    """
    raise NotImplementedError(
        "generate_markdown() is deprecated. Use generate_markdown_from_graph() with TraceGraph."
    )
