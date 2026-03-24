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
from elspais.graph.metrics import RollupMetrics


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
    falls back to local graph build.
    """
    from elspais.commands._engine import call as engine_call

    fmt = getattr(args, "format", "text") or "text"
    spec_dir = getattr(args, "spec_dir", None)

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

    Uses pre-computed RollupMetrics from annotate_coverage().
    """
    from elspais.config import get_status_roles

    roles = get_status_roles(config or {})
    exclude_status = roles.coverage_excluded_statuses()

    # Group requirements by level manually (node.level is lowercase)
    level_groups: dict[str, list] = {"prd": [], "ops": [], "dev": []}
    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        lvl = (node.level or "").lower()
        if lvl in level_groups:
            level_groups[lvl].append(node)

    levels = []
    excluded_counts: dict[str, int] = {}

    for level_key, display_name in (("prd", "PRD"), ("ops", "OPS"), ("dev", "DEV")):
        nodes = level_groups[level_key]
        active_nodes = [n for n in nodes if n.status not in exclude_status]
        excluded = len(nodes) - len(active_nodes)
        if excluded > 0:
            for n in nodes:
                if n.status in exclude_status:
                    excluded_counts[n.status] = excluded_counts.get(n.status, 0) + 1

        level_totals = {
            "level": display_name,
            "total": len(active_nodes),
            "with_code_refs": 0,
            "with_test_refs": 0,
            "with_passing": 0,
            "total_assertions": 0,
            "implemented_assertions": 0,
            "validated_assertions": 0,
            "passing_assertions": 0,
        }

        for node in sorted(active_nodes, key=lambda n: n.id):
            rollup: RollupMetrics | None = node.get_metric("rollup_metrics")
            if rollup is None:
                total = 0
                implemented = 0
                validated = 0
                passing = 0
            else:
                total = rollup.total_assertions
                implemented = rollup.implemented.indirect
                validated = rollup.tested.direct
                passing = rollup.verified.direct

            if implemented > 0:
                level_totals["with_code_refs"] += 1
            if validated > 0:
                level_totals["with_test_refs"] += 1
            if passing > 0:
                level_totals["with_passing"] += 1
            level_totals["total_assertions"] += total
            level_totals["implemented_assertions"] += implemented
            level_totals["validated_assertions"] += validated
            level_totals["passing_assertions"] += passing

        levels.append(level_totals)

    return {
        "levels": levels,
        "excluded": excluded_counts,
    }


def _pct(num: int, denom: int) -> float:
    return round(num / denom * 100, 1) if denom > 0 else 0.0


def _render(data: dict, fmt: str) -> str:
    if fmt == "json":
        return _render_json(data)
    elif fmt == "csv":
        return _render_csv(data)
    elif fmt == "markdown":
        return _render_markdown(data)
    else:
        return _render_text(data)


def _render_text(data: dict) -> str:
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
            f"    Implemented: {lv['implemented_assertions']}/{ta}"
            f" ({_pct(lv['implemented_assertions'], ta):.1f}%)"
        )
        lines.append(
            f"    Validated:   {lv['validated_assertions']}/{ta}"
            f" ({_pct(lv['validated_assertions'], ta):.1f}%)"
        )
        lines.append(
            f"    Passing:     {lv['passing_assertions']}/{ta}"
            f" ({_pct(lv['passing_assertions'], ta):.1f}%)"
        )

    excluded = data.get("excluded", {})
    if excluded:
        parts = [f"{v} {k}" for k, v in sorted(excluded.items())]
        lines.append(f"  ({', '.join(parts)} not included in coverage)")

    lines.append("")
    return "\n".join(lines) + "\n"


def _render_markdown(data: dict) -> str:
    lines = []
    lines.append("# Coverage Summary")
    lines.append("")

    # Level summary
    lines.append("## Summary by Level")
    lines.append("")
    lines.append("| Level | Requirements | Assertions | Implemented | Validated | Passing |")
    lines.append("|-------|-------------|------------|-------------|-----------|---------|")
    for lv in data["levels"]:
        ta = lv["total_assertions"]
        ia = lv["implemented_assertions"]
        va = lv["validated_assertions"]
        pa = lv["passing_assertions"]
        impl = f"{ia}/{ta} ({_pct(ia, ta):.0f}%)"
        val = f"{va}/{ta} ({_pct(va, ta):.0f}%)"
        pas = f"{pa}/{ta} ({_pct(pa, ta):.0f}%)"
        lines.append(f"| {lv['level']} | {lv['total']} | {ta} | {impl} | {val} | {pas} |")

    excluded = data.get("excluded", {})
    if excluded:
        parts = [f"{v} {k}" for k, v in sorted(excluded.items())]
        lines.append("")
        lines.append(f"*{', '.join(parts)} not included in coverage.*")

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
            "Validated",
            "Validated %",
            "Passing",
            "Passing %",
        ]
    )
    for lv in data["levels"]:
        ta = lv["total_assertions"]
        ia = lv["implemented_assertions"]
        va = lv["validated_assertions"]
        pa = lv["passing_assertions"]
        writer.writerow(
            [
                lv["level"],
                lv["total"],
                ta,
                ia,
                _pct(ia, ta),
                va,
                _pct(va, ta),
                pa,
                _pct(pa, ta),
            ]
        )
    return buf.getvalue()
