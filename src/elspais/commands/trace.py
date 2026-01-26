# Implements: REQ-int-d00003 (CLI Extension)
"""
elspais.commands.trace - Generate traceability matrix command.

STUB: This command needs arch3 implementation.
Old implementation removed during arch3 migration.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

from elspais.arch3 import (
    DEFAULT_CONFIG,
    find_config_file,
    get_spec_directories,
    load_config,
    load_requirements_from_directories,
)
from elspais.arch3.Graph.builder import GraphBuilder, TraceGraph


def run(args: argparse.Namespace) -> int:
    """Run the trace command.

    Generates traceability output in various formats.
    """
    # Check for features not yet implemented in arch3
    use_trace_view = (
        getattr(args, "view", False)
        or getattr(args, "embed_content", False)
        or getattr(args, "edit_mode", False)
        or getattr(args, "review_mode", False)
        or getattr(args, "server", False)
    )

    if use_trace_view:
        print("Error: trace-view features not yet implemented in arch3", file=sys.stderr)
        print("Use: --format markdown|html|csv|json instead", file=sys.stderr)
        return 1

    return run_graph_trace(args)


def run_graph_trace(args: argparse.Namespace) -> int:
    """Run trace using the arch3 traceability graph."""

    # Load configuration
    config_path = getattr(args, "config", None) or find_config_file(Path.cwd())
    if config_path and config_path.exists():
        config_data = load_config(config_path).get_raw()
    else:
        config_data = dict(DEFAULT_CONFIG)

    # Get spec directories
    spec_dirs = get_spec_directories(getattr(args, "spec_dir", None), config_data)
    if not spec_dirs:
        print("Error: No spec directories found", file=sys.stderr)
        return 1

    # Parse requirements
    requirements = load_requirements_from_directories(spec_dirs, config_data)

    if not requirements:
        print("No requirements found.")
        return 1

    if not getattr(args, "quiet", False):
        print(f"Found {len(requirements)} requirements")

    # Build graph
    repo_root = spec_dirs[0].parent if spec_dirs[0].name == "spec" else Path.cwd()
    builder = GraphBuilder(repo_root=repo_root)

    # Convert requirements to graph nodes
    for req_id, req in requirements.items():
        from elspais.arch3.Graph.MDparser import ParsedContent

        # Create ParsedContent from requirement
        parsed_data = {
            "id": req.id,
            "title": req.title,
            "level": req.level,
            "status": req.status,
            "hash": req.hash,
            "implements": req.implements,
            "refines": req.refines,
            "assertions": [
                {"label": a.label, "text": a.text}
                for a in req.assertions
            ],
        }
        content = ParsedContent(
            content_type="requirement",
            start_line=req.line_number or 1,
            end_line=req.line_number or 1,
            parsed_data=parsed_data,
            raw_text="",
        )
        builder.add_parsed_content(content)

    graph = builder.build()

    # Output format
    output_format = getattr(args, "format", "markdown") or "markdown"
    output_path = getattr(args, "output", None)

    if output_format == "json" or getattr(args, "graph_json", False):
        output = format_json(graph, requirements)
    elif output_format == "csv":
        output = format_csv(graph, requirements)
    elif output_format == "html":
        output = format_html(graph, requirements)
    else:  # markdown
        output = format_markdown(graph, requirements)

    # Write output
    if output_path:
        Path(output_path).write_text(output, encoding="utf-8")
        if not getattr(args, "quiet", False):
            print(f"Wrote: {output_path}")
    else:
        print(output)

    return 0


def format_markdown(graph: TraceGraph, requirements: Dict[str, Any]) -> str:
    """Format graph as markdown traceability matrix."""
    lines = ["# Traceability Matrix", ""]
    lines.append("| ID | Title | Level | Status | Implements |")
    lines.append("|---|---|---|---|---|")

    for node in sorted(graph.roots, key=lambda n: n.id):
        req = requirements.get(node.id)
        if req:
            impl = ", ".join(req.implements) if req.implements else "-"
            lines.append(f"| {req.id} | {req.title} | {req.level} | {req.status} | {impl} |")

    return "\n".join(lines)


def format_csv(graph: TraceGraph, requirements: Dict[str, Any]) -> str:
    """Format graph as CSV."""
    lines = ["id,title,level,status,implements"]

    for node in sorted(graph.roots, key=lambda n: n.id):
        req = requirements.get(node.id)
        if req:
            impl = ";".join(req.implements) if req.implements else ""
            # Escape CSV fields
            title = req.title.replace('"', '""')
            lines.append(f'"{req.id}","{title}","{req.level}","{req.status}","{impl}"')

    return "\n".join(lines)


def format_html(graph: TraceGraph, requirements: Dict[str, Any]) -> str:
    """Format graph as basic HTML table."""
    html = """<!DOCTYPE html>
<html>
<head>
    <title>Traceability Matrix</title>
    <style>
        body { font-family: sans-serif; margin: 2em; }
        table { border-collapse: collapse; width: 100%; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #4CAF50; color: white; }
        tr:nth-child(even) { background-color: #f2f2f2; }
    </style>
</head>
<body>
    <h1>Traceability Matrix</h1>
    <table>
        <tr><th>ID</th><th>Title</th><th>Level</th><th>Status</th><th>Implements</th></tr>
"""
    for node in sorted(graph.roots, key=lambda n: n.id):
        req = requirements.get(node.id)
        if req:
            impl = ", ".join(req.implements) if req.implements else "-"
            html += f"        <tr><td>{req.id}</td><td>{req.title}</td><td>{req.level}</td><td>{req.status}</td><td>{impl}</td></tr>\n"

    html += """    </table>
</body>
</html>"""
    return html


def format_json(graph: TraceGraph, requirements: Dict[str, Any]) -> str:
    """Format graph as JSON."""
    output = {}
    for req_id, req in requirements.items():
        output[req_id] = {
            "id": req.id,
            "title": req.title,
            "level": req.level,
            "status": req.status,
            "body": req.body,
            "implements": req.implements,
            "refines": req.refines,
            "assertions": [
                {"label": a.label, "text": a.text, "is_placeholder": a.is_placeholder}
                for a in req.assertions
            ],
            "hash": req.hash,
            "file_path": str(req.file_path) if req.file_path else None,
            "line_number": req.line_number,
        }
    return json.dumps(output, indent=2)
