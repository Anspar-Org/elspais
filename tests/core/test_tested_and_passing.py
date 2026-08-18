# Verifies: REQ-d00258-N
"""The Passing dimension: what the tests declared against an *Assertion* returned.

Line coverage credits no *Traceability* dimension (REQ-d00254-B), so
``tested_and_passing`` reads ``verified`` alone; ``lcov_tested`` can neither
credit an *Assertion* into Passing nor exclude one from it.
"""

import pytest

from elspais.graph.aggregation import covered_labels
from elspais.graph.metrics import (
    CoverageDimension,
    RollupMetrics,
    tested_and_passing,
    tested_partition,
)


def _credited(label: str, fraction: float = 1.0, **kwargs) -> CoverageDimension:
    """A dimension crediting one label at `fraction`, cited by name here."""
    return CoverageDimension(
        total=1,
        immediate_direct_by_label={label: fraction},
        **kwargs,
    )


# Verifies: REQ-d00258-N
def test_line_coverage_of_another_assertion_does_not_enter_passing():
    """Only the *Assertion* a test declared against and passed is counted. An
    *Assertion* line coverage reached but no test named stays out of Passing
    entirely -- out of the labels, and out of the figures."""
    m = RollupMetrics(total_assertions=2)
    m.verified = CoverageDimension(total=2, immediate_direct_by_label={"A": 1.0})
    m.lcov_tested = CoverageDimension(total=2, immediate_direct_by_label={"B": 1.0})
    u = tested_and_passing(m)
    assert u.total == 2
    assert covered_labels(u, "total") == {"A"}
    assert u.covered == 1.0


# Verifies: REQ-d00258-N
def test_line_coverage_failure_does_not_flag_passing():
    """A failure recorded against line coverage is a fact about `lcov_tested`,
    which is reported in its own right (REQ-d00254-B). It says nothing about
    whether a test declared against an *Assertion* failed, so it must not
    raise the Passing dimension's failure flag."""
    m = RollupMetrics(total_assertions=1)
    m.lcov_tested = CoverageDimension(total=1, has_failures=True)
    assert tested_and_passing(m).has_failures is False


# Verifies: REQ-d00258-N
def test_line_coverage_does_not_raise_a_partial_assertion_to_full():
    """Fuller line coverage must not top up what the declared tests returned:
    the per-label fraction is the `verified` fraction, not the max of the two.
    Regression guard against the max-merge union returning."""
    m = RollupMetrics(total_assertions=1)
    m.verified = CoverageDimension(total=1, immediate_indirect_by_label={"A": 0.5})
    m.lcov_tested = CoverageDimension(total=1, immediate_indirect_by_label={"A": 1.0})
    u = tested_and_passing(m)
    assert u.total_by_label["A"] == 0.5
    assert u.covered == 0.5


# Verifies: REQ-d00258-N
def test_a_failing_declared_test_excludes_its_own_assertion():
    """`no such test returned a failure` is a condition on the same evidence
    that credits: an *Assertion* one declared test passed and another failed
    contributes nothing to the Passing figures."""
    m = RollupMetrics(total_assertions=1)
    m.verified = _credited("A", has_failures=True, failing_labels={"A"})

    u = tested_and_passing(m)
    assert u.immediate_direct == 0.0
    assert u.covered == 0.0


# Verifies: REQ-d00258-N
def test_line_coverage_cannot_exclude_an_assertion_its_tests_passed():
    """The mirror of the crediting rule. Line coverage is not a test declared
    against the *Assertion*, so a failure it records neither excludes the
    *Assertion* from Passing nor names it as failing."""
    m = RollupMetrics(total_assertions=1)
    m.verified = _credited("A")
    m.lcov_tested = _credited("A", has_failures=True, failing_labels={"A"})

    u = tested_and_passing(m)
    assert u.immediate_direct == 1.0
    assert u.covered == 1.0
    assert u.failing_labels == set()


# Verifies: REQ-d00258-N
def test_exclusion_is_per_assertion_not_requirement_wide():
    """A sibling's failure must not cost a passing assertion the credit its
    own declared tests earned."""
    m = RollupMetrics(total_assertions=2)
    m.verified = CoverageDimension(
        total=2,
        has_failures=True,
        failing_labels={"A"},
        immediate_direct_by_label={"B": 0.5},
    )

    u = tested_and_passing(m)
    # B keeps its own 0.5; A (failing) contributes nothing.
    assert u.immediate_direct == 0.5
    assert u.covered == 0.5


# Verifies: REQ-d00258-N, REQ-d00258-G
def test_excluded_assertion_keeps_its_failing_standing():
    """A failing assertion contributes to no measure of Passing, and the record
    that it failed survives in ``failing_labels`` -- which is what a
    per-*Assertion* standing reads first (REQ-d00258-G), so the assertion still
    renders under its own standing rather than disappearing."""
    m = RollupMetrics(total_assertions=1)
    m.verified = _credited("A", has_failures=True, failing_labels={"A"})

    u = tested_and_passing(m)
    assert "A" not in covered_labels(u, "immediate_direct")
    assert "A" not in covered_labels(u, "total")
    assert u.covered == 0.0
    assert u.failing_labels == {"A"}
    assert u.has_failures is True
    # The failing assertion is excluded from the numerator, never the denominator.
    assert u.total == 1


# ---------------------------------------------------------------------------
# The Tested breakdown (REQ-d00258-O)
# ---------------------------------------------------------------------------


def _dim(fractions: dict[str, float], *, total: int, **kwargs) -> CoverageDimension:
    """A dimension crediting each label at its fraction, cited by name here."""
    return CoverageDimension(
        total=total,
        immediate_direct_by_label=dict(fractions),
        **kwargs,
    )


# Verifies: REQ-d00258-O
def test_partition_counts_a_failed_assertion_as_failed_not_passed():
    """An assertion whose declared test failed is failed, however many of its
    implementing lines a run happened to execute."""
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
    state each, so the three counts account for the whole tested set.

    C is the demonstration of what N changed. Its implementing lines were
    executed and nothing reports it failing, but no test declared against it
    returned a verdict -- so it is awaiting a result, not passed. Counting it
    as passed was the union reporting an annotation nobody wrote.
    """
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
    assert (part.passed, part.failed, part.awaiting) == (1, 1, 2)
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
        tested_labels = {lbl for lbl, frac in rollup.tested.total_by_label.items() if frac > 0}
        seen_tested += len(tested_labels)
        assert tested_partition(rollup).tested == len(tested_labels), node.id

    # The fixture must actually test something, or the loop asserts nothing.
    assert seen_tested > 0
