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
from elspais.graph.relations import EdgeKind


@dataclass
class GapEntry:
    """A single gap: a REQ with optionally listed uncovered assertions."""

    req_id: str
    title: str
    assertions: list[str] = field(default_factory=list)  # empty = whole REQ uncovered


@dataclass
class GapData:
    """Collected gap data across all gap types."""

    uncovered: list[GapEntry] = field(default_factory=list)
    untested: list[GapEntry] = field(default_factory=list)
    unvalidated: list[GapEntry] = field(default_factory=list)
    failing: list[tuple[str, str, str]] = field(default_factory=list)  # (req_id, title, source)
    no_assertions: list[GapEntry] = field(default_factory=list)


def _reqs_with_code_refs(graph: FederatedGraph, excluded_ids: set[str]) -> set[str]:
    """Return set of requirement IDs that have at least one CODE reference."""
    covered: set[str] = set()
    for node in graph.nodes_by_kind(NodeKind.CODE):
        for parent in node.iter_parents():
            if parent.kind == NodeKind.REQUIREMENT and parent.id not in excluded_ids:
                covered.add(parent.id)
            elif parent.kind == NodeKind.ASSERTION:
                for grandparent in parent.iter_parents():
                    if (
                        grandparent.kind == NodeKind.REQUIREMENT
                        and grandparent.id not in excluded_ids
                    ):
                        covered.add(grandparent.id)
    return covered


def collect_gaps(graph: FederatedGraph, exclude_status: set[str]) -> GapData:
    """Single-pass collection of coverage gaps from the graph.

    Args:
        graph: The federated traceability graph.
        exclude_status: Set of status values to skip (e.g. {"Retired"}).

    Returns:
        GapData with all gap lists populated.
    """
    data = GapData()

    excluded_ids: set[str] = set()
    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        if node.status in exclude_status:
            excluded_ids.add(node.id)

    code_covered = _reqs_with_code_refs(graph, excluded_ids)

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        if node.status in exclude_status:
            continue

        req_id = node.id
        title = node.get_label() or ""
        metrics = node.get_metric("rollup_metrics")

        # Collect assertion labels for this REQ
        assertion_labels = [
            child.id
            for child in node.iter_children(edge_kinds={EdgeKind.STRUCTURES})
            if child.kind == NodeKind.ASSERTION
        ]

        # Uncovered: no code references
        if req_id not in code_covered:
            data.uncovered.append(GapEntry(req_id, title))
        elif metrics is not None and metrics.implemented.indirect < metrics.implemented.total:
            # Partially covered: find which assertions lack coverage
            uncov = _uncovered_assertions(metrics, assertion_labels, "implemented")
            if uncov:
                data.uncovered.append(GapEntry(req_id, title, uncov))

        # Untested: no direct test coverage
        if metrics is None or metrics.tested.indirect <= 0:
            data.untested.append(GapEntry(req_id, title))
        elif metrics.tested.indirect < metrics.tested.total:
            uncov = _uncovered_assertions(metrics, assertion_labels, "tested")
            if uncov:
                data.untested.append(GapEntry(req_id, title, uncov))

        # Unvalidated: no UAT coverage
        if metrics is None or metrics.uat_coverage.indirect <= 0:
            data.unvalidated.append(GapEntry(req_id, title))
        elif metrics.uat_coverage.indirect < metrics.uat_coverage.total:
            uncov = _uncovered_assertions(metrics, assertion_labels, "uat_coverage")
            if uncov:
                data.unvalidated.append(GapEntry(req_id, title, uncov))

        # No assertions: not testable
        if not assertion_labels:
            data.no_assertions.append(GapEntry(req_id, title))

        # Failing: test or UAT failures
        if metrics is not None:
            if metrics.verified.has_failures:
                data.failing.append((req_id, title, "test"))
            if metrics.uat_verified.has_failures:
                data.failing.append((req_id, title, "uat"))

    return data


def _uncovered_assertions(
    metrics: Any,
    assertion_labels: list[str],
    dimension: str,
) -> list[str]:
    """Return assertion IDs that have no coverage for the given dimension.

    Uses the assertion_coverage dict on RollupMetrics to check which
    assertions received contributions relevant to the dimension.
    """
    from elspais.graph.metrics import CoverageSource

    # Map dimensions to the coverage source types that satisfy them
    _DIM_SOURCES: dict[str, set[CoverageSource]] = {
        "implemented": {
            CoverageSource.DIRECT,
            CoverageSource.EXPLICIT,
            CoverageSource.INFERRED,
            CoverageSource.INDIRECT,
        },
        "tested": {
            CoverageSource.DIRECT,
            CoverageSource.INDIRECT,
        },
        "uat_coverage": {
            CoverageSource.UAT_EXPLICIT,
            CoverageSource.UAT_INFERRED,
        },
    }
    relevant_sources = _DIM_SOURCES.get(dimension, set())

    uncovered: list[str] = []
    for label in assertion_labels:
        contribs = metrics.assertion_coverage.get(label, [])
        has_relevant = any(c.source in relevant_sources for c in contribs)
        if not has_relevant:
            uncovered.append(label)
    return uncovered


# =============================================================================
# Rendering
# =============================================================================

_LABELS = {
    "uncovered": "UNCOVERED (no code refs)",
    "untested": "UNTESTED (no test coverage)",
    "unvalidated": "UNVALIDATED (no UAT coverage)",
    "failing": "FAILING",
    "no_assertions": "NOT TESTABLE (no assertions)",
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
        for entry in sorted(gaps, key=lambda e: e.req_id):
            if entry.assertions:
                # Partial gap: show REQ with uncovered assertions
                labels = ", ".join(
                    a.rsplit("-", 1)[-1] if "-" in a else a for a in entry.assertions
                )
                lines.append(f"  {entry.req_id:20s} {entry.title}  [{labels}]")
            else:
                lines.append(f"  {entry.req_id:20s} {entry.title}")
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
        lines.append("| Requirement | Title | Uncovered Assertions |")
        lines.append("|-------------|-------|---------------------|")
        for entry in sorted(gaps, key=lambda e: e.req_id):
            assertions = ", ".join(entry.assertions) if entry.assertions else "(all)"
            lines.append(f"| {entry.req_id} | {entry.title} | {assertions} |")
    return "\n".join(lines)


# =============================================================================
# Composable section
# =============================================================================

_ALL_GAP_TYPES = ["uncovered", "untested", "unvalidated", "failing", "no_assertions"]


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
            items = getattr(data, gt)
            if gt == "failing":
                result[gt] = [list(item) for item in items]
            else:
                result[gt] = [_gap_entry_to_list(entry) for entry in items]
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
    "no_assertions": "no_assertions",
}


def _gap_entry_to_list(entry: GapEntry) -> list:
    """Serialize GapEntry for JSON."""
    result: list = [entry.req_id, entry.title]
    if entry.assertions:
        result.append(entry.assertions)
    return result


def _gap_data_from_dict(data: dict[str, Any]) -> GapData:
    """Reconstruct GapData from a JSON dict returned by the daemon."""
    gd = GapData()
    for gt in ("uncovered", "untested", "unvalidated", "no_assertions"):
        for item in data.get(gt, []):
            assertions = item[2] if len(item) > 2 else []
            getattr(gd, gt).append(GapEntry(item[0], item[1], assertions))
    for item in data.get("failing", []):
        gd.failing.append(tuple(item))  # type: ignore[arg-type]
    return gd


def compute_gaps(graph: FederatedGraph, config: dict, params: dict[str, str]) -> dict:
    """Engine-compatible wrapper around collect_gaps.

    Params:
        type: Optional gap type filter (uncovered, untested, unvalidated, failing).
        status: Optional comma-separated statuses to include.
    """
    import argparse as _argparse

    from elspais.commands.health import _resolve_exclude_status

    fake_args = _argparse.Namespace()
    status_str = params.get("status", None)
    fake_args.status = status_str.split(",") if status_str else None

    exclude_status = _resolve_exclude_status(fake_args, config=config)
    data = collect_gaps(graph, exclude_status)

    def _serialize_gap_list(gt: str) -> list:
        items = getattr(data, gt)
        if gt == "failing":
            return [list(item) for item in items]
        return [_gap_entry_to_list(entry) for entry in items]

    gap_type = params.get("type", None)
    if gap_type and gap_type in (
        "uncovered",
        "untested",
        "unvalidated",
        "failing",
        "no_assertions",
    ):
        return {gap_type: _serialize_gap_list(gap_type)}

    result: dict[str, Any] = {}
    for gt in ("uncovered", "untested", "unvalidated", "failing", "no_assertions"):
        result[gt] = _serialize_gap_list(gt)
    return result


def run(args: argparse.Namespace) -> int:
    """Run a standalone gap listing command.

    Tries a running daemon/viewer first for fast results,
    falls back to local graph build.
    """
    from elspais.commands._engine import call as engine_call

    command = getattr(args, "command", "gaps")
    gap_type = _GAP_TYPE_MAP.get(command)
    gap_types: list[str] | None = [gap_type] if gap_type else None
    fmt = getattr(args, "format", "text")
    spec_dir = getattr(args, "spec_dir", None)

    params: dict[str, str] = {}
    if gap_type:
        params["type"] = gap_type

    data = engine_call(
        "/api/run/gaps",
        params,
        compute_gaps,
        config_path=getattr(args, "config", None),
        skip_daemon=bool(spec_dir),
    )

    if fmt == "json":
        output = json.dumps(data, indent=2)
    else:
        gap_data = _gap_data_from_dict(data)
        types_to_render = gap_types or _ALL_GAP_TYPES
        if fmt == "markdown":
            sections = [render_gap_markdown(gt, gap_data) for gt in types_to_render]
            output = "\n\n".join(sections)
        else:
            sections = [render_gap_text(gt, gap_data) for gt in types_to_render]
            output = "\n\n".join(sections)

    output_file = getattr(args, "output", None)
    if output_file:
        Path(output_file).write_text(output + "\n")
    else:
        print(output)

    return 0
