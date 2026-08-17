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
    credited_labels,
    denominator_labels,
    iter_uncredited_evidence,
    numerator_dimension,
    relative_tier,
    relative_tier_for,
    tier_buckets,
)
from elspais.graph.federated import FederatedGraph
from elspais.graph.GraphNode import GraphNode, NodeKind
from elspais.graph.metrics import CoverageDimension, RollupMetrics
from tests.core.graph_test_helpers import grammar_for


def _make_req(req_id: str, level: str = "dev", status: str = "Active") -> GraphNode:
    node = GraphNode(id=req_id, kind=NodeKind.REQUIREMENT, label=req_id)
    node.set_field("level", level)
    node.set_field("status", status)
    return node


def _make_graph(*nodes: GraphNode) -> FederatedGraph:
    """Build a graph through GraphBuilder (respecting graph encapsulation).

    Callers prepare bare REQUIREMENT nodes carrying level/status fields and a
    ``rollup_metrics`` metric; the real graph is built from equivalent
    ParsedContent and the prepared rollup is re-attached to the built node.
    """
    # ParsedContent built directly (not via make_requirement, whose level
    # validation is PRD/OPS/DEV-only — these tests exercise custom levels).
    from elspais.graph.builder import GraphBuilder
    from elspais.graph.parsers import ParsedContent

    builder = GraphBuilder(namespace="REQ", resolver=grammar_for("REQ"))
    for n in nodes:
        builder.add_parsed_content(
            ParsedContent(
                content_type="requirement",
                start_line=1,
                end_line=2,
                raw_text="",
                parsed_data={
                    "id": n.id,
                    "title": n.id,
                    "level": n.get_field("level") or "dev",
                    "status": n.get_field("status") or "Active",
                    "assertions": [],
                },
            )
        )
    tg = builder.build()
    for n in nodes:
        built = tg.find_by_id(n.id)
        assert built is not None, f"builder did not produce {n.id}"
        rollup = n.get_metric("rollup_metrics")
        if rollup is not None:
            built.set_metric("rollup_metrics", rollup)
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


def _dim_with_zeros(covered, zeros, *, total=0, failing=()):
    """A CoverageDimension crediting ``covered`` at 1.0 while seeding ``zeros``
    at 0.0 in the per-label maps.

    Mirrors ``_conduct_refines_coverage`` (annotators.py), which rebuilds
    ``indirect_pct_by_label`` with an entry for EVERY assertion label -- 0.0 for
    the ones not covered in that dimension. A denominator built from the dict
    KEYS would therefore wrongly include those unimplemented labels
    (REQ-d00258-I).
    """
    covered = set(covered)
    zeros = set(zeros)
    pct = {**dict.fromkeys(covered, 1.0), **dict.fromkeys(zeros, 0.0)}
    return CoverageDimension(
        total=total,
        direct=len(covered),
        indirect=len(covered),
        has_failures=bool(failing),
        failing_labels=set(failing),
        direct_labels=set(covered),
        indirect_labels=set(covered),
        direct_pct_by_label=dict(pct),
        indirect_pct_by_label=dict(pct),
    )


# Verifies: REQ-d00258-I
class TestDenominatorExcludesUnimplementedLabels:
    """REGRESSION (REQ-d00258-I): the relative denominator is the set of labels
    ACTUALLY covered in the prior dimension (indirect fraction > 0), NOT every
    label present in ``indirect_pct_by_label``.

    ``_conduct_refines_coverage`` seeds a 0.0 entry for every assertion label
    (including unimplemented ones), so building the denominator from the dict
    keys silently makes the "relative" chain absolute -- disagreeing with the
    gaps/MCP surfaces (which filter frac > 0).
    """

    def test_relative_tier_for_excludes_zero_conducted_label(self):
        # implemented: A covered (1.0), B present-but-unimplemented (0.0).
        rollup = RollupMetrics(
            total_assertions=2,
            implemented=_dim_with_zeros({"A"}, {"B"}, total=2),
            tested=_dim_with_zeros({"A"}, {"B"}, total=2),
        )
        # denom must be {A} only -> A tested -> full, NOT partial over {A,B}.
        assert relative_tier_for(rollup, "tested") == ("full", False)

    def test_relative_tier_for_all_zero_denominator_is_na(self):
        # Nothing implemented (both labels present at 0.0), but tested credits
        # both -> the denominator is EMPTY -> N/A, not a spurious full.
        rollup = RollupMetrics(
            total_assertions=2,
            implemented=_dim_with_zeros(set(), {"A", "B"}, total=2),
            tested=_dim_with_zeros({"A", "B"}, set(), total=2),
        )
        assert relative_tier_for(rollup, "tested") == ("missing", True)

    def test_tier_buckets_excludes_zero_conducted_label(self):
        req = _make_req("REQ-d00020")
        req.set_metric(
            "rollup_metrics",
            RollupMetrics(
                total_assertions=2,
                implemented=_dim_with_zeros({"A"}, {"B"}, total=2),
                tested=_dim_with_zeros({"A"}, {"B"}, total=2),
            ),
        )
        b = tier_buckets(_make_graph(req), "tested")
        assert b.full == 1
        assert b.partial == 0

    def test_tier_buckets_all_zero_denominator_is_missing(self):
        req = _make_req("REQ-d00021")
        req.set_metric(
            "rollup_metrics",
            RollupMetrics(
                total_assertions=2,
                implemented=_dim_with_zeros(set(), {"A", "B"}, total=2),
                tested=_dim_with_zeros({"A", "B"}, set(), total=2),
            ),
        )
        b = tier_buckets(_make_graph(req), "tested")
        assert b.missing == 1
        assert b.full == 0
        assert b.partial == 0


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


# Verifies: REQ-d00274
class TestDenominatorLabelsAbsoluteDimensions:
    """REQ-d00274-B: uncredited evidence reads the denominator through the
    exact same helper the tier code uses. An absolute dimension has no
    relative denominator to leave anything out of."""

    def test_implemented_has_no_denominator(self):
        rollup = RollupMetrics(total_assertions=1, implemented=_dim({"A"}, total=1))
        assert denominator_labels(rollup, "implemented") is None

    def test_uat_coverage_has_no_denominator(self):
        rollup = RollupMetrics(total_assertions=1, uat_coverage=_dim({"A"}, total=1))
        assert denominator_labels(rollup, "uat_coverage") is None

    @pytest.mark.parametrize("dimension,denom_name", list(DENOMINATOR_DIMENSION.items()))
    def test_chained_dimension_denominator_matches_prior_link_labels(self, dimension, denom_name):
        rollup = RollupMetrics(
            total_assertions=1,
            **{denom_name: _dim({"A"}, total=1)},
        )
        assert denominator_labels(rollup, dimension) == {"A"}


# Verifies: REQ-d00274
class TestNumeratorDimension:
    """REQ-d00274-B: the numerator read for a chained dimension's evidence is
    exactly the dimension the tier figures measure -- 'verified' reads the
    tested_and_passing union, not the raw verified dimension."""

    def test_tested_numerator_is_the_tested_dimension(self):
        rollup = RollupMetrics(total_assertions=1, tested=_dim({"A"}, total=1))
        assert numerator_dimension(rollup, "tested") is rollup.tested

    def test_verified_numerator_unions_verified_and_lcov(self):
        # verified alone credits nothing; lcov_tested credits A -- the union
        # (tested_and_passing) must see A, so the raw `.verified` dimension is
        # NOT what gets read.
        rollup = RollupMetrics(
            total_assertions=1,
            verified=_dim(set(), total=1),
            lcov_tested=_dim({"A"}, total=1),
        )
        num = numerator_dimension(rollup, "verified")
        assert num is not rollup.verified
        assert credited_labels(num) == {"A"}


# Verifies: REQ-d00274
class TestCreditedLabels:
    """REQ-d00274-B: the numerator honors the project's configured footing --
    only direct per-label fractions credit under allow_indirect=False."""

    def test_generous_footing_credits_indirect_only_labels(self):
        dim = _dim({"A", "B"}, direct=set())
        assert credited_labels(dim, allow_indirect=True) == {"A", "B"}

    def test_strict_footing_excludes_indirect_only_labels(self):
        dim = _dim({"A", "B"}, direct=set())
        assert credited_labels(dim, allow_indirect=False) == set()

    def test_strict_footing_still_credits_direct_labels(self):
        dim = _dim({"A", "B"}, direct={"A"})
        assert credited_labels(dim, allow_indirect=False) == {"A"}


# Verifies: REQ-d00274-A, REQ-d00274-D, REQ-d00274-F
class TestIterUncreditedEvidence:
    """REQ-d00274: evidence naming an assertion its chained dimension does not
    count is reported, exactly once, naming what it named and what it missed."""

    def test_evidence_outside_denominator_is_reported(self):
        """A: a test naming an unimplemented assertion (B) is reported against
        the 'tested' dimension, naming B and the 'implemented' denominator it
        did not reach."""
        req = _make_req("REQ-d00001")
        req.set_metric(
            "rollup_metrics",
            RollupMetrics(
                total_assertions=2,
                implemented=_dim({"A"}, total=2),
                tested=_dim({"A", "B"}, total=2),
            ),
        )
        graph = _make_graph(req)
        items = iter_uncredited_evidence(graph)
        assert len(items) == 1
        item = items[0]
        assert item.requirement_id == "REQ-d00001"
        assert item.dimension == "tested"
        assert item.denominator == "implemented"
        assert item.assertion_label == "B"
        assert item.labels == ("B",)

    def test_evidence_fully_inside_denominator_reports_nothing(self):
        """Healthy shape: every tested label is also implemented -- no finding."""
        req = _make_req("REQ-d00002")
        req.set_metric(
            "rollup_metrics",
            RollupMetrics(
                total_assertions=1,
                implemented=_dim({"A"}, total=1),
                tested=_dim({"A"}, total=1),
            ),
        )
        graph = _make_graph(req)
        assert iter_uncredited_evidence(graph) == []

    def test_dimension_counts_no_assertion_reports_once_for_requirement(self):
        """F: nothing implemented at all -> one finding for the requirement,
        not one per assertion the tested evidence names."""
        req = _make_req("REQ-d00003")
        req.set_metric(
            "rollup_metrics",
            RollupMetrics(
                total_assertions=2,
                implemented=_dim(set(), total=2),
                tested=_dim({"A", "B"}, total=2),
            ),
        )
        graph = _make_graph(req)
        items = iter_uncredited_evidence(graph)
        assert len(items) == 1
        assert items[0].assertion_label is None
        assert set(items[0].labels) == {"A", "B"}

    def test_footing_toggles_whether_indirect_only_evidence_is_reported(self):
        """B: the numerator honors `allow_indirect`. A blanket (whole-req) test
        result credits B only indirectly; under the strict footing it is not
        credited at all, so there is nothing to report as uncredited."""
        req = _make_req("REQ-d00004")
        req.set_metric(
            "rollup_metrics",
            RollupMetrics(
                total_assertions=2,
                implemented=_dim({"A"}, total=2),
                tested=_dim({"A", "B"}, direct=set(), total=2),
            ),
        )
        graph = _make_graph(req)
        generous = iter_uncredited_evidence(graph)
        assert len(generous) == 1
        assert generous[0].assertion_label == "B"

        strict_cfg = {"rules": {"coverage": {"allow_indirect": False}}}
        strict = iter_uncredited_evidence(graph, strict_cfg)
        assert strict == []

    def test_no_double_report_across_chained_dimensions(self):
        """An assertion reported as uncredited under 'tested' is not ALSO
        reported under 'verified': verified's denominator is the tested
        labels, and B qualifies there even though it fails the implemented
        denominator for 'tested'."""
        req = _make_req("REQ-d00005")
        req.set_metric(
            "rollup_metrics",
            RollupMetrics(
                total_assertions=2,
                implemented=_dim({"A"}, total=2),
                tested=_dim({"A", "B"}, total=2),
                verified=_dim({"A", "B"}, total=2),
            ),
        )
        graph = _make_graph(req)
        items = iter_uncredited_evidence(graph)
        assert [(i.dimension, i.assertion_label) for i in items] == [("tested", "B")]
        assert not any(i.dimension == "verified" for i in items)

    def test_zero_assertion_requirement_skipped(self):
        req = _make_req("REQ-d00006")
        req.set_metric("rollup_metrics", RollupMetrics(total_assertions=0))
        graph = _make_graph(req)
        assert iter_uncredited_evidence(graph) == []

    def test_requirement_without_rollup_metrics_skipped(self):
        req = _make_req("REQ-d00007")
        graph = _make_graph(req)
        assert iter_uncredited_evidence(graph) == []

    def test_reporting_does_not_alter_coverage_figures(self):
        """E: computing the uncredited-evidence report changes no metric --
        the same aggregate_dimension answer comes back before and after."""
        req = _make_req("REQ-d00008")
        req.set_metric(
            "rollup_metrics",
            RollupMetrics(
                total_assertions=2,
                implemented=_dim({"A"}, total=2),
                tested=_dim({"A", "B"}, total=2),
            ),
        )
        graph = _make_graph(req)
        before = aggregate_dimension(graph, "tested")
        iter_uncredited_evidence(graph)
        after = aggregate_dimension(graph, "tested")
        assert before.total == after.total
        assert before.direct == after.direct
        assert before.covered == after.covered
        assert before.req_with_any == after.req_with_any
        rollup = graph.find_by_id(req.id).get_metric("rollup_metrics")
        assert rollup.tested.indirect_pct_by_label == {"A": 1.0, "B": 1.0}
        assert rollup.implemented.indirect_pct_by_label == {"A": 1.0}


# Verifies: REQ-d00274-B
# Verifies: REQ-p00019-J
class TestUncreditedEvidenceExcludesVerifiedLink:
    """'verified' is not scanned by ``iter_uncredited_evidence``: its numerator
    (``tested_and_passing`` -- Verifies-results UNION line-coverage credit,
    plus the transitive CODE->TEST provenance path) counts routes the
    ``tested`` dimension never records. A label credited only by one of those
    routes is therefore outside the Passing denominator BY CONSTRUCTION, for
    every estate -- reporting it as "no test covers this" would be untrue of
    every such finding, violating REQ-p00019-J's rule that a finding's
    description must be true of everything it covers.

    Regression guard: if 'verified' is ever added back to the reportable
    chain, these tests must fail.
    """

    def test_verified_crediting_beyond_tested_produces_no_finding(self):
        """1: verified/lcov credits A while tested credits nothing for A --
        under the retired 'verified' link this would be an uncredited-evidence
        finding; it must not be one now."""
        req = _make_req("REQ-d00009")
        req.set_metric(
            "rollup_metrics",
            RollupMetrics(
                total_assertions=1,
                implemented=_dim({"A"}, total=1),
                tested=_dim(set(), total=1),
                verified=_dim({"A"}, total=1),
            ),
        )
        graph = _make_graph(req)
        assert iter_uncredited_evidence(graph) == []

    def test_tested_finding_still_fires_while_verified_stays_silent(self):
        """2: same shape (verified credits a label 'tested' does not), plus a
        genuinely uncredited 'tested' assertion (B, tested but unimplemented).
        Exactly one finding comes back -- the 'tested' one for B -- and
        excluding 'verified' did not also suppress it."""
        req = _make_req("REQ-d00010")
        req.set_metric(
            "rollup_metrics",
            RollupMetrics(
                total_assertions=2,
                implemented=_dim({"A"}, total=2),  # only A implemented
                tested=_dim({"B"}, total=2),  # B tested, not implemented -> uncredited
                verified=_dim({"A"}, total=2),  # A verified/passing, but tested never counted A
            ),
        )
        graph = _make_graph(req)
        items = iter_uncredited_evidence(graph)
        assert len(items) == 1
        assert items[0].dimension == "tested"
        assert items[0].assertion_label == "B"
        assert not any(i.dimension == "verified" for i in items)

    def test_uat_verified_link_is_still_scanned(self):
        """3: 'uat_verified' is NOT excluded like 'verified' -- UAT-Passed
        evidence naming an assertion no journey validates is still reported."""
        req = _make_req("REQ-d00011")
        req.set_metric(
            "rollup_metrics",
            RollupMetrics(
                total_assertions=2,
                uat_coverage=_dim({"B"}, total=2),  # only B validated by a journey
                uat_verified=_dim({"A"}, total=2),  # UAT-Passed evidence names A
            ),
        )
        graph = _make_graph(req)
        items = iter_uncredited_evidence(graph)
        assert len(items) == 1
        assert items[0].dimension == "uat_verified"
        assert items[0].denominator == "uat_coverage"
        assert items[0].assertion_label == "A"
