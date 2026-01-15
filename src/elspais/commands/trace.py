# Implements: REQ-int-d00003 (CLI Extension)
"""
elspais.commands.trace - Generate traceability matrix command.

Supports both basic matrix generation and enhanced trace-view features.
"""

import argparse
import sys
from pathlib import Path
from typing import Dict, List

from elspais.config.defaults import DEFAULT_CONFIG
from elspais.config.loader import find_config_file, get_spec_directories, load_config
from elspais.core.models import Requirement
from elspais.core.parser import RequirementParser
from elspais.core.patterns import PatternConfig


def run(args: argparse.Namespace) -> int:
    """Run the trace command.

    REQ-int-d00003-C: Existing elspais trace --format html behavior SHALL be preserved.
    """
    # Check if enhanced trace-view features are requested
    use_trace_view = (
        getattr(args, 'view', False) or
        getattr(args, 'embed_content', False) or
        getattr(args, 'edit_mode', False) or
        getattr(args, 'review_mode', False) or
        getattr(args, 'server', False)
    )

    if use_trace_view:
        return run_trace_view(args)

    # Original basic trace functionality
    return run_basic_trace(args)


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
        if args.verbose if hasattr(args, 'verbose') else False:
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
        sponsor=getattr(args, 'sponsor', None),
        mode=getattr(args, 'mode', 'core'),
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
    quiet = getattr(args, 'quiet', False)
    generator.generate(
        format=output_format,
        output_file=output_file,
        embed_content=getattr(args, 'embed_content', False),
        edit_mode=getattr(args, 'edit_mode', False),
        review_mode=getattr(args, 'review_mode', False),
        quiet=quiet,
    )

    return 0


def run_review_server(args: argparse.Namespace) -> int:
    """Start the review server.

    REQ-int-d00002-C: Review server SHALL require flask, flask-cors via
                      elspais[trace-review] extra.
    """
    try:
        from elspais.trace_view.review import create_app, FLASK_AVAILABLE
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

    port = getattr(args, 'port', 8080)

    print(f"""
======================================
  elspais Review Server
======================================

Repository: {repo_root}
Server:     http://localhost:{port}

Press Ctrl+C to stop
""")

    app = create_app(repo_root, auto_sync=True)
    try:
        app.run(host='0.0.0.0', port=port, debug=False)
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
            impl_by = find_implementers(req_id, requirements)
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
                f'        <tr {subdir_attr}><td>{req_id}</td><td>{req.title}</td>'
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
        lines.append(f'"{req_id}","{title}","{req.level}","{req.status}","{impl_str}","{req.subdir}"')

    return "\n".join(lines)


def find_implementers(req_id: str, requirements: Dict[str, Requirement]) -> List[str]:
    """Find requirements that implement the given requirement."""
    implementers = []
    short_id = req_id.split("-")[-1] if "-" in req_id else req_id

    for other_id, other_req in requirements.items():
        for impl in other_req.implements:
            if impl == req_id or impl == short_id or impl.endswith(short_id):
                implementers.append(other_id)
                break

    return implementers
