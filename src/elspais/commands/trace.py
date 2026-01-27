# Implements: REQ-int-d00003 (CLI Extension)
"""
elspais.commands.trace - Generate traceability matrix command.

Uses the graph-based system to generate traceability reports in various formats.
Commands only work with graph data (zero file I/O for reading requirements).

OUTPUT FORMATS:
- markdown: Table with ID, Title, Level, Status, Implements columns
- csv: Same columns, comma-separated with proper escaping
- html: Basic styled HTML table
- json: Full requirement data including body, assertions, hash, file_path
- both: Generates both markdown and csv (legacy mode)

INTERACTIVE VIEW (--view):
- Uses elspais.html.HTMLGenerator
- Generates interactive HTML with collapsible hierarchy
- Default output: traceability_view.html
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Iterator

if TYPE_CHECKING:
    from elspais.graph.builder import TraceGraph

from elspais.graph import NodeKind
from elspais.graph.relations import EdgeKind


def format_markdown(graph: TraceGraph) -> Iterator[str]:
    """Generate markdown table. Streams one node at a time."""
    yield "# Traceability Matrix"
    yield ""
    yield "| ID | Title | Level | Status | Implements |"
    yield "|----|-------|-------|--------|------------|"

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        # Use iterator API for edges - get parents (what this node implements)
        impl_ids = []
        for parent in node.iter_parents():
            if parent.kind == NodeKind.REQUIREMENT:
                impl_ids.append(parent.id)
        impl = ", ".join(impl_ids) or "-"
        yield f"| {node.id} | {node.label} | {node.level or ''} | {node.status or ''} | {impl} |"


def format_csv(graph: TraceGraph) -> Iterator[str]:
    """Generate CSV. Streams one node at a time."""

    def escape(s: str) -> str:
        if "," in s or '"' in s or "\n" in s:
            return '"' + s.replace('"', '""') + '"'
        return s

    yield "id,title,level,status,implements"

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        impl_ids = []
        for parent in node.iter_parents():
            if parent.kind == NodeKind.REQUIREMENT:
                impl_ids.append(parent.id)
        impl = ";".join(impl_ids)
        yield ",".join([
            escape(node.id),
            escape(node.label or ""),
            escape(node.level or ""),
            escape(node.status or ""),
            escape(impl),
        ])


def format_html(graph: TraceGraph) -> Iterator[str]:
    """Generate basic HTML table. Streams one node at a time."""
    yield "<!DOCTYPE html>"
    yield "<html><head><style>"
    yield "table { border-collapse: collapse; width: 100%; }"
    yield "th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }"
    yield "th { background-color: #4CAF50; color: white; }"
    yield "tr:nth-child(even) { background-color: #f2f2f2; }"
    yield "</style></head><body>"
    yield "<h1>Traceability Matrix</h1>"
    yield "<table>"
    yield "<tr><th>ID</th><th>Title</th><th>Level</th><th>Status</th><th>Implements</th></tr>"

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        impl_ids = []
        for parent in node.iter_parents():
            if parent.kind == NodeKind.REQUIREMENT:
                impl_ids.append(parent.id)
        impl = ", ".join(impl_ids) or "-"
        # Escape HTML special characters
        title = (node.label or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        yield f"<tr><td>{node.id}</td><td>{title}</td><td>{node.level or ''}</td><td>{node.status or ''}</td><td>{impl}</td></tr>"

    yield "</table></body></html>"


def format_json(graph: TraceGraph) -> Iterator[str]:
    """Generate JSON array. Streams one node at a time."""
    yield "["
    first = True
    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        if not first:
            yield ","
        first = False
        # Get implements IDs via parent iteration
        impl_ids = []
        for parent in node.iter_parents():
            if parent.kind == NodeKind.REQUIREMENT:
                impl_ids.append(parent.id)
        node_json = json.dumps({
            "id": node.id,
            "title": node.label,
            "level": node.level,
            "status": node.status,
            "hash": node.hash,
            "implements": impl_ids,
            "source": {
                "path": node.source.path if node.source else None,
                "line": node.source.line if node.source else None,
            },
        }, indent=2)
        yield node_json
    yield "]"


def format_view(graph: TraceGraph, embed_content: bool = False) -> str:
    """Generate interactive HTML via HTMLGenerator."""
    try:
        from elspais.html import HTMLGenerator
    except ImportError:
        raise ImportError(
            "HTMLGenerator requires the trace-view extra. "
            "Install with: pip install elspais[trace-view]"
        )
    generator = HTMLGenerator(graph)
    return generator.generate(embed_content=embed_content)


def run(args: argparse.Namespace) -> int:
    """Run the trace command.

    Uses graph factory to build TraceGraph, then streams output in requested format.
    """
    # Handle not-implemented features
    for flag in ("edit_mode", "review_mode", "server"):
        if getattr(args, flag, False):
            print(f"Error: --{flag.replace('_', '-')} not yet implemented", file=sys.stderr)
            return 1

    # Build graph using factory
    from elspais.graph.factory import build_graph

    spec_dir = getattr(args, "spec_dir", None)
    config_path = getattr(args, "config", None)

    graph = build_graph(
        spec_dirs=[spec_dir] if spec_dir else None,
        config_path=config_path,
    )

    # Handle --view mode (interactive HTML)
    if getattr(args, "view", False):
        try:
            content = format_view(graph, getattr(args, "embed_content", False))
        except ImportError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

        output_path = args.output or Path("traceability_view.html")
        Path(output_path).write_text(content)

        if not getattr(args, "quiet", False):
            print(f"Generated: {output_path}", file=sys.stderr)
        return 0

    # Handle --graph-json mode
    if getattr(args, "graph_json", False):
        from elspais.graph.serialize import serialize_graph
        output = json.dumps(serialize_graph(graph), indent=2)
        if args.output:
            Path(args.output).write_text(output)
            if not getattr(args, "quiet", False):
                print(f"Generated: {args.output}", file=sys.stderr)
        else:
            print(output)
        return 0

    # Select formatter based on format
    fmt = getattr(args, "format", "markdown")

    # Handle legacy "both" format
    if fmt == "both":
        # Generate both markdown and csv
        output_base = args.output or Path("traceability")
        if isinstance(output_base, str):
            output_base = Path(output_base)

        md_path = output_base.with_suffix(".md")
        csv_path = output_base.with_suffix(".csv")

        with open(md_path, "w") as f:
            for line in format_markdown(graph):
                f.write(line + "\n")

        with open(csv_path, "w") as f:
            for line in format_csv(graph):
                f.write(line + "\n")

        if not getattr(args, "quiet", False):
            print(f"Generated: {md_path}", file=sys.stderr)
            print(f"Generated: {csv_path}", file=sys.stderr)
        return 0

    # Single format output
    formatters = {
        "markdown": format_markdown,
        "csv": format_csv,
        "html": format_html,
        "json": format_json,
    }

    if fmt not in formatters:
        print(f"Error: Unknown format '{fmt}'", file=sys.stderr)
        return 1

    line_generator = formatters[fmt](graph)
    output_path = args.output

    # Stream output line by line
    if output_path:
        with open(output_path, "w") as f:
            for line in line_generator:
                f.write(line + "\n")
        if not getattr(args, "quiet", False):
            print(f"Generated: {output_path}", file=sys.stderr)
    else:
        for line in line_generator:
            print(line)

    return 0
