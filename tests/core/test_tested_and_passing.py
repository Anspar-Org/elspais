# Verifies: REQ-d00254-B
"""Union of verified + lcov_tested for the headline score (CUR-1533)."""

import pytest

from elspais.graph.metrics import (
    CoverageDimension,
    RollupMetrics,
    tested_and_passing,
    tested_partition,
)


def _credited(label: str, fraction: float = 1.0, **kwargs) -> CoverageDimension:
    """A dimension crediting one label at `fraction` on both footings."""
    return CoverageDimension(
        total=1,
        direct=fraction,
        indirect=fraction,
        direct_labels={label},
        indirect_labels={label},
        direct_pct_by_label={label: fraction},
        indirect_pct_by_label={label: fraction},
        **kwargs,
    )


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


# Verifies: REQ-d00258-N
def test_lcov_credit_does_not_pass_an_assertion_whose_result_failed():
    """Line coverage never observes a verdict, so full lcov credit must not
    carry an assertion the `verified` dimension reports as failing into the
    Passing totals."""
    m = RollupMetrics(total_assertions=1)
    m.verified = CoverageDimension(total=1, has_failures=True, failing_labels={"A"})
    m.lcov_tested = _credited("A")

    u = tested_and_passing(m)
    assert u.direct == 0.0
    assert u.indirect == 0.0


# Verifies: REQ-d00258-N
@pytest.mark.parametrize("failing_source", ["verified", "lcov_tested"])
def test_failure_from_either_source_excludes_the_assertion(failing_source):
    """A failing verdict excludes the assertion whichever dimension recorded
    it -- the other dimension's credit does not rescue it."""
    m = RollupMetrics(total_assertions=1)
    m.verified = _credited("A")
    m.lcov_tested = _credited("A")
    setattr(
        m,
        failing_source,
        _credited("A", has_failures=True, failing_labels={"A"}),
    )

    u = tested_and_passing(m)
    assert u.direct == 0.0
    assert u.indirect == 0.0


# Verifies: REQ-d00258-N
def test_exclusion_is_per_assertion_not_requirement_wide():
    """A sibling's failure must not cost a passing assertion its credit, and
    that credit is still the max across both sources."""
    m = RollupMetrics(total_assertions=2)
    m.verified = CoverageDimension(
        total=2,
        direct=0.5,
        indirect=0.5,
        has_failures=True,
        failing_labels={"A"},
        direct_labels={"B"},
        indirect_labels={"B"},
        direct_pct_by_label={"B": 0.5},
        indirect_pct_by_label={"B": 0.5},
    )
    m.lcov_tested = CoverageDimension(
        total=2,
        direct=2.0,
        indirect=2.0,
        direct_labels={"A", "B"},
        indirect_labels={"A", "B"},
        direct_pct_by_label={"A": 1.0, "B": 1.0},
        indirect_pct_by_label={"A": 1.0, "B": 1.0},
    )

    u = tested_and_passing(m)
    # B keeps the max of 0.5 (verified) and 1.0 (lcov); A contributes nothing.
    assert u.direct == 1.0
    assert u.indirect == 1.0


# Verifies: REQ-d00258-N, REQ-d00258-G
def test_excluded_assertion_keeps_its_evidence_and_its_failing_standing():
    """Excluding the failing assertion from the totals must not erase what was
    credited to it, nor the record that it failed."""
    m = RollupMetrics(total_assertions=1)
    m.verified = CoverageDimension(total=1, has_failures=True, failing_labels={"A"})
    m.lcov_tested = _credited("A")

    u = tested_and_passing(m)
    assert u.direct_pct_by_label["A"] == 1.0
    assert u.indirect_pct_by_label["A"] == 1.0
    assert "A" in u.direct_labels
    assert "A" in u.indirect_labels
    assert u.failing_labels == {"A"}
    assert u.has_failures is True
    # The failing assertion is excluded from the numerator, never the denominator.
    assert u.total == 1


# ---------------------------------------------------------------------------
# The Tested breakdown (REQ-d00258-O)
# ---------------------------------------------------------------------------


def _dim(fractions: dict[str, float], *, total: int, **kwargs) -> CoverageDimension:
    """A dimension crediting each label at its fraction on both footings."""
    return CoverageDimension(
        total=total,
        direct=sum(fractions.values()),
        indirect=sum(fractions.values()),
        direct_labels={lbl for lbl, f in fractions.items() if f > 0},
        indirect_labels={lbl for lbl, f in fractions.items() if f > 0},
        direct_pct_by_label=dict(fractions),
        indirect_pct_by_label=dict(fractions),
        **kwargs,
    )


# Verifies: REQ-d00258-O
def test_partition_counts_a_failed_assertion_as_failed_not_passed():
    """An assertion whose result failed is failed, however much passing credit
    another source gave it -- line coverage never observes a verdict."""
    m = RollupMetrics(total_assertions=1)
    m.tested = _dim({"A": 1.0}, total=1)
    m.verified = CoverageDimension(total=1, has_failures=True, failing_labels={"A"})
    m.lcov_tested = _credited("A")

    part = tested_partition(m)
    assert (part.passed, part.failed, part.awaiting) == (0, 1, 0)


# Verifies: REQ-d00258-O
def test_partition_counts_a_tested_assertion_with_no_verdict_as_awaiting():
    """Tested with no passing evidence and no failure is awaiting a result --
    the test was declared and nothing came back."""
    m = RollupMetrics(total_assertions=1)
    m.tested = _dim({"A": 1.0}, total=1)

    part = tested_partition(m)
    assert (part.passed, part.failed, part.awaiting) == (0, 0, 1)


# Verifies: REQ-d00258-O
def test_partition_accounts_for_every_tested_assertion():
    """Four tested assertions in four different conditions land in exactly one
    state each, so the three counts account for the whole tested set."""
    m = RollupMetrics(total_assertions=5)
    # E is deliberately absent from the tested set.
    m.tested = _dim({"A": 1.0, "B": 1.0, "C": 1.0, "D": 1.0, "E": 0.0}, total=5)
    m.verified = _dim(
        {"A": 1.0, "B": 0.0, "C": 0.0, "D": 0.0},
        total=5,
        has_failures=True,
        failing_labels={"B"},
    )
    # C is credited only by line coverage; D has neither kind of evidence.
    m.lcov_tested = _dim({"C": 1.0}, total=5)

    part = tested_partition(m)
    assert (part.passed, part.failed, part.awaiting) == (2, 1, 1)
    assert part.tested == 4


# Verifies: REQ-d00258-O
def test_partition_ignores_an_assertion_outside_the_tested_set():
    """The breakdown breaks Tested down, so an assertion Tested does not count
    is in none of the three -- even one carrying a failing result."""
    m = RollupMetrics(total_assertions=2)
    m.tested = _dim({"A": 1.0, "B": 0.0}, total=2)
    m.verified = _dim(
        {"A": 1.0},
        total=2,
        has_failures=True,
        failing_labels={"B"},
    )

    part = tested_partition(m)
    assert (part.passed, part.failed, part.awaiting) == (1, 0, 0)
    assert part.tested == 1


# Verifies: REQ-d00258-O
@pytest.mark.parametrize("fraction", [0.25, 0.5, 1.0])
def test_partition_counts_a_partially_credited_assertion_once(fraction):
    """Counts assertions, not fractional credit: a partly-credited assertion is
    still one assertion, and it is the assertion that passed."""
    m = RollupMetrics(total_assertions=1)
    m.tested = _dim({"A": fraction}, total=1)
    m.verified = _dim({"A": fraction}, total=1)

    part = tested_partition(m)
    assert (part.passed, part.failed, part.awaiting) == (1, 0, 0)


# Verifies: REQ-d00258-O
def test_partition_matches_the_tested_set_of_a_built_graph(canonical_graph):
    """Against rollups the annotators actually produced, the breakdown accounts
    for exactly the assertions Tested counts -- no more, and none dropped."""
    from elspais.graph.GraphNode import NodeKind

    seen_tested = 0
    for node in canonical_graph.iter_by_kind(NodeKind.REQUIREMENT):
        rollup = node.get_metric("rollup_metrics")
        if rollup is None:
            continue
        tested_labels = {
            lbl for lbl, frac in rollup.tested.indirect_pct_by_label.items() if frac > 0
        }
        seen_tested += len(tested_labels)
        assert tested_partition(rollup).tested == len(tested_labels), node.id

    # The fixture must actually test something, or the loop asserts nothing.
    assert seen_tested > 0
