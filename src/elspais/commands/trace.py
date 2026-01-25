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
from elspais.core.loader import load_requirements_from_directories
from elspais.core.models import Requirement


def run(args: argparse.Namespace) -> int:
    """Run the trace command.

    REQ-int-d00003-C: Existing elspais trace --format html behavior SHALL be preserved.
    """
    # Check if graph mode is requested
    use_graph = getattr(args, "graph", False) or getattr(args, "graph_json", False)
    if use_graph:
        return run_graph_trace(args)

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


def run_graph_trace(args: argparse.Namespace) -> int:
    """Run trace using the unified traceability graph."""

    from elspais.core.graph_builder import TraceGraphBuilder

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
    requirements = load_requirements_from_directories(spec_dirs, config)

    if not requirements:
        print("No requirements found.")
        return 1

    # Build graph
    repo_root = spec_dirs[0].parent if spec_dirs[0].name == "spec" else Path.cwd()
    include_file_nodes = getattr(args, "graph_file", False)
    builder = TraceGraphBuilder(repo_root=repo_root, include_file_nodes=include_file_nodes)
    builder.add_requirements(requirements)

    # If file nodes are enabled, parse with structure and add to builder
    if include_file_nodes:
        from elspais.core.loader import create_parser

        parser = create_parser(config)
        file_structures = []
        for spec_dir in spec_dirs:
            for md_file in spec_dir.rglob("*.md"):
                try:
                    result = parser.parse_file_with_structure(md_file, repo_root)
                    file_structures.append(result)
                except Exception:
                    # Skip files that can't be parsed
                    pass
        if file_structures:
            builder.add_file_structures(file_structures)
            if not getattr(args, "quiet", False):
                print(f"Captured structure from {len(file_structures)} spec files")

    # Add test coverage if testing is enabled
    testing_config = config.get("testing", {})
    if testing_config.get("enabled", False):
        from elspais.core.graph import SourceLocation
        from elspais.core.graph_schema import NodeTypeSchema
        from elspais.parsers import get_parser
        from elspais.testing.config import TestingConfig

        test_cfg = TestingConfig.from_dict(testing_config)
        test_dirs = test_cfg.test_dirs or ["tests"]
        file_patterns = test_cfg.patterns or ["test_*.py", "*_test.py"]

        # Get the test parser from registry
        test_parser = get_parser("test")
        if test_parser is None:
            print("Warning: Test parser not found in registry", file=sys.stderr)
        else:
            # Create schema for test nodes
            test_schema = NodeTypeSchema(name="test")

            # Scan test directories and parse each file
            test_nodes = []
            files_scanned = 0
            suppressed_count = 0

            for dir_pattern in test_dirs:
                # Handle directory patterns
                if dir_pattern in (".", ""):
                    dirs_to_scan = [repo_root]
                else:
                    dirs_to_scan = list(repo_root.glob(dir_pattern))

                for test_dir in dirs_to_scan:
                    if not test_dir.is_dir():
                        continue

                    # Find test files in this directory
                    for file_pattern in file_patterns:
                        for test_file in test_dir.rglob(file_pattern):
                            if not test_file.is_file():
                                continue

                            try:
                                content = test_file.read_text(encoding="utf-8", errors="replace")
                            except Exception:
                                continue

                            # Create source location
                            try:
                                rel_path = str(test_file.relative_to(repo_root))
                            except ValueError:
                                rel_path = str(test_file)

                            source = SourceLocation(path=rel_path, line=1)

                            # Parse the file content
                            nodes = test_parser.parse(content, source, test_schema)
                            test_nodes.extend(nodes)

                            # Count suppressed refs
                            for node in nodes:
                                expected_broken = node.metrics.get("_expected_broken_targets", [])
                                suppressed_count += len(expected_broken)

                            files_scanned += 1

            if files_scanned > 0:
                builder.add_test_coverage(test_nodes)
                if not getattr(args, "quiet", False):
                    print(f"Scanned {files_scanned} test files, "
                          f"found {len(test_nodes)} test references")
                    if suppressed_count > 0:
                        print(f"Marked {suppressed_count} references "
                              f"as expected broken (from markers)")

    graph, validation = builder.build_and_validate()

    # Compute rollup metrics
    builder.compute_metrics(graph)

    # Get report schema
    from elspais.core.graph_schema import ReportSchema

    report_name = getattr(args, "report", None) or "standard"
    report_presets = ReportSchema.defaults()
    report_schema = report_presets.get(report_name)
    if not report_schema:
        print(f"Warning: Unknown report '{report_name}', using 'standard'", file=sys.stderr)
        report_schema = report_presets["standard"]

    # Apply --depth override if provided
    depth_arg = getattr(args, "depth", None)
    if depth_arg is not None:
        # Named depth levels mapping
        depth_map = {
            "requirements": 1,
            "reqs": 1,
            "assertions": 2,
            "implementation": 3,
            "impl": 3,
            "full": None,
            "unlimited": None,
        }
        if depth_arg.lower() in depth_map:
            report_schema.max_depth = depth_map[depth_arg.lower()]
        else:
            try:
                report_schema.max_depth = int(depth_arg)
            except ValueError:
                print(
                    f"Warning: Invalid depth '{depth_arg}', using report default",
                    file=sys.stderr,
                )

    # Handle JSON output
    if getattr(args, "graph_json", False):
        output = graph_to_json(graph)
        if args.output:
            args.output.write_text(output)
            print(f"Generated: {args.output}")
        else:
            print(output)
        return 0

    # Default output format based on --format
    output_format = args.format

    if output_format in ["markdown", "both"]:
        md_output = generate_graph_markdown(graph, report_schema)
        if args.output:
            if output_format == "markdown":
                output_path = args.output
            else:
                output_path = args.output.with_suffix(".md")
        else:
            output_path = Path("traceability_graph.md")
        output_path.write_text(md_output)
        print(f"Generated: {output_path}")

    if output_format in ["html", "both"]:
        html_output = generate_graph_html(graph, report_schema)
        if args.output:
            if output_format == "html":
                output_path = args.output
            else:
                output_path = args.output.with_suffix(".html")
        else:
            output_path = Path("traceability_graph.html")
        output_path.write_text(html_output)
        print(f"Generated: {output_path}")

    if output_format == "csv":
        csv_output = generate_graph_csv(graph, report_schema)
        output_path = args.output or Path("traceability_graph.csv")
        output_path.write_text(csv_output)
        print(f"Generated: {output_path}")

    # Show validation info (suppressed warnings)
    if validation.info and not getattr(args, "quiet", False):
        print(f"\nSuppressed {len(validation.info)} expected broken link warnings")

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
    requirements = load_requirements_from_directories(spec_dirs, config)

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


# Graph-based output generators


def graph_to_json(tree) -> str:
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
        "graph": {
            "repo_root": str(tree.repo_root),
            "node_count": tree.node_count(),
            "counts_by_kind": {k.value: v for k, v in tree.count_by_kind().items()},
            "roots": [node_to_dict(r) for r in tree.roots],
        }
    }

    return json.dumps(output, indent=2)


def generate_graph_markdown(tree, report_schema=None) -> str:
    """Generate Markdown output from tree.

    Args:
        tree: The TraceGraph to render.
        report_schema: Optional ReportSchema controlling output fields and metrics.
    """
    from elspais.core.graph import NodeKind
    from elspais.core.graph_schema import ReportSchema

    # Use standard report if none provided
    if report_schema is None:
        report_schema = ReportSchema.defaults()["standard"]

    lines = [
        f"# Traceability Report: {report_schema.name.title()}",
        "",
        f"*{report_schema.description}*",
        "",
        f"**Total Nodes**: {tree.node_count()}",
        "",
    ]

    # Add metrics summary if included
    if report_schema.include_metrics:
        # Get root-level aggregated metrics
        total_assertions = sum(
            r.metrics.get("total_assertions", 0) for r in tree.roots
        )
        covered_assertions = sum(
            r.metrics.get("covered_assertions", 0) for r in tree.roots
        )
        # Coverage breakdown by source type
        direct_covered = sum(
            r.metrics.get("direct_covered", 0) for r in tree.roots
        )
        explicit_covered = sum(
            r.metrics.get("explicit_covered", 0) for r in tree.roots
        )
        inferred_covered = sum(
            r.metrics.get("inferred_covered", 0) for r in tree.roots
        )
        total_tests = sum(r.metrics.get("total_tests", 0) for r in tree.roots)
        passed_tests = sum(r.metrics.get("passed_tests", 0) for r in tree.roots)

        coverage_pct = (
            (covered_assertions / total_assertions * 100) if total_assertions > 0 else 0
        )
        pass_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0

        # Direct + Explicit are high-confidence coverage
        direct_explicit = direct_covered + explicit_covered

        lines.extend([
            "## Summary Metrics",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Total Assertions | {total_assertions} |",
            f"| Covered Assertions | {covered_assertions} |",
            f"| — Direct (test→assertion) | {direct_covered} |",
            f"| — Explicit (REQ→assertion) | {explicit_covered} |",
            f"| — Inferred (REQ→REQ) | {inferred_covered} |",
            f"| Direct/Explicit (high confidence) | {direct_explicit} |",
            f"| Coverage | {coverage_pct:.1f}% |",
            f"| Total Tests | {total_tests} |",
            f"| Passed Tests | {passed_tests} |",
            f"| Pass Rate | {pass_rate:.1f}% |",
            "",
        ])

    lines.extend(["## Hierarchy", ""])

    def format_node(node, indent: int = 0, depth: int = 0) -> list[str]:
        """Format a node with indentation."""
        # Check max_depth
        if report_schema.max_depth is not None and depth > report_schema.max_depth:
            return []

        result = []
        prefix = "  " * indent

        if node.kind == NodeKind.REQUIREMENT:
            status_emoji = (
                "✅" if node.requirement and node.requirement.status == "Active" else "📝"
            )

            # Build field string based on include_fields
            parts = []
            if "id" in report_schema.include_fields:
                parts.append(f"**{node.id}**")
            if "title" in report_schema.include_fields and node.requirement:
                parts.append(node.requirement.title)
            if "status" in report_schema.include_fields and node.requirement:
                parts.append(f"[{node.requirement.status}]")
            if "level" in report_schema.include_fields and node.requirement:
                parts.append(f"({node.requirement.level})")

            node_text = " ".join(parts) if parts else node.id

            # Add metrics if included
            metrics_str = ""
            if report_schema.include_metrics and node.metrics:
                metric_parts = []
                m = node.metrics
                if "coverage_pct" in report_schema.metric_fields:
                    metric_parts.append(f"{m.get('coverage_pct', 0):.0f}% cov")
                if "total_assertions" in report_schema.metric_fields:
                    metric_parts.append(f"{m.get('total_assertions', 0)} assertions")
                if "total_tests" in report_schema.metric_fields:
                    metric_parts.append(f"{m.get('total_tests', 0)} tests")
                if "pass_rate_pct" in report_schema.metric_fields:
                    metric_parts.append(f"{m.get('pass_rate_pct', 0):.0f}% pass")
                if metric_parts:
                    metrics_str = f" — {', '.join(metric_parts)}"

            result.append(f"{prefix}- {status_emoji} {node_text}{metrics_str}")

        elif node.kind == NodeKind.ASSERTION:
            # Only show assertions if children are included
            if not report_schema.include_children:
                return result

            covered = "✓" if node.metrics.get("covered_assertions", 0) > 0 else "○"
            text = node.assertion.text[:50] if node.assertion else ""
            result.append(f"{prefix}- {covered} {node.id}: {text}...")

        else:
            if report_schema.include_children:
                result.append(f"{prefix}- {node.label}")

        # Add children if included
        if report_schema.include_children:
            for child in node.children:
                result.extend(format_node(child, indent + 1, depth + 1))

        return result

    for root in tree.roots:
        lines.extend(format_node(root))
        lines.append("")

    # Add statistics
    counts = tree.count_by_kind()
    lines.extend([
        "## Statistics",
        "",
        "| Type | Count |",
        "|------|-------|",
    ])
    for kind, count in sorted(counts.items(), key=lambda x: x[0].value):
        lines.append(f"| {kind.value.title()} | {count} |")

    lines.extend(["", "---", f"*Generated by elspais ({report_schema.name} report)*"])
    return "\n".join(lines)


def generate_graph_html(tree, report_schema=None) -> str:
    """Generate HTML output from tree.

    Args:
        tree: The TraceGraph to render.
        report_schema: Optional ReportSchema controlling output fields and metrics.
    """
    from elspais.core.graph import NodeKind
    from elspais.core.graph_schema import ReportSchema

    if report_schema is None:
        report_schema = ReportSchema.defaults()["standard"]

    report_title = f"Traceability Report: {report_schema.name.title()}"

    html = (
        f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{report_title}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 2rem; }}
        h1 {{ color: #333; }}
        .tree {{ margin: 1rem 0; }}
        .tree ul {{ list-style-type: none; padding-left: 20px; }}
        .tree li {{ margin: 0.3rem 0; }}
        .node {{ padding: 0.3rem 0.5rem; border-radius: 4px; display: inline-block; }}
        .requirement {{ background: #e3f2fd; border: 1px solid #2196f3; }}
        .assertion {{ background: #f3e5f5; border: 1px solid #9c27b0; font-size: 0.9em; }}
        .code {{ background: #e8f5e9; border: 1px solid #4caf50; }}
        .test {{ background: #fff3e0; border: 1px solid #ff9800; }}
        .status-active {{ color: #2e7d32; }}
        .status-draft {{ color: #f57c00; }}
        .toggle {{ cursor: pointer; margin-right: 0.5rem; }}
        .collapsed > ul {{ display: none; }}
        .stats {{ margin-top: 2rem; }}
        .stats table {{ border-collapse: collapse; }}
        .stats th, .stats td {{ border: 1px solid #ddd; padding: 0.5rem; }}
        .stats th {{ background: #f5f5f5; }}
    </style>
</head>
<body>
    <h1>Traceability Graph</h1>
    <p>Total nodes: <strong>"""
        + str(tree.node_count())
        + """</strong></p>

    <div class="graph">
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
    <p><em>Generated by elspais (graph mode)</em></p>
</body>
</html>"""

    return html


def generate_graph_csv(tree, report_schema=None) -> str:
    """Generate CSV output from tree (unique nodes using index).

    Args:
        tree: The TraceGraph to render.
        report_schema: Optional ReportSchema controlling output fields and metrics.
    """
    from elspais.core.graph_schema import ReportSchema

    if report_schema is None:
        report_schema = ReportSchema.defaults()["standard"]

    # Build header based on report schema
    headers = ["ID", "Kind", "Label"]
    if "level" in report_schema.include_fields:
        headers.append("Level")
    if "status" in report_schema.include_fields:
        headers.append("Status")
    headers.extend(["Parent", "Source"])

    # Add metric columns if included
    if report_schema.include_metrics:
        for mf in report_schema.metric_fields:
            # Convert snake_case to Title Case
            headers.append(mf.replace("_", " ").title())

    lines = [",".join(headers)]

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

        # Build row
        row = [f'"{node.id}"', f'"{kind}"', f'"{label}"']
        if "level" in report_schema.include_fields:
            row.append(f'"{level}"')
        if "status" in report_schema.include_fields:
            row.append(f'"{status}"')
        row.extend([f'"{parent}"', f'"{source}"'])

        # Add metric values if included
        if report_schema.include_metrics:
            for mf in report_schema.metric_fields:
                val = node.metrics.get(mf, 0)
                if isinstance(val, float):
                    row.append(f"{val:.1f}")
                else:
                    row.append(str(val))

        lines.append(",".join(row))

    return "\n".join(lines)
