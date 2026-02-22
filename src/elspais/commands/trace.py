# Implements: REQ-int-d00003 (CLI Extension)
# Implements: REQ-p00001-B, REQ-p00003-A, REQ-p00003-B
# Implements: REQ-d00052-B, REQ-d00052-C, REQ-d00052-G
"""
elspais.commands.trace - Generate traceability matrix command.

Uses the graph-based system to generate traceability reports in various formats.
Commands only work with graph data (zero file I/O for reading requirements).

OUTPUT FORMATS:
- markdown: Table with columns based on report preset
- csv: Same columns, comma-separated with proper escaping
- html: Basic styled HTML table
- json: Full requirement data including body, assertions, hash, file_path
- both: Generates both markdown and csv (legacy mode)

REPORT PRESETS (--report):
- minimal: ID, Title, Status only (quick overview)
- standard: ID, Title, Level, Status, Implements (default)
- full: All fields including Body, Assertions, Hash, Code/Test refs

INTERACTIVE VIEW (--view):
- Uses elspais.html.HTMLGenerator
- Generates interactive HTML with collapsible hierarchy
- Default output: traceability_view.html
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from elspais.graph.builder import TraceGraph

from elspais.graph import NodeKind


@dataclass
class ReportPreset:
    """Configuration for a report preset."""

    name: str
    columns: list[str]
    include_body: bool = False
    include_assertions: bool = False
    include_code_refs: bool = False
    include_test_refs: bool = False


# Define report presets
REPORT_PRESETS = {
    "minimal": ReportPreset(
        name="minimal",
        columns=["id", "title", "status"],
    ),
    "standard": ReportPreset(
        name="standard",
        columns=["id", "title", "level", "status", "implements"],
    ),
    "full": ReportPreset(
        name="full",
        columns=["id", "title", "level", "status", "implements", "hash", "file"],
        include_body=True,
        include_assertions=True,
        include_code_refs=True,
        include_test_refs=True,
    ),
}

DEFAULT_PRESET = "standard"


def _get_node_data(node, graph: TraceGraph) -> dict:
    """Extract data from a node for use in formatters."""
    # Get implements IDs via parent iteration
    impl_ids = []
    for parent in node.iter_parents():
        if parent.kind == NodeKind.REQUIREMENT:
            impl_ids.append(parent.id)

    # Get code references (CODE nodes that implement this requirement)
    code_refs = []
    for child in node.iter_children():
        if child.kind == NodeKind.CODE:
            code_refs.append(child.id)

    # Get test references (TEST nodes that validate this requirement)
    test_refs = []
    for child in node.iter_children():
        if child.kind == NodeKind.TEST:
            test_refs.append(child.id)

    # Get assertions
    assertions = []
    for child in node.iter_children():
        if child.kind == NodeKind.ASSERTION:
            assertions.append(
                {"label": child.get_field("label", ""), "text": child.get_label() or ""}
            )

    return {
        "id": node.id,
        "title": node.get_label() or "",
        "level": node.level or "",
        "status": node.status or "",
        "implements": impl_ids,
        "hash": node.hash or "",
        "file": node.source.path if node.source else "",
        "body": node.get_field("body", "") or "",
        "assertions": assertions,
        "code_refs": code_refs,
        "test_refs": test_refs,
    }


def format_markdown(graph: TraceGraph, preset: ReportPreset | None = None) -> Iterator[str]:
    """Generate markdown table. Streams one node at a time."""
    if preset is None:
        preset = REPORT_PRESETS[DEFAULT_PRESET]

    yield "# Traceability Matrix"
    yield ""

    # Build header based on preset columns
    column_headers = {
        "id": "ID",
        "title": "Title",
        "level": "Level",
        "status": "Status",
        "implements": "Implements",
        "hash": "Hash",
        "file": "File",
    }
    headers = [column_headers.get(col, col.title()) for col in preset.columns]
    yield "| " + " | ".join(headers) + " |"
    yield "|" + "|".join(["----"] * len(headers)) + "|"

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        data = _get_node_data(node, graph)
        row_values = []
        for col in preset.columns:
            if col == "implements":
                row_values.append(", ".join(data["implements"]) or "-")
            else:
                row_values.append(str(data.get(col, "")))
        yield "| " + " | ".join(row_values) + " |"

        # For full preset, add body and assertions after the row
        if preset.include_body and data["body"]:
            yield ""
            yield "<details><summary>Body</summary>"
            yield ""
            yield data["body"]
            yield ""
            yield "</details>"

        if preset.include_assertions and data["assertions"]:
            yield ""
            yield f"<details><summary>Assertions ({len(data['assertions'])})</summary>"
            yield ""
            for a in data["assertions"]:
                yield f"- **{a['label']}**: {a['text']}"
            yield ""
            yield "</details>"

        if preset.include_code_refs and data["code_refs"]:
            yield ""
            yield f"<details><summary>Code Refs ({len(data['code_refs'])})</summary>"
            yield ""
            for ref in data["code_refs"]:
                yield f"- `{ref}`"
            yield ""
            yield "</details>"

        if preset.include_test_refs and data["test_refs"]:
            yield ""
            yield f"<details><summary>Test Refs ({len(data['test_refs'])})</summary>"
            yield ""
            for ref in data["test_refs"]:
                yield f"- `{ref}`"
            yield ""
            yield "</details>"


def format_csv(graph: TraceGraph, preset: ReportPreset | None = None) -> Iterator[str]:
    """Generate CSV. Streams one node at a time."""
    if preset is None:
        preset = REPORT_PRESETS[DEFAULT_PRESET]

    def escape(s: str) -> str:
        if "," in s or '"' in s or "\n" in s:
            return '"' + s.replace('"', '""') + '"'
        return s

    # Build header based on preset columns
    base_columns = list(preset.columns)
    extra_columns = []
    if preset.include_assertions:
        extra_columns.append("assertions")
    if preset.include_code_refs:
        extra_columns.append("code_refs")
    if preset.include_test_refs:
        extra_columns.append("test_refs")

    yield ",".join(base_columns + extra_columns)

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        data = _get_node_data(node, graph)
        row_values = []
        for col in base_columns:
            if col == "implements":
                row_values.append(escape(";".join(data["implements"])))
            else:
                row_values.append(escape(str(data.get(col, ""))))

        # Add extra columns for full preset
        if preset.include_assertions:
            assertions_str = "; ".join(f"{a['label']}: {a['text']}" for a in data["assertions"])
            row_values.append(escape(assertions_str))
        if preset.include_code_refs:
            row_values.append(escape(";".join(data["code_refs"])))
        if preset.include_test_refs:
            row_values.append(escape(";".join(data["test_refs"])))

        yield ",".join(row_values)


def format_html(graph: TraceGraph, preset: ReportPreset | None = None) -> Iterator[str]:
    """Generate basic HTML table. Streams one node at a time."""
    if preset is None:
        preset = REPORT_PRESETS[DEFAULT_PRESET]

    def escape_html(s: str) -> str:
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    yield "<!DOCTYPE html>"
    yield "<html><head><style>"
    yield "table { border-collapse: collapse; width: 100%; }"
    yield "th, td { border: 1px solid #ddd; padding: 8px; text-align: left; vertical-align: top; }"
    yield "th { background-color: #4CAF50; color: white; }"
    yield "tr:nth-child(even) { background-color: #f2f2f2; }"
    yield ".assertions, .refs { font-size: 0.9em; color: #666; }"
    yield ".assertion-label { font-weight: bold; }"
    yield "details { margin: 5px 0; }"
    yield "summary { cursor: pointer; color: #4CAF50; }"
    yield "</style></head><body>"
    yield "<h1>Traceability Matrix</h1>"

    # Build header based on preset columns
    column_headers = {
        "id": "ID",
        "title": "Title",
        "level": "Level",
        "status": "Status",
        "implements": "Implements",
        "hash": "Hash",
        "file": "File",
    }
    headers = [column_headers.get(col, col.title()) for col in preset.columns]

    # Add extra columns for full preset
    if preset.include_assertions:
        headers.append("Assertions")
    if preset.include_code_refs:
        headers.append("Code Refs")
    if preset.include_test_refs:
        headers.append("Test Refs")

    yield "<table>"
    yield "<tr>" + "".join(f"<th>{h}</th>" for h in headers) + "</tr>"

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        data = _get_node_data(node, graph)
        cells = []
        for col in preset.columns:
            if col == "implements":
                impl_str = ", ".join(data["implements"]) or "-"
                cells.append(f"<td>{escape_html(impl_str)}</td>")
            elif col == "title":
                cells.append(f"<td>{escape_html(data['title'])}</td>")
            else:
                cells.append(f"<td>{escape_html(str(data.get(col, '')))}</td>")

        # Add extra columns for full preset
        if preset.include_assertions:
            if data["assertions"]:
                assertion_html = "<br>".join(
                    f"<span class='assertion-label'>{a['label']}:</span> {escape_html(a['text'])}"
                    for a in data["assertions"]
                )
                cells.append(f"<td class='assertions'>{assertion_html}</td>")
            else:
                cells.append("<td>-</td>")

        if preset.include_code_refs:
            if data["code_refs"]:
                refs_html = "<br>".join(f"<code>{escape_html(r)}</code>" for r in data["code_refs"])
                cells.append(f"<td class='refs'>{refs_html}</td>")
            else:
                cells.append("<td>-</td>")

        if preset.include_test_refs:
            if data["test_refs"]:
                refs_html = "<br>".join(f"<code>{escape_html(r)}</code>" for r in data["test_refs"])
                cells.append(f"<td class='refs'>{refs_html}</td>")
            else:
                cells.append("<td>-</td>")

        yield f"<tr>{''.join(cells)}</tr>"

    yield "</table></body></html>"


def format_json(graph: TraceGraph, preset: ReportPreset | None = None) -> Iterator[str]:
    """Generate JSON array. Streams one node at a time."""
    if preset is None:
        preset = REPORT_PRESETS[DEFAULT_PRESET]

    yield "["
    first = True
    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        if not first:
            yield ","
        first = False

        data = _get_node_data(node, graph)

        # Build node dict based on preset columns
        node_dict: dict = {}
        for col in preset.columns:
            if col == "file":
                node_dict["source"] = {
                    "path": node.source.path if node.source else None,
                    "line": node.source.line if node.source else None,
                }
            else:
                node_dict[col] = data.get(col)

        # Add extra fields for full preset
        if preset.include_body:
            node_dict["body"] = data["body"]
        if preset.include_assertions:
            node_dict["assertions"] = data["assertions"]
        if preset.include_code_refs:
            node_dict["code_refs"] = data["code_refs"]
        if preset.include_test_refs:
            node_dict["test_refs"] = data["test_refs"]

        yield json.dumps(node_dict, indent=2)
    yield "]"


# Implements: REQ-p00006-A
def format_view(graph: TraceGraph, embed_content: bool = False, base_path: str = "") -> str:
    """Generate interactive HTML via HTMLGenerator."""
    try:
        from elspais.html import HTMLGenerator
    except ImportError as err:
        raise ImportError(
            "HTMLGenerator requires the trace-view extra. "
            "Install with: pip install elspais[trace-view]"
        ) from err
    generator = HTMLGenerator(graph, base_path=base_path)
    return generator.generate(embed_content=embed_content)


def _is_port_in_use(port: int) -> bool:
    """Check if something is listening on 127.0.0.1:port."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _is_elspais_server(port: int) -> bool:
    """Check if an elspais server is running on the given port."""
    import json
    from urllib.request import urlopen

    try:
        with urlopen(f"http://127.0.0.1:{port}/api/status", timeout=2) as resp:
            data = json.loads(resp.read())
            return "node_counts" in data
    except Exception:
        return False


def _shutdown_server(port: int) -> bool:
    """Shut down an elspais server, preferring the API then falling back to OS kill."""
    import time
    from urllib.request import Request, urlopen

    # Try clean shutdown via API
    try:
        req = Request(f"http://127.0.0.1:{port}/api/shutdown", method="POST", data=b"")
        urlopen(req, timeout=3)
    except Exception:
        pass  # Server may drop connection as it exits — that's fine

    # Wait for the port to free up
    for _ in range(10):
        time.sleep(0.5)
        if not _is_port_in_use(port):
            return True

    # Fall back to OS-level kill
    import os
    import signal
    import subprocess

    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        pids = [int(p) for p in result.stdout.strip().split() if p.isdigit()]
        for pid in pids:
            os.kill(pid, signal.SIGTERM)

        time.sleep(2)
        if not _is_port_in_use(port):
            return True

        # Force kill
        for pid in pids:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        time.sleep(1)
    except Exception:
        pass

    return not _is_port_in_use(port)


def _find_free_port(start: int) -> int:
    """Find the next free port starting from start+1."""
    for port in range(start + 1, start + 51):
        if not _is_port_in_use(port):
            return port
    raise RuntimeError(f"No free port found in range {start + 1}-{start + 50}")


# Implements: REQ-d00010-A
def _run_server(args: argparse.Namespace, open_browser: bool = False) -> int:
    """Start the Flask trace-edit server.

    Builds the graph, creates the Flask app, and runs the dev server.

    Args:
        args: Parsed CLI arguments.
        open_browser: If True, open the browser automatically (--edit-mode).

    Returns:
        Exit code (0 = success).
    """
    try:
        from elspais.server import create_app
    except ImportError:
        print(
            "Error: Flask server requires the trace-review extra.\n"
            "Install with: pip install elspais[trace-review]",
            file=sys.stderr,
        )
        return 1

    from elspais.config import get_config
    from elspais.graph.factory import build_graph

    spec_dir = getattr(args, "spec_dir", None)
    config_path = getattr(args, "config", None)
    explicit_path = getattr(args, "path", None)
    repo_root = Path(explicit_path).resolve() if explicit_path else Path.cwd().resolve()

    config = get_config(start_path=repo_root, quiet=True)
    canonical_root = getattr(args, "canonical_root", None)
    graph = build_graph(
        spec_dirs=[spec_dir] if spec_dir else None,
        config_path=config_path,
        repo_root=repo_root,
        canonical_root=canonical_root,
    )

    app = create_app(repo_root=repo_root, graph=graph, config=config)
    app.config["ELSPAIS_DEBUG"] = getattr(args, "verbose", False)

    port = 5000
    quiet = getattr(args, "quiet", False)

    if _is_port_in_use(port):
        is_elspais = _is_elspais_server(port)

        if sys.stdin.isatty():
            if is_elspais:
                print(f"An elspais server is already running on port {port}.", file=sys.stderr)
            else:
                print(f"Port {port} is already in use by another process.", file=sys.stderr)
            print("  [R]eplace - stop existing and take over (default)", file=sys.stderr)
            print("  [N]ew port - start alongside on next free port", file=sys.stderr)
            print("  [A]bort - cancel", file=sys.stderr)
            choice = input("Choice [R/n/a]: ").strip().lower() or "r"
        else:
            choice = "n"

        if choice.startswith("a"):
            return 0
        elif choice.startswith("n"):
            port = _find_free_port(port)
        else:
            # Replace
            if is_elspais:
                if not quiet:
                    print(f"Shutting down existing server on port {port}...", file=sys.stderr)
                if not _shutdown_server(port):
                    print("Could not stop existing server. Using new port.", file=sys.stderr)
                    port = _find_free_port(port)
            else:
                print("Cannot replace non-elspais process. Using new port.", file=sys.stderr)
                port = _find_free_port(port)

    url = f"http://127.0.0.1:{port}"
    verbose = getattr(args, "verbose", False)

    if not quiet:
        print(f"Starting trace-edit server at {url}", file=sys.stderr)

    if open_browser:
        import subprocess
        import webbrowser

        # Suppress GTK/Chrome stderr noise from browser launch
        try:
            subprocess.Popen(
                ["xdg-open", url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            webbrowser.open(url)

    # Suppress Flask/Werkzeug noise unless verbose
    if not verbose:
        import logging

        logging.getLogger("werkzeug").setLevel(logging.ERROR)

    try:
        app.run(host="127.0.0.1", port=port, debug=False)
    except KeyboardInterrupt:
        if not quiet:
            print("\nServer stopped.", file=sys.stderr)

    return 0


def run(args: argparse.Namespace) -> int:
    """Run the trace command.

    Uses graph factory to build TraceGraph, then streams output in requested format.
    """
    # Handle --review-mode (still not implemented)
    if getattr(args, "review_mode", False):
        print("Error: --review-mode not yet implemented", file=sys.stderr)
        return 1

    # Handle --server and --edit-mode (trace-edit server)
    want_server = getattr(args, "server", False)
    want_edit = getattr(args, "edit_mode", False)
    if want_server or want_edit:
        return _run_server(args, open_browser=want_edit)

    # Parse --report preset
    report_name = getattr(args, "report", None)
    if report_name:
        if report_name not in REPORT_PRESETS:
            available = ", ".join(REPORT_PRESETS.keys())
            print(f"Error: Unknown report preset '{report_name}'", file=sys.stderr)
            print(f"Available presets: {available}", file=sys.stderr)
            return 1
        preset = REPORT_PRESETS[report_name]
    else:
        preset = REPORT_PRESETS[DEFAULT_PRESET]

    # Build graph using factory
    from elspais.graph.factory import build_graph

    spec_dir = getattr(args, "spec_dir", None)
    config_path = getattr(args, "config", None)
    canonical_root = getattr(args, "canonical_root", None)
    explicit_path = getattr(args, "path", None)
    repo_root = Path(explicit_path).resolve() if explicit_path else Path.cwd().resolve()

    graph = build_graph(
        spec_dirs=[spec_dir] if spec_dir else None,
        config_path=config_path,
        repo_root=repo_root,
        canonical_root=canonical_root,
    )

    # Handle --view mode (interactive HTML)
    if getattr(args, "view", False):
        try:
            # Get absolute base path for VS Code links
            base_path = str(repo_root)
            content = format_view(graph, getattr(args, "embed_content", False), base_path=base_path)
        except ImportError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

        output_path = args.output or Path("traceability_view.html")
        Path(output_path).write_text(content, encoding="utf-8")

        if not getattr(args, "quiet", False):
            print(f"Generated: {output_path}", file=sys.stderr)
        return 0

    # Handle --graph-json mode
    if getattr(args, "graph_json", False):
        from elspais.graph.annotators import annotate_graph_git_state
        from elspais.graph.serialize import serialize_graph

        annotate_graph_git_state(graph)
        output = json.dumps(serialize_graph(graph), indent=2)
        if args.output:
            Path(args.output).write_text(output, encoding="utf-8")
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

        with open(md_path, "w", encoding="utf-8") as f:
            for line in format_markdown(graph, preset):
                f.write(line + "\n")

        with open(csv_path, "w", encoding="utf-8") as f:
            for line in format_csv(graph, preset):
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

    line_generator = formatters[fmt](graph, preset)
    output_path = args.output

    # Stream output line by line
    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            for line in line_generator:
                f.write(line + "\n")
        if not getattr(args, "quiet", False):
            print(f"Generated: {output_path}", file=sys.stderr)
    else:
        for line in line_generator:
            print(line)

    return 0
