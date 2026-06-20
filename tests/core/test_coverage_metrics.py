# Validates REQ-p00006-B
"""Tests for Coverage Metrics (RollupMetrics, annotate_coverage)."""

import pytest

from elspais.graph.annotators import annotate_coverage
from elspais.graph.metrics import CoverageContribution, CoverageSource, RollupMetrics
from tests.core.graph_test_helpers import (
    build_graph,
    make_code_ref,
    make_requirement,
    make_test_ref,
)


class TestRollupMetrics:
    """Tests for RollupMetrics dataclass."""

    # Implements: REQ-d00086-B
    def test_add_contribution(self):
        """Contributions are stored by assertion label."""
        metrics = RollupMetrics(total_assertions=2)
        contrib_a = CoverageContribution("code:1", CoverageSource.DIRECT, "A")
        contrib_b = CoverageContribution("req:2", CoverageSource.EXPLICIT, "B")

        metrics.add_contribution(contrib_a)
        metrics.add_contribution(contrib_b)

        assert len(metrics.assertion_coverage["A"]) == 1
        assert len(metrics.assertion_coverage["B"]) == 1
        assert metrics.assertion_coverage["A"][0] == contrib_a
        assert metrics.assertion_coverage["B"][0] == contrib_b

    # Implements: REQ-d00069-D
    def test_finalize_computes_aggregates(self):
        """Finalize computes aggregate counts and percentage."""
        metrics = RollupMetrics(total_assertions=4)
        metrics.add_contribution(CoverageContribution("test:1", CoverageSource.DIRECT, "A"))
        metrics.add_contribution(CoverageContribution("req:2", CoverageSource.EXPLICIT, "B"))
        # C and D have no coverage

        metrics.finalize()

        # implemented.direct = DIRECT + EXPLICIT = {A, B} = 2
        assert metrics.implemented.direct == 2
        # implemented.indirect = DIRECT + EXPLICIT + INFERRED = {A, B} = 2
        assert metrics.implemented.indirect == 2
        # No inferred: indirect - direct == 0
        assert metrics.implemented.indirect - metrics.implemented.direct == 0
        # 2/4 = 50%
        assert metrics.implemented.indirect_pct == 50.0

    # Implements: REQ-d00069-D
    def test_finalize_handles_zero_assertions(self):
        """Finalize handles zero assertions gracefully."""
        metrics = RollupMetrics(total_assertions=0)

        metrics.finalize()

        assert metrics.implemented.indirect_pct == 0.0

    # Implements: REQ-d00086-B
    def test_multiple_contributors_same_assertion(self):
        """Multiple contributors to same assertion only count once."""
        metrics = RollupMetrics(total_assertions=1)
        # Two different tests validate same assertion
        metrics.add_contribution(CoverageContribution("test:1", CoverageSource.DIRECT, "A"))
        metrics.add_contribution(CoverageContribution("test:2", CoverageSource.DIRECT, "A"))

        metrics.finalize()

        assert metrics.implemented.indirect == 1  # Only one assertion covered
        assert metrics.implemented.direct == 1
        assert len(metrics.assertion_coverage["A"]) == 2  # But two contributors


class TestAnnotateCoverageDirect:
    """Tests for direct coverage (TEST/CODE -> assertion)."""

    # Implements: REQ-d00086-B
    def test_direct_coverage_from_test(self):
        """TEST node validates assertion -> DIRECT coverage."""
        # Build: REQ-100 with assertion A, validated by test
        graph = build_graph(
            make_requirement(
                "REQ-100",
                level="PRD",
                assertions=[{"label": "A", "text": "The system shall..."}],
            ),
            make_test_ref(verifies=["REQ-100-A"]),
        )

        annotate_coverage(graph)

        node = graph.find_by_id("REQ-100")
        metrics: RollupMetrics = node.get_metric("rollup_metrics")

        assert metrics.total_assertions == 1
        assert metrics.implemented.direct == 1
        assert metrics.implemented.indirect == 1
        assert metrics.implemented.indirect_pct == 100.0

    # Implements: REQ-d00086-B
    def test_direct_coverage_from_code(self):
        """CODE node implements assertion -> DIRECT coverage."""
        graph = build_graph(
            make_requirement(
                "REQ-100",
                level="PRD",
                assertions=[{"label": "A", "text": "The system shall..."}],
            ),
            make_code_ref(implements=["REQ-100-A"]),
        )

        annotate_coverage(graph)

        node = graph.find_by_id("REQ-100")
        metrics: RollupMetrics = node.get_metric("rollup_metrics")

        assert metrics.total_assertions == 1
        assert metrics.implemented.direct == 1
        assert metrics.implemented.indirect_pct == 100.0


class TestAnnotateCoverageExplicit:
    """Tests for explicit coverage (REQ -> specific assertions)."""

    # Implements: REQ-d00086-B
    def test_explicit_coverage_from_req_with_assertion_syntax(self):
        """REQ implements specific assertion(s) -> EXPLICIT coverage."""
        # REQ-020 implements REQ-100-B (explicit assertion syntax)
        graph = build_graph(
            make_requirement(
                "REQ-100",
                level="PRD",
                assertions=[
                    {"label": "A", "text": "Assertion A"},
                    {"label": "B", "text": "Assertion B"},
                ],
            ),
            make_requirement(
                "REQ-020",
                level="OPS",
                implements=["REQ-100-B"],
            ),
        )

        annotate_coverage(graph)

        node = graph.find_by_id("REQ-100")
        metrics: RollupMetrics = node.get_metric("rollup_metrics")

        assert metrics.total_assertions == 2
        # B is EXPLICIT, which counts as direct (assertion-targeted)
        assert metrics.implemented.direct == 1
        assert metrics.implemented.indirect == 1  # Only B is covered
        # No inferred: indirect - direct == 0
        assert metrics.implemented.indirect - metrics.implemented.direct == 0
        assert metrics.implemented.indirect_pct == 50.0

        # Verify it's assertion B that's covered
        assert "B" in metrics.assertion_coverage
        assert metrics.assertion_coverage["B"][0].source_type == CoverageSource.EXPLICIT


class TestAnnotateCoverageInferred:
    """Tests for inferred coverage (REQ -> parent REQ)."""

    # Implements: REQ-d00086-B
    def test_inferred_coverage_from_req_implements_parent(self):
        """REQ implements parent REQ -> INFERRED coverage for all assertions."""
        # REQ-020 implements REQ-100 (all assertions implied)
        graph = build_graph(
            make_requirement(
                "REQ-100",
                level="PRD",
                assertions=[
                    {"label": "A", "text": "Assertion A"},
                    {"label": "B", "text": "Assertion B"},
                ],
            ),
            make_requirement(
                "REQ-020",
                level="OPS",
                implements=["REQ-100"],  # No assertion specifier = inferred
            ),
        )

        annotate_coverage(graph)

        node = graph.find_by_id("REQ-100")
        metrics: RollupMetrics = node.get_metric("rollup_metrics")

        assert metrics.total_assertions == 2
        assert metrics.implemented.indirect == 2  # Both A and B covered (inferred)
        assert metrics.implemented.direct == 0  # No assertion-targeted coverage
        # All inferred: indirect - direct == 2
        assert metrics.implemented.indirect - metrics.implemented.direct == 2
        assert metrics.implemented.indirect_pct == 100.0


class TestAnnotateCoverageRefines:
    """Tests for REFINES edge coverage conduction (REQ-d00069-J)."""

    # Implements: REQ-d00069-J
    def test_refines_does_not_contribute_coverage(self):
        """An empty refining requirement conducts 0 coverage.

        This exercises the "adds no coverage by itself" half of REQ-d00069-J:
        REQ-010 refines REQ-100-A but has NO assertions, so its own rolled-up
        coverage is 0 and the conducted contribution to REQ-100-A is 0.
        """
        # REQ-010 refines REQ-100-A but is empty -> conducts 0
        graph = build_graph(
            make_requirement(
                "REQ-100",
                level="PRD",
                assertions=[
                    {"label": "A", "text": "Assertion A"},
                ],
            ),
            make_requirement(
                "REQ-010",
                level="OPS",
                refines=["REQ-100-A"],  # REFINES, not IMPLEMENTS
            ),
        )

        annotate_coverage(graph)

        node = graph.find_by_id("REQ-100")
        metrics: RollupMetrics = node.get_metric("rollup_metrics")

        assert metrics.total_assertions == 1
        assert metrics.implemented.indirect == 0  # REFINES doesn't count
        assert metrics.implemented.indirect_pct == 0.0


class TestAnnotateCoverageMixed:
    """Tests for mixed coverage sources."""

    # Implements: REQ-d00086-B
    def test_mixed_coverage_sources(self):
        """Multiple coverage sources on different assertions."""
        # REQ-100 has A, B, C, D
        # - A: covered by TEST (direct)
        # - B: covered by REQ-020 implements B (explicit)
        # - C: covered by CODE (direct)
        # - D: no coverage
        graph = build_graph(
            make_requirement(
                "REQ-100",
                level="PRD",
                assertions=[
                    {"label": "A", "text": "Assertion A"},
                    {"label": "B", "text": "Assertion B"},
                    {"label": "C", "text": "Assertion C"},
                    {"label": "D", "text": "Assertion D"},
                ],
            ),
            make_test_ref(verifies=["REQ-100-A"]),  # A - direct
            make_requirement(
                "REQ-020",
                level="OPS",
                implements=["REQ-100-B"],  # B - explicit
            ),
            make_code_ref(implements=["REQ-100-C"]),  # C - direct
            # D has no coverage
        )

        annotate_coverage(graph)

        node = graph.find_by_id("REQ-100")
        metrics: RollupMetrics = node.get_metric("rollup_metrics")

        assert metrics.total_assertions == 4
        # implemented.direct = DIRECT + EXPLICIT = {A, B, C} = 3
        assert metrics.implemented.direct == 3
        # implemented.indirect = DIRECT + EXPLICIT + INFERRED = {A, B, C} = 3
        assert metrics.implemented.indirect == 3
        # No inferred: indirect - direct == 0
        assert metrics.implemented.indirect - metrics.implemented.direct == 0
        assert metrics.implemented.indirect_pct == 75.0


class TestUserExample:
    """The specific 4-assertion scenario from user.

    REQ-100: 4 assertions (A, B, C, D)
    REQ-010 refines REQ-100-A (no coverage!)
    REQ-020 implements REQ-100-B (explicit coverage)
    TEST validates REQ-100-A and REQ-100-B

    Expected:
    - A: DIRECT from TEST (validates)
    - B: DIRECT from TEST + EXPLICIT from REQ-020
    - C, D: no coverage
    """

    # Implements: REQ-d00069-J
    def test_user_example_scenario(self):
        """User's 4-assertion scenario with refines vs implements."""
        graph = build_graph(
            make_requirement(
                "REQ-100",
                level="PRD",
                assertions=[
                    {"label": "A", "text": "Assertion A"},
                    {"label": "B", "text": "Assertion B"},
                    {"label": "C", "text": "Assertion C"},
                    {"label": "D", "text": "Assertion D"},
                ],
            ),
            make_requirement(
                "REQ-010",
                level="OPS",
                refines=["REQ-100-A"],  # REFINES - no coverage
            ),
            make_requirement(
                "REQ-020",
                level="OPS",
                implements=["REQ-100-B"],  # IMPLEMENTS B - explicit
            ),
            make_test_ref(
                verifies=["REQ-100-A"],
                source_path="tests/test_a.py",
            ),
            make_test_ref(
                verifies=["REQ-100-B"],
                source_path="tests/test_b.py",
            ),
        )

        annotate_coverage(graph)

        node = graph.find_by_id("REQ-100")
        metrics: RollupMetrics = node.get_metric("rollup_metrics")

        # Total assertions: 4
        assert metrics.total_assertions == 4

        # Under REQ-d00069-J equal-weight conduction, the empty refiner REQ-010
        # (refines REQ-100-A but has no assertions, so conducts 0.0) is an extra
        # equal-weight contributor to A alongside the direct test (1.0). A's
        # fraction is therefore mean(1.0, 0.0) = 0.5, diluting it from 1.0.
        # B = 1.0 (test + REQ-020 explicit, no diluting refiner). C, D = 0.
        # Covered sum: A=0.5 + B=1.0 + C=0 + D=0 = 1.5.
        assert metrics.implemented.indirect == 1.5

        # A is covered by TEST (DIRECT)
        assert "A" in metrics.assertion_coverage
        assert any(c.source_type == CoverageSource.DIRECT for c in metrics.assertion_coverage["A"])

        # B is covered by TEST (DIRECT) AND REQ-020 (EXPLICIT)
        assert "B" in metrics.assertion_coverage
        b_sources = {c.source_type for c in metrics.assertion_coverage["B"]}
        assert CoverageSource.DIRECT in b_sources
        assert CoverageSource.EXPLICIT in b_sources

        # REFINES from REQ-010 should NOT contribute to A's coverage
        # (we already verified A is only DIRECT from TEST, not from REQ-010)
        a_contributors = [c.source_id for c in metrics.assertion_coverage["A"]]
        assert all("REQ-010" not in c for c in a_contributors)

        # C and D have no coverage
        assert "C" not in metrics.assertion_coverage
        assert "D" not in metrics.assertion_coverage

        # Coverage percentage: 1.5/4 = 37.5% (A diluted to 0.5 by empty refiner)
        assert metrics.implemented.indirect_pct == 37.5


class TestNoAssertions:
    """Tests for requirements without assertions."""

    # Implements: REQ-d00051-E
    def test_requirement_with_no_assertions(self):
        """Requirements with no assertions have zero metrics."""
        graph = build_graph(
            make_requirement(
                "REQ-100",
                level="PRD",
                assertions=[],  # No assertions
            ),
        )

        annotate_coverage(graph)

        node = graph.find_by_id("REQ-100")
        metrics: RollupMetrics = node.get_metric("rollup_metrics")

        assert metrics.total_assertions == 0
        assert metrics.implemented.indirect == 0
        assert metrics.implemented.indirect_pct == 0.0


class TestCoveragePercentStored:
    """Verify implemented.indirect_pct is accessible from rollup_metrics."""

    # Implements: REQ-d00055-D
    def test_coverage_pct_accessible_from_rollup(self):
        """implemented.indirect_pct is accessible from the rollup_metrics object."""
        graph = build_graph(
            make_requirement(
                "REQ-100",
                level="PRD",
                assertions=[
                    {"label": "A", "text": "Assertion A"},
                    {"label": "B", "text": "Assertion B"},
                ],
            ),
            make_test_ref(verifies=["REQ-100-A"]),  # 1/2 = 50%
        )

        annotate_coverage(graph)

        node = graph.find_by_id("REQ-100")

        rollup: RollupMetrics = node.get_metric("rollup_metrics")
        assert rollup.implemented.indirect_pct == 50.0


class TestTestSpecificMetrics:
    """Tests for TEST-specific metrics (tested, verified dimensions)."""

    # Implements: REQ-d00069-B
    def test_direct_tested_counts_test_coverage(self):
        """tested.direct counts assertions with TEST nodes (not CODE)."""
        graph = build_graph(
            make_requirement(
                "REQ-100",
                level="PRD",
                assertions=[
                    {"label": "A", "text": "Assertion A"},
                    {"label": "B", "text": "Assertion B"},
                    {"label": "C", "text": "Assertion C"},
                ],
            ),
            make_test_ref(verifies=["REQ-100-A"]),  # TEST covers A
            make_code_ref(implements=["REQ-100-B"]),  # CODE covers B
            # C has no coverage
        )

        annotate_coverage(graph)

        node = graph.find_by_id("REQ-100")
        rollup: RollupMetrics = node.get_metric("rollup_metrics")

        assert rollup.tested.direct == 1  # Only A (TEST), not B (CODE)
        assert rollup.implemented.indirect == 2  # Both A and B covered

    # Implements: REQ-d00069-F
    def test_validated_counts_passing_tests(self):
        """verified.direct counts assertions with passing TEST_RESULTs."""
        from tests.core.graph_test_helpers import make_test_result

        graph = build_graph(
            make_requirement(
                "REQ-100",
                level="PRD",
                assertions=[
                    {"label": "A", "text": "Assertion A"},
                    {"label": "B", "text": "Assertion B"},
                ],
            ),
            make_test_ref(
                verifies=["REQ-100-A"],
                source_path="tests/test_a.py",
            ),
            make_test_ref(
                verifies=["REQ-100-B"],
                source_path="tests/test_b.py",
            ),
            make_test_result(
                "result-a",
                status="passed",
                test_id="test:tests/test_a.py:1",
            ),
            make_test_result(
                "result-b",
                status="failed",
                test_id="test:tests/test_b.py:1",
            ),
        )

        annotate_coverage(graph)

        node = graph.find_by_id("REQ-100")
        rollup: RollupMetrics = node.get_metric("rollup_metrics")

        assert rollup.tested.direct == 2  # Both have TEST nodes
        assert rollup.verified.direct == 1  # Only A has passing result
        assert rollup.verified.has_failures is True  # B failed

    # Implements: REQ-d00069-F
    def test_has_failures_true_when_test_fails(self):
        """verified.has_failures is True when any TEST_RESULT is failed/error."""
        from tests.core.graph_test_helpers import make_test_result

        graph = build_graph(
            make_requirement(
                "REQ-100",
                level="PRD",
                assertions=[{"label": "A", "text": "Assertion A"}],
            ),
            make_test_ref(verifies=["REQ-100-A"]),
            make_test_result("result-1", status="error", test_id="test:tests/test_module.py:1"),
        )

        annotate_coverage(graph)

        node = graph.find_by_id("REQ-100")
        rollup: RollupMetrics = node.get_metric("rollup_metrics")

        assert rollup.verified.has_failures is True

    # Implements: REQ-d00069-F
    def test_has_failures_false_when_all_pass(self):
        """verified.has_failures is False when all tests pass."""
        from tests.core.graph_test_helpers import make_test_result

        graph = build_graph(
            make_requirement(
                "REQ-100",
                level="PRD",
                assertions=[{"label": "A", "text": "Assertion A"}],
            ),
            make_test_ref(verifies=["REQ-100-A"]),
            make_test_result("result-1", status="passed", test_id="test:tests/test_module.py:1"),
        )

        annotate_coverage(graph)

        node = graph.find_by_id("REQ-100")
        rollup: RollupMetrics = node.get_metric("rollup_metrics")

        assert rollup.verified.has_failures is False
        assert rollup.verified.direct == 1

    # Implements: REQ-d00069-B
    def test_no_tests_means_zero_test_metrics(self):
        """Without TEST nodes, test metrics are zero."""
        graph = build_graph(
            make_requirement(
                "REQ-100",
                level="PRD",
                assertions=[{"label": "A", "text": "Assertion A"}],
            ),
            make_code_ref(implements=["REQ-100-A"]),  # CODE only, no TEST
        )

        annotate_coverage(graph)

        node = graph.find_by_id("REQ-100")
        rollup: RollupMetrics = node.get_metric("rollup_metrics")

        assert rollup.tested.direct == 0
        assert rollup.verified.direct == 0
        assert rollup.verified.has_failures is False
        assert rollup.implemented.indirect == 1  # Still covered by CODE


class TestRefinesCoverageConduction:
    """REFINES edges conduct the refiner's own coverage up to the parent assertion.

    Per REQ-d00069-J, a `Refines:` edge contributes the refining requirement's
    own rolled-up coverage as one equal-weight incoming contribution to the
    targeted parent *Assertion*, computed per dimension and recursively.
    """

    # Implements: REQ-d00069-J
    def test_basic_propagation_with_negative_control(self):
        """A tested refiner lifts its targeted parent assertion; siblings stay 0.

        REQ-010 refines REQ-100-A and is itself tested (a test verifies
        REQ-010-A). That coverage conducts up to REQ-100-A (-> 1.0) while
        REQ-100-B, which nothing refines or tests, stays 0.0.
        """
        graph = build_graph(
            make_requirement(
                "REQ-100",
                level="PRD",
                assertions=[
                    {"label": "A", "text": "Assertion A"},
                    {"label": "B", "text": "Assertion B"},
                ],
            ),
            make_requirement(
                "REQ-010",
                level="OPS",
                refines=["REQ-100-A"],
                assertions=[{"label": "A", "text": "Refined A"}],
            ),
            make_test_ref(verifies=["REQ-010-A"], source_path="tests/test_010.py"),
        )

        annotate_coverage(graph)

        parent = graph.find_by_id("REQ-100").get_metric("rollup_metrics")
        # A is conducted up from the tested refiner; B is the negative control.
        assert parent.tested.direct_pct_by_label["A"] == 1.0
        assert parent.tested.direct_pct_by_label["B"] == 0.0
        assert parent.tested.direct_pct == 50.0  # 1 of 2 assertions covered

        # The refiner itself is directly tested.
        child = graph.find_by_id("REQ-010").get_metric("rollup_metrics")
        assert child.tested.direct_pct_by_label["A"] == 1.0

    # Implements: REQ-d00069-J
    def test_equal_weight_per_refine_edge(self):
        """Each assertion-targeted refine edge is one equal-weight contributor.

        Three requirements refine REQ-900-A; two are tested, one is not, so
        REQ-900-A == mean(1.0, 1.0, 0.0) == 2/3. One requirement refines
        REQ-900-B and is tested, so REQ-900-B == 1.0. Requirement coverage is
        the unweighted mean of its assertions: (2/3 + 1.0) / 2 == 83.33%.
        """
        graph = build_graph(
            make_requirement(
                "REQ-900",
                level="PRD",
                assertions=[
                    {"label": "A", "text": "Assertion A"},
                    {"label": "B", "text": "Assertion B"},
                ],
            ),
            make_requirement(
                "REQ-901",
                level="OPS",
                refines=["REQ-900-A"],
                assertions=[{"label": "A", "text": "Refined A1"}],
            ),
            make_requirement(
                "REQ-902",
                level="OPS",
                refines=["REQ-900-A"],
                assertions=[{"label": "A", "text": "Refined A2"}],
            ),
            make_requirement(
                "REQ-903",
                level="OPS",
                refines=["REQ-900-A"],
                assertions=[{"label": "A", "text": "Refined A3 (untested)"}],
            ),
            make_requirement(
                "REQ-904",
                level="OPS",
                refines=["REQ-900-B"],
                assertions=[{"label": "A", "text": "Refined B"}],
            ),
            make_test_ref(verifies=["REQ-901-A"], source_path="tests/test_901.py"),
            make_test_ref(verifies=["REQ-902-A"], source_path="tests/test_902.py"),
            make_test_ref(verifies=["REQ-904-A"], source_path="tests/test_904.py"),
        )

        annotate_coverage(graph)

        parent = graph.find_by_id("REQ-900").get_metric("rollup_metrics")
        assert parent.tested.direct_pct_by_label["A"] == pytest.approx(2 / 3)
        assert parent.tested.direct_pct_by_label["B"] == 1.0
        assert parent.tested.direct_pct == pytest.approx(83.33, abs=0.01)

    # Implements: REQ-d00069-J
    def test_recursion_over_two_hop_chain(self):
        """Coverage conducts recursively through a 2-hop refine chain.

        REQ-720 refines REQ-710-A refines REQ-700-A. A test verifies
        REQ-720-A, which must conduct all the way up to REQ-700-A.
        """
        graph = build_graph(
            make_requirement(
                "REQ-700",
                level="PRD",
                assertions=[{"label": "A", "text": "Top A"}],
            ),
            make_requirement(
                "REQ-710",
                level="OPS",
                refines=["REQ-700-A"],
                assertions=[{"label": "A", "text": "Mid A"}],
            ),
            make_requirement(
                "REQ-720",
                level="DEV",
                refines=["REQ-710-A"],
                assertions=[{"label": "A", "text": "Leaf A"}],
            ),
            make_test_ref(verifies=["REQ-720-A"], source_path="tests/test_720.py"),
        )

        annotate_coverage(graph)

        top = graph.find_by_id("REQ-700").get_metric("rollup_metrics")
        assert top.tested.direct_pct_by_label["A"] == 1.0

    # Implements: REQ-d00069-J
    def test_blanket_refine_contributes_to_indirect_only(self):
        """A whole-requirement refine shows in indirect, not direct.

        REQ-C refines REQ-P (no /A suffix == blanket), so its coverage is a
        blanket contributor: it never appears in the direct fraction. A blanket
        Refines names no assertion, so it is worth only one assertion's share
        (1/N) of the refiner's coverage (REQ-d00069-J), credited to every parent
        assertion that lacks direct coverage. REQ-P has N=2 assertions and REQ-C
        is fully tested, so each uncovered parent assertion gets (1/2)*1.0 = 0.5.
        """
        graph = build_graph(
            make_requirement(
                "REQ-P",
                level="PRD",
                assertions=[
                    {"label": "A", "text": "Assertion A"},
                    {"label": "B", "text": "Assertion B"},
                ],
            ),
            make_requirement(
                "REQ-C",
                level="OPS",
                refines=["REQ-P"],  # whole requirement -> blanket
                assertions=[{"label": "A", "text": "Refined A"}],
            ),
            make_test_ref(verifies=["REQ-C-A"], source_path="tests/test_c.py"),
        )

        annotate_coverage(graph)

        parent = graph.find_by_id("REQ-P").get_metric("rollup_metrics")
        # Blanket refine never contributes to direct.
        assert parent.tested.direct_pct_by_label["A"] == 0.0
        assert parent.tested.direct_pct_by_label["B"] == 0.0
        # It contributes 1/N of the refiner's coverage to each uncovered
        # assertion: (1/2) * 1.0 == 0.5. Partial, so each remains a gap.
        assert parent.tested.indirect_pct_by_label["A"] == 0.5
        assert parent.tested.indirect_pct_by_label["B"] == 0.5

    # Implements: REQ-d00069-J
    def test_dimensions_propagate_independently(self):
        """Conduction is per-dimension: a tested refiner lifts `tested` only.

        REQ-MC is covered in the `tested` dimension (a verifying test) but has
        no UAT/journey coverage, so REQ-M-A propagates to 1.0 in `tested` while
        `uat_coverage` stays 0.0.
        """
        graph = build_graph(
            make_requirement(
                "REQ-M",
                level="PRD",
                assertions=[{"label": "A", "text": "Assertion A"}],
            ),
            make_requirement(
                "REQ-MC",
                level="OPS",
                refines=["REQ-M-A"],
                assertions=[{"label": "A", "text": "Refined A"}],
            ),
            make_test_ref(verifies=["REQ-MC-A"], source_path="tests/test_mc.py"),
        )

        annotate_coverage(graph)

        parent = graph.find_by_id("REQ-M").get_metric("rollup_metrics")
        assert parent.tested.direct_pct_by_label["A"] == 1.0
        # No UAT/journey coverage anywhere -> stays 0 in that dimension.
        assert parent.uat_coverage.direct_pct_by_label["A"] == 0.0
        assert parent.uat_coverage.indirect_pct_by_label["A"] == 0.0

    # Implements: REQ-d00069-J
    def test_cycle_safety(self):
        """A refine cycle degrades gracefully -- no hang, finite [0,1] values.

        REQ-X refines REQ-Y-A and REQ-Y refines REQ-X-A (a cycle). annotate
        must terminate and produce finite fractions within [0, 1].
        """
        graph = build_graph(
            make_requirement(
                "REQ-X",
                level="PRD",
                refines=["REQ-Y-A"],
                assertions=[{"label": "A", "text": "X A"}],
            ),
            make_requirement(
                "REQ-Y",
                level="PRD",
                refines=["REQ-X-A"],
                assertions=[{"label": "A", "text": "Y A"}],
            ),
            make_test_ref(verifies=["REQ-X-A"], source_path="tests/test_x.py"),
        )

        # Must not hang or raise on the cycle.
        annotate_coverage(graph)

        for req_id in ("REQ-X", "REQ-Y"):
            metrics = graph.find_by_id(req_id).get_metric("rollup_metrics")
            for mode in ("direct_pct_by_label", "indirect_pct_by_label"):
                value = getattr(metrics.tested, mode)["A"]
                assert isinstance(value, float)
                assert 0.0 <= value <= 1.0

    # Implements: REQ-d00069-J
    def test_blanket_refine_multiple_edges_averaged(self):
        """Multiple blanket refines are averaged, then scaled by 1/N.

        PARENT has N=3 assertions (A, B, C) with no direct coverage. Three
        requirements each blanket-refine PARENT (`Refines: PARENT`); two are
        fully tested and one is untested, so the mean child coverage across the
        blanket edges is (1 + 1 + 0) / 3 == 2/3. A blanket refine is worth only
        one assertion's share, so each uncovered parent assertion gets
        (1/N) * mean == (1/3) * (2/3) == 0.2222.
        """
        graph = build_graph(
            make_requirement(
                "PARENT",
                level="PRD",
                assertions=[
                    {"label": "A", "text": "Assertion A"},
                    {"label": "B", "text": "Assertion B"},
                    {"label": "C", "text": "Assertion C"},
                ],
            ),
            make_requirement(
                "REQ-R1",
                level="OPS",
                refines=["PARENT"],
                assertions=[{"label": "A", "text": "Refiner 1 A"}],
            ),
            make_requirement(
                "REQ-R2",
                level="OPS",
                refines=["PARENT"],
                assertions=[{"label": "A", "text": "Refiner 2 A"}],
            ),
            make_requirement(
                "REQ-R3",
                level="OPS",
                refines=["PARENT"],
                assertions=[{"label": "A", "text": "Refiner 3 A (untested)"}],
            ),
            make_test_ref(verifies=["REQ-R1-A"], source_path="tests/test_r1.py"),
            make_test_ref(verifies=["REQ-R2-A"], source_path="tests/test_r2.py"),
        )

        annotate_coverage(graph)

        parent = graph.find_by_id("PARENT").get_metric("rollup_metrics")
        expected = (1 / 3) * (2 / 3)  # 0.2222
        assert parent.tested.indirect_pct_by_label["A"] == pytest.approx(expected, abs=0.001)
        assert parent.tested.indirect_pct_by_label["B"] == pytest.approx(expected, abs=0.001)
        assert parent.tested.indirect_pct_by_label["C"] == pytest.approx(expected, abs=0.001)
        # Blanket refines never contribute to direct.
        assert parent.tested.direct_pct_by_label["A"] == 0.0
        assert parent.tested.direct_pct_by_label["B"] == 0.0
        assert parent.tested.direct_pct_by_label["C"] == 0.0

    # Implements: REQ-d00069-J
    def test_blanket_credit_skips_assertions_with_direct_coverage(self):
        """Blanket credit applies only to parent assertions lacking direct cover.

        PARENT has N=2 assertions (A, B). A has its own direct test. One
        requirement blanket-refines PARENT and is fully tested. A keeps its
        direct 1.0 (blanket credit ignored for an already-covered assertion);
        B, which has no direct coverage, gets (1/N) * 1.0 == 0.5.
        """
        graph = build_graph(
            make_requirement(
                "PARENT",
                level="PRD",
                assertions=[
                    {"label": "A", "text": "Assertion A"},
                    {"label": "B", "text": "Assertion B"},
                ],
            ),
            make_requirement(
                "REQ-BLANK",
                level="OPS",
                refines=["PARENT"],
                assertions=[{"label": "A", "text": "Refined A"}],
            ),
            make_test_ref(verifies=["PARENT-A"], source_path="tests/test_a.py"),
            make_test_ref(verifies=["REQ-BLANK-A"], source_path="tests/test_blank.py"),
        )

        annotate_coverage(graph)

        parent = graph.find_by_id("PARENT").get_metric("rollup_metrics")
        # A has its own direct test -> 1.0, blanket credit not applied.
        assert parent.tested.indirect_pct_by_label["A"] == pytest.approx(1.0)
        # B has no direct coverage -> blanket credit (1/2) * 1.0 == 0.5.
        assert parent.tested.indirect_pct_by_label["B"] == pytest.approx(0.5)

    # Implements: REQ-d00069-J
    def test_assertion_targeted_refine_keeps_full_weight(self):
        """An assertion-targeted refine contributes at full weight, not 1/N.

        PARENT has N=2 assertions (A, B). One requirement targets PARENT-A
        (`Refines: PARENT-A`) and is fully tested. A gets the child's full
        coverage (1.0), NOT (1/N); B, untouched, stays 0.0. This contrasts
        targeted (full weight) against blanket (1/N).
        """
        graph = build_graph(
            make_requirement(
                "PARENT",
                level="PRD",
                assertions=[
                    {"label": "A", "text": "Assertion A"},
                    {"label": "B", "text": "Assertion B"},
                ],
            ),
            make_requirement(
                "REQ-TGT",
                level="OPS",
                refines=["PARENT-A"],  # assertion-targeted
                assertions=[{"label": "A", "text": "Refined A"}],
            ),
            make_test_ref(verifies=["REQ-TGT-A"], source_path="tests/test_tgt.py"),
        )

        annotate_coverage(graph)

        parent = graph.find_by_id("PARENT").get_metric("rollup_metrics")
        assert parent.tested.indirect_pct_by_label["A"] == pytest.approx(1.0)
        assert parent.tested.indirect_pct_by_label["B"] == pytest.approx(0.0)

    # Implements: REQ-d00069-J
    def test_partial_conducted_coverage_is_a_gap(self):
        """Partial conducted coverage (0 < f < 1) is still reported as a gap.

        PARENT has N=2 assertions (A, B), one fully-tested blanket refiner, so
        each parent assertion gets (1/2) * 1.0 == 0.5. The gaps surface treats
        an assertion as covered only at ~1.0, so both A and B remain gaps.
        """
        from elspais.commands.gaps import _uncovered_assertions

        graph = build_graph(
            make_requirement(
                "PARENT",
                level="PRD",
                assertions=[
                    {"label": "A", "text": "Assertion A"},
                    {"label": "B", "text": "Assertion B"},
                ],
            ),
            make_requirement(
                "REQ-BLANK",
                level="OPS",
                refines=["PARENT"],
                assertions=[{"label": "A", "text": "Refined A"}],
            ),
            make_test_ref(verifies=["REQ-BLANK-A"], source_path="tests/test_blank.py"),
        )

        annotate_coverage(graph)

        metrics = graph.find_by_id("PARENT").get_metric("rollup_metrics")
        assert metrics.tested.indirect_pct_by_label["A"] == pytest.approx(0.5)
        assert metrics.tested.indirect_pct_by_label["B"] == pytest.approx(0.5)

        # Partial coverage is a gap: both assertions reported as uncovered.
        uncov = _uncovered_assertions(metrics, ["A", "B"], "tested")
        assert set(uncov) == {"A", "B"}
