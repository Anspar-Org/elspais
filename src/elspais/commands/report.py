# Implements: REQ-d00085-A+B+C+D+E+F+G+K+L
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
    "no_assertions",
    "gaps",
    "unresolved",
    "uncited",
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
    "no_assertions": {"text", "markdown", "json"},
    "gaps": {"text", "markdown", "json"},
    "unresolved": {"text", "markdown", "json"},
    "uncited": {"text", "markdown", "json"},
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
    "no_assertions": 16,
    "gaps": 16,
    "unresolved": 32,
    "uncited": 64,
}


# Implements: REQ-d00279-C
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
    # A composed report is assembled differently from the same section asked for
    # alone, and this parser is where the difference would show: a selection it
    # does not register is a selection the composed report cannot honour.
    parser.add_argument("--level", nargs="*", default=None)
    parser.add_argument("--not-level", nargs="*", default=None, dest="not_level")
    parser.add_argument("--status", nargs="*", default=None)
    parser.add_argument("--not-status", nargs="*", default=None, dest="not_status")
    parser.add_argument("--match-status-roles", action="store_true", dest="match_status_roles")
    parser.add_argument("--scope", default=None)
    # Implements: REQ-d00282-E
    # The other axis of the same report, registered here for the same reason:
    # a selection this parser does not read is one the composed report cannot
    # honour, and a section composed with others would state different values
    # from the same section asked for alone.
    parser.add_argument("--values", default=None)
    parser.add_argument("--treat-active", nargs="*", default=None, dest="treat_active")
    # Trace-specific shared flags
    parser.add_argument("--preset", choices=["minimal", "standard", "full"])
    parser.add_argument("--body", action="store_true")
    parser.add_argument("--assertions", dest="show_assertions", action="store_true")
    parser.add_argument("--tests", dest="show_tests", action="store_true")
    return parser.parse_args(argv)


# Implements: REQ-d00282-F
# name: VALUE_SECTIONS
# use:  which composable sections state facts about each requirement at all.
# def:  section name -> the module owning the values it offers.
#
# The rest emit lists of what is missing rather than tables of facts about
# requirements, so they have no values to select among. A selection reaching
# one of them is a selection the composed report cannot honour, and F wants no
# report produced under one honoured in part.
VALUE_SECTIONS: dict[str, str] = {
    "summary": "elspais.commands.summary",
    "trace": "elspais.commands.trace",
}


# Implements: REQ-d00282-F
def _refuse_unhonourable_values(sections: list[str], args: argparse.Namespace) -> str | None:
    """The reason this composition cannot honour its selection, or None.

    Judged before anything is built and before anything is written, because a
    refusal that has already produced an artifact has produced the report it
    refused. A reader who names a value no section offers, and a reader who
    names a section that states no values, are both asking for a report the
    tool cannot assemble.
    """
    from importlib import import_module

    from elspais.commands._values import UnofferedValues, values_from_args
    from elspais.config import get_config
    from elspais.graph.values import resolve_values

    # Read against the project's own declarations too: a selection a named
    # scope carries (REQ-d00280-C) is refused on the same terms as one written
    # on the invocation.
    selection = values_from_args(args, get_config(getattr(args, "config", None)))
    if selection is None:
        return None
    silent = [s for s in sections if s not in VALUE_SECTIONS]
    if silent:
        named = ", ".join(sorted(set(silent)))
        return (
            f"--values states which facts a report gives about each requirement, "
            f"and '{named}' states none: it lists what is missing. "
            "Ask for it without --values, or compose only sections that state values."
        )
    for section in sections:
        module = import_module(VALUE_SECTIONS[section])
        try:
            resolve_values(selection, module.OFFERED_VALUES)
        except UnofferedValues as exc:
            return f"{section}: {exc}"
    return None


# Implements: REQ-d00085-A+B+C
def run(
    sections: list[str],
    argv_remaining: list[str],
) -> int:
    """Run composed report with multiple sections."""
    args = parse_shared_args(argv_remaining)
    fmt = args.format

    # Validate format support for each section
    for section in sections:
        supported = FORMAT_SUPPORT.get(section, set())
        if fmt not in supported:
            supported_str = ", ".join(sorted(supported))
            print(
                f"Error: Format '{fmt}' not supported for '{section}'. Supported: {supported_str}",
                file=sys.stderr,
            )
            return 1

    # Implements: REQ-d00282-F
    refusal = _refuse_unhonourable_values(sections, args)
    if refusal is not None:
        print(f"Error: {refusal}", file=sys.stderr)
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
        "no_assertions",
        "gaps",
        "unresolved",
        "uncited",
    }
    if set(sections) & graph_sections:
        from elspais.config import get_config
        from elspais.graph.factory import build_graph

        spec_dir = getattr(args, "spec_dir", None)
        config_path = getattr(args, "config", None)

        graph = build_graph(
            spec_dirs=[spec_dir] if spec_dir else None,
            config_path=config_path,
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

        return render_section(graph, args, config)
    elif name == "changed":
        return _render_changed(args)
    elif name in ("uncovered", "untested", "unvalidated", "failing", "no_assertions"):
        from elspais.commands.gaps import render_section as gap_render

        return gap_render(graph, config, args, gap_types=[name])
    elif name == "gaps":
        from elspais.commands.gaps import render_section as gap_render

        return gap_render(graph, config, args)
    elif name in ("unresolved", "uncited"):
        # The same narrowing the standalone command applies (REQ-d00285-C):
        # a section composed with others says what the command alone says.
        from elspais.commands.health import render_section

        return render_section(graph, config, args, preset=name)
    else:
        return f"Error: Unknown section '{name}'", 1


# Implements: REQ-d00085-D
def _render_changed(args: argparse.Namespace) -> tuple[str, int]:
    """Render changed section by capturing stdout from changed.run()."""
    from elspais.commands import changed

    buf = io.StringIO()
    with redirect_stdout(buf):
        exit_code = changed.run(args)
    return buf.getvalue().rstrip("\n"), exit_code
