# Verifies: REQ-d00215-B
"""Union of verified + lcov_tested for the headline score (CUR-1533)."""

from elspais.graph.metrics import CoverageDimension, RollupMetrics, tested_and_passing


def test_union_combines_disjoint_assertions():
    m = RollupMetrics(total_assertions=2)
    m.verified = CoverageDimension(
        total=2,
        direct=1.0,
        indirect=1.0,
        direct_labels={"A"},
        indirect_labels={"A"},
        direct_pct_by_label={"A": 1.0},
        indirect_pct_by_label={"A": 1.0},
    )
    m.lcov_tested = CoverageDimension(
        total=2,
        direct=1.0,
        indirect=1.0,
        direct_labels={"B"},
        indirect_labels={"B"},
        direct_pct_by_label={"B": 1.0},
        indirect_pct_by_label={"B": 1.0},
    )
    u = tested_and_passing(m)
    assert u.total == 2
    assert u.indirect_labels == {"A", "B"}
    assert u.indirect == 2.0


def test_union_failure_in_either_sets_has_failures():
    m = RollupMetrics(total_assertions=1)
    m.lcov_tested = CoverageDimension(total=1, has_failures=True)
    assert tested_and_passing(m).has_failures is True


def test_union_takes_max_fraction_per_label():
    m = RollupMetrics(total_assertions=1)
    m.verified = CoverageDimension(
        total=1, indirect=0.5, indirect_pct_by_label={"A": 0.5}, indirect_labels={"A"}
    )
    m.lcov_tested = CoverageDimension(
        total=1, indirect=1.0, indirect_pct_by_label={"A": 1.0}, indirect_labels={"A"}
    )
    u = tested_and_passing(m)
    assert u.indirect_pct_by_label["A"] == 1.0
