"""
elspais.commands.summary - Coverage summary report section.

# Implements: REQ-d00086-A+B+C+D

Produces a coverage summary showing Implemented/Tested/Passing status
aggregated by level (PRD, OPS, DEV), plus an External integrations table when
`Integrates:` references are present. UAT Covered/UAT Passed are not among
the headline figures here (see the trace command for per-requirement detail,
including UAT columns). Supports text, markdown, json, and csv output
formats.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from elspais.graph.federated import FederatedGraph

from elspais.graph.aggregation import collect_coverage
from elspais.graph.metrics import fmt_assertion_count


# Implements: REQ-d00085-A
def render_section(
    graph: FederatedGraph,
    args: argparse.Namespace,
    config: dict | None = None,
) -> tuple[str, int]:
    """Render coverage as a composed report section.

    Returns (formatted_output, exit_code).
    """
    fmt = getattr(args, "format", "text") or "text"
    data = collect_coverage(graph, config=config)
    content = _render(data, fmt)
    return content.rstrip("\n"), 0


def compute_summary(graph: FederatedGraph, config: dict, params: dict[str, str]) -> dict:
    """Engine-compatible wrapper around the shared coverage collector."""
    return collect_coverage(graph, config=config)


def run(args: argparse.Namespace) -> int:
    """Run the coverage command.

    Tries a running daemon/viewer first for fast results,
    falls back to local graph build. --targets forces a local build so the
    fresh set threads into build_graph() (a cached daemon graph can't know
    which targets this invocation considers fresh).
    """
    from elspais.commands._engine import call as engine_call

    fmt = getattr(args, "format", "text") or "text"
    spec_dir = getattr(args, "spec_dir", None)
    # Implements: REQ-d00254-I
    fresh_targets = set(args.targets) if getattr(args, "targets", None) else None

    if fresh_targets is not None:
        from elspais.config import get_config
        from elspais.graph.factory import build_graph

        config_path = getattr(args, "config", None)
        graph = build_graph(
            spec_dirs=[spec_dir] if spec_dir else None,
            config_path=config_path,
            fresh_targets=fresh_targets,
        )
        config = get_config(config_path)
        data = compute_summary(graph, config, {})
        data["graph_source"] = {"type": "local"}
    else:
        data = engine_call(
            "/api/run/summary",
            {},
            compute_summary,
            skip_daemon=bool(spec_dir),
            config_path=getattr(args, "config", None),
        )

    content = _render(data, fmt)
    sys.stdout.write(content)

    return 0


def _pct(num: int, denom: int) -> float:
    return round(num / denom * 100, 1) if denom > 0 else 0.0


def _render(data: dict, fmt: str) -> str:
    from elspais.utilities.report_meta import report_metadata

    data["meta"] = report_metadata()
    if fmt == "json":
        return _render_json(data)
    elif fmt == "csv":
        return _render_csv(data)
    elif fmt == "markdown":
        return _render_markdown(data)
    else:
        return _render_text(data)


# Implements: REQ-d00069-L, REQ-d00258-A, REQ-d00258-J
# The four measures behind a dimension's headline total, in health.py's
# vocabulary (check_dimension_coverage): "cited by name here" for what a
# citation named and attached directly, "whole-requirement" for a citation
# that named only the requirement, and "conducted" for what a `Refines:`
# chain carries up from a refining requirement's own evidence. Published
# beside the total rather than behind a caveat marker (REQ-d00258-J).
def _measures_line(lv: dict, prefix: str) -> str:
    from elspais.graph.aggregation import MEASURE_WORDS, MEASURES

    return ", ".join(
        f"{MEASURE_WORDS[m]}: {fmt_assertion_count(lv[f'{prefix}_{m}'])}" for m in MEASURES
    )


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
    return f"  [{passed} passed, {failed} failed, {awaiting} awaiting a result]"


def _render_text(data: dict) -> str:
    # Implements: REQ-d00254-I
    carried = data.get("carried_result_targets", 0) or 0
    total_targets = data.get("total_result_targets", 0) or 0
    carry_marker = "*" if carried > 0 else ""

    lines = []
    lines.append("Coverage Summary")
    lines.append("=" * 60)

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
    for lv in data["levels"]:
        if lv["total"] == 0:
            continue
        ta = lv["total_assertions"]
        lines.append(f"  {lv['level']}: {lv['total']} requirements, {ta} assertions")
        # Implements: REQ-d00069-N, REQ-d00258-A, REQ-d00258-J
        # The headline is the per-*Assertion* TOTAL (the greatest of the
        # four measures); the measures line beneath it is what a reader
        # checks instead of a caveat marker (REQ-d00258-J).
        lines.append(
            f"    Implemented: {fmt_assertion_count(lv['implemented_total_covered'])}/{ta}"
            f" ({_pct(lv['implemented_total_covered'], ta):.1f}%)"
        )
        lines.append(f"      ({_measures_line(lv, 'implemented')})")
        # Implements: REQ-d00258-O
        # The breakdown qualifies Tested rather than standing beside it, so it
        # rides on the Tested line and adds no coverage term of its own.
        lines.append(
            f"    Tested:      {fmt_assertion_count(lv['tested_total_covered'])}/{ta}"
            f" ({_pct(lv['tested_total_covered'], ta):.1f}%)"
            f"{_tested_breakdown(lv)}"
        )
        lines.append(f"      ({_measures_line(lv, 'tested')})")
        lines.append(
            f"    Passing:     {fmt_assertion_count(lv['passing_total_covered'])}/{ta}"
            f" ({_pct(lv['passing_total_covered'], ta):.1f}%){carry_marker}"
        )
        lines.append(f"      ({_measures_line(lv, 'passing')})")

    excluded = data.get("excluded", {})
    if excluded:
        parts = [f"{v} {k}" for k, v in sorted(excluded.items())]
        lines.append(f"  ({', '.join(parts)} not included in coverage)")

    # REQ-d00252-F: External integrations grouped by owning associate.
    # "Passing" (REQ-d00258-B vocabulary, REQ-d00258-N):
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


def _render_markdown(data: dict) -> str:
    # Implements: REQ-d00254-I
    carried = data.get("carried_result_targets", 0) or 0
    total_targets = data.get("total_result_targets", 0) or 0
    carry_marker = "*" if carried > 0 else ""

    lines = []
    lines.append("# Coverage Summary")
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
    lines.append("| Level | Requirements | Assertions | Implemented | Tested | Passing |")
    lines.append("|-------|-------------|------------|-------------|--------|---------|")
    for lv in data["levels"]:
        ta = lv["total_assertions"]
        # Implements: REQ-d00069-N, REQ-d00258-A, REQ-d00258-J
        # The headline is the per-*Assertion* TOTAL; the measures line
        # beneath it (in the same cell) is what a reader checks instead of
        # a caveat marker (REQ-d00258-J).
        ia = lv["implemented_total_covered"]
        ta_tested = lv["tested_total_covered"]
        pa = lv["passing_total_covered"]
        impl = (
            f"{fmt_assertion_count(ia)}/{ta} ({_pct(ia, ta):.0f}%)"
            f"<br>({_measures_line(lv, 'implemented')})"
        )
        tested = (
            f"{fmt_assertion_count(ta_tested)}/{ta} ({_pct(ta_tested, ta):.0f}%)"
            f"{_tested_breakdown(lv)}"
            f"<br>({_measures_line(lv, 'tested')})"
        )
        pas = (
            f"{fmt_assertion_count(pa)}/{ta} ({_pct(pa, ta):.0f}%){carry_marker}"
            f"<br>({_measures_line(lv, 'passing')})"
        )
        lines.append(f"| {lv['level']} | {lv['total']} | {ta} | {impl} | {tested} | {pas} |")

    excluded = data.get("excluded", {})
    if excluded:
        parts = [f"{v} {k}" for k, v in sorted(excluded.items())]
        lines.append("")
        lines.append(f"*{', '.join(parts)} not included in coverage.*")

    # REQ-d00252-F: External integrations grouped by owning associate.
    # "Passing" (REQ-d00258-B vocabulary, REQ-d00258-N):
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


def _render_json(data: dict) -> str:
    return json.dumps(data, indent=2) + "\n"


# Implements: REQ-d00069-L, REQ-d00258-A
# The four measure-column suffixes and their headers, shared by every
# dimension's CSV columns -- one place naming them so the header row and the
# data row cannot drift apart.
_CSV_MEASURE_COLUMNS: list[tuple[str, str]] = [
    ("_immediate_direct", "Immediate Direct"),
    ("_immediate_indirect", "Immediate Indirect"),
    ("_rolled_direct", "Rolled Direct"),
    ("_rolled_indirect", "Rolled Indirect"),
]


def _render_csv(data: dict) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    header = ["Level", "Requirements", "Assertions"]
    for prefix, label in (("implemented", "Implemented"), ("tested", "Tested")):
        header.extend([label, f"{label} %"])
        if prefix == "tested":
            # Implements: REQ-d00258-O
            header.extend(["Tested Passed", "Tested Failed", "Tested Awaiting"])
        header.extend(f"{label} {m_label}" for _suffix, m_label in _CSV_MEASURE_COLUMNS)
    header.extend(["Passing", "Passing %"])
    header.extend(f"Passing {m_label}" for _suffix, m_label in _CSV_MEASURE_COLUMNS)
    writer.writerow(header)

    for lv in data["levels"]:
        ta = lv["total_assertions"]
        # Implements: REQ-d00069-N, REQ-d00258-A, REQ-d00258-J
        # The headline is the per-*Assertion* TOTAL; the measure columns
        # are what a reader reads instead of a caveat marker (REQ-d00258-J).
        ia = lv["implemented_total_covered"]
        te = lv["tested_total_covered"]
        pa = lv["passing_total_covered"]
        row = [lv["level"], lv["total"], ta]
        row.extend([ia, _pct(ia, ta)])
        row.extend(lv[f"implemented{suffix}"] for suffix, _label in _CSV_MEASURE_COLUMNS)
        row.extend([te, _pct(te, ta)])
        row.extend(
            [lv.get("tested_passed", 0), lv.get("tested_failed", 0), lv.get("tested_awaiting", 0)]
        )
        row.extend(lv[f"tested{suffix}"] for suffix, _label in _CSV_MEASURE_COLUMNS)
        row.extend([pa, _pct(pa, ta)])
        row.extend(lv[f"passing{suffix}"] for suffix, _label in _CSV_MEASURE_COLUMNS)
        writer.writerow(row)

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
