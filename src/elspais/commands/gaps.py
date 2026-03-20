"""Gap listing composable sections for traceability coverage gaps."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

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
