# Implements: REQ-d00085-A+B+C+D+E+F+G+K+L
"""
elspais.commands.report - Composable multi-section report system.

Accepts multiple section names (`COMPOSABLE_SECTIONS`) and renders them in
order, concatenating output. Shared flags apply globally. The exit code sets
one bit per failing section.
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
    "malformed",
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
    "malformed": {"text", "markdown", "json"},
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
    "malformed": 128,
}


# Implements: REQ-d00085-F
# name: QUIET_FORMATS
# use:  the renderings `-q`/`--quiet` collapses to one summary line.
# def:  the formats a person reads. A structured format is read by a program,
#       which needs the whole document whatever the terminal wanted.
QUIET_FORMATS = frozenset({"text", "markdown"})


def renders_quietly(args: argparse.Namespace, default_format: str = "text") -> bool:
    """Whether this invocation asked a section for its one summary line."""
    fmt = getattr(args, "format", None) or default_format
    return bool(getattr(args, "quiet", False)) and fmt in QUIET_FORMATS


# Implements: REQ-d00279-C, REQ-d00085-B+P
def shared_parser() -> argparse.ArgumentParser:
    """The parser for the flags a composed report reads.

    The one declaration of those flags: `cli.main` reads it too, to tell a
    flag's value from a section name when the flags precede the sections.
    """
    parser = argparse.ArgumentParser(prog="elspais", add_help=False)
    # Every format some section renders. A format a named section does not
    # render is refused by `run`, naming the section.
    parser.add_argument(
        "--format",
        choices=sorted(set().union(*FORMAT_SUPPORT.values())),
        default="text",
    )
    parser.add_argument("-o", "--output", type=Path)
    # The same spellings the single-section parser accepts for these globals,
    # including the negated ones, so a flag reads alike on both paths.
    parser.add_argument("-q", "--quiet", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("-v", "--verbose", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--lenient", action="store_true")
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
    parser.add_argument("--preset", choices=["minimal", "standard", "full", "evidence"])
    parser.add_argument("--body", action="store_true")
    parser.add_argument("--assertions", dest="show_assertions", action="store_true")
    parser.add_argument("--tests", dest="show_tests", action="store_true")
    # Implements: REQ-d00085-P
    # The selection `summary` and `trace` read alone, read here with the same
    # accumulation, and resolved by `run` through the same function.
    parser.add_argument("--targets", nargs="*", action="extend", default=None)
    return parser


def parse_shared_args(argv: list[str]) -> argparse.Namespace:
    """Parse shared flags for composed reports."""
    return shared_parser().parse_args(argv)


# Implements: REQ-d00085-P+Q
# name: TARGET_SECTIONS
# use:  the sections that read a test-target selection.
# def:  the sections whose standalone command accepts `--targets` to mark
#       provenance. `checks` reads it only to run targets, which a composed
#       report never does.
TARGET_SECTIONS = ("summary", "trace")

# The flags every invocation reads, whichever sections it names.
_GLOBAL_DESTS = frozenset({"format", "output", "quiet", "verbose", "config", "spec_dir"})


def _section_options() -> dict[str, frozenset[str]]:
    """The options each composable section accepts when asked for alone.

    Read off the section's own argument class, so what a composition accepts
    for a section is what that section accepts alone.
    """
    import dataclasses
    import typing

    from elspais.commands.args import Command

    accepted: dict[str, frozenset[str]] = {}
    for arg in typing.get_args(Command):
        base, *meta = typing.get_args(arg)
        names = [m.name for m in meta if hasattr(m, "name")]
        if names and names[0] in COMPOSABLE_SECTIONS:
            accepted[names[0]] = frozenset(f.name for f in dataclasses.fields(base))
    return accepted


# Implements: REQ-d00085-Q
def _unread_option(sections: list[str], args: argparse.Namespace) -> str | None:
    """The refusal for an option no section in this composition reads, or None.

    A section reads an option it accepts alone. A test-target selection is
    read only by the sections in `TARGET_SECTIONS`: `checks` accepts one alone
    to choose what it runs, and a composed report runs nothing.
    """
    accepted = _section_options()
    for action in shared_parser()._actions:
        dest = action.dest
        # A values selection has its own refusal, `_unhonourable_selection`.
        if dest in _GLOBAL_DESTS or dest == "values" or not action.option_strings:
            continue
        value = getattr(args, dest, None)
        if value in (None, False, [], action.default):
            continue
        if dest == "targets":
            readers = list(TARGET_SECTIONS)
        else:
            readers = sorted(s for s, fields in accepted.items() if dest in fields)
        if any(section in readers for section in sections):
            continue
        flag = max(action.option_strings, key=len)
        return (
            f"{flag} is read by {', '.join(readers)}, and this report names none of "
            f"them. Add one, or drop {flag}."
        )
    return None


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


# Implements: REQ-d00282-A
def _identity_key_for(section: str) -> str:
    """What a row of this section is about, for the values it offers.

    Read off the owning module the same way ``_offered_by`` reads its offer --
    a module whose rows are not one requirement each (``summary``) names its
    own; everything else states nothing beyond a value (REQ-d00282-A).
    """
    from importlib import import_module

    module = import_module(VALUE_SECTIONS[section])
    return getattr(module, "IDENTITY_VALUE", "")


# Implements: REQ-d00282-F, REQ-d00279-C
def _unhonourable_selection(
    sections: list[str], args: argparse.Namespace, config: dict | None
) -> str | None:
    """The reason this composition cannot honour its selection, or None.

    Judged before anything is built and before anything is written, because a
    refusal that has already produced an artifact has produced the report it
    refused. A reader who names a value no section offers, and a reader who
    names a section that states nothing about a requirement, are both asking
    for a report the tool cannot assemble.

    Judged through the one edge a standalone invocation uses
    (``report_inputs_from_args``) rather than a second, hand-rolled check, so
    a composed report refuses exactly what asking for the section alone
    would. Each section's own ``ReportInputs`` is derived and discarded here
    on purpose: nothing downstream needs the resolved scope or selection this
    early, only whether resolving it raises -- each section's renderer
    derives its own copy later, from the same deterministic edge, at the
    point it actually renders.
    """
    from elspais.commands._edges import report_inputs_from_args
    from elspais.commands._values import UnofferedValues, value_silent_refusal

    silent = [s for s in sections if s not in VALUE_SECTIONS]
    if silent:
        # The same helper the standalone invocation of such a section uses, so
        # composing it and asking for it alone refuse in the same words
        # (REQ-d00279-C, REQ-d00085-D).
        refusal = value_silent_refusal(args, config, ", ".join(sorted(set(silent))))
        if refusal is not None:
            return refusal
    for section in sections:
        if section not in VALUE_SECTIONS:
            continue
        try:
            report_inputs_from_args(args, config, _offered_by(section), _identity_key_for(section))
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

    unread = _unread_option(sections, args)
    if unread is not None:
        print(f"error: {unread}", file=sys.stderr)
        return 2

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

    from elspais.config import get_config

    config = get_config(getattr(args, "config", None))

    # Implements: REQ-d00282-F
    # Refused before anything is built, using the same edge each standalone
    # invocation resolves its own inputs through. Each section's renderer
    # below re-derives its own inputs from `args` rather than being handed
    # what was resolved here -- the values are identical because both calls
    # reach the same deterministic edge, and `_render_section`'s dispatch
    # shape (name, graph, config, args) is a standalone command's own
    # signature, not a composition-only interface a derived value could be
    # threaded through.
    refusal = _unhonourable_selection(sections, args, config)
    if refusal is not None:
        print(f"Error: {refusal}", file=sys.stderr)
        return 1

    # Implements: REQ-d00085-P+Q, REQ-d00283-H+K
    # Resolved the way `summary` and `trace` resolve it alone, so a composed
    # report marks the same targets fresh and refuses the same selections.
    from elspais.commands._targets import resolve_fresh_targets

    fresh_targets = None
    if any(section in TARGET_SECTIONS for section in sections):
        try:
            fresh_targets = resolve_fresh_targets(args, config)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    # Build graph once for sections that need it
    graph = None
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
        "malformed",
        "uncited",
    }
    if set(sections) & graph_sections:
        from elspais.graph.factory import build_graph

        spec_dir = getattr(args, "spec_dir", None)

        graph = build_graph(
            spec_dirs=[spec_dir] if spec_dir else None,
            config_path=getattr(args, "config", None),
            fresh_targets=fresh_targets,
        )

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
    elif name in ("unresolved", "malformed", "uncited"):
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
