# Verifies: REQ-d00258-C
from pathlib import Path

import pytest

from elspais.graph.aggregation import (
    TIER_TO_BUCKET,
    _level_keys,
    aggregate_by_level,
    aggregate_dimension,
    tier_buckets,
)
from elspais.graph.builder import TraceGraph
from elspais.graph.federated import FederatedGraph
from elspais.graph.GraphNode import GraphNode, NodeKind
from elspais.graph.metrics import CoverageDimension, RollupMetrics


def _make_req(req_id: str, level: str = "dev", status: str = "Active") -> GraphNode:
    node = GraphNode(id=req_id, kind=NodeKind.REQUIREMENT, label=req_id)
    node.set_field("level", level)
    node.set_field("status", status)
    return node


def _make_graph(*nodes: GraphNode) -> FederatedGraph:
    tg = TraceGraph()
    for node in nodes:
        tg._index[node.id] = node
        if node.kind == NodeKind.REQUIREMENT:
            tg._roots.append(node)
    return FederatedGraph.from_single(
        tg, config={"project": {"name": "test", "namespace": "REQ"}}, repo_root=Path(".")
    )


class TestAggregateByLevel:
    def test_levels_match_config_order(self, canonical_graph, canonical_config):
        levels = aggregate_by_level(canonical_graph, canonical_config)
        assert [lv.level for lv in levels] == ["PRD", "OPS", "DEV"]

    def test_sums_equal_manual_rollup_walk(self, canonical_graph, canonical_config):
        # The aggregate must equal a hand-rolled walk over rollup_metrics
        # (generous footing) for one level.
        levels = {lv.level: lv for lv in aggregate_by_level(canonical_graph, canonical_config)}
        expected_impl = 0.0
        expected_total = 0
        for node in canonical_graph.nodes_by_kind(NodeKind.REQUIREMENT):
            if (node.level or "").upper() != "DEV":
                continue
            rollup = node.get_metric("rollup_metrics")
            if rollup is None:
                continue
            expected_impl += rollup.implemented.indirect
            expected_total += rollup.total_assertions
        assert levels["DEV"].implemented.covered == pytest.approx(expected_impl)
        assert levels["DEV"].implemented.total == expected_total

    def test_passing_uses_union_dimension(self, canonical_graph, canonical_config):
        levels = aggregate_by_level(canonical_graph, canonical_config)
        for lv in levels:
            # passing can never exceed tested on the same footing
            assert lv.passing.covered <= lv.tested.covered + 1e-9


class TestLevelKeys:
    """REQ-d00258-C: a [levels] key missing `rank` still aggregates -- it
    sorts after ranked keys instead of being silently dropped."""

    def test_rankless_level_sorts_after_ranked_not_dropped(self):
        config = {
            "levels": {
                "dev": {"rank": 3},
                "prd": {"rank": 1},
                "extra": {},  # no rank -- must not be excluded
                "ops": {"rank": 2},
            }
        }
        assert _level_keys(config) == ["prd", "ops", "dev", "extra"]

    def test_multiple_rankless_levels_keep_stable_relative_order(self):
        config = {
            "levels": {
                "b_extra": {},
                "dev": {"rank": 1},
                "a_extra": {},
            }
        }
        assert _level_keys(config) == ["dev", "b_extra", "a_extra"]

    def test_rankless_level_requirements_still_aggregate(self):
        # A requirement under a rank-less level must appear in the aggregate
        # output instead of being excluded from every level's totals.
        config = {
            "levels": {
                "dev": {"rank": 1},
                "extra": {},
            }
        }
        req = _make_req("REQ-x00001", level="extra")
        req.set_metric(
            "rollup_metrics",
            RollupMetrics(
                total_assertions=1,
                implemented=CoverageDimension(total=1, direct=1, indirect=1),
            ),
        )
        graph = _make_graph(req)
        levels = {lv.level: lv for lv in aggregate_by_level(graph, config)}
        assert "EXTRA" in levels
        assert levels["EXTRA"].total_requirements == 1
        assert levels["EXTRA"].implemented.covered == pytest.approx(1.0)


class TestAggregateDimension:
    """REQ-d00258-C: the single whole-graph per-dimension walk health.py's
    dimension-coverage check must consume instead of re-implementing."""

    def test_sums_match_manual_walk(self):
        req1 = _make_req("REQ-d00001")
        req1.set_metric(
            "rollup_metrics",
            RollupMetrics(
                total_assertions=2,
                tested=CoverageDimension(total=2, direct=1, indirect=2),
            ),
        )
        req2 = _make_req("REQ-d00002")
        req2.set_metric(
            "rollup_metrics",
            RollupMetrics(
                total_assertions=3,
                tested=CoverageDimension(total=3, direct=0, indirect=1),
            ),
        )
        graph = _make_graph(req1, req2)

        agg = aggregate_dimension(graph, "tested")
        assert agg.total == 5
        assert agg.direct == pytest.approx(1.0)
        assert agg.covered == pytest.approx(3.0)
        assert agg.req_count == 2
        assert agg.req_with_any == 2  # both have tested.indirect > 0
        assert agg.req_with_direct == 1  # only req1 has tested.direct > 0

    def test_no_rollup_metrics_counts_req_but_not_covered(self):
        req = _make_req("REQ-d00001")
        graph = _make_graph(req)

        agg = aggregate_dimension(graph, "implemented")
        assert agg.req_count == 1
        assert agg.req_with_any == 0
        assert agg.req_with_direct == 0
        assert agg.total == 0

    def test_excluded_status_filters_requirement(self):
        active = _make_req("REQ-d00001", status="Active")
        active.set_metric(
            "rollup_metrics",
            RollupMetrics(
                total_assertions=1,
                implemented=CoverageDimension(total=1, direct=1, indirect=1),
            ),
        )
        deprecated = _make_req("REQ-d00002", status="Deprecated")
        deprecated.set_metric(
            "rollup_metrics",
            RollupMetrics(
                total_assertions=1,
                implemented=CoverageDimension(total=1, direct=1, indirect=1),
            ),
        )
        graph = _make_graph(active, deprecated)

        agg = aggregate_dimension(graph, "implemented", exclude_status={"Deprecated"})
        assert agg.req_count == 1
        assert agg.total == 1

    def test_has_failures_true_when_any_dimension_fails(self):
        req = _make_req("REQ-d00001")
        req.set_metric(
            "rollup_metrics",
            RollupMetrics(
                total_assertions=1,
                verified=CoverageDimension(total=1, direct=0, indirect=0, has_failures=True),
            ),
        )
        graph = _make_graph(req)

        agg = aggregate_dimension(graph, "verified")
        assert agg.has_failures is True


class TestTierBuckets:
    def test_buckets_partition_total(self, canonical_graph):
        b = tier_buckets(canonical_graph, "implemented")
        assert b.full + b.partial + b.missing + b.failing == b.total

    # Verifies: REQ-d00258-A
    def test_tier_to_bucket_is_identity_over_unified_vocab(self):
        """TIER_TO_BUCKET maps each unified tier to the like-named bucket
        (REQ-d00258): {full, partial, failing, missing}, no legacy split."""
        assert set(TIER_TO_BUCKET) == {"full", "partial", "failing", "missing"}
        assert TIER_TO_BUCKET["full"] == "full"
        assert TIER_TO_BUCKET["missing"] == "missing"

    # Verifies: REQ-d00258-A
    def test_missing_tier_lands_in_missing_bucket(self, canonical_graph):
        """A requirement with no coverage is counted in the ``missing`` bucket
        (was ``none``)."""
        b = tier_buckets(canonical_graph, "uat_verified")
        # canonical fixture has requirements with no UAT verification -> missing
        assert b.missing >= 1
