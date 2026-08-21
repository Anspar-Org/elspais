"""
elspais.commands.summary - Coverage summary report section.

The report that AGGREGATES: every row is a level, not a requirement, and every
figure in it is the summed credit over the summed assertions of that group
(REQ-d00258-P). Alongside the level table it renders an External integrations
table when `Integrates:` references are present. Supports text, markdown, json
and csv output.

Which facts each row states is a column selection (REQ-d00282), read off the
invocation and carried to a serving process so a daemon-answered report states
the same columns a locally computed one does. Every coverage dimension of
REQ-d00277 is offered here -- Implemented, Tested, Passing, UAT Covered and UAT
Passed -- each as its per-*Assertion* total and each of the four measures behind
it (REQ-d00069-L). The line dimensions of REQ-d00254-B are deliberately absent:
they are measured in lines, and a level has no line figure.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from elspais.graph.federated import FederatedGraph

from elspais.graph.aggregation import (
    COVERAGE_DIMENSIONS,
    MEASURE_WORDS,
    MEASURES,
    collect_coverage,
)
from elspais.graph.columns import (
    COLUMN_SPECS,
    MEASURE_KEY_SEPARATOR,
    figure_cell,
    header_for,
)
from elspais.graph.metrics import fmt_assertion_count


# Implements: REQ-d00282-A+B+L
# name: OFFERED_COLUMNS
# use:  the columns this report offers, in the order it states them absent a
#       selection. Built from the estate's own vocabularies rather than written
#       out, so a dimension or a measure added to REQ-d00277/REQ-d00069-L is
#       offered here without this module being edited.
# def:  the identity column naming what each row is about (REQ-d00282-L -- a
#       level, not a requirement), the two counts describing the group itself,
#       then each coverage dimension's per-*Assertion* total and the four
#       measures behind it. The counts are OFFERED rather than prepended: a
#       reader who named one column is answered with one column.
def _offered_columns() -> tuple[str, ...]:
    keys: list[str] = ["level", "requirements", "assertions"]
    for dimension in COVERAGE_DIMENSIONS:
        keys.append(dimension)
        keys.extend(f"{dimension}{MEASURE_KEY_SEPARATOR}{m}" for m in MEASURES)
    return tuple(keys)


OFFERED_COLUMNS: tuple[str, ...] = _offered_columns()

# This report declares no named default sets, so a reader who names nothing is
# answered with everything it offers.
DEFAULT_COLUMNS: tuple[str, ...] = OFFERED_COLUMNS

# The identity column: these rows are groups of requirements, so what a row is
# about is a level (REQ-d00282-L).
IDENTITY_COLUMN = "level"

# Implements: REQ-d00258-C
# The column vocabulary names a dimension by the attribute REQ-d00277 defines it
# under; ``collect_coverage`` keys its payload under the words the level table
# grew up with. One map rather than a lookup per renderer, so no surface can
# read a column off a field belonging to a different dimension.
_PAYLOAD_PREFIX: dict[str, str] = {
    "implemented": "implemented",
    "tested": "tested",
    "verified": "passing",
    "uat_coverage": "uat_covered",
    "uat_verified": "uat_passed",
}


# Implements: REQ-d00282-M
def _figure(level_row: dict, key: str) -> float | None:
    """The figure one level states in one column, or None where it states none.

    A group whose requirements confer no *Assertion* has no coverage figure to
    state -- not a figure of zero. Returning None rather than 0.0 is what lets
    every renderer keep the two apart, so a reader never reads an absence as
    work undone that was never owed.
    """
    spec = COLUMN_SPECS[key]
    if not spec.states_a_figure:
        return None
    if not level_row.get("total_assertions"):
        return None
    prefix = _PAYLOAD_PREFIX[spec.dimension]
    field = f"{prefix}_{spec.measure}" if spec.measure else f"{prefix}_total_covered"
    return level_row.get(field)


def _stated_columns(data: dict) -> tuple[str, ...]:
    """The columns this rendering states.

    Read off the payload rather than off the invocation, because the payload is
    what reaches a formatter by either path -- computed here or handed back by a
    serving process. A payload carrying no stamp is one produced under no
    selection, and states the report's default set (REQ-d00282-E).
    """
    stated = data.get("columns")
    return tuple(stated) if stated else DEFAULT_COLUMNS


def _resolve_columns(args_or_params: Any, config: dict | None) -> tuple[str, ...]:
    from elspais.commands._columns import resolve_report_columns

    return resolve_report_columns(
        args_or_params,
        OFFERED_COLUMNS,
        DEFAULT_COLUMNS,
        config,
        identity_key=IDENTITY_COLUMN,
    )


def _stamp_columns(data: dict, args_or_params: Any, config: dict | None) -> None:
    """Record the stated columns on the payload, where a selection named any.

    Stamped only when something was named: an unstamped payload is the default
    report, and stamping the default would make a consumer unable to tell a
    reader who asked for everything from one who asked for nothing.
    """
    from elspais.commands._columns import columns_from_args, columns_from_params

    named = (
        columns_from_params(args_or_params)
        if isinstance(args_or_params, dict)
        else columns_from_args(args_or_params, config)
    )
    resolved = _resolve_columns(args_or_params, config)
    if named is not None:
        data["columns"] = list(resolved)


# Implements: REQ-d00085-A, REQ-d00086-A+B+C+D
def render_section(
    graph: FederatedGraph,
    args: argparse.Namespace,
    config: dict | None = None,
) -> tuple[str, int]:
    """Render coverage as a composed report section.

    Returns (formatted_output, exit_code).
    """
    fmt = getattr(args, "format", "text") or "text"
    # Implements: REQ-p00084-A+D, REQ-d00279-C
    from elspais.commands._columns import UnofferedColumns
    from elspais.commands._scope import resolve_scope_for_report, scope_disclosure

    result = resolve_scope_for_report(graph, args, config)
    ids = None if len(result.ids) == result.population else result.ids
    data = collect_coverage(graph, config=config, node_ids=ids)
    data["scope"] = scope_disclosure(result)
    # Implements: REQ-d00282-F
    # A section composed with others honours the same selection it honours
    # alone, and refuses on the same terms: a report produced under a selection
    # honoured in part looks exactly like the one the reader asked for.
    try:
        _stamp_columns(data, args, config)
    except UnofferedColumns as exc:
        return f"Coverage Summary\nerror: {exc}", 1
    content = _render(data, fmt, config)
    return content.rstrip("\n"), 0


# Implements: REQ-d00279-C
def compute_summary(graph: FederatedGraph, config: dict, params: dict[str, str]) -> dict:
    """Engine-compatible wrapper around the shared coverage collector.

    Reads both the scope and the column selection from ``params``: this is the
    path a summary takes when a serving process answers it, and either axis
    failing to survive the trip would make that answer differ from a locally
    computed one (REQ-d00279-C, REQ-d00282-E).
    """
    from elspais.commands._scope import resolve_scope_for_report, scope_disclosure

    result = resolve_scope_for_report(graph, params, config)
    ids = None if len(result.ids) == result.population else result.ids
    data = collect_coverage(graph, config=config, node_ids=ids)
    data["scope"] = scope_disclosure(result)
    # Implements: REQ-d00282-E
    # The selection travels in ``params`` for the same reason the scope does: a
    # report answered by a serving process states the columns the reader asked
    # for, or a daemon-served report and a locally computed one disagree about
    # the same estate.
    _stamp_columns(data, params, config)
    return data


def run(args: argparse.Namespace) -> int:
    """Run the coverage command.

    Tries a running daemon/viewer first for fast results,
    falls back to local graph build. --targets forces a local build so the
    fresh set threads into build_graph() (a cached daemon graph can't know
    which targets this invocation considers fresh).
    """
    from elspais.commands._columns import UnofferedColumns, column_params_from_args
    from elspais.commands._engine import call as engine_call
    from elspais.commands._scope import scope_params_from_args
    from elspais.config import get_config

    fmt = getattr(args, "format", "text") or "text"
    spec_dir = getattr(args, "spec_dir", None)
    config_path = getattr(args, "config", None)
    config = get_config(config_path)
    # Implements: REQ-d00254-I
    fresh_targets = set(args.targets) if getattr(args, "targets", None) else None

    # Implements: REQ-d00282-F
    # Judged before anything is built or asked of a serving process: a report is
    # not produced under a selection the tool cannot honour in full, and a
    # reader told so before the work starts is told the same thing however the
    # report would have been answered.
    try:
        _resolve_columns(args, config)
    except UnofferedColumns as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2

    params = {**scope_params_from_args(args, config), **column_params_from_args(args, config)}

    if fresh_targets is not None:
        from elspais.graph.factory import build_graph

        graph = build_graph(
            spec_dirs=[spec_dir] if spec_dir else None,
            config_path=config_path,
            fresh_targets=fresh_targets,
        )
        data = compute_summary(graph, config, params)
        data["graph_source"] = {"type": "local"}
    else:
        data = engine_call(
            "/api/run/summary",
            params,
            compute_summary,
            skip_daemon=bool(spec_dir),
            config_path=config_path,
        )

    # Stamped again from the invocation, so the columns stated are the ones this
    # reader asked for even where the payload was computed by another process
    # (REQ-d00282-E+F). The figures are untouched: a selection decides which
    # facts are stated, never what they are (REQ-d00282-D).
    _stamp_columns(data, args, config)

    content = _render(data, fmt, config)
    sys.stdout.write(content)

    return 0


def _pct(num: int, denom: int) -> float:
    return round(num / denom * 100, 1) if denom > 0 else 0.0


# Implements: REQ-d00282-E
# Every format renders from one resolved column list carried on the payload, so
# a selection means the same thing in the artifact a reader checks and in the
# one they file.
def _render(data: dict, fmt: str, config: dict | None = None) -> str:
    from elspais.utilities.report_meta import report_metadata

    data["meta"] = report_metadata()
    if fmt == "json":
        return _render_json(data)
    elif fmt == "csv":
        return _render_csv(data, config)
    elif fmt == "markdown":
        return _render_markdown(data, config)
    else:
        return _render_text(data, config)


# Implements: REQ-d00282-M
# The mark a column stating no figure carries. "-" and "0" are different facts,
# and a reader shown one for the other concludes work is undone that was never
# owed. One mark for every format people read, so the two never look alike in
# one rendering and different in another (REQ-d00282-E); JSON carries ``null``,
# which is the same distinction in a format that has one.
ABSENT_FIGURE = "-"


# Implements: REQ-d00282-E+M
def _cell(level_row: dict, key: str, carry: str = "") -> str:
    """The text one level states in ONE column.

    Every format people read states its rows through here, so a named column is
    one column with one value wherever it is rendered. A figure carries its own
    denominator and proportion (``102/187 (54.5%)``) rather than leaning on
    companion columns: a figure and what it was taken over are one fact, and
    splitting them is what made one named column produce five in CSV.
    """
    if key == "level":
        return str(level_row["level"])
    if key == "requirements":
        return str(level_row["total"])
    if key == "assertions":
        return str(level_row["total_assertions"])
    figure = _figure(level_row, key)
    if figure is None:
        return ABSENT_FIGURE
    spec = COLUMN_SPECS[key]
    cell = figure_cell(figure, level_row["total_assertions"], decimals=1)
    if spec.measure:
        return cell
    if spec.dimension == "verified":
        cell += carry
    # Implements: REQ-d00258-O
    # The breakdown QUALIFIES the Tested figure, so it rides inside that
    # figure's cell in every format. Given cells of its own it read as three
    # further columns, which is a display term of its own -- the thing O
    # forbids -- and made the Tested selection state four columns in CSV and
    # one in markdown.
    if spec.dimension == "tested":
        cell += _tested_breakdown(level_row)
    return cell


# Implements: REQ-d00282-K
def _column_groups(keys: tuple[str, ...]) -> list[tuple[str, str, tuple[str, ...]]]:
    """The stated columns in the stated order, consecutive measures gathered.

    Grouping decides only how a run of measures is LAID OUT; it never moves a
    column past another, so a report still states its columns in the order the
    selection named them. Yields ``(kind, dimension, keys)`` where kind is
    "measures" for a gathered run and "column" for anything else.
    """
    groups: list[tuple[str, str, tuple[str, ...]]] = []
    index = 0
    while index < len(keys):
        spec = COLUMN_SPECS[keys[index]]
        if not spec.measure:
            groups.append(("column", spec.dimension, (keys[index],)))
            index += 1
            continue
        run: list[str] = []
        while index < len(keys):
            nxt = COLUMN_SPECS[keys[index]]
            if not nxt.measure or nxt.dimension != spec.dimension:
                break
            run.append(keys[index])
            index += 1
        groups.append(("measures", spec.dimension, tuple(run)))
    return groups


# Implements: REQ-d00069-L, REQ-d00258-A, REQ-d00258-J, REQ-d00282-C
# The measures behind a dimension's headline total, in the ONE vocabulary
# (MEASURE_WORDS): "cited by name here" for what a citation named and attached
# directly, "whole-requirement" for a citation that named only the requirement,
# and "conducted" for what a `Refines:` chain carries up from a refining
# requirement's own evidence. Published beside the total rather than behind a
# caveat marker (REQ-d00258-J). The dimension is named too -- by the headline
# this run sits beneath where there is one, and in the line itself where the
# selection did not state that headline (REQ-d00282-C).
def _measures_line(lv: dict, run: tuple[str, ...]) -> str:
    return ", ".join(f"{MEASURE_WORDS[COLUMN_SPECS[k].measure]}: {_cell(lv, k)}" for k in run)


# Implements: REQ-d00258-O
def _tested_breakdown(lv: dict) -> str:
    """The tested assertions of one level, by what came back.

    Silent when nothing is tested: there is no breakdown of an empty set, and
    "(0 passed, 0 failed, 0 awaiting a result)" reads as a finding where there
    is only an absence.
    """
    passed = lv.get("tested_passed", 0)
    failed = lv.get("tested_failed", 0)
    awaiting = lv.get("tested_awaiting", 0)
    if passed + failed + awaiting == 0:
        return ""
    # Rendered through the shared assertion-count formatter: the breakdown is
    # in the same fractional units as the Tested figure it qualifies
    # (REQ-d00258-O), and a whole number still reads whole.
    return (
        f" [{fmt_assertion_count(passed)} passed, {fmt_assertion_count(failed)} failed, "
        f"{fmt_assertion_count(awaiting)} awaiting a result]"
    )


# Implements: REQ-d00282-E+K+L
def _level_heading(lv: dict, keys: tuple[str, ...]) -> str:
    """The line naming what a group of rows is about, and what else it counts.

    The identity column is always stated (REQ-d00282-L), so a reader always
    knows which level the figures beneath belong to. The two counts appear only
    where the selection named them -- a text rendering that stated them
    regardless would make the same selection state more here than in a table,
    which is the format-dependence REQ-d00282-E forbids.
    """
    counts = []
    if "requirements" in keys:
        counts.append(f"{lv['total']} requirements")
    if "assertions" in keys:
        counts.append(f"{lv['total_assertions']} assertions")
    tail = f" {', '.join(counts)}" if counts else ""
    return f"  {lv['level']}:{tail}"


# Implements: REQ-d00282-A+C+K+M
def _level_lines(lv: dict, keys: tuple[str, ...], config: dict | None, carry: str) -> list[str]:
    """One level's stated figures, as text, in the order they were named.

    A group conferring no *Assertion* states no coverage figure at all, and says
    so once rather than printing a row of zeros (REQ-d00282-M).
    """
    total_assertions = lv["total_assertions"]
    if not total_assertions:
        return ["    (no assertions in this group; no coverage figure is stated)"]

    width = max(
        (
            len(header_for(k, config)) + 1
            for k in keys
            if COLUMN_SPECS[k].states_a_figure and not COLUMN_SPECS[k].measure
        ),
        default=0,
    )
    lines: list[str] = []
    headline_dimension = ""
    for kind, dimension, run in _column_groups(keys):
        if kind == "measures":
            body = _measures_line(lv, run)
            if headline_dimension == dimension:
                lines.append(f"      ({body})")
            else:
                # No headline above this run to say what it measures, so the
                # line names the dimension itself (REQ-d00282-C).
                lines.append(f"      {header_for(dimension, config)}: ({body})")
            headline_dimension = ""
            continue
        spec = COLUMN_SPECS[run[0]]
        if not spec.states_a_figure:
            headline_dimension = ""
            continue
        label = f"{header_for(run[0], config)}:"
        lines.append(f"    {label:<{width}} {_cell(lv, run[0], carry)}")
        headline_dimension = spec.dimension
    return lines


def _render_text(data: dict, config: dict | None = None) -> str:
    # Implements: REQ-d00254-I
    carried = data.get("carried_result_targets", 0) or 0
    total_targets = data.get("total_result_targets", 0) or 0
    carry_marker = "*" if carried > 0 else ""

    lines = []
    lines.append("Coverage Summary")
    lines.append("=" * 60)
    # Implements: REQ-p00084-D
    for line in data.get("scope") or []:
        lines.append(line)

    # Level summary
    lines.append("")
    lines.append("Summary by Level")
    lines.append("-" * 60)
    # Implements: REQ-d00258-A
    # Without this the natural read of a headline above four measures is that
    # the measures sum to it. They do not: they are four readings of the same
    # assertions, and the headline takes the greatest of them per *Assertion*.
    # Said once here rather than per level, so it is a caption and not noise.
    lines.append("  (each headline counts an assertion once, at the greatest of")
    lines.append("   its four measures; the measures overlap and do not sum)")
    # Implements: REQ-d00069-N, REQ-d00258-A, REQ-d00258-J, REQ-d00282-A
    # A dimension's headline is the per-*Assertion* TOTAL (the greatest of the
    # four measures); the measures beneath it are what a reader checks instead
    # of a caveat marker (REQ-d00258-J). Which of them this report states is the
    # reader's selection.
    keys = _stated_columns(data)
    for lv in data["levels"]:
        if lv["total"] == 0:
            continue
        lines.append(_level_heading(lv, keys))
        lines.extend(_level_lines(lv, keys, config, carry_marker))

    excluded = data.get("excluded", {})
    if excluded:
        parts = [f"{v} {k}" for k, v in sorted(excluded.items())]
        lines.append(f"  ({', '.join(parts)} not included in coverage)")

    # REQ-d00252-F: External integrations grouped by owning associate.
    # "Passing" (REQ-d00258-K vocabulary, REQ-d00277-C):
    # integrates_by_associate() folds the library node's
    # tested_and_passing() Passing dimension into these figures, so the
    # label matches the other coverage columns. `!` marks a row whose library
    # suite has failing results -- the covered figure alone cannot say whether
    # an uncounted assertion failed or was never tested, so the marker
    # (footnoted below, like `*`) is the only red signal.
    integrations = data.get("integrations") or []
    if integrations:
        any_failing = any(row.get("has_failures") for row in integrations)
        lines.append("")
        lines.append("External integrations (by associate)")
        lines.append(f"  {'associate':<18} {'reqs':>5}   {'implemented':>11}   {'passing':>19}")
        for row in integrations:
            impl = f"{fmt_assertion_count(row['implemented_covered'])}/{row['implemented_total']}"
            ver = (
                f"{fmt_assertion_count(row['verified_covered'])}/{row['verified_total']}"
                f"{' !' if row.get('has_failures') else ''}"
            )
            lines.append(
                f"  {row['associate']:<18} {row['requirement_count']:>5}   {impl:>11}   {ver:>19}"
            )
        lines.append("  " + "-" * 57)
        tot = data.get("integration_total")
        if tot:
            impl = f"{fmt_assertion_count(tot['implemented_covered'])}/{tot['implemented_total']}"
            ver = (
                f"{fmt_assertion_count(tot['verified_covered'])}/{tot['verified_total']}"
                f"{' !' if tot.get('has_failures') else ''}"
            )
            lines.append(f"  {'total':<18} {tot['requirement_count']:>5}   {impl:>11}   {ver:>19}")
        if any_failing:
            lines.append("  ! failing test results in the integrated library")

    meta = data.get("meta")
    if meta:
        from elspais.utilities.report_meta import format_meta_line

        lines.append(f"  {format_meta_line(meta)}")

    # Implements: REQ-d00254-I
    if carried > 0:
        lines.append("")
        lines.append(f"* {carried}/{total_targets} test results from previous runs")

    lines.append("")
    return "\n".join(lines) + "\n"


# Implements: REQ-d00282-E+K+L
def _tabular_headers(keys: tuple[str, ...], config: dict | None) -> list[str]:
    """The header cells a tabular rendering states, in the stated order.

    One header per stated column and no cell that rides along beside it: the
    figure's denominator and its proportion live inside its own cell, and the
    Tested breakdown (REQ-d00258-O) qualifies the Tested cell rather than
    standing beside it. Every heading is read through ``header_for``, so a
    project that renames a dimension renames it here too (REQ-d00258-K).
    """
    return [header_for(key, config) for key in keys]


def _render_markdown(data: dict, config: dict | None = None) -> str:
    # Implements: REQ-d00254-I
    carried = data.get("carried_result_targets", 0) or 0
    total_targets = data.get("total_result_targets", 0) or 0
    carry_marker = "*" if carried > 0 else ""

    lines = []
    lines.append("# Coverage Summary")
    lines.append("")
    # Implements: REQ-p00084-D
    for line in data.get("scope") or []:
        lines.append(f"*{line}*")
        lines.append("")

    # Level summary
    lines.append("## Summary by Level")
    lines.append("")
    # Implements: REQ-d00258-A
    # See the text renderer: the measures beneath each headline are four
    # readings of the same assertions, not parts of it.
    lines.append(
        "*Each headline counts an assertion once, at the greatest of its four"
        " measures; the measures overlap and do not sum.*"
    )
    lines.append("")
    # Implements: REQ-d00069-N, REQ-d00258-A, REQ-d00258-J, REQ-d00282-E
    # One column per stated key, the same set and the same order the CSV
    # states: which columns a report states does not depend on the format it is
    # rendered in. The headline is the per-*Assertion* TOTAL; each measure
    # behind it is a column of its own.
    keys = _stated_columns(data)
    headers = _tabular_headers(keys, config)
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("|" + "|".join("-" * (len(h) + 2) for h in headers) + "|")
    for lv in data["levels"]:
        lines.append("| " + " | ".join([_cell(lv, key, carry_marker) for key in keys]) + " |")

    excluded = data.get("excluded", {})
    if excluded:
        parts = [f"{v} {k}" for k, v in sorted(excluded.items())]
        lines.append("")
        lines.append(f"*{', '.join(parts)} not included in coverage.*")

    # REQ-d00252-F: External integrations grouped by owning associate.
    # "Passing" (REQ-d00258-K vocabulary, REQ-d00277-C):
    # integrates_by_associate() folds the library node's tested_and_passing()
    # Passing dimension into these figures, so the label matches the other
    # coverage columns. `!` marks a row whose library suite has failing
    # results -- the covered figure alone cannot say whether an uncounted
    # assertion failed or was never tested, so the marker (footnoted below,
    # like `*`) is the only red signal.
    integrations = data.get("integrations") or []
    if integrations:
        any_failing = any(row.get("has_failures") for row in integrations)
        lines.append("")
        lines.append("## External integrations (by associate)")
        lines.append("")
        lines.append("| Associate | Reqs | Implemented | Passing |")
        lines.append("|-----------|------|-------------|---------|")
        for row in integrations:
            impl = f"{fmt_assertion_count(row['implemented_covered'])}/{row['implemented_total']}"
            ver = (
                f"{fmt_assertion_count(row['verified_covered'])}/{row['verified_total']}"
                f"{' !' if row.get('has_failures') else ''}"
            )
            lines.append(f"| {row['associate']} | {row['requirement_count']} | {impl} | {ver} |")
        tot = data.get("integration_total")
        if tot:
            impl = f"{fmt_assertion_count(tot['implemented_covered'])}/{tot['implemented_total']}"
            ver = (
                f"{fmt_assertion_count(tot['verified_covered'])}/{tot['verified_total']}"
                f"{' !' if tot.get('has_failures') else ''}"
            )
            lines.append(f"| total | {tot['requirement_count']} | {impl} | {ver} |")
        if any_failing:
            lines.append("")
            lines.append("*! failing test results in the integrated library*")

    # Implements: REQ-d00254-I
    if carried > 0:
        lines.append("")
        lines.append(f"* {carried}/{total_targets} test results from previous runs")

    meta = data.get("meta")
    if meta:
        from elspais.utilities.report_meta import format_meta_line

        lines.append("")
        lines.append(f"*Generated by {format_meta_line(meta)}*")

    lines.append("")
    return "\n".join(lines) + "\n"


# Implements: REQ-d00282-A+E+M
def _project_level(lv: dict, keys: tuple[str, ...]) -> dict:
    """One level's row, reduced to the columns the report states.

    Keyed by column KEY rather than by display word, so a consumer reading a
    committed report is unaffected by a project renaming a label
    (REQ-d00282-J). One key per stated column and no companion key beside it --
    the same cells the read formats state, so a selection is one stated shape
    in every format (REQ-d00282-E). A column stating no figure carries
    ``null``, which is how this format tells an absence from a zero
    (REQ-d00282-M).
    """
    row: dict[str, Any] = {}
    for key in keys:
        if key == "requirements":
            row[key] = lv["total"]
        elif key == "assertions":
            row[key] = lv["total_assertions"]
        elif key == IDENTITY_COLUMN:
            row[key] = lv["level"]
        elif _figure(lv, key) is None:
            row[key] = None
        else:
            row[key] = _cell(lv, key)
    return row


def _render_json(data: dict) -> str:
    stated = data.get("columns")
    if stated:
        # A report produced under a selection states that selection here too:
        # the columns a report states do not depend on the format it is
        # rendered in (REQ-d00282-E). Absent a selection the payload is left
        # whole -- it is a data document, and a reader who named nothing asked
        # for nothing to be withheld.
        keys = tuple(stated)
        data = {**data, "levels": [_project_level(lv, keys) for lv in data["levels"]]}
    else:
        data = {**data, "levels": [_absent_figures_as_null(lv) for lv in data["levels"]]}
    return json.dumps(data, indent=2) + "\n"


# Implements: REQ-d00282-M, REQ-d00258-O
# name: _absent_figures_as_null
# use:  keep a group with nothing to state distinguishable from one whose
#       figures are genuinely zero, in the whole payload a reader who named no
#       columns receives.
# def:  every coverage figure, every measure behind it and the three counts of
#       the Tested breakdown, set to null for a group conferring no *Assertion*
#       and left exactly as computed for every other group.
#
# A level whose requirements confer no *Assertion* is owed no coverage; a level
# with assertions and no evidence is owed all of it. Reported as 0 the two read
# alike, and a reader concludes work is undone that was never owed. The zeros a
# real group reports are real answers and are untouched -- nothing tested and
# nothing failing is a finding, not an absence.
def _absent_figures_as_null(lv: dict) -> dict:
    if lv.get("total_assertions"):
        return lv
    fields = {"tested_passed", "tested_failed", "tested_awaiting"}
    for prefix in _PAYLOAD_PREFIX.values():
        fields.add(f"{prefix}_total_covered")
        fields.update(f"{prefix}_{measure}" for measure in MEASURES)
    return {k: (None if k in fields else v) for k, v in lv.items()}


# Implements: REQ-d00069-L, REQ-d00069-N, REQ-d00258-A, REQ-d00282-A+E+K
# One column per stated key, headers and cells built from the same walk over
# the same list so the two cannot drift apart. The headline is the
# per-*Assertion* TOTAL; the measure columns are what a reader reads instead of
# a caveat marker (REQ-d00258-J).
def _render_csv(data: dict, config: dict | None = None) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    keys = _stated_columns(data)
    writer.writerow(_tabular_headers(keys, config))
    for lv in data["levels"]:
        # The machine format states the same cells the read ones do: a
        # figure is one cell (REQ-d00282-E), and a consumer that
        # met three columns here and one in markdown could not use a
        # selection as a stated shape at all.
        writer.writerow([_cell(lv, key) for key in keys])

    # Implements: REQ-d00254-I
    # Structured carried-results counts (no asterisk -- machine format).
    # Omitted entirely when there are no RESULT-target-bearing nodes, so CSV
    # output for graphs without test results stays unchanged.
    total_targets = data.get("total_result_targets", 0) or 0
    if total_targets > 0:
        writer.writerow([])
        writer.writerow(
            [
                "Carried Result Targets",
                data.get("carried_result_targets", 0),
                "Total Result Targets",
                total_targets,
            ]
        )
    return buf.getvalue()
