# Implements: REQ-int-d00003 (CLI Extension)
"""
elspais.commands.trace - Generate traceability matrix command.

Supports both basic matrix generation and enhanced trace-view features.
"""

import argparse
import sys
from pathlib import Path
from typing import Dict

from elspais.config.defaults import DEFAULT_CONFIG
from elspais.config.loader import find_config_file, get_spec_directories, load_config
from elspais.core.hierarchy import find_children_ids
from elspais.core.models import Requirement
from elspais.core.parser import RequirementParser
from elspais.core.patterns import PatternConfig


def run(args: argparse.Namespace) -> int:
    """Run the trace command.

    REQ-int-d00003-C: Existing elspais trace --format html behavior SHALL be preserved.
    """
    # Check if tree mode is requested
    use_tree = getattr(args, "tree", False) or getattr(args, "tree_json", False)
    if use_tree:
        return run_tree_trace(args)

    # Check if enhanced trace-view features are requested
    use_trace_view = (
        getattr(args, "view", False)
        or getattr(args, "embed_content", False)
        or getattr(args, "edit_mode", False)
        or getattr(args, "review_mode", False)
        or getattr(args, "server", False)
    )

    if use_trace_view:
        return run_trace_view(args)

    # Original basic trace functionality
    return run_basic_trace(args)


def run_tree_trace(args: argparse.Namespace) -> int:
    """Run trace using the unified traceability tree."""

    from elspais.core.tree_builder import TraceTreeBuilder

    # Load configuration
    config_path = args.config or find_config_file(Path.cwd())
    if config_path and config_path.exists():
        config = load_config(config_path)
    else:
        config = DEFAULT_CONFIG

    # Get spec directories
    spec_dirs = get_spec_directories(args.spec_dir, config)
    if not spec_dirs:
        print("Error: No spec directories found", file=sys.stderr)
        return 1

    # Parse requirements
    pattern_config = PatternConfig.from_dict(config.get("patterns", {}))
    spec_config = config.get("spec", {})
    no_reference_values = spec_config.get("no_reference_values")
    skip_files = spec_config.get("skip_files", [])
    parser = RequirementParser(pattern_config, no_reference_values=no_reference_values)
    requirements = parser.parse_directories(spec_dirs, skip_files=skip_files)

    if not requirements:
        print("No requirements found.")
        return 1

    # Build tree
    repo_root = spec_dirs[0].parent if spec_dirs[0].name == "spec" else Path.cwd()
    builder = TraceTreeBuilder(repo_root=repo_root)
    builder.add_requirements(requirements)
    tree, validation = builder.build_and_validate()

    # Handle JSON output
    if getattr(args, "tree_json", False):
        output = tree_to_json(tree)
        if args.output:
            args.output.write_text(output)
            print(f"Generated: {args.output}")
        else:
            print(output)
        return 0

    # Default output format based on --format
    output_format = args.format

    if output_format in ["markdown", "both"]:
        md_output = generate_tree_markdown(tree)
        if args.output:
            if output_format == "markdown":
                output_path = args.output
            else:
                output_path = args.output.with_suffix(".md")
        else:
            output_path = Path("traceability_tree.md")
        output_path.write_text(md_output)
        print(f"Generated: {output_path}")

    if output_format in ["html", "both"]:
        html_output = generate_tree_html(tree)
        if args.output:
            if output_format == "html":
                output_path = args.output
            else:
                output_path = args.output.with_suffix(".html")
        else:
            output_path = Path("traceability_tree.html")
        output_path.write_text(html_output)
        print(f"Generated: {output_path}")

    if output_format == "csv":
        csv_output = generate_tree_csv(tree)
        output_path = args.output or Path("traceability_tree.csv")
        output_path.write_text(csv_output)
        print(f"Generated: {output_path}")

    # Show validation warnings
    if validation.warnings and not getattr(args, "quiet", False):
        print("\nWarnings:")
        for warning in validation.warnings[:5]:
            print(f"  - {warning}")
        if len(validation.warnings) > 5:
            print(f"  ... and {len(validation.warnings) - 5} more")

    return 0


def run_basic_trace(args: argparse.Namespace) -> int:
    """Run basic trace matrix generation (original behavior)."""
    # Load configuration
    config_path = args.config or find_config_file(Path.cwd())
    if config_path and config_path.exists():
        config = load_config(config_path)
    else:
        config = DEFAULT_CONFIG

    # Get spec directories
    spec_dirs = get_spec_directories(args.spec_dir, config)
    if not spec_dirs:
        print("Error: No spec directories found", file=sys.stderr)
        return 1

    # Parse requirements
    pattern_config = PatternConfig.from_dict(config.get("patterns", {}))
    spec_config = config.get("spec", {})
    no_reference_values = spec_config.get("no_reference_values")
    skip_files = spec_config.get("skip_files", [])
    parser = RequirementParser(pattern_config, no_reference_values=no_reference_values)
    requirements = parser.parse_directories(spec_dirs, skip_files=skip_files)

    if not requirements:
        print("No requirements found.")
        return 1

    # Determine output format
    output_format = args.format

    # Generate output
    if output_format in ["markdown", "both"]:
        md_output = generate_markdown_matrix(requirements)
        if args.output:
            if output_format == "markdown":
                output_path = args.output
            else:
                output_path = args.output.with_suffix(".md")
        else:
            output_path = Path("traceability.md")
        output_path.write_text(md_output)
        print(f"Generated: {output_path}")

    if output_format in ["html", "both"]:
        html_output = generate_html_matrix(requirements)
        if args.output:
            if output_format == "html":
                output_path = args.output
            else:
                output_path = args.output.with_suffix(".html")
        else:
            output_path = Path("traceability.html")
        output_path.write_text(html_output)
        print(f"Generated: {output_path}")

    if output_format == "csv":
        csv_output = generate_csv_matrix(requirements)
        output_path = args.output or Path("traceability.csv")
        output_path.write_text(csv_output)
        print(f"Generated: {output_path}")

    return 0


def run_trace_view(args: argparse.Namespace) -> int:
    """Run enhanced trace-view features.

    REQ-int-d00003-A: Trace-view features SHALL be accessible via elspais trace command.
    REQ-int-d00003-B: New flags SHALL include: --view, --embed-content, --edit-mode,
                      --review-mode, --server.
    """
    # Check if starting review server
    if args.server:
        return run_review_server(args)

    # Import trace_view (requires jinja2)
    try:
        from elspais.trace_view import TraceViewGenerator
    except ImportError as e:
        print("Error: trace-view features require additional dependencies.", file=sys.stderr)
        print("Install with: pip install elspais[trace-view]", file=sys.stderr)
        if args.verbose if hasattr(args, "verbose") else False:
            print(f"Import error: {e}", file=sys.stderr)
        return 1

    # Load configuration
    config_path = args.config or find_config_file(Path.cwd())
    if config_path and config_path.exists():
        config = load_config(config_path)
    else:
        config = DEFAULT_CONFIG

    # Determine spec directory
    spec_dir = args.spec_dir
    if not spec_dir:
        spec_dirs = get_spec_directories(None, config)
        spec_dir = spec_dirs[0] if spec_dirs else Path.cwd() / "spec"

    repo_root = spec_dir.parent if spec_dir.name == "spec" else spec_dir.parent.parent

    # Get implementation directories from config
    impl_dirs = []
    dirs_config = config.get("directories", {})
    code_dirs = dirs_config.get("code", [])
    for code_dir in code_dirs:
        impl_path = repo_root / code_dir
        if impl_path.exists():
            impl_dirs.append(impl_path)

    # Create generator
    generator = TraceViewGenerator(
        spec_dir=spec_dir,
        impl_dirs=impl_dirs,
        sponsor=getattr(args, "sponsor", None),
        mode=getattr(args, "mode", "core"),
        repo_root=repo_root,
        config=config,
    )

    # Determine output format
    # --view implies HTML
    output_format = "html" if args.view else args.format
    if output_format == "both":
        output_format = "html"

    # Determine output file
    output_file = args.output
    if output_file is None:
        if output_format == "html":
            output_file = Path("traceability_matrix.html")
        elif output_format == "csv":
            output_file = Path("traceability_matrix.csv")
        else:
            output_file = Path("traceability_matrix.md")

    # Generate
    quiet = getattr(args, "quiet", False)
    generator.generate(
        format=output_format,
        output_file=output_file,
        embed_content=getattr(args, "embed_content", False),
        edit_mode=getattr(args, "edit_mode", False),
        review_mode=getattr(args, "review_mode", False),
        quiet=quiet,
    )

    return 0


def run_review_server(args: argparse.Namespace) -> int:
    """Start the review server.

    REQ-int-d00002-C: Review server SHALL require flask, flask-cors via
                      elspais[trace-review] extra.
    """
    try:
        from elspais.trace_view.review import FLASK_AVAILABLE, create_app
    except ImportError:
        print("Error: Review server requires additional dependencies.", file=sys.stderr)
        print("Install with: pip install elspais[trace-review]", file=sys.stderr)
        return 1

    if not FLASK_AVAILABLE:
        print("Error: Review server requires Flask.", file=sys.stderr)
        print("Install with: pip install elspais[trace-review]", file=sys.stderr)
        return 1

    # Determine repo root
    spec_dir = args.spec_dir
    if spec_dir:
        repo_root = spec_dir.parent if spec_dir.name == "spec" else spec_dir.parent.parent
    else:
        repo_root = Path.cwd()

    port = getattr(args, "port", 8080)

    print(
        f"""
======================================
  elspais Review Server
======================================

Repository: {repo_root}
Server:     http://localhost:{port}

Press Ctrl+C to stop
"""
    )

    app = create_app(repo_root, auto_sync=True)
    try:
        app.run(host="0.0.0.0", port=port, debug=False)
    except KeyboardInterrupt:
        print("\nServer stopped.")

    return 0


def generate_markdown_matrix(requirements: Dict[str, Requirement]) -> str:
    """Generate Markdown traceability matrix."""
    lines = ["# Traceability Matrix", "", "## Requirements Hierarchy", ""]

    # Group by type
    prd_reqs = {k: v for k, v in requirements.items() if v.level.upper() in ["PRD", "PRODUCT"]}
    ops_reqs = {k: v for k, v in requirements.items() if v.level.upper() in ["OPS", "OPERATIONS"]}
    dev_reqs = {k: v for k, v in requirements.items() if v.level.upper() in ["DEV", "DEVELOPMENT"]}

    # PRD table
    if prd_reqs:
        lines.extend(["### Product Requirements", ""])
        lines.append("| ID | Title | Status | Implemented By |")
        lines.append("|---|---|---|---|")
        for req_id, req in sorted(prd_reqs.items()):
            impl_by = find_children_ids(req_id, requirements)
            impl_str = ", ".join(impl_by) if impl_by else "-"
            lines.append(f"| {req_id} | {req.title} | {req.status} | {impl_str} |")
        lines.append("")

    # OPS table
    if ops_reqs:
        lines.extend(["### Operations Requirements", ""])
        lines.append("| ID | Title | Implements | Status |")
        lines.append("|---|---|---|---|")
        for req_id, req in sorted(ops_reqs.items()):
            impl_str = ", ".join(req.implements) if req.implements else "-"
            lines.append(f"| {req_id} | {req.title} | {impl_str} | {req.status} |")
        lines.append("")

    # DEV table
    if dev_reqs:
        lines.extend(["### Development Requirements", ""])
        lines.append("| ID | Title | Implements | Status |")
        lines.append("|---|---|---|---|")
        for req_id, req in sorted(dev_reqs.items()):
            impl_str = ", ".join(req.implements) if req.implements else "-"
            lines.append(f"| {req_id} | {req.title} | {impl_str} | {req.status} |")
        lines.append("")

    lines.extend(["---", "*Generated by elspais*"])
    return "\n".join(lines)


def generate_html_matrix(requirements: Dict[str, Requirement]) -> str:
    """Generate HTML traceability matrix."""
    html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Traceability Matrix</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 2rem; }
        h1 { color: #333; }
        table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
        th, td { border: 1px solid #ddd; padding: 0.5rem; text-align: left; }
        th { background: #f5f5f5; }
        tr:hover { background: #f9f9f9; }
        .status-active { color: green; }
        .status-draft { color: orange; }
        .status-deprecated { color: red; }
    </style>
</head>
<body>
    <h1>Traceability Matrix</h1>
"""

    # Group by type
    prd_reqs = {k: v for k, v in requirements.items() if v.level.upper() in ["PRD", "PRODUCT"]}
    ops_reqs = {k: v for k, v in requirements.items() if v.level.upper() in ["OPS", "OPERATIONS"]}
    dev_reqs = {k: v for k, v in requirements.items() if v.level.upper() in ["DEV", "DEVELOPMENT"]}

    for title, reqs in [
        ("Product Requirements", prd_reqs),
        ("Operations Requirements", ops_reqs),
        ("Development Requirements", dev_reqs),
    ]:
        if not reqs:
            continue

        html += f"    <h2>{title}</h2>\n"
        html += "    <table>\n"
        html += "        <tr><th>ID</th><th>Title</th><th>Implements</th><th>Status</th></tr>\n"

        for req_id, req in sorted(reqs.items()):
            impl_str = ", ".join(req.implements) if req.implements else "-"
            status_class = f"status-{req.status.lower()}"
            subdir_attr = f'data-subdir="{req.subdir}"'
            html += (
                f"        <tr {subdir_attr}><td>{req_id}</td><td>{req.title}</td>"
                f'<td>{impl_str}</td><td class="{status_class}">{req.status}</td></tr>\n'
            )

        html += "    </table>\n"

    html += """    <hr>
    <p><em>Generated by elspais</em></p>
</body>
</html>"""
    return html


def generate_csv_matrix(requirements: Dict[str, Requirement]) -> str:
    """Generate CSV traceability matrix."""
    lines = ["ID,Title,Level,Status,Implements,Subdir"]

    for req_id, req in sorted(requirements.items()):
        impl_str = ";".join(req.implements) if req.implements else ""
        title = req.title.replace('"', '""')
        lines.append(
            f'"{req_id}","{title}","{req.level}","{req.status}","{impl_str}","{req.subdir}"'
        )

    return "\n".join(lines)


# Tree-based output generators


def tree_to_json(tree) -> str:
    """Convert tree to JSON format."""
    import json

    def node_to_dict(node, depth: int = 0) -> dict:
        """Convert a node to dictionary."""
        result = {
            "id": node.id,
            "kind": node.kind.value,
            "label": node.label,
            "depth": depth,
        }

        if node.source:
            result["source"] = {
                "path": node.source.path,
                "line": node.source.line,
            }
            if node.source.repo:
                result["source"]["repo"] = node.source.repo

        if node.requirement:
            result["requirement"] = {
                "title": node.requirement.title,
                "level": node.requirement.level,
                "status": node.requirement.status,
                "implements": node.requirement.implements,
            }

        if node.assertion:
            result["assertion"] = {
                "label": node.assertion.label,
                "text": node.assertion.text,
                "is_placeholder": node.assertion.is_placeholder,
            }

        if node.metrics:
            result["metrics"] = {k: v for k, v in node.metrics.items() if not k.startswith("_")}

        if node.children:
            result["children"] = [node_to_dict(c, depth + 1) for c in node.children]

        return result

    output = {
        "tree": {
            "repo_root": str(tree.repo_root),
            "node_count": tree.node_count(),
            "counts_by_kind": {k.value: v for k, v in tree.count_by_kind().items()},
            "roots": [node_to_dict(r) for r in tree.roots],
        }
    }

    return json.dumps(output, indent=2)


def generate_tree_markdown(tree) -> str:
    """Generate Markdown output from tree."""
    from elspais.core.tree import NodeKind

    lines = [
        "# Traceability Tree",
        "",
        f"**Total Nodes**: {tree.node_count()}",
        "",
        "## Hierarchy",
        "",
    ]

    def format_node(node, indent: int = 0) -> list[str]:
        """Format a node with indentation."""
        result = []
        prefix = "  " * indent

        if node.kind == NodeKind.REQUIREMENT:
            status_emoji = (
                "✅" if node.requirement and node.requirement.status == "Active" else "📝"
            )
            title = node.requirement.title if node.requirement else ""
            result.append(f"{prefix}- {status_emoji} **{node.id}**: {title}")
        elif node.kind == NodeKind.ASSERTION:
            result.append(
                f"{prefix}- 📋 {node.id}: {node.assertion.text[:60] if node.assertion else ''}..."
            )
        else:
            result.append(f"{prefix}- {node.label}")

        # Add children
        for child in node.children:
            result.extend(format_node(child, indent + 1))

        return result

    for root in tree.roots:
        lines.extend(format_node(root))
        lines.append("")

    # Add statistics
    counts = tree.count_by_kind()
    lines.extend(
        [
            "## Statistics",
            "",
            "| Type | Count |",
            "|------|-------|",
        ]
    )
    for kind, count in sorted(counts.items(), key=lambda x: x[0].value):
        lines.append(f"| {kind.value.title()} | {count} |")

    lines.extend(["", "---", "*Generated by elspais (tree mode)*"])
    return "\n".join(lines)


def generate_tree_html(tree) -> str:
    """Generate HTML output from tree."""
    from elspais.core.tree import NodeKind

    html = (
        """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Traceability Tree</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 2rem; }
        h1 { color: #333; }
        .tree { margin: 1rem 0; }
        .tree ul { list-style-type: none; padding-left: 20px; }
        .tree li { margin: 0.3rem 0; }
        .node { padding: 0.3rem 0.5rem; border-radius: 4px; display: inline-block; }
        .requirement { background: #e3f2fd; border: 1px solid #2196f3; }
        .assertion { background: #f3e5f5; border: 1px solid #9c27b0; font-size: 0.9em; }
        .code { background: #e8f5e9; border: 1px solid #4caf50; }
        .test { background: #fff3e0; border: 1px solid #ff9800; }
        .status-active { color: #2e7d32; }
        .status-draft { color: #f57c00; }
        .toggle { cursor: pointer; margin-right: 0.5rem; }
        .collapsed > ul { display: none; }
        .stats { margin-top: 2rem; }
        .stats table { border-collapse: collapse; }
        .stats th, .stats td { border: 1px solid #ddd; padding: 0.5rem; }
        .stats th { background: #f5f5f5; }
    </style>
</head>
<body>
    <h1>Traceability Tree</h1>
    <p>Total nodes: <strong>"""
        + str(tree.node_count())
        + """</strong></p>

    <div class="tree">
        <ul>
"""
    )

    def render_node(node, depth: int = 0) -> str:
        """Render a node as HTML."""
        kind_class = node.kind.value
        has_children = len(node.children) > 0

        # Build label
        if node.kind == NodeKind.REQUIREMENT and node.requirement:
            label = f"<strong>{node.id}</strong>: {node.requirement.title}"
            status_class = f"status-{node.requirement.status.lower()}"
            label += f' <span class="{status_class}">[{node.requirement.status}]</span>'
        elif node.kind == NodeKind.ASSERTION and node.assertion:
            text = node.assertion.text[:80]
            label = f"<strong>{node.id}</strong>: {text}..."
        else:
            label = node.label

        toggle = (
            '<span class="toggle">▶</span>'
            if has_children
            else '<span style="margin-right:1.1rem"></span>'
        )

        result = f'<li><span class="node {kind_class}">{toggle}{label}</span>'

        if has_children:
            result += "\n<ul>"
            for child in node.children:
                result += render_node(child, depth + 1)
            result += "</ul>"

        result += "</li>\n"
        return result

    for root in tree.roots:
        html += render_node(root)

    html += """        </ul>
    </div>

    <div class="stats">
        <h2>Statistics</h2>
        <table>
            <tr><th>Type</th><th>Count</th></tr>
"""

    for kind, count in sorted(tree.count_by_kind().items(), key=lambda x: x[0].value):
        html += f"            <tr><td>{kind.value.title()}</td><td>{count}</td></tr>\n"

    html += """        </table>
    </div>

    <script>
        document.querySelectorAll('.toggle').forEach(toggle => {
            toggle.addEventListener('click', (e) => {
                const li = e.target.closest('li');
                li.classList.toggle('collapsed');
                e.target.textContent = li.classList.contains('collapsed') ? '▶' : '▼';
            });
        });
        // Start expanded
        document.querySelectorAll('.toggle').forEach(t => t.textContent = '▼');
    </script>

    <hr>
    <p><em>Generated by elspais (tree mode)</em></p>
</body>
</html>"""

    return html


def generate_tree_csv(tree) -> str:
    """Generate CSV output from tree (unique nodes using index)."""

    lines = ["ID,Kind,Label,Level,Status,Parent,Source"]

    # Use index for unique nodes
    for node_id in sorted(tree._index.keys()):
        node = tree._index[node_id]
        kind = node.kind.value
        label = node.label.replace('"', '""')
        level = ""
        status = ""
        source = ""

        if node.requirement:
            level = node.requirement.level
            status = node.requirement.status

        if node.source:
            source = f"{node.source.path}:{node.source.line}"

        # Get first parent ID
        parent = node.parents[0].id if node.parents else ""

        lines.append(f'"{node.id}","{kind}","{label}","{level}","{status}","{parent}","{source}"')

    return "\n".join(lines)
