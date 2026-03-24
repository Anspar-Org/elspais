# Implements: REQ-d00125
"""elspais.commands.analysis_cmd - Foundation analysis for requirement prioritization."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from elspais.graph.analysis import FoundationReport


def compute_analysis(graph: Any, config: dict[str, Any], params: dict[str, str]) -> dict:
    """Pure compute function: run foundation analysis on a graph.

    Called by engine.call (local path) and by routes_api (server path).
    Params are always string-valued; parsing happens here.
    """
    from elspais.graph.analysis import NodeKind as NK
    from elspais.graph.analysis import analyze_foundations

    include_kinds = {NK.REQUIREMENT, NK.ASSERTION}
    if params.get("include_code", "false") == "true":
        include_kinds.add(NK.CODE)

    top_n = int(params.get("top", "10"))

    weights_str = params.get("weights", None)
    weights = (0.3, 0.2, 0.2, 0.3)
    if weights_str:
        try:
            parts = [float(x.strip()) for x in weights_str.split(",")]
            if len(parts) in (3, 4):
                weights = tuple(parts)
        except ValueError:
            pass

    report = analyze_foundations(
        graph,
        include_kinds=include_kinds,
        weights=weights,
        top_n=top_n,
    )

    level_filter = params.get("level", None)
    if level_filter:
        level_upper = level_filter.upper()
        report.ranked_nodes = [ns for ns in report.ranked_nodes if ns.level == level_upper]
        report.top_foundations = [ns for ns in report.top_foundations if ns.level == level_upper]
        report.actionable_leaves = [
            ns for ns in report.actionable_leaves if ns.level == level_upper
        ]

    return asdict(report)


def _render_table(report: FoundationReport, show: str) -> None:
    """Render the report as a formatted table."""
    if show in ("all", "foundations") and report.top_foundations:
        print("Top Foundations:")
        print(
            f"  {'Rank':>4}  {'ID':<14}  {'Title':<30}  "
            f"{'Centrality':>10}  {'Fan-In':>6}  {'Neighbors':>9}  "
            f"{'Uncovered':>9}  {'Score':>5}"
        )
        print(
            f"  {'----':>4}  {'----------':<14}  {'------------------------------':<30}  "
            f"{'----------':>10}  {'------':>6}  {'---------':>9}  "
            f"{'---------':>9}  {'-----':>5}"
        )
        for i, ns in enumerate(report.top_foundations, 1):
            title = ns.label[:30]
            print(
                f"  {i:>4}  {ns.node_id:<14}  {title:<30}  "
                f"{ns.centrality:>10.4f}  {ns.fan_in_branches:>6}  "
                f"{ns.neighborhood:>9.1f}  "
                f"{ns.uncovered_dependents:>9}  {ns.composite_score:>5.2f}"
            )
        print()

    if show in ("all", "leaves") and report.actionable_leaves:
        print("Most Impactful Work Items:")
        print(
            f"  {'Rank':>4}  {'ID':<14}  {'Title':<30}  "
            f"{'Level':<5}  {'Neighbors':>9}  {'Score':>5}"
        )
        print(
            f"  {'----':>4}  {'----------':<14}  {'------------------------------':<30}  "
            f"{'-----':<5}  {'---------':>9}  {'-----':>5}"
        )
        for i, ns in enumerate(report.actionable_leaves, 1):
            title = ns.label[:30]
            print(
                f"  {i:>4}  {ns.node_id:<14}  {title:<30}  "
                f"{ns.level:<5}  {ns.neighborhood:>9.1f}  {ns.composite_score:>5.2f}"
            )
        print()

    if not report.top_foundations and not report.actionable_leaves:
        print("No requirements found for analysis.")


def _render_json(report: FoundationReport) -> None:
    """Render the report as JSON."""
    print(json.dumps(asdict(report), indent=2))


def _report_from_dict(data: dict) -> FoundationReport:
    """Reconstruct a FoundationReport from a JSON dict."""
    from elspais.graph.analysis import FoundationReport, NodeScore

    def _ns(d: dict) -> NodeScore:
        return NodeScore(
            node_id=d["node_id"],
            label=d["label"],
            level=d["level"],
            centrality=d["centrality"],
            descendant_count=d["descendant_count"],
            fan_in_branches=d["fan_in_branches"],
            neighborhood=d["neighborhood"],
            uncovered_dependents=d["uncovered_dependents"],
            composite_score=d["composite_score"],
        )

    return FoundationReport(
        ranked_nodes=[_ns(n) for n in data.get("ranked_nodes", [])],
        top_foundations=[_ns(n) for n in data.get("top_foundations", [])],
        actionable_leaves=[_ns(n) for n in data.get("actionable_leaves", [])],
        graph_stats=data.get("graph_stats", {}),
    )


def run(args: argparse.Namespace) -> int:
    """Run the analysis command.

    Tries a running daemon/viewer first for fast results,
    falls back to local graph build.
    """
    from elspais.commands._engine import call as engine_call

    output_format = getattr(args, "format", "table")
    show = getattr(args, "show", "all")
    level_filter = getattr(args, "level", None)

    # Build params dict from args
    params: dict[str, str] = {}
    top_n = getattr(args, "top", 10)
    params["top"] = str(top_n)
    if getattr(args, "include_code", False):
        params["include_code"] = "true"
    weights_str = getattr(args, "weights", None)
    if weights_str:
        params["weights"] = weights_str
    if level_filter:
        params["level"] = level_filter

    # Validate weights BEFORE engine call (bug fix: was skipped on daemon path)
    if weights_str:
        try:
            parts = [float(x.strip()) for x in weights_str.split(",")]
            if len(parts) not in (3, 4):
                print("Error: --weights must have 3 or 4 comma-separated values")
                return 1
        except ValueError:
            print("Error: --weights must be numeric values")
            return 1

    data = engine_call(
        "/api/run/analysis",
        params,
        compute_analysis,
        config_path=getattr(args, "config", None),
    )
    report = _report_from_dict(data)

    if output_format == "json":
        _render_json(report)
    else:
        _render_table(report, show)

    return 0
