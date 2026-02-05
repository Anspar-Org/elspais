# Validates REQ-p00006-B
"""Tests for Coverage Metrics (RollupMetrics, annotate_coverage)."""

from elspais.graph.annotators import annotate_coverage
from elspais.graph.metrics import CoverageContribution, CoverageSource, RollupMetrics
from tests.core.graph_test_helpers import (
    build_graph,
    make_code_ref,
    make_requirement,
    make_test_ref,
)


class TestCoverageSource:
    """Tests for CoverageSource enum."""

    def test_source_values(self):
        """Verify enum values."""
        assert CoverageSource.DIRECT.value == "direct"
        assert CoverageSource.EXPLICIT.value == "explicit"
        assert CoverageSource.INFERRED.value == "inferred"


class TestCoverageContribution:
    """Tests for CoverageContribution dataclass."""

    def test_contribution_fields(self):
        """Contribution stores all fields correctly."""
        contrib = CoverageContribution(
            source_id="test:foo.py:10",
            source_type=CoverageSource.DIRECT,
            assertion_label="A",
        )

        assert contrib.source_id == "test:foo.py:10"
        assert contrib.source_type == CoverageSource.DIRECT
        assert contrib.assertion_label == "A"


class TestRollupMetrics:
    """Tests for RollupMetrics dataclass."""

    def test_default_values(self):
        """Default metrics are all zero."""
        metrics = RollupMetrics()

        assert metrics.total_assertions == 0
        assert metrics.covered_assertions == 0
        assert metrics.direct_covered == 0
        assert metrics.explicit_covered == 0
        assert metrics.inferred_covered == 0
        assert metrics.coverage_pct == 0.0
        assert metrics.assertion_coverage == {}

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

    def test_finalize_computes_aggregates(self):
        """Finalize computes aggregate counts and percentage."""
        metrics = RollupMetrics(total_assertions=4)
        metrics.add_contribution(CoverageContribution("test:1", CoverageSource.DIRECT, "A"))
        metrics.add_contribution(CoverageContribution("req:2", CoverageSource.EXPLICIT, "B"))
        # C and D have no coverage

        metrics.finalize()

        assert metrics.covered_assertions == 2
        assert metrics.direct_covered == 1
        assert metrics.explicit_covered == 1
        assert metrics.inferred_covered == 0
        assert metrics.coverage_pct == 50.0

    def test_finalize_handles_zero_assertions(self):
        """Finalize handles zero assertions gracefully."""
        metrics = RollupMetrics(total_assertions=0)

        metrics.finalize()

        assert metrics.coverage_pct == 0.0

    def test_multiple_contributors_same_assertion(self):
        """Multiple contributors to same assertion only count once."""
        metrics = RollupMetrics(total_assertions=1)
        # Two different tests validate same assertion
        metrics.add_contribution(CoverageContribution("test:1", CoverageSource.DIRECT, "A"))
        metrics.add_contribution(CoverageContribution("test:2", CoverageSource.DIRECT, "A"))

        metrics.finalize()

        assert metrics.covered_assertions == 1  # Only one assertion covered
        assert metrics.direct_covered == 1
        assert len(metrics.assertion_coverage["A"]) == 2  # But two contributors


class TestAnnotateCoverageDirect:
    """Tests for direct coverage (TEST/CODE → assertion)."""

    def test_direct_coverage_from_test(self):
        """TEST node validates assertion → DIRECT coverage."""
        # Build: REQ-100 with assertion A, validated by test
        graph = build_graph(
            make_requirement(
                "REQ-100",
                level="PRD",
                assertions=[{"label": "A", "text": "The system shall..."}],
            ),
            make_test_ref(validates=["REQ-100-A"]),
        )

        annotate_coverage(graph)

        node = graph.find_by_id("REQ-100")
        metrics: RollupMetrics = node.get_metric("rollup_metrics")

        assert metrics.total_assertions == 1
        assert metrics.covered_assertions == 1
        assert metrics.direct_covered == 1
        assert metrics.coverage_pct == 100.0

    def test_direct_coverage_from_code(self):
        """CODE node implements assertion → DIRECT coverage."""
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
        assert metrics.direct_covered == 1
        assert metrics.coverage_pct == 100.0


class TestAnnotateCoverageExplicit:
    """Tests for explicit coverage (REQ → specific assertions)."""

    def test_explicit_coverage_from_req_with_assertion_syntax(self):
        """REQ implements specific assertion(s) → EXPLICIT coverage."""
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
        assert metrics.covered_assertions == 1  # Only B is covered
        assert metrics.explicit_covered == 1
        assert metrics.direct_covered == 0
        assert metrics.inferred_covered == 0
        assert metrics.coverage_pct == 50.0

        # Verify it's assertion B that's covered
        assert "B" in metrics.assertion_coverage
        assert metrics.assertion_coverage["B"][0].source_type == CoverageSource.EXPLICIT


class TestAnnotateCoverageInferred:
    """Tests for inferred coverage (REQ → parent REQ)."""

    def test_inferred_coverage_from_req_implements_parent(self):
        """REQ implements parent REQ → INFERRED coverage for all assertions."""
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
        assert metrics.covered_assertions == 2  # Both A and B covered
        assert metrics.inferred_covered == 2
        assert metrics.explicit_covered == 0
        assert metrics.direct_covered == 0
        assert metrics.coverage_pct == 100.0


class TestAnnotateCoverageRefines:
    """Tests for REFINES edge (no coverage contribution)."""

    def test_refines_does_not_contribute_coverage(self):
        """REFINES edge does NOT contribute to coverage."""
        # REQ-010 refines REQ-100-A - should NOT count as coverage
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
        assert metrics.covered_assertions == 0  # REFINES doesn't count
        assert metrics.coverage_pct == 0.0


class TestAnnotateCoverageMixed:
    """Tests for mixed coverage sources."""

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
            make_test_ref(validates=["REQ-100-A"]),  # A - direct
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
        assert metrics.covered_assertions == 3  # A, B, C covered
        assert metrics.direct_covered == 2  # A (test), C (code)
        assert metrics.explicit_covered == 1  # B
        assert metrics.inferred_covered == 0  # D has none, no inferred
        assert metrics.coverage_pct == 75.0


class TestUserExample:
    """The specific 4-assertion scenario from user.

    REQ-100: 4 assertions (A, B, C, D)
    REQ-010 refines REQ-100-A (no coverage!)
    REQ-020 implements REQ-100-B (explicit coverage)
    TEST validates REQ-100-A and REQ-100-B

    Expected:
    - Implemented: 1 (only B via IMPLEMENTS edge)
    - Tested: 2 (A and B have TEST nodes)
    - But wait - tests DO provide DIRECT coverage, so:
      - A: DIRECT from TEST (validates)
      - B: DIRECT from TEST + EXPLICIT from REQ-020
    """

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
                validates=["REQ-100-A"],
                source_path="tests/test_a.py",
            ),
            make_test_ref(
                validates=["REQ-100-B"],
                source_path="tests/test_b.py",
            ),
        )

        annotate_coverage(graph)

        node = graph.find_by_id("REQ-100")
        metrics: RollupMetrics = node.get_metric("rollup_metrics")

        # Total assertions: 4
        assert metrics.total_assertions == 4

        # Covered assertions: A (test), B (test + REQ-020)
        # C and D have no coverage
        assert metrics.covered_assertions == 2

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

        # Coverage percentage: 2/4 = 50%
        assert metrics.coverage_pct == 50.0


class TestNoAssertions:
    """Tests for requirements without assertions."""

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
        assert metrics.covered_assertions == 0
        assert metrics.coverage_pct == 0.0


class TestCoveragePercentStored:
    """Verify coverage_pct is stored in node metrics."""

    def test_coverage_pct_stored_in_metrics(self):
        """coverage_pct is stored directly in node._metrics for convenience."""
        graph = build_graph(
            make_requirement(
                "REQ-100",
                level="PRD",
                assertions=[
                    {"label": "A", "text": "Assertion A"},
                    {"label": "B", "text": "Assertion B"},
                ],
            ),
            make_test_ref(validates=["REQ-100-A"]),  # 1/2 = 50%
        )

        annotate_coverage(graph)

        node = graph.find_by_id("REQ-100")

        # Both methods should give same value
        rollup: RollupMetrics = node.get_metric("rollup_metrics")
        coverage_pct = node.get_metric("coverage_pct")

        assert coverage_pct == 50.0
        assert rollup.coverage_pct == 50.0


class TestTestSpecificMetrics:
    """Tests for TEST-specific metrics (direct_tested, validated, has_failures)."""

    def test_direct_tested_counts_test_coverage(self):
        """direct_tested counts assertions with TEST nodes (not CODE)."""
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
            make_test_ref(validates=["REQ-100-A"]),  # TEST covers A
            make_code_ref(implements=["REQ-100-B"]),  # CODE covers B
            # C has no coverage
        )

        annotate_coverage(graph)

        node = graph.find_by_id("REQ-100")
        rollup: RollupMetrics = node.get_metric("rollup_metrics")

        assert rollup.direct_tested == 1  # Only A (TEST), not B (CODE)
        assert rollup.covered_assertions == 2  # Both A and B covered

    def test_validated_counts_passing_tests(self):
        """validated counts assertions with passing TEST_RESULTs."""
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
                validates=["REQ-100-A"],
                source_path="tests/test_a.py",
            ),
            make_test_ref(
                validates=["REQ-100-B"],
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

        assert rollup.direct_tested == 2  # Both have TEST nodes
        assert rollup.validated == 1  # Only A has passing result
        assert rollup.has_failures is True  # B failed

    def test_has_failures_true_when_test_fails(self):
        """has_failures is True when any TEST_RESULT is failed/error."""
        from tests.core.graph_test_helpers import make_test_result

        graph = build_graph(
            make_requirement(
                "REQ-100",
                level="PRD",
                assertions=[{"label": "A", "text": "Assertion A"}],
            ),
            make_test_ref(validates=["REQ-100-A"]),
            make_test_result("result-1", status="error", test_id="test:tests/test_module.py:1"),
        )

        annotate_coverage(graph)

        node = graph.find_by_id("REQ-100")
        rollup: RollupMetrics = node.get_metric("rollup_metrics")

        assert rollup.has_failures is True

    def test_has_failures_false_when_all_pass(self):
        """has_failures is False when all tests pass."""
        from tests.core.graph_test_helpers import make_test_result

        graph = build_graph(
            make_requirement(
                "REQ-100",
                level="PRD",
                assertions=[{"label": "A", "text": "Assertion A"}],
            ),
            make_test_ref(validates=["REQ-100-A"]),
            make_test_result("result-1", status="passed", test_id="test:tests/test_module.py:1"),
        )

        annotate_coverage(graph)

        node = graph.find_by_id("REQ-100")
        rollup: RollupMetrics = node.get_metric("rollup_metrics")

        assert rollup.has_failures is False
        assert rollup.validated == 1

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

        assert rollup.direct_tested == 0
        assert rollup.validated == 0
        assert rollup.has_failures is False
        assert rollup.covered_assertions == 1  # Still covered by CODE
