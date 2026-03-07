# Implements: REQ-d00085-A+B+C+D+E+F+G
"""
elspais.commands.report - Composable multi-section report system.

Accepts multiple section names (health, coverage, trace, changed) and renders
them in order, concatenating output. Shared flags apply globally. Exit code
is worst-of-all-sections.
"""
from __future__ import annotations

import argparse
import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

COMPOSABLE_SECTIONS = ("health", "coverage", "trace", "changed")

# Implements: REQ-d00085-E
FORMAT_SUPPORT = {
    "health": {"text", "markdown", "json"},
    "coverage": {"text", "markdown", "json", "csv"},
    "trace": {"text", "markdown", "json", "csv"},
    "changed": {"text", "json"},
}


def parse_shared_args(argv: list[str]) -> argparse.Namespace:
    """Parse shared flags for composed reports."""
    parser = argparse.ArgumentParser(prog="elspais", add_help=False)
    parser.add_argument(
        "--format",
        choices=["text", "markdown", "json", "csv"],
        default="text",
    )
    parser.add_argument("-o", "--output", type=Path)
    parser.add_argument("-q", "--quiet", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--lenient", action="store_true")
    parser.add_argument("--mode", choices=["core", "combined"], default="core")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--spec-dir", type=Path, dest="spec_dir")
    # Trace-specific shared flags
    parser.add_argument("--preset", choices=["minimal", "standard", "full"])
    parser.add_argument("--body", action="store_true")
    parser.add_argument("--assertions", dest="show_assertions", action="store_true")
    parser.add_argument("--tests", dest="show_tests", action="store_true")
    return parser.parse_args(argv)


# Implements: REQ-d00085-A+B+C
def run(
    sections: list[str],
    argv_remaining: list[str],
    canonical_root: Path | None = None,
) -> int:
    """Run composed report with multiple sections."""
    args = parse_shared_args(argv_remaining)
    args.canonical_root = canonical_root
    fmt = args.format

    # Validate format support for each section
    for section in sections:
        supported = FORMAT_SUPPORT.get(section, set())
        if fmt not in supported:
            supported_str = ", ".join(sorted(supported))
            print(
                f"Error: Format '{fmt}' not supported for '{section}'."
                f" Supported: {supported_str}",
                file=sys.stderr,
            )
            return 1

    # Build graph once for sections that need it
    graph = None
    config = None
    graph_sections = {"health", "coverage", "trace"}
    if set(sections) & graph_sections:
        from elspais.config import ConfigLoader, get_config
        from elspais.graph.factory import build_graph

        spec_dir = getattr(args, "spec_dir", None)
        config_path = getattr(args, "config", None)

        graph = build_graph(
            spec_dirs=[spec_dir] if spec_dir else None,
            config_path=config_path,
            canonical_root=canonical_root,
        )
        config_dict = get_config(config_path)
        config = ConfigLoader.from_dict(config_dict)

    outputs: list[str] = []
    worst_exit = 0

    for section in sections:
        output, exit_code = _render_section(section, graph, config, args)
        if output:
            outputs.append(output)
        worst_exit = max(worst_exit, exit_code)

    # Implements: REQ-d00085-G
    if args.lenient and worst_exit == 1:
        # Re-check: only suppress if it was warnings-only
        # (the individual sections already handle --lenient in their exit codes,
        # so this is a safety net for the composed case)
        pass

    combined = "\n\n".join(outputs)
    if args.output:
        args.output.write_text(combined + "\n" if combined else "")
        if not args.quiet:
            print(f"Generated: {args.output}", file=sys.stderr)
    else:
        if combined:
            print(combined)

    return worst_exit


def _render_section(
    name: str,
    graph,
    config,
    args: argparse.Namespace,
) -> tuple[str, int]:
    """Dispatch to the appropriate section renderer."""
    if name == "health":
        from elspais.commands.health import render_section

        return render_section(graph, config, args)
    elif name == "coverage":
        from elspais.commands.coverage import render_section

        return render_section(graph, args)
    elif name == "trace":
        from elspais.commands.trace import render_section

        return render_section(graph, args)
    elif name == "changed":
        return _render_changed(args)
    else:
        return f"Error: Unknown section '{name}'", 1


def _render_changed(args: argparse.Namespace) -> tuple[str, int]:
    """Render changed section by capturing stdout from changed.run()."""
    from elspais.commands import changed

    buf = io.StringIO()
    with redirect_stdout(buf):
        exit_code = changed.run(args)
    return buf.getvalue().rstrip("\n"), exit_code
