"""Gap listing composable sections for traceability coverage gaps."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from elspais.graph.federated import FederatedGraph

from elspais.graph import NodeKind


@dataclass
class GapData:
    """Collected gap data across all gap types."""

    uncovered: list[tuple[str, str]] = field(default_factory=list)  # (req_id, title)
    untested: list[tuple[str, str]] = field(default_factory=list)  # (req_id, title)
    unvalidated: list[tuple[str, str]] = field(default_factory=list)  # (req_id, title)
    failing: list[tuple[str, str, str]] = field(default_factory=list)  # (req_id, title, source)


def collect_gaps(graph: FederatedGraph, exclude_status: set[str]) -> GapData:
    """Single-pass collection of coverage gaps from the graph.

    Args:
        graph: The federated traceability graph.
        exclude_status: Set of status values to skip (e.g. {"Retired"}).

    Returns:
        GapData with all gap lists populated.
    """
    data = GapData()

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        if node.status in exclude_status:
            continue

        req_id = node.id
        title = node.get_label() or ""
        metrics = node.get_metric("rollup_metrics")

        # Uncovered: no coverage at all
        if metrics is None or metrics.coverage_pct <= 0:
            data.uncovered.append((req_id, title))

        # Untested: no direct test coverage
        if metrics is None or metrics.direct_tested <= 0:
            data.untested.append((req_id, title))

        # Unvalidated: no UAT coverage
        if metrics is None or metrics.uat_covered <= 0:
            data.unvalidated.append((req_id, title))

        # Failing: test or UAT failures
        if metrics is not None:
            if metrics.has_failures:
                data.failing.append((req_id, title, "test"))
            if metrics.uat_has_failures:
                data.failing.append((req_id, title, "uat"))

    return data


# =============================================================================
# Rendering
# =============================================================================

_LABELS = {
    "uncovered": "UNCOVERED (no code refs)",
    "untested": "UNTESTED (no test coverage)",
    "unvalidated": "UNVALIDATED (no UAT coverage)",
    "failing": "FAILING",
}


def render_gap_text(gap_type: str, data: GapData) -> str:
    """Render a single gap section as plain text."""
    label = _LABELS[gap_type]
    gaps = getattr(data, gap_type)
    if not gaps:
        return f"\n{label}: none"
    lines = [f"\n{label} ({len(gaps)}):"]
    if gap_type == "failing":
        for rid, title, source in sorted(gaps):
            lines.append(f"  {rid:20s} [{source}] {title}")
    else:
        for rid, title in sorted(gaps):
            lines.append(f"  {rid:20s} {title}")
    return "\n".join(lines)


def render_gap_markdown(gap_type: str, data: GapData) -> str:
    """Render a single gap section as markdown."""
    label = _LABELS[gap_type]
    gaps = getattr(data, gap_type)
    if not gaps:
        return f"## {label}\n\nNo gaps found."
    lines = [f"## {label} ({len(gaps)})", ""]
    if gap_type == "failing":
        lines.append("| Requirement | Source | Title |")
        lines.append("|-------------|--------|-------|")
        for rid, title, source in sorted(gaps):
            lines.append(f"| {rid} | {source} | {title} |")
    else:
        lines.append("| Requirement | Title |")
        lines.append("|-------------|-------|")
        for rid, title in sorted(gaps):
            lines.append(f"| {rid} | {title} |")
    return "\n".join(lines)


# =============================================================================
# Composable section
# =============================================================================

_ALL_GAP_TYPES = ["uncovered", "untested", "unvalidated", "failing"]


def render_section(
    graph: FederatedGraph,
    config: dict[str, Any] | None,
    args: argparse.Namespace,
    gap_types: list[str] | None = None,
) -> tuple[str, int]:
    """Render gap sections for the given gap types.

    Returns:
        Tuple of (rendered output string, exit code).
        Exit code is always 0 (gap sections are informational).
    """
    from elspais.commands.health import _resolve_exclude_status

    if gap_types is None:
        gap_types = _ALL_GAP_TYPES

    exclude_status = _resolve_exclude_status(args, config=config or {})
    data = collect_gaps(graph, exclude_status)

    fmt = getattr(args, "format", "text")

    if fmt == "json":
        result: dict[str, Any] = {}
        for gt in gap_types:
            result[gt] = [list(item) for item in getattr(data, gt)]
        return json.dumps(result, indent=2), 0

    if fmt == "markdown":
        sections = [render_gap_markdown(gt, data) for gt in gap_types]
        return "\n\n".join(sections), 0

    # Default: text
    sections = [render_gap_text(gt, data) for gt in gap_types]
    return "\n\n".join(sections), 0


# =============================================================================
# Standalone run
# =============================================================================

_GAP_TYPE_MAP: dict[str, str | None] = {
    "gaps": None,  # None = all gap types
    "uncovered": "uncovered",
    "untested": "untested",
    "unvalidated": "unvalidated",
    "failing": "failing",
}


def run(args: argparse.Namespace) -> int:
    """Run a standalone gap listing command.

    Builds the graph and renders the requested gap types.
    """
    from elspais.config import get_config
    from elspais.graph.factory import build_graph

    spec_dir = getattr(args, "spec_dir", None)
    config_path = getattr(args, "config", None)
    canonical_root = getattr(args, "canonical_root", None)
    start_path = Path.cwd()

    config = get_config(config_path, start_path=start_path)
    graph = build_graph(
        spec_dirs=[spec_dir] if spec_dir else None,
        config_path=config_path,
        canonical_root=canonical_root,
    )

    command = getattr(args, "command", "gaps")
    gap_type = _GAP_TYPE_MAP.get(command)
    gap_types: list[str] | None = [gap_type] if gap_type else None

    output, exit_code = render_section(graph, config, args, gap_types=gap_types)

    output_file = getattr(args, "output", None)
    if output_file:
        Path(output_file).write_text(output + "\n")
    else:
        print(output)

    return exit_code
