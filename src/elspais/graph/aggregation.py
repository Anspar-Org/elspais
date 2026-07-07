"""Single shared coverage aggregation for all reporting surfaces.

Implements: REQ-d00258-C
CLI summary, MCP get_project_summary, and the viewer all read this module so
identical questions receive identical answers. Counts use the generous
footing (CoverageDimension.indirect) per REQ-d00069-L; the strict footing is
carried alongside for detail/marker rendering.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from elspais.graph.GraphNode import NodeKind
from elspais.graph.metrics import (
    CoverageDimension,
    RollupMetrics,
    has_integration,
    tested_and_passing,
)

TIER_TO_BUCKET: dict[str, str] = {
    "full": "full",
    "partial": "partial",
    "failing": "failing",
    "missing": "missing",
}


@dataclass
class DimensionSums:
    covered: float = 0.0
    direct: float = 0.0
    total: int = 0


@dataclass
class LevelAggregate:
    level: str
    total_requirements: int = 0
    with_code_refs: int = 0
    with_test_refs: int = 0
    with_passing: int = 0
    total_assertions: int = 0
    implemented: DimensionSums = field(default_factory=DimensionSums)
    tested: DimensionSums = field(default_factory=DimensionSums)
    passing: DimensionSums = field(default_factory=DimensionSums)
    uat_covered: DimensionSums = field(default_factory=DimensionSums)
    uat_passed: DimensionSums = field(default_factory=DimensionSums)


@dataclass
class TierBuckets:
    total: int = 0
    full: int = 0
    partial: int = 0
    missing: int = 0
    failing: int = 0


@dataclass
class DimensionAggregate:
    """Whole-graph per-dimension sums plus the per-REQ counts health reports.

    ``total``/``direct``/``covered`` are the same assertion-fraction sums as
    ``DimensionSums`` (generous footing on ``covered``); the ``req_*`` fields
    and ``has_failures`` are the additional per-requirement tallies
    health.py's dimension-coverage check needs for its message.
    """

    total: int = 0
    direct: float = 0.0
    covered: float = 0.0
    req_count: int = 0
    req_with_any: int = 0
    req_with_direct: int = 0
    has_failures: bool = False


def _level_keys(config: dict[str, Any] | None) -> list[str]:
    """Ordered [levels] keys: ranked keys first (by rank), rank-less keys after.

    A key missing ``rank`` still aggregates -- it is not excluded -- it just
    sorts after every ranked key, in stable (declaration) order among peers.
    """
    from elspais.config import default_level_keys

    levels_cfg = (config or {}).get("levels") or {}
    if isinstance(levels_cfg, dict) and levels_cfg:
        ordered = sorted(
            (
                (k, (v or {}).get("rank") if isinstance(v, dict) else None)
                for k, v in levels_cfg.items()
            ),
            key=lambda kv: kv[1] if kv[1] is not None else 9999,
        )
        keys = [k for k, _rank in ordered]
        if keys:
            return keys
    return default_level_keys()


def _accumulate(sums: DimensionSums, dim: CoverageDimension) -> None:
    sums.covered += dim.indirect
    sums.direct += dim.direct
    sums.total += dim.total


def aggregate_by_level(graph: Any, config: dict[str, Any] | None = None) -> list[LevelAggregate]:
    """Per-level assertion-fraction sums on the generous footing."""
    from elspais.config import get_status_roles

    exclude_status = get_status_roles(config or {}).coverage_excluded_statuses()
    keys = _level_keys(config)
    groups: dict[str, LevelAggregate] = {k.lower(): LevelAggregate(level=k.upper()) for k in keys}

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        agg = groups.get((node.level or "").lower())
        if agg is None or node.status in exclude_status:
            continue
        agg.total_requirements += 1
        rollup: RollupMetrics | None = node.get_metric("rollup_metrics")
        if rollup is None:
            if has_integration(node):
                agg.with_code_refs += 1
            continue
        passing_dim = tested_and_passing(rollup)
        agg.total_assertions += rollup.total_assertions
        _accumulate(agg.implemented, rollup.implemented)
        _accumulate(agg.tested, rollup.tested)
        _accumulate(agg.passing, passing_dim)
        _accumulate(agg.uat_covered, rollup.uat_coverage)
        _accumulate(agg.uat_passed, rollup.uat_verified)
        # REQ-d00252-F: INTEGRATES delegation counts as implemented.
        if rollup.implemented.indirect > 0 or has_integration(node):
            agg.with_code_refs += 1
        if rollup.tested.indirect > 0:
            agg.with_test_refs += 1
        if passing_dim.indirect > 0:
            agg.with_passing += 1

    return [groups[k.lower()] for k in keys]


def aggregate_dimension(
    graph: Any,
    dimension: str,
    exclude_status: set[str] | None = None,
    level_filter: Any = None,
) -> DimensionAggregate:
    """Whole-graph sums + per-REQ counts for one CoverageDimension.

    Mirrors the per-level accumulation in ``aggregate_by_level`` but flattened
    across all levels (no level grouping) and generalized to any dimension
    name on ``RollupMetrics`` (e.g. 'implemented', 'tested', 'verified',
    'uat_coverage', 'uat_verified'). This is the single place health.py's
    dimension-coverage check should read counts from -- it must not
    re-implement this walk (REQ-d00258-C).

    ``level_filter`` (optional) is a predicate ``(level: str | None) -> bool``.
    When given, only requirements whose level satisfies it are counted (both
    numerator and denominator). Used by the UAT coverage check so that
    non-``expects_validation`` levels neither count toward nor drag the gap
    (REQ-d00258-F).

    REQ-d00252-F: an INTEGRATES-delegating requirement has no local
    ``rollup_metrics`` but is still covered for the 'implemented' dimension
    specifically; other dimensions do not receive the INTEGRATES credit.
    """
    agg = DimensionAggregate()
    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        if exclude_status and node.status in exclude_status:
            continue
        if level_filter is not None and not level_filter(node.level):
            continue
        agg.req_count += 1
        integrates = dimension == "implemented" and has_integration(node)
        rollup: RollupMetrics | None = node.get_metric("rollup_metrics")
        if rollup is None:
            if integrates:
                agg.req_with_any += 1
                agg.req_with_direct += 1
            continue
        dim: CoverageDimension | None = getattr(rollup, dimension, None)
        if dim is None:
            continue
        agg.total += dim.total
        agg.direct += dim.direct
        agg.covered += dim.indirect
        if dim.indirect > 0 or integrates:
            agg.req_with_any += 1
        if dim.direct > 0 or integrates:
            agg.req_with_direct += 1
        if dim.has_failures:
            agg.has_failures = True
    return agg


def tier_buckets(
    graph: Any,
    dimension: str = "implemented",
    exclude_status: set[str] | None = None,
) -> TierBuckets:
    """Requirement-level tier bucket counts for one dimension."""
    buckets = TierBuckets()
    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        if exclude_status and node.status in exclude_status:
            continue
        buckets.total += 1
        rollup: RollupMetrics | None = node.get_metric("rollup_metrics")
        dim: CoverageDimension | None = getattr(rollup, dimension, None) if rollup else None
        if dim is None:
            buckets.missing += 1
            continue
        bucket = TIER_TO_BUCKET.get(dim.tier, "missing")
        setattr(buckets, bucket, getattr(buckets, bucket) + 1)
    return buckets


__all__ = [
    "TIER_TO_BUCKET",
    "DimensionAggregate",
    "DimensionSums",
    "LevelAggregate",
    "TierBuckets",
    "aggregate_by_level",
    "aggregate_dimension",
    "tier_buckets",
]
