# Validates REQ-d00069-A, REQ-d00069-B, REQ-d00069-C, REQ-d00069-D
# Validates REQ-d00069-E, REQ-d00069-F
# Validates REQ-d00070-A, REQ-d00070-B, REQ-d00070-C, REQ-d00070-D, REQ-d00070-E
"""Tests for INDIRECT coverage from whole-requirement tests.

INDIRECT coverage counts whole-req tests (tests targeting a requirement without
assertion suffixes) as covering all assertions. This provides a "progress indicator"
view alongside the strict traceability view.
"""

from elspais.graph.annotators import annotate_coverage
from elspais.graph.metrics import CoverageContribution, CoverageSource, RollupMetrics
from tests.core.graph_test_helpers import (
    build_graph,
    make_requirement,
    make_test_ref,
    make_test_result,
)


class TestIndirectCoverageSource:
    """Tests for CoverageSource.INDIRECT enum value.

    Validates REQ-d00069-A: INDIRECT enum exists in CoverageSource.
    """

    def test_REQ_d00069_A_indirect_enum_value(self):
        """INDIRECT enum value exists and has correct string value."""
        assert CoverageSource.INDIRECT.value == "indirect"

    def test_REQ_d00069_A_indirect_is_distinct(self):
        """INDIRECT is distinct from other coverage sources."""
        values = {s.value for s in CoverageSource}
        assert "indirect" in values
        assert len(values) == 4  # DIRECT, EXPLICIT, INFERRED, INDIRECT


class TestIndirectCoverageContributions:
    """Tests for INDIRECT contributions from whole-req tests.

    Validates REQ-d00069-B: Whole-req tests emit INDIRECT for all assertions.
    """

    def test_REQ_d00069_B_whole_req_test_adds_indirect(self):
        """Whole-req test (no assertion suffix) adds INDIRECT for all assertions."""
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
            make_test_ref(
                validates=["REQ-100"],  # Whole-req: no assertion suffix
                source_path="tests/test_whole.py",
            ),
        )

        annotate_coverage(graph)

        node = graph.find_by_id("REQ-100")
        rollup: RollupMetrics = node.get_metric("rollup_metrics")

        # INDIRECT contributions for all 3 assertions
        assert "A" in rollup.assertion_coverage
        assert "B" in rollup.assertion_coverage
        assert "C" in rollup.assertion_coverage

        # All should be INDIRECT source type
        for label in ["A", "B", "C"]:
            sources = [c.source_type for c in rollup.assertion_coverage[label]]
            assert CoverageSource.INDIRECT in sources

    def test_REQ_d00069_B_whole_req_test_zero_strict_coverage(self):
        """Whole-req test gives 0% strict coverage (INDIRECT excluded)."""
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
                validates=["REQ-100"],
                source_path="tests/test_whole.py",
            ),
        )

        annotate_coverage(graph)

        node = graph.find_by_id("REQ-100")
        rollup: RollupMetrics = node.get_metric("rollup_metrics")

        # Strict coverage excludes INDIRECT
        assert rollup.coverage_pct == 0.0
        assert rollup.covered_assertions == 0

        # Indirect coverage includes INDIRECT
        assert rollup.indirect_coverage_pct == 100.0


class TestDualCoverageMetrics:
    """Tests for dual coverage percentages (strict vs indirect).

    Validates REQ-d00069-C: coverage_pct excludes INDIRECT, indirect_coverage_pct includes it.
    """

    def test_REQ_d00069_C_strict_excludes_indirect(self):
        """coverage_pct (strict) does NOT include INDIRECT contributions."""
        graph = build_graph(
            make_requirement(
                "REQ-100",
                level="PRD",
                assertions=[
                    {"label": "A", "text": "Assertion A"},
                    {"label": "B", "text": "Assertion B"},
                ],
            ),
            make_test_ref(validates=["REQ-100"], source_path="tests/test_whole.py"),
        )

        annotate_coverage(graph)

        node = graph.find_by_id("REQ-100")
        rollup: RollupMetrics = node.get_metric("rollup_metrics")

        assert rollup.coverage_pct == 0.0
        assert rollup.indirect_coverage_pct == 100.0

    def test_REQ_d00069_C_both_equal_without_indirect(self):
        """When no whole-req tests, both metrics are equal."""
        graph = build_graph(
            make_requirement(
                "REQ-100",
                level="PRD",
                assertions=[
                    {"label": "A", "text": "Assertion A"},
                    {"label": "B", "text": "Assertion B"},
                ],
            ),
            make_test_ref(validates=["REQ-100-A"], source_path="tests/test_a.py"),
        )

        annotate_coverage(graph)

        node = graph.find_by_id("REQ-100")
        rollup: RollupMetrics = node.get_metric("rollup_metrics")

        assert rollup.coverage_pct == 50.0
        assert rollup.indirect_coverage_pct == 50.0  # Same: no INDIRECT source


class TestValidatedWithIndirect:
    """Tests for validated_with_indirect metric.

    Validates REQ-d00069-D: validated_with_indirect includes whole-req passing tests.
    """

    def test_REQ_d00069_D_passing_whole_req_validates_all(self):
        """Passing whole-req test validates all assertions indirectly."""
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
            make_test_ref(validates=["REQ-100"], source_path="tests/test_whole.py"),
            make_test_result(
                "result-whole",
                status="passed",
                test_id="test:tests/test_whole.py:1",
            ),
        )

        annotate_coverage(graph)

        node = graph.find_by_id("REQ-100")
        rollup: RollupMetrics = node.get_metric("rollup_metrics")

        assert rollup.validated == 0  # Strict: no assertion-targeted passing tests
        assert rollup.validated_with_indirect == 3  # All 3 assertions

    def test_REQ_d00069_D_mixed_targeted_and_whole(self):
        """validated_with_indirect unions targeted and whole-req validations."""
        graph = build_graph(
            make_requirement(
                "REQ-100",
                level="PRD",
                assertions=[
                    {"label": "A", "text": "Assertion A"},
                    {"label": "B", "text": "Assertion B"},
                ],
            ),
            make_test_ref(validates=["REQ-100-A"], source_path="tests/test_a.py"),
            make_test_ref(validates=["REQ-100"], source_path="tests/test_whole.py"),
            make_test_result("result-a", status="passed", test_id="test:tests/test_a.py:1"),
            make_test_result("result-whole", status="passed", test_id="test:tests/test_whole.py:1"),
        )

        annotate_coverage(graph)

        node = graph.find_by_id("REQ-100")
        rollup: RollupMetrics = node.get_metric("rollup_metrics")

        assert rollup.validated == 1  # Only A via targeted test
        assert rollup.validated_with_indirect == 2  # A + B (union)


class TestEdgeCase1MixedDirectIndirect:
    """Edge case 1: Mixed direct + indirect coverage.

    REQ has 11 assertions. 3 have direct tests. 1 whole-req test also exists.
    Strict: 3/11=27%. Indirect: 11/11=100%.

    Validates REQ-d00069-E: Mixed direct + indirect edge case.
    """

    def test_REQ_d00069_E_mixed_direct_indirect(self):
        """3 assertion-targeted + 1 whole-req test: strict 27% vs indirect 100%."""
        assertions = [{"label": chr(65 + i), "text": f"Assertion {chr(65 + i)}"} for i in range(11)]

        graph = build_graph(
            make_requirement("REQ-100", level="PRD", assertions=assertions),
            # 3 assertion-targeted tests
            make_test_ref(validates=["REQ-100-A"], source_path="tests/test_a.py"),
            make_test_ref(validates=["REQ-100-B"], source_path="tests/test_b.py"),
            make_test_ref(validates=["REQ-100-C"], source_path="tests/test_c.py"),
            # 1 whole-req test
            make_test_ref(validates=["REQ-100"], source_path="tests/test_whole.py"),
        )

        annotate_coverage(graph)

        node = graph.find_by_id("REQ-100")
        rollup: RollupMetrics = node.get_metric("rollup_metrics")

        # Strict: only 3 direct assertions covered
        assert rollup.covered_assertions == 3
        assert rollup.direct_covered == 3
        assert abs(rollup.coverage_pct - (3 / 11 * 100)) < 0.1

        # Indirect: all 11 covered (direct 3 + indirect 8, union = 11)
        assert rollup.indirect_coverage_pct == 100.0


class TestEdgeCase2MultipleTestsOneFailing:
    """Edge case 2: Multiple tests on same assertion, one failing.

    Assertion A targeted by 3 tests: test1 passes, test2 passes, test3 fails.
    has_failures=True, assertion A is validated (at least one pass).

    Validates REQ-d00069-F: has_failures same in both modes.
    """

    def test_REQ_d00069_F_multiple_tests_mixed_results(self):
        """Assertion validated if at least one test passes; has_failures true."""
        graph = build_graph(
            make_requirement(
                "REQ-100",
                level="PRD",
                assertions=[{"label": "A", "text": "Assertion A"}],
            ),
            make_test_ref(validates=["REQ-100-A"], source_path="tests/test_1.py"),
            make_test_ref(validates=["REQ-100-A"], source_path="tests/test_2.py"),
            make_test_ref(validates=["REQ-100-A"], source_path="tests/test_3.py"),
            make_test_result("r1", status="passed", test_id="test:tests/test_1.py:1"),
            make_test_result("r2", status="passed", test_id="test:tests/test_2.py:1"),
            make_test_result("r3", status="failed", test_id="test:tests/test_3.py:1"),
        )

        annotate_coverage(graph)

        node = graph.find_by_id("REQ-100")
        rollup: RollupMetrics = node.get_metric("rollup_metrics")

        assert rollup.validated == 1  # A is validated (at least one pass)
        assert rollup.has_failures is True  # r3 failed
        assert rollup.coverage_pct == 100.0  # A is directly covered


class TestEdgeCase3WholeReqMixedResults:
    """Edge case 3: Whole-req test, mixed results.

    REQ has 5 assertions. Whole-req test1 passes, whole-req test2 fails.
    Strict: 0/5=0%. Indirect: 5/5=100%. has_failures=True.

    Validates REQ-d00070-A: Whole-req mixed results.
    """

    def test_REQ_d00070_A_whole_req_mixed_results(self):
        """Whole-req tests: one pass + one fail. Indirect 100%, strict 0%."""
        assertions = [{"label": chr(65 + i), "text": f"Assertion {chr(65 + i)}"} for i in range(5)]

        graph = build_graph(
            make_requirement("REQ-100", level="PRD", assertions=assertions),
            make_test_ref(validates=["REQ-100"], source_path="tests/test_pass.py"),
            make_test_ref(validates=["REQ-100"], source_path="tests/test_fail.py"),
            make_test_result("r-pass", status="passed", test_id="test:tests/test_pass.py:1"),
            make_test_result("r-fail", status="failed", test_id="test:tests/test_fail.py:1"),
        )

        annotate_coverage(graph)

        node = graph.find_by_id("REQ-100")
        rollup: RollupMetrics = node.get_metric("rollup_metrics")

        assert rollup.coverage_pct == 0.0  # Strict: none
        assert rollup.indirect_coverage_pct == 100.0  # Indirect: full
        assert rollup.has_failures is True
        assert rollup.validated_with_indirect == 5  # All 5 validated indirectly


class TestEdgeCase4NoWholeReqTest:
    """Edge case 4: No whole-req test, only assertion-specific.

    REQ has 5 assertions. Tests target A, B, C (all pass). D, E untested.
    Both modes: 3/5=60% partial. Indirect mode only affects empty assertion_targets.

    Validates REQ-d00070-B: No whole-req test = both modes identical.
    """

    def test_REQ_d00070_B_no_whole_req_test(self):
        """Without whole-req tests, strict and indirect coverage are equal."""
        assertions = [{"label": chr(65 + i), "text": f"Assertion {chr(65 + i)}"} for i in range(5)]

        graph = build_graph(
            make_requirement("REQ-100", level="PRD", assertions=assertions),
            make_test_ref(validates=["REQ-100-A"], source_path="tests/test_a.py"),
            make_test_ref(validates=["REQ-100-B"], source_path="tests/test_b.py"),
            make_test_ref(validates=["REQ-100-C"], source_path="tests/test_c.py"),
        )

        annotate_coverage(graph)

        node = graph.find_by_id("REQ-100")
        rollup: RollupMetrics = node.get_metric("rollup_metrics")

        assert rollup.coverage_pct == 60.0
        assert rollup.indirect_coverage_pct == 60.0  # Same: no INDIRECT
        assert rollup.covered_assertions == 3


class TestRollupMetricsIndirectDefaults:
    """Tests for RollupMetrics INDIRECT field defaults.

    Validates REQ-d00070-C: Default values for new indirect fields.
    """

    def test_REQ_d00070_C_default_indirect_fields(self):
        """New indirect fields default to zero."""
        metrics = RollupMetrics()
        assert metrics.indirect_coverage_pct == 0.0
        assert metrics.validated_with_indirect == 0

    def test_REQ_d00070_C_finalize_with_indirect_contributions(self):
        """Finalize correctly computes indirect_coverage_pct from INDIRECT contributions."""
        metrics = RollupMetrics(total_assertions=4)
        # A and B covered by INDIRECT
        metrics.add_contribution(CoverageContribution("test:1", CoverageSource.INDIRECT, "A"))
        metrics.add_contribution(CoverageContribution("test:1", CoverageSource.INDIRECT, "B"))
        # C covered by DIRECT
        metrics.add_contribution(CoverageContribution("test:2", CoverageSource.DIRECT, "C"))

        metrics.finalize()

        # Strict: only C (DIRECT)
        assert metrics.covered_assertions == 1
        assert metrics.coverage_pct == 25.0

        # Indirect: A + B (INDIRECT) + C (DIRECT) = 3/4
        assert metrics.indirect_coverage_pct == 75.0


class TestIntegrationWholeReqTest:
    """Integration test: whole-req test -> coverage_pct=0, indirect_coverage_pct=100.

    Validates REQ-d00070-D: End-to-end integration of indirect coverage.
    """

    def test_REQ_d00070_D_integration_whole_req(self):
        """End-to-end: whole-req test produces 0% strict, 100% indirect."""
        graph = build_graph(
            make_requirement(
                "REQ-100",
                level="PRD",
                assertions=[
                    {"label": "A", "text": "System shall do A"},
                    {"label": "B", "text": "System shall do B"},
                    {"label": "C", "text": "System shall do C"},
                ],
            ),
            make_test_ref(validates=["REQ-100"], source_path="tests/test_whole.py"),
            make_test_result("result-whole", status="passed", test_id="test:tests/test_whole.py:1"),
        )

        annotate_coverage(graph)

        node = graph.find_by_id("REQ-100")
        rollup: RollupMetrics = node.get_metric("rollup_metrics")

        # Strict: 0% (INDIRECT excluded)
        assert rollup.coverage_pct == 0.0
        assert rollup.covered_assertions == 0
        assert node.get_metric("coverage_pct") == 0.0

        # Indirect: 100%
        assert rollup.indirect_coverage_pct == 100.0

        # Validation
        assert rollup.validated == 0  # No targeted tests pass
        assert rollup.validated_with_indirect == 3  # All validated indirectly
        assert rollup.has_failures is False


class TestIndirectWithExistingSources:
    """Tests that INDIRECT works alongside other coverage sources.

    Validates REQ-d00070-E: INDIRECT doesn't interfere with existing sources.
    """

    def test_REQ_d00070_E_indirect_with_inferred(self):
        """INDIRECT from tests and INFERRED from reqs work independently."""
        graph = build_graph(
            make_requirement(
                "REQ-100",
                level="PRD",
                assertions=[
                    {"label": "A", "text": "Assertion A"},
                    {"label": "B", "text": "Assertion B"},
                ],
            ),
            # Child REQ implements parent (all assertions = INFERRED)
            make_requirement("REQ-020", level="OPS", implements=["REQ-100"]),
            # Whole-req test (all assertions = INDIRECT)
            make_test_ref(validates=["REQ-100"], source_path="tests/test_whole.py"),
        )

        annotate_coverage(graph)

        node = graph.find_by_id("REQ-100")
        rollup: RollupMetrics = node.get_metric("rollup_metrics")

        # INFERRED gives strict coverage (100%)
        assert rollup.coverage_pct == 100.0
        assert rollup.inferred_covered == 2

        # Indirect also 100% (union of INFERRED + INDIRECT)
        assert rollup.indirect_coverage_pct == 100.0

        # Both sources present in assertion_coverage
        a_sources = {c.source_type for c in rollup.assertion_coverage["A"]}
        assert CoverageSource.INFERRED in a_sources
        assert CoverageSource.INDIRECT in a_sources
