# Implements: REQ-d00085-A+B+C+D+E+F+G
"""
elspais.commands.report - Composable multi-section report system.

Accepts multiple section names (health, summary, trace, changed) and renders
them in order, concatenating output. Shared flags apply globally. Exit code
is worst-of-all-sections.
"""
from __future__ import annotations

import argparse
import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

COMPOSABLE_SECTIONS = (
    "checks",
    "summary",
    "trace",
    "changed",
    "uncovered",
    "untested",
    "unvalidated",
    "failing",
    "gaps",
    "broken",
    "unlinked",
)

# Implements: REQ-d00085-E
FORMAT_SUPPORT = {
    "checks": {"text", "markdown", "json", "junit", "sarif"},
    "summary": {"text", "markdown", "json", "csv"},
    "trace": {"text", "markdown", "json", "csv"},
    "changed": {"text", "json"},
    "uncovered": {"text", "markdown", "json"},
    "untested": {"text", "markdown", "json"},
    "unvalidated": {"text", "markdown", "json"},
    "failing": {"text", "markdown", "json"},
    "gaps": {"text", "markdown", "json"},
    "broken": {"text", "markdown", "json"},
    "unlinked": {"text", "markdown", "json"},
}

EXIT_BIT: dict[str, int] = {
    "checks": 1,
    "summary": 2,
    "trace": 4,
    "changed": 8,
    "uncovered": 16,
    "untested": 16,
    "unvalidated": 16,
    "failing": 16,
    "gaps": 16,
    "broken": 32,
    "unlinked": 64,
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
    graph_sections = {
        "checks",
        "summary",
        "trace",
        "uncovered",
        "untested",
        "unvalidated",
        "failing",
        "gaps",
        "broken",
        "unlinked",
    }
    if set(sections) & graph_sections:
        from elspais.config import get_config
        from elspais.graph.factory import build_graph

        spec_dir = getattr(args, "spec_dir", None)
        config_path = getattr(args, "config", None)

        graph = build_graph(
            spec_dirs=[spec_dir] if spec_dir else None,
            config_path=config_path,
            canonical_root=canonical_root,
        )
        config = get_config(config_path)

    outputs: list[str] = []
    combined_exit = 0

    for section in sections:
        output, exit_code = _render_section(section, graph, config, args)
        if output:
            outputs.append(output)
        if exit_code:
            combined_exit |= EXIT_BIT.get(section, 0)

    combined = "\n\n".join(outputs)
    if args.output:
        args.output.write_text(combined + "\n" if combined else "")
        if not args.quiet:
            print(f"Generated: {args.output}", file=sys.stderr)
    else:
        if combined:
            print(combined)

    return combined_exit


def _render_section(
    name: str,
    graph,
    config,
    args: argparse.Namespace,
) -> tuple[str, int]:
    """Dispatch to the appropriate section renderer."""
    if name == "checks":
        from elspais.commands.health import render_section

        return render_section(graph, config, args)
    elif name == "summary":
        from elspais.commands.summary import render_section

        raw_config = config if config is not None else None
        return render_section(graph, args, config=raw_config)
    elif name == "trace":
        from elspais.commands.trace import render_section

        return render_section(graph, args)
    elif name == "changed":
        return _render_changed(args)
    elif name in ("uncovered", "untested", "unvalidated", "failing"):
        from elspais.commands.gaps import render_section as gap_render

        return gap_render(graph, config, args, gap_types=[name])
    elif name == "gaps":
        from elspais.commands.gaps import render_section as gap_render

        return gap_render(graph, config, args)
    elif name == "broken":
        from elspais.commands.broken import render_section as broken_render

        return broken_render(graph, config, args)
    elif name == "unlinked":
        from elspais.commands.unlinked import render_section as unlinked_render

        return unlinked_render(graph, config, args)
    else:
        return f"Error: Unknown section '{name}'", 1


def _render_changed(args: argparse.Namespace) -> tuple[str, int]:
    """Render changed section by capturing stdout from changed.run()."""
    from elspais.commands import changed

    buf = io.StringIO()
    with redirect_stdout(buf):
        exit_code = changed.run(args)
    return buf.getvalue().rstrip("\n"), exit_code
