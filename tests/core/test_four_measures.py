# Verifies: REQ-d00069-L, REQ-d00069-M, REQ-d00069-N
"""The four coverage measures, and the total taken per assertion."""

from elspais.graph.metrics import CoverageDimension, RollupMetrics


def test_immediate_measures_sum_whole_evidence():
    dim = CoverageDimension(
        total=3,
        immediate_direct_by_label={"A": 1.0},
        immediate_indirect_by_label={"A": 1.0, "B": 1.0, "C": 1.0},
    )
    assert dim.immediate_direct == 1.0
    assert dim.immediate_indirect == 3.0


def test_total_counts_an_assertion_covered_twice_only_once():
    dim = CoverageDimension(
        total=3,
        immediate_direct_by_label={"A": 1.0},
        immediate_indirect_by_label={"A": 1.0, "B": 1.0, "C": 1.0},
    )
    assert dim.covered == 3.0
    assert dim.covered <= dim.total


def test_total_takes_the_greatest_measure_per_assertion():
    dim = CoverageDimension(
        total=2,
        immediate_direct_by_label={"A": 1.0},
        rolled_direct_by_label={"A": 0.5, "B": 0.25},
    )
    assert dim.total_by_label == {"A": 1.0, "B": 0.25}
    assert dim.covered == 1.25


# Verifies: REQ-d00069-B, REQ-d00069-M
def test_a_blanket_citation_credits_every_assertion_indirectly(canonical_graph):
    from elspais.graph import NodeKind

    for node in canonical_graph.nodes_by_kind(NodeKind.REQUIREMENT):
        rollup = node.get_metric("rollup_metrics")
        if rollup is None:
            continue
        for name in ("implemented", "tested"):
            dim = getattr(rollup, name)
            # implemented/tested evidence is all-or-nothing, so their
            # immediate measures never hold a fraction (REQ-d00069-M).
            assert all(v == 1.0 for v in dim.immediate_direct_by_label.values())
            assert all(v == 1.0 for v in dim.immediate_indirect_by_label.values())


# Verifies: REQ-d00069-M
def test_a_partially_verified_journey_leaves_a_fraction_in_the_immediate_map():
    """A journey verified in 1 of its 2 steps credits its ratio, not 1.0.

    REQ-d00069-M: immediate coverage records the strength of the evidence
    attached to it, whole where the evidence is whole and partial where the
    evidence itself is partial -- so uat_verified's immediate map must carry
    the verified-step ratio, not flatten it to whole.
    """
    rollup = RollupMetrics(total_assertions=2)
    rollup.populate_test_dimensions(
        tested_direct_labels=set(),
        tested_indirect_labels=set(),
        verified_direct_labels=set(),
        verified_indirect_labels=set(),
        verified_failures=False,
        uat_verified_direct_pct={"A": 0.5},
        uat_verified_indirect_pct={},
        uat_verified_failures=False,
    )
    assert rollup.uat_verified.immediate_direct_by_label == {"A": 0.5}
    assert rollup.uat_verified.immediate_indirect_by_label == {"A": 0.5}
