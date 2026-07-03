# Verifies: REQ-d00258-C
import pytest

from elspais.graph.aggregation import (
    TIER_TO_BUCKET,
    aggregate_by_level,
    tier_buckets,
)
from elspais.graph.GraphNode import NodeKind


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


class TestTierBuckets:
    def test_buckets_partition_total(self, canonical_graph):
        b = tier_buckets(canonical_graph, "implemented")
        assert b.full + b.partial + b.none + b.failing == b.total

    def test_tier_to_bucket_covers_all_tiers(self):
        assert set(TIER_TO_BUCKET) == {
            "full-direct",
            "full-indirect",
            "partial",
            "none",
            "failing",
        }
        assert TIER_TO_BUCKET["full-indirect"] == "full"
