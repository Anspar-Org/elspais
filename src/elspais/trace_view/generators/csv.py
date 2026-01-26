"""
elspais.trace_view.generators.csv - CSV generation.

Provides functions to generate CSV traceability matrices from TraceGraph.
"""

import csv
from io import StringIO

from elspais.core.graph import NodeKind, TraceGraph


def generate_csv(graph: TraceGraph) -> str:
    """Generate CSV traceability matrix from TraceGraph.

    Args:
        graph: The TraceGraph to render

    Returns:
        CSV string with columns: Requirement ID, Title, Level, Status,
        Implements, Traced By, File, Line, Implementation Files
    """
    output = StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow(
        [
            "Requirement ID",
            "Title",
            "Level",
            "Status",
            "Implements",
            "Traced By",
            "File",
            "Line",
            "Implementation Files",
        ]
    )

    # Collect requirement nodes
    req_nodes = [n for n in graph.all_nodes() if n.kind == NodeKind.REQUIREMENT]
    req_nodes.sort(key=lambda n: n.id)

    for node in req_nodes:
        req = node.requirement
        if not req:
            continue

        # Get children (traced by) from graph - only REQUIREMENT children
        children_ids = [c.id for c in node.children if c.kind == NodeKind.REQUIREMENT]

        # Get implementation files from metrics
        impl_files = node.metrics.get("implementation_files", [])
        impl_files_str = (
            ", ".join([f"{path}:{line}" for path, line in impl_files])
            if impl_files
            else "-"
        )

        # Get display info from metrics
        display_filename = node.metrics.get("display_filename", "")
        line_number = node.source.line if node.source else 0

        writer.writerow(
            [
                node.id,
                req.title,
                req.level,
                req.status,
                ", ".join(req.implements) if req.implements else "-",
                ", ".join(sorted(children_ids)) if children_ids else "-",
                display_filename,
                line_number,
                impl_files_str,
            ]
        )

    return output.getvalue()


def generate_planning_csv(graph: TraceGraph) -> str:
    """Generate CSV for sprint planning (actionable items only) from TraceGraph.

    Args:
        graph: The TraceGraph to render

    Returns:
        CSV with columns: REQ ID, Title, Level, Status, Impl Status, Coverage, Code Refs
        Includes only actionable items (Active or Draft status, not deprecated)
    """
    output = StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow(["REQ ID", "Title", "Level", "Status", "Impl Status", "Coverage", "Code Refs"])

    # Filter to actionable requirements (Active or Draft status)
    req_nodes = [
        n for n in graph.all_nodes()
        if n.kind == NodeKind.REQUIREMENT
        and n.requirement
        and n.requirement.status in ["Active", "Draft"]
    ]

    # Sort by ID
    req_nodes.sort(key=lambda n: n.id)

    for node in req_nodes:
        req = node.requirement
        if not req:
            continue

        # Get implementation status from coverage metrics
        coverage_pct = node.metrics.get("coverage_pct", 0)
        if coverage_pct >= 100:
            impl_status = "Full"
        elif coverage_pct > 0:
            impl_status = "Partial"
        else:
            impl_status = "Unimplemented"

        # Get coverage from metrics
        total_assertions = node.metrics.get("total_assertions", 0)
        covered_assertions = node.metrics.get("covered_assertions", 0)
        coverage_str = f"{covered_assertions}/{total_assertions}"

        # Get code refs from implementation files
        impl_files = node.metrics.get("implementation_files", [])
        code_refs = len(impl_files)

        writer.writerow(
            [
                node.id,
                req.title,
                req.level,
                req.status,
                impl_status,
                coverage_str,
                code_refs,
            ]
        )

    return output.getvalue()
