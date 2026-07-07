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

# Implements: REQ-d00258-H
# Unified coverage-state vocabulary: the requirement tier, per-assertion standing,
# and viewer filter bucket all draw from this single {full,partial,failing,missing}
# set (identity map -- no separate direct/indirect tier states).
TIER_TO_BUCKET: dict[str, str] = {
    "full": "full",
    "partial": "partial",
    "failing": "failing",
    "missing": "missing",
}

# The coverage chain's RELATIVE-denominator convention, single-sourced here so
# both the requirement-level tier buckets (this module) and the badge
# projection (html/generator.py) measure each chained dimension over the SAME
# label set (REQ-d00258-C). Each measured dimension is scored over the labels
# that qualified at the PRIOR link of the chain, not over every assertion:
# Tested over IMPLEMENTED labels, Passing (verified) over TESTED labels,
# UAT-Passed over UAT-COVERED labels. ``implemented`` and ``uat_coverage`` are
# ABSOLUTE (measured over all assertions) and deliberately absent from this map.
DENOMINATOR_DIMENSION: dict[str, str] = {
    "tested": "implemented",
    "verified": "tested",
    "uat_verified": "uat_coverage",
}


# Implements: REQ-d00258-I
def relative_tier(
    num_dim: CoverageDimension,
    denom_labels: set[str],
    *,
    allow_indirect: bool = True,
) -> tuple[str, bool]:
    """Tier of ``num_dim`` measured over the relative denominator ``denom_labels``.

    Returns ``(tier, is_na)``. ``is_na`` is True when the denominator is empty
    (nothing to measure -> ``missing`` at neutral severity, design §1/§2). A
    failing label within the denominator wins (``failing``). ``allow_indirect``
    selects the credited per-label fractions (Phase 4 threads the config).

    Single home for the relative-tier logic (REQ-d00258-C): both the badge
    projection (html/generator.py) and the requirement-level tier buckets read
    this one helper so identical questions receive identical answers.
    """
    eps = 1e-9
    if not denom_labels:
        return "missing", True
    if num_dim.failing_labels & denom_labels:
        return "failing", False
    pct = num_dim.indirect_pct_by_label if allow_indirect else num_dim.direct_pct_by_label
    covered = sum(min(pct.get(lbl, 0.0), 1.0) for lbl in denom_labels)
    n = len(denom_labels)
    if covered >= n - eps:
        return "full", False
    if covered > eps:
        return "partial", False
    return "missing", False


def absolute_tier(dim: CoverageDimension, *, allow_indirect: bool = True) -> str:
    """Absolute tier of a dimension, honoring ``allow_indirect``.

    With ``allow_indirect=True`` this is exactly ``dim.tier`` (the generous
    footing, REQ-d00069-L). With ``allow_indirect=False`` only DIRECT coverage
    credits the state: a dimension covered solely via indirect conduction reads
    ``missing`` (REQ-d00258, Phase 4). A failing dimension is ``failing`` either
    way. The ``CoverageDimension.tier`` property is deliberately unchanged (it
    remains the allow_indirect=True semantics used elsewhere).
    """
    if allow_indirect:
        return dim.tier
    eps = 1e-9
    if dim.has_failures:
        return "failing"
    if dim.total > 0 and dim.direct >= dim.total - eps:
        return "full"
    if dim.direct > eps:
        return "partial"
    return "missing"


def _allow_indirect_from_config(config: Any | None) -> bool:
    """Extract ``[rules.coverage] allow_indirect`` from a config dict/model.

    Defaults to True (generous footing) when absent. Accepts both the plain
    config ``dict`` form and an already-parsed model, mirroring how
    ``compute_coverage_tiers`` reads its coverage config.
    """
    if not config:
        return True
    rules = config.get("rules", {}) if isinstance(config, dict) else getattr(config, "rules", None)
    if rules is None:
        return True
    cov = rules.get("coverage", {}) if isinstance(rules, dict) else getattr(rules, "coverage", None)
    if cov is None:
        return True
    if isinstance(cov, dict):
        return bool(cov.get("allow_indirect", True))
    return bool(getattr(cov, "allow_indirect", True))


def relative_tier_for(
    rollup: RollupMetrics,
    dimension: str,
    *,
    allow_indirect: bool = True,
) -> tuple[str, bool]:
    """``(tier, is_na)`` for one dimension of a rollup, honoring the chain.

    For a chained dimension (in ``DENOMINATOR_DIMENSION``) the tier is measured
    RELATIVELY over the label-set that qualified at the prior link. The
    'verified' numerator is ``tested_and_passing`` (verified | lcov credit),
    matching the badge projection -- NOT the raw ``rollup.verified`` dimension,
    which would miss line-coverage credit. An absolute dimension (implemented,
    uat_coverage) returns its own ``.tier`` and is never N/A.
    """
    denom_name = DENOMINATOR_DIMENSION.get(dimension)
    if denom_name is None:
        return absolute_tier(getattr(rollup, dimension), allow_indirect=allow_indirect), False
    # The denominator is the set of labels ACTUALLY covered in the prior
    # dimension (fraction > 0), NOT every label present in the per-label map:
    # ``_conduct_refines_coverage`` seeds a 0.0 entry for every assertion label
    # (incl. unimplemented ones), so building the set from the dict keys would
    # silently make this "relative" chain absolute and disagree with the
    # gaps/MCP surfaces (which filter frac > 0). REQ-d00258-I.
    denom_labels = {
        lbl for lbl, frac in getattr(rollup, denom_name).indirect_pct_by_label.items() if frac > 0
    }
    num_dim = tested_and_passing(rollup) if dimension == "verified" else getattr(rollup, dimension)
    return relative_tier(num_dim, denom_labels, allow_indirect=allow_indirect)


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


def _counts_for_coverage(config: dict[str, Any] | None, status: str | None) -> bool:
    """Whether a requirement STATUS is INCLUDED in coverage aggregation.

    The single coverage-inclusion gate (REQ-d00258-C): delegates to the
    ``status_expects_implementation`` resolver so summary/health/mcp and the
    viewer answer 'does this status count?' identically. For DEFAULT config
    (no ``[statuses.<Name>]`` override) this is EXACTLY
    ``status not in coverage_excluded_statuses()`` -- the role system remains
    the default source; an explicit ``expects_implementation`` flag diverges
    surgically. Deferred import mirrors the other config helpers here to avoid
    an import cycle.
    """
    from elspais.config import status_expects_implementation

    return status_expects_implementation(config or {}, status)


def aggregate_by_level(graph: Any, config: dict[str, Any] | None = None) -> list[LevelAggregate]:
    """Per-level assertion-fraction sums on the generous footing."""
    keys = _level_keys(config)
    groups: dict[str, LevelAggregate] = {k.lower(): LevelAggregate(level=k.upper()) for k in keys}

    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        agg = groups.get((node.level or "").lower())
        if agg is None or not _counts_for_coverage(config, node.status):
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
    config: dict[str, Any] | None = None,
    level_filter: Any = None,
) -> DimensionAggregate:
    """Whole-graph sums + per-REQ counts for one CoverageDimension.

    Mirrors the per-level accumulation in ``aggregate_by_level`` but flattened
    across all levels (no level grouping) and generalized to any dimension
    name on ``RollupMetrics`` (e.g. 'implemented', 'tested', 'verified',
    'uat_coverage', 'uat_verified'). This is the single place health.py's
    dimension-coverage check should read counts from -- it must not
    re-implement this walk (REQ-d00258-C).

    Coverage inclusion is gated by ``status_expects_implementation`` via
    ``_counts_for_coverage(config, ...)`` -- the same resolver the viewer,
    summary, and tier buckets use (REQ-d00258-C). Behavior-preserving for
    default config; an explicit ``[statuses.<Name>].expects_implementation``
    flag diverges surgically.

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
        if not _counts_for_coverage(config, node.status):
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
    config: dict[str, Any] | None = None,
) -> TierBuckets:
    """Requirement-level tier bucket counts for one dimension.

    Chained dimensions (tested/verified/uat_verified) bucket by their RELATIVE
    tier -- measured over the prior link's label set via ``relative_tier_for``
    (REQ-d00258-C) -- so a requirement whose every implemented assertion is
    tested lands in ``full`` even when some assertions are unimplemented. The
    absolute dimensions (implemented/uat_coverage) bucket by their own tier. A
    node with no rollup counts as ``missing``.

    Coverage inclusion is gated by ``_counts_for_coverage(config, ...)`` -- the
    shared ``status_expects_implementation`` resolver (REQ-d00258-C).
    Behavior-preserving for default config.
    """
    allow_indirect = _allow_indirect_from_config(config)
    buckets = TierBuckets()
    for node in graph.nodes_by_kind(NodeKind.REQUIREMENT):
        if not _counts_for_coverage(config, node.status):
            continue
        buckets.total += 1
        rollup: RollupMetrics | None = node.get_metric("rollup_metrics")
        if rollup is None or getattr(rollup, dimension, None) is None:
            buckets.missing += 1
            continue
        tier, _is_na = relative_tier_for(rollup, dimension, allow_indirect=allow_indirect)
        bucket = TIER_TO_BUCKET.get(tier, "missing")
        setattr(buckets, bucket, getattr(buckets, bucket) + 1)
    return buckets


__all__ = [
    "DENOMINATOR_DIMENSION",
    "TIER_TO_BUCKET",
    "DimensionAggregate",
    "DimensionSums",
    "LevelAggregate",
    "TierBuckets",
    "absolute_tier",
    "aggregate_by_level",
    "aggregate_dimension",
    "relative_tier",
    "relative_tier_for",
    "tier_buckets",
]
