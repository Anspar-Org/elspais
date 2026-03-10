# Implements: REQ-d00125
"""elspais.commands.analysis_cmd - Foundation analysis for requirement prioritization."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from elspais.graph.analysis import FoundationReport


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


def run(args: argparse.Namespace) -> int:
    """Run the analysis command."""
    from elspais.graph.analysis import NodeKind as NK
    from elspais.graph.analysis import analyze_foundations
    from elspais.graph.factory import build_graph

    canonical_root = getattr(args, "canonical_root", None)
    config_path = getattr(args, "config", None)

    graph = build_graph(
        config_path=config_path,
        canonical_root=canonical_root,
    )

    # Determine include_kinds
    include_kinds = {NK.REQUIREMENT, NK.ASSERTION}
    if getattr(args, "include_code", False):
        include_kinds.add(NK.CODE)

    # Parse weights (4 values: centrality, fan-in, neighborhood, uncovered)
    weights = (0.3, 0.2, 0.2, 0.3)
    weights_str = getattr(args, "weights", None)
    if weights_str:
        try:
            parts = [float(x.strip()) for x in weights_str.split(",")]
            if len(parts) not in (3, 4):
                print("Error: --weights must have 3 or 4 comma-separated values")
                return 1
            weights = tuple(parts)
        except ValueError:
            print("Error: --weights must be numeric values")
            return 1

    top_n = getattr(args, "top", 10)
    output_format = getattr(args, "format", "table")
    show = getattr(args, "show", "all")
    level_filter = getattr(args, "level", None)

    report = analyze_foundations(
        graph,
        include_kinds=include_kinds,
        weights=weights,
        top_n=top_n,
    )

    # Apply level filter if specified
    if level_filter:
        level_upper = level_filter.upper()
        report.ranked_nodes = [ns for ns in report.ranked_nodes if ns.level == level_upper]
        report.top_foundations = [ns for ns in report.top_foundations if ns.level == level_upper]
        report.actionable_leaves = [
            ns for ns in report.actionable_leaves if ns.level == level_upper
        ]

    if output_format == "json":
        _render_json(report)
    else:
        _render_table(report, show)

    return 0
