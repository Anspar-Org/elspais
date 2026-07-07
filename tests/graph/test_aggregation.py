# Verifies: REQ-d00258-C
from pathlib import Path

import pytest

from elspais.graph.aggregation import (
    DENOMINATOR_DIMENSION,
    TIER_TO_BUCKET,
    _level_keys,
    absolute_tier,
    aggregate_by_level,
    aggregate_dimension,
    relative_tier,
    relative_tier_for,
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

        # Deprecated is a RETIRED-role status: excluded by default config via
        # the status_expects_implementation gate (REQ-d00258-C).
        agg = aggregate_dimension(graph, "implemented")
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


def _dim(labels, *, direct=None, failing=(), total=0):
    """A CoverageDimension crediting ``labels`` at fraction 1.0.

    ``total`` sets the absolute assertion count (only relevant to the absolute
    ``.tier``); relative measurement ignores it and uses the label dicts.
    """
    labels = set(labels)
    direct = set(labels if direct is None else direct)
    return CoverageDimension(
        total=total,
        direct=len(direct),
        indirect=len(labels),
        failing_labels=set(failing),
        direct_pct_by_label=dict.fromkeys(direct, 1.0),
        indirect_pct_by_label=dict.fromkeys(labels, 1.0),
    )


# Verifies: REQ-d00258-C
# Verifies: REQ-d00258-E
class TestRelativeTierFor:
    """``relative_tier_for`` picks the relative denominator per dimension."""

    def test_denominator_map_covers_the_chained_dimensions(self):
        """Only the chained dimensions have a relative denominator; the
        absolute dimensions (implemented, uat_coverage) are NOT in the map."""
        assert DENOMINATOR_DIMENSION == {
            "tested": "implemented",
            "verified": "tested",
            "uat_verified": "uat_coverage",
        }

    def test_tested_measured_over_implemented_labels(self):
        """implemented=partial (A of A,B) but every implemented label tested ->
        tested is RELATIVELY full, not partial."""
        rollup = RollupMetrics(
            total_assertions=2,
            implemented=_dim({"A"}, total=2),
            tested=_dim({"A"}, total=2),
        )
        # Relative: denom = implemented labels {A}; A tested -> full.
        assert relative_tier_for(rollup, "tested") == ("full", False)
        # Absolute would have been partial (1 of 2 assertions).
        assert rollup.tested.tier == "partial"

    def test_tested_empty_denominator_is_na(self):
        """Nothing implemented -> tested has an empty denominator -> N/A
        ('missing', is_na=True), a neutral non-gap (REQ-d00258-E)."""
        rollup = RollupMetrics(
            total_assertions=2,
            implemented=_dim(set(), total=2),
            tested=_dim(set(), total=2),
        )
        assert relative_tier_for(rollup, "tested") == ("missing", True)

    def test_verified_uses_tested_and_passing_union(self):
        """The 'verified' numerator is tested_and_passing (verified | lcov),
        NOT the raw verified dimension -- lcov-only credit still counts."""
        rollup = RollupMetrics(
            total_assertions=1,
            tested=_dim({"A"}, total=1),
            verified=_dim(set(), total=1),  # no // Verifies: result
            lcov_tested=_dim({"A"}, total=1),  # but line-coverage credits A
        )
        # denom = tested labels {A}; union credits A -> full.
        assert relative_tier_for(rollup, "verified") == ("full", False)
        # Raw verified alone would be a gap.
        assert rollup.verified.tier == "missing"

    def test_absolute_dimension_returns_dim_tier(self):
        """A dimension NOT in the denominator map returns the absolute
        ``.tier`` (never N/A)."""
        rollup = RollupMetrics(
            total_assertions=2,
            implemented=_dim({"A"}, total=2),
        )
        assert relative_tier_for(rollup, "implemented") == ("partial", False)


# Verifies: REQ-d00258-C
# Verifies: REQ-d00258-E
class TestTierBucketsRelative:
    """``tier_buckets`` honors the relative denominators for chained dims."""

    def test_tested_bucket_is_relative_full(self):
        """implemented=partial, all-implemented tested -> the req lands in the
        ``full`` tested bucket (relative), not ``partial``."""
        req = _make_req("REQ-d00001")
        req.set_metric(
            "rollup_metrics",
            RollupMetrics(
                total_assertions=2,
                implemented=_dim({"A"}, total=2),
                tested=_dim({"A"}, total=2),
            ),
        )
        graph = _make_graph(req)
        b = tier_buckets(graph, "tested")
        assert b.full == 1
        assert b.partial == 0

    def test_nothing_implemented_tested_bucket_is_missing(self):
        """No implemented labels -> tested denominator empty -> the req is in
        the ``missing`` bucket (N/A), not partial or full."""
        req = _make_req("REQ-d00002")
        req.set_metric(
            "rollup_metrics",
            RollupMetrics(
                total_assertions=1,
                implemented=_dim(set(), total=1),
                tested=_dim(set(), total=1),
            ),
        )
        graph = _make_graph(req)
        b = tier_buckets(graph, "tested")
        assert b.missing == 1
        assert b.full == 0
        assert b.partial == 0

    def test_implemented_bucket_stays_absolute(self):
        """The absolute 'implemented' dimension still buckets by its own tier
        (partial when 1 of 2 assertions implemented)."""
        req = _make_req("REQ-d00003")
        req.set_metric(
            "rollup_metrics",
            RollupMetrics(
                total_assertions=2,
                implemented=_dim({"A"}, total=2),
            ),
        )
        graph = _make_graph(req)
        b = tier_buckets(graph, "implemented")
        assert b.partial == 1
        assert b.full == 0


# Verifies: REQ-d00258-C
def test_relative_tier_shared_helper_measures_over_denominator():
    """The shared ``relative_tier`` lives in aggregation and measures a
    numerator dimension over an explicit label-set denominator."""
    dim = _dim({"A"})
    assert relative_tier(dim, {"A", "B"}) == ("partial", False)
    assert relative_tier(dim, set()) == ("missing", True)


# Verifies: REQ-d00258
# Verifies: REQ-d00069-L
class TestAllowIndirect:
    """``allow_indirect`` toggles whether indirect coverage credits the state.

    Default True preserves the generous footing (REQ-d00069-L). When False, only
    direct coverage lifts a tier -- for the absolute helper (``absolute_tier``),
    the shared relative helper (``relative_tier_for``), and the requirement-level
    ``tier_buckets`` rollup.
    """

    def test_absolute_tier_indirect_only_true_full_false_missing(self):
        """An absolute dimension covered only indirectly (direct=0) is ``full``
        when allow_indirect=True and ``missing`` when False."""
        dim = _dim({"A", "B"}, direct=set(), total=2)
        assert absolute_tier(dim) == "full"  # default True
        assert absolute_tier(dim, allow_indirect=True) == "full"
        assert absolute_tier(dim, allow_indirect=False) == "missing"

    def test_absolute_tier_direct_full_under_both(self):
        """Direct coverage credits the absolute tier regardless of the flag."""
        dim = _dim({"A", "B"}, direct={"A", "B"}, total=2)
        assert absolute_tier(dim, allow_indirect=True) == "full"
        assert absolute_tier(dim, allow_indirect=False) == "full"

    def test_absolute_tier_direct_partial_when_false(self):
        """Partial direct credit -> ``partial`` under allow_indirect=False."""
        dim = _dim({"A", "B"}, direct={"A"}, total=2)
        assert absolute_tier(dim, allow_indirect=False) == "partial"

    def test_absolute_tier_failing_wins(self):
        """A failing dimension is ``failing`` under both settings."""
        dim = CoverageDimension(
            total=1,
            direct=1,
            indirect=1,
            has_failures=True,
            failing_labels={"A"},
            direct_pct_by_label={"A": 1.0},
            indirect_pct_by_label={"A": 1.0},
        )
        assert absolute_tier(dim, allow_indirect=False) == "failing"
        assert absolute_tier(dim, allow_indirect=True) == "failing"

    def test_relative_tier_for_absolute_dim_honors_allow_indirect(self):
        """``relative_tier_for`` on an absolute dim (implemented) credits direct
        only when allow_indirect=False."""
        rollup = RollupMetrics(
            total_assertions=2,
            implemented=_dim({"A", "B"}, direct=set(), total=2),
        )
        assert relative_tier_for(rollup, "implemented") == ("full", False)
        assert relative_tier_for(rollup, "implemented", allow_indirect=False) == (
            "missing",
            False,
        )

    def test_relative_tier_for_chained_dim_honors_allow_indirect(self):
        """A chained dim (tested) credits its direct numerator only when False."""
        rollup = RollupMetrics(
            total_assertions=2,
            implemented=_dim({"A", "B"}, total=2),
            tested=_dim({"A", "B"}, direct=set(), total=2),
        )
        assert relative_tier_for(rollup, "tested") == ("full", False)
        assert relative_tier_for(rollup, "tested", allow_indirect=False) == (
            "missing",
            False,
        )

    def test_tier_buckets_absolute_dim_config_false(self):
        """`[rules.coverage] allow_indirect=false` moves an indirect-only
        implemented req from the ``full`` bucket to ``missing``."""
        req = _make_req("REQ-d00010")
        req.set_metric(
            "rollup_metrics",
            RollupMetrics(
                total_assertions=2,
                implemented=_dim({"A", "B"}, direct=set(), total=2),
            ),
        )
        graph = _make_graph(req)
        assert tier_buckets(graph, "implemented").full == 1  # default True
        cfg = {"rules": {"coverage": {"allow_indirect": False}}}
        b = tier_buckets(graph, "implemented", config=cfg)
        assert b.missing == 1
        assert b.full == 0

    def test_tier_buckets_relative_dim_config_false(self):
        """allow_indirect=false also moves an indirect-only tested req to
        ``missing``."""
        req = _make_req("REQ-d00011")
        req.set_metric(
            "rollup_metrics",
            RollupMetrics(
                total_assertions=2,
                implemented=_dim({"A", "B"}, total=2),
                tested=_dim({"A", "B"}, direct=set(), total=2),
            ),
        )
        graph = _make_graph(req)
        assert tier_buckets(graph, "tested").full == 1
        cfg = {"rules": {"coverage": {"allow_indirect": False}}}
        b = tier_buckets(graph, "tested", config=cfg)
        assert b.missing == 1
        assert b.full == 0


# Verifies: REQ-d00258-C
class TestCoverageInclusionViaExpectsImplementation:
    """Coverage-aggregation inclusion is gated by
    ``status_expects_implementation`` (design §3), replacing the implicit
    ``coverage_excluded_statuses()`` gate.

    SAFETY ANCHOR: for DEFAULT config (no ``[statuses.*]`` override),
    ``not status_expects_implementation(config, status)`` is EXACTLY
    ``status in coverage_excluded_statuses()`` -- every non-active-role status
    is excluded. So a Draft (provisional role) is excluded by default, and an
    explicit ``expects_implementation=true`` flag surgically includes it.
    """

    _EXPECTS_DRAFT = {"statuses": {"Draft": {"expects_implementation": True}}}

    def _active_and_draft_graph(self) -> FederatedGraph:
        active = _make_req("REQ-d00001", status="Active")
        active.set_metric(
            "rollup_metrics",
            RollupMetrics(
                total_assertions=1,
                implemented=CoverageDimension(total=1, direct=1, indirect=1),
            ),
        )
        draft = _make_req("REQ-d00002", status="Draft")
        draft.set_metric(
            "rollup_metrics",
            RollupMetrics(
                total_assertions=1,
                implemented=CoverageDimension(total=1, direct=1, indirect=1),
            ),
        )
        return _make_graph(active, draft)

    def test_default_config_draft_excluded_from_aggregate_by_level(self):
        """PRESERVED: with default config a Draft req does not count toward the
        per-level implemented totals (Draft's provisional role -> excluded)."""
        graph = self._active_and_draft_graph()
        levels = {
            lv.level: lv for lv in aggregate_by_level(graph, {"levels": {"dev": {"rank": 3}}})
        }
        dev = levels["DEV"]
        assert dev.total_requirements == 1  # only the Active req
        assert dev.implemented.covered == pytest.approx(1.0)

    def test_expects_implementation_flag_includes_draft_in_aggregate_by_level(self):
        """NEW: ``[statuses.Draft] expects_implementation=true`` surgically
        counts the Draft req in the implemented totals -- the behavior the old
        ``active=["Active","Draft"]`` hack gave, now per-status."""
        graph = self._active_and_draft_graph()
        config = {"levels": {"dev": {"rank": 3}}, **self._EXPECTS_DRAFT}
        levels = {lv.level: lv for lv in aggregate_by_level(graph, config)}
        dev = levels["DEV"]
        assert dev.total_requirements == 2  # Active + Draft now counted
        assert dev.implemented.covered == pytest.approx(2.0)

    @pytest.mark.parametrize(
        "config,expected_req_count,expected_total",
        [
            ({}, 1, 1),  # default: Draft excluded (role gate)
            ({"statuses": {"Draft": {"expects_implementation": True}}}, 2, 2),
        ],
    )
    def test_aggregate_dimension_gates_via_config(self, config, expected_req_count, expected_total):
        graph = self._active_and_draft_graph()
        agg = aggregate_dimension(graph, "implemented", config=config)
        assert agg.req_count == expected_req_count
        assert agg.total == expected_total

    @pytest.mark.parametrize(
        "config,expected_total",
        [
            ({}, 1),  # default: Draft excluded (role gate)
            ({"statuses": {"Draft": {"expects_implementation": True}}}, 2),
        ],
    )
    def test_tier_buckets_gates_via_config(self, config, expected_total):
        graph = self._active_and_draft_graph()
        b = tier_buckets(graph, "implemented", config=config)
        assert b.total == expected_total
