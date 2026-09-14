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
    # Implements: REQ-d00278-C
    # `extend` rather than the default store: a property accumulates across
    # repetitions of its flag here exactly as it does on the tyro side
    # (`args.ScopeOptions`), so a composed report reads the same invocation the
    # same way a section asked for alone does.
    parser.add_argument("--level", nargs="*", action="extend", default=None)
    parser.add_argument("--not-level", nargs="*", action="extend", default=None, dest="not_level")
    parser.add_argument("--status", nargs="*", action="extend", default=None)
    parser.add_argument("--not-status", nargs="*", action="extend", default=None, dest="not_status")
    parser.add_argument("--match-status-roles", action="store_true", dest="match_status_roles")
    parser.add_argument("--scope", default=None)
    # Implements: REQ-d00282-E
    # The other axis of the same report, registered here for the same reason:
    # a selection this parser does not read is one the composed report cannot
    # honour, and a section composed with others would state different values
    # from the same section asked for alone.
    parser.add_argument("--values", default=None)
    parser.add_argument(
        "--treat-active", nargs="*", action="extend", default=None, dest="treat_active"
    )
    # Trace-specific shared flags
    parser.add_argument("--preset", choices=["minimal", "standard", "full"])
    parser.add_argument("--body", action="store_true")
    parser.add_argument("--assertions", dest="show_assertions", action="store_true")
    parser.add_argument("--tests", dest="show_tests", action="store_true")
    return parser.parse_args(argv)


# Implements: REQ-d00282-F
# name: VALUE_SECTIONS
# use:  which composable sections a values selection selects among, and where
#       each one's offer is declared.
# def:  section name -> the module owning the values it offers.
#
# A section states facts about each requirement (`summary`, `trace`) or lists
# the requirements one dimension has not credited (the four shortfall
# listings). Both read a dimension, so both have values to select among: the
# first decides which columns are stated, the second which listings appear.
#
# The sections left out state nothing about a requirement at all -- `checks`
# and its narrowings report findings, `changed` reports files -- so a values
# selection reaching one of them names nothing it offers and is refused.
VALUE_SECTIONS: dict[str, str] = {
    "summary": "elspais.commands.summary",
    "trace": "elspais.commands.trace",
    "gaps": "elspais.commands.gaps",
    "uncovered": "elspais.commands.gaps",
    "untested": "elspais.commands.gaps",
    "unvalidated": "elspais.commands.gaps",
    "failing": "elspais.commands.gaps",
}


# Implements: REQ-d00282-A
def _offered_by(section: str) -> tuple[str, ...]:
    """The values one composable section offers.

    A module whose sections each offer a different set declares them in
    ``COMMAND_VALUES`` keyed by section name -- a shorthand listing offers the
    one dimension it IS, so `uncovered --values tested` is refused rather than
    quietly becoming `untested`. Everything else offers one set.
    """
    from importlib import import_module

    module = import_module(VALUE_SECTIONS[section])
    per_section = getattr(module, "COMMAND_VALUES", None)
    if per_section is not None and section in per_section:
        return tuple(per_section[section])
    return tuple(module.OFFERED_VALUES)


# Implements: REQ-d00282-F
def _refuse_unhonourable_values(sections: list[str], args: argparse.Namespace) -> str | None:
    """The reason this composition cannot honour its selection, or None.

    Judged before anything is built and before anything is written, because a
    refusal that has already produced an artifact has produced the report it
    refused. A reader who names a value no section offers, and a reader who
    names a section that states nothing about a requirement, are both asking
    for a report the tool cannot assemble.
    """
    from elspais.commands._values import (
        UnofferedValues,
        value_silent_refusal,
        values_from_args,
    )
    from elspais.config import get_config
    from elspais.graph.values import resolve_values

    config = get_config(getattr(args, "config", None))
    silent = [s for s in sections if s not in VALUE_SECTIONS]
    if silent:
        # The same helper the standalone invocation of such a section uses, so
        # composing it and asking for it alone refuse in the same words
        # (REQ-d00279-C, REQ-d00085-D).
        refusal = value_silent_refusal(args, config, ", ".join(sorted(set(silent))))
        if refusal is not None:
            return refusal
    selection = values_from_args(args, config)
    if selection is None:
        return None
    for section in sections:
        if section not in VALUE_SECTIONS:
            continue
        try:
            resolve_values(selection, _offered_by(section), identity_key="")
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
    elif name in ("uncovered", "untested", "unvalidated", "failing", "gaps"):
        # The section composed with others is the standalone command: it reads
        # the same selection, offers the same values and refuses the same names
        # (REQ-d00279-C).
        from elspais.commands._values import UnofferedValues
        from elspais.commands.gaps import render_section as gap_render

        try:
            return gap_render(graph, config, args, command=name)
        except UnofferedValues as exc:
            return f"Error: {name}: {exc}", 1
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
