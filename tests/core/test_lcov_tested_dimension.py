# Verifies: REQ-d00254-B
"""RollupMetrics exposes a separate lcov_tested dimension (CUR-1533)."""

from elspais.graph.metrics import CoverageDimension, RollupMetrics


def test_rollup_has_lcov_tested_dimension():
    m = RollupMetrics()
    assert isinstance(m.lcov_tested, CoverageDimension)
    assert m.lcov_tested.total == 0
    assert m.lcov_tested.direct == 0.0
    assert m.lcov_tested.indirect == 0.0


def test_lcov_tested_independent_of_verified():
    m = RollupMetrics()
    m.lcov_tested = CoverageDimension(
        total=2, indirect=2.0, indirect_pct_by_label={"A": 1.0, "B": 1.0}
    )
    # verified stays empty — the two dimensions never alias
    assert m.verified.indirect == 0.0
