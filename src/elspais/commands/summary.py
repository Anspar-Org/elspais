"""
elspais.commands.summary - Coverage summary report section.

# Implements: REQ-d00086-A+B+C+D

Produces a coverage summary showing implementation, validation, and test-passing
status aggregated by level (PRD, OPS, DEV). Per-requirement detail is in the
trace command. Supports text, markdown, json, and csv output formats.
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

from elspais.graph import NodeKind
from elspais.graph.metrics import (
    fmt_assertion_count,
    integrates_by_associate,
    integrates_total,
)


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
    data = _collect_coverage(graph, config=config)
    content = _render(data, fmt)
    return content.rstrip("\n"), 0


def compute_summary(graph: FederatedGraph, config: dict, params: dict[str, str]) -> dict:
    """Engine-compatible wrapper around _collect_coverage."""
    return _collect_coverage(graph, config=config)


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


def _collect_coverage(graph: FederatedGraph, config: dict | None = None) -> dict:
    """Collect coverage data from the graph.

    Delegates per-level aggregation to the shared `aggregate_by_level()`
    (REQ-d00258-C) so the CLI summary, MCP project summary, and viewer derive
    identical statistics from identical data.
    """
    from elspais.config import default_level_keys, get_status_roles
    from elspais.graph.aggregation import aggregate_by_level

    roles = get_status_roles(config or {})
    exclude_status = roles.coverage_excluded_statuses()

    # Known level keys (case-insensitive), mirroring aggregate_by_level's own
    # level-key derivation, so excluded_counts only reflects requirements that
    # actually land in a rendered level bucket.
    levels_cfg = (config or {}).get("levels") or {}
    if isinstance(levels_cfg, dict) and levels_cfg:
        ordered = sorted(
            (
                (k, (v or {}).get("rank") if isinstance(v, dict) else None)
                for k, v in levels_cfg.items()
            ),
            key=lambda kv: kv[1] if kv[1] is not None else 9999,
        )
        level_keys = [k for k, rank in ordered if rank is not None] or default_level_keys()
    else:
        level_keys = default_level_keys()
    known_levels = {k.lower() for k in level_keys}

    # excluded_counts is still computed locally (aggregate_by_level excludes
    # these statuses from its sums but doesn't report per-status counts).
    excluded_counts: dict[str, int] = {}
    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        if (node.level or "").lower() in known_levels and node.status in exclude_status:
            excluded_counts[node.status] = excluded_counts.get(node.status, 0) + 1

    levels = []
    for agg in aggregate_by_level(graph, config):
        levels.append(
            {
                "level": agg.level,
                "total": agg.total_requirements,
                "with_code_refs": agg.with_code_refs,
                "with_test_refs": agg.with_test_refs,
                "with_passing": agg.with_passing,
                "total_assertions": agg.total_assertions,
                "implemented_assertions": round(agg.implemented.covered, 3),
                "implemented_direct": round(agg.implemented.direct, 3),
                "tested_assertions": round(agg.tested.covered, 3),
                "tested_direct": round(agg.tested.direct, 3),
                "passing_assertions": round(agg.passing.covered, 3),
                "passing_direct": round(agg.passing.direct, 3),
            }
        )

    # REQ-d00252-F: per-associate Integrates rollup + federation total.
    integration_rows = integrates_by_associate(graph)
    integrations: list[dict] = [
        {
            "associate": row.associate,
            "requirement_count": row.requirement_count,
            "implemented_covered": row.implemented_covered,
            "implemented_total": row.implemented_total,
            "verified_covered": row.verified_covered,
            "verified_total": row.verified_total,
        }
        for row in integration_rows
    ]
    integration_total: dict | None = None
    if integration_rows:
        tot = integrates_total(integration_rows)
        integration_total = {
            "associate": tot.associate,
            "requirement_count": tot.requirement_count,
            "implemented_covered": tot.implemented_covered,
            "implemented_total": tot.implemented_total,
            "verified_covered": tot.verified_covered,
            "verified_total": tot.verified_total,
        }

    result = {
        "levels": levels,
        "excluded": excluded_counts,
        "integrations": integrations,
        "integration_total": integration_total,
    }

    # Implements: REQ-d00254-I
    # Carry-forward provenance (distinct RESULT target names + how many are
    # carried baselines) is meaningful only for a selective `--targets` run, so
    # a selective run isn't a silent no-op on rendered output. Omit it entirely
    # otherwise, so a full run stays byte-identical to the pre-selectivity
    # output in every format (JSON keys and the CSV row included).
    if getattr(graph, "render_fresh_targets", None) is not None:
        all_result_targets: set[str] = set()
        carried_result_targets_set: set[str] = set()
        for result_node in graph.iter_by_kind(NodeKind.RESULT):
            tgt = result_node.get_field("target")
            if not tgt:
                continue
            all_result_targets.add(tgt)
            if result_node.get_field("carried"):
                carried_result_targets_set.add(tgt)
        result["total_result_targets"] = len(all_result_targets)
        result["carried_result_targets"] = len(carried_result_targets_set)

    return result


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


def _marker(covered: float, direct: float) -> str:
    """REQ-d00258-A: `~` flags a count whose evidence is not fully direct."""
    return " ~" if covered > direct + 1e-9 else ""


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
    for lv in data["levels"]:
        if lv["total"] == 0:
            continue
        ta = lv["total_assertions"]
        lines.append(f"  {lv['level']}: {lv['total']} requirements, {ta} assertions")
        lines.append(
            f"    Implemented: {fmt_assertion_count(lv['implemented_assertions'])}/{ta}"
            f" ({_pct(lv['implemented_assertions'], ta):.1f}%)"
            f"{_marker(lv['implemented_assertions'], lv['implemented_direct'])}"
        )
        lines.append(
            f"    Tested:      {fmt_assertion_count(lv['tested_assertions'])}/{ta}"
            f" ({_pct(lv['tested_assertions'], ta):.1f}%)"
            f"{_marker(lv['tested_assertions'], lv['tested_direct'])}"
        )
        lines.append(
            f"    Passing:     {fmt_assertion_count(lv['passing_assertions'])}/{ta}"
            f" ({_pct(lv['passing_assertions'], ta):.1f}%){carry_marker}"
            f"{_marker(lv['passing_assertions'], lv['passing_direct'])}"
        )

    excluded = data.get("excluded", {})
    if excluded:
        parts = [f"{v} {k}" for k, v in sorted(excluded.items())]
        lines.append(f"  ({', '.join(parts)} not included in coverage)")

    # REQ-d00252-F: External integrations grouped by owning associate.
    integrations = data.get("integrations") or []
    if integrations:
        lines.append("")
        lines.append("External integrations (by associate)")
        lines.append(f"  {'associate':<18} {'reqs':>5}   {'implemented':>11}   {'verified':>8}")
        for row in integrations:
            impl = f"{fmt_assertion_count(row['implemented_covered'])}/{row['implemented_total']}"
            ver = f"{fmt_assertion_count(row['verified_covered'])}/{row['verified_total']}"
            lines.append(
                f"  {row['associate']:<18} {row['requirement_count']:>5}"
                f"   {impl:>11}   {ver:>8}"
            )
        lines.append("  " + "-" * 46)
        tot = data.get("integration_total")
        if tot:
            impl = f"{fmt_assertion_count(tot['implemented_covered'])}/{tot['implemented_total']}"
            ver = f"{fmt_assertion_count(tot['verified_covered'])}/{tot['verified_total']}"
            lines.append(
                f"  {'total':<18} {tot['requirement_count']:>5}" f"   {impl:>11}   {ver:>8}"
            )

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
    lines.append("| Level | Requirements | Assertions | Implemented | Tested | Passing |")
    lines.append("|-------|-------------|------------|-------------|--------|---------|")
    for lv in data["levels"]:
        ta = lv["total_assertions"]
        ia = lv["implemented_assertions"]
        ta_tested = lv["tested_assertions"]
        pa = lv["passing_assertions"]
        impl = (
            f"{fmt_assertion_count(ia)}/{ta} ({_pct(ia, ta):.0f}%)"
            f"{_marker(ia, lv['implemented_direct'])}"
        )
        tested = (
            f"{fmt_assertion_count(ta_tested)}/{ta} ({_pct(ta_tested, ta):.0f}%)"
            f"{_marker(ta_tested, lv['tested_direct'])}"
        )
        pas = (
            f"{fmt_assertion_count(pa)}/{ta} ({_pct(pa, ta):.0f}%){carry_marker}"
            f"{_marker(pa, lv['passing_direct'])}"
        )
        lines.append(f"| {lv['level']} | {lv['total']} | {ta} | {impl} | {tested} | {pas} |")

    excluded = data.get("excluded", {})
    if excluded:
        parts = [f"{v} {k}" for k, v in sorted(excluded.items())]
        lines.append("")
        lines.append(f"*{', '.join(parts)} not included in coverage.*")

    # REQ-d00252-F: External integrations grouped by owning associate.
    integrations = data.get("integrations") or []
    if integrations:
        lines.append("")
        lines.append("## External integrations (by associate)")
        lines.append("")
        lines.append("| Associate | Reqs | Implemented | Verified |")
        lines.append("|-----------|------|-------------|----------|")
        for row in integrations:
            impl = f"{fmt_assertion_count(row['implemented_covered'])}/{row['implemented_total']}"
            ver = f"{fmt_assertion_count(row['verified_covered'])}/{row['verified_total']}"
            lines.append(f"| {row['associate']} | {row['requirement_count']} | {impl} | {ver} |")
        tot = data.get("integration_total")
        if tot:
            impl = f"{fmt_assertion_count(tot['implemented_covered'])}/{tot['implemented_total']}"
            ver = f"{fmt_assertion_count(tot['verified_covered'])}/{tot['verified_total']}"
            lines.append(f"| total | {tot['requirement_count']} | {impl} | {ver} |")

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


def _render_csv(data: dict) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "Level",
            "Requirements",
            "Assertions",
            "Implemented",
            "Implemented %",
            "Tested",
            "Tested %",
            "Passing",
            "Passing %",
        ]
    )
    for lv in data["levels"]:
        ta = lv["total_assertions"]
        ia = lv["implemented_assertions"]
        te = lv["tested_assertions"]
        pa = lv["passing_assertions"]
        writer.writerow(
            [
                lv["level"],
                lv["total"],
                ta,
                ia,
                _pct(ia, ta),
                te,
                _pct(te, ta),
                pa,
                _pct(pa, ta),
            ]
        )

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
