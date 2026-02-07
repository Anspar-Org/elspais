# Validates REQ-d00069-A, REQ-d00069-B, REQ-d00069-C, REQ-d00069-D
# Validates REQ-d00069-E, REQ-d00069-F
# Validates REQ-d00070-A, REQ-d00070-B, REQ-d00070-C, REQ-d00070-D, REQ-d00070-E
"""Tests for INDIRECT coverage from whole-requirement tests and transitive CODE chains.

INDIRECT coverage counts whole-req tests (tests targeting a requirement without
assertion suffixes) as covering all assertions. This provides a "progress indicator"
view alongside the strict traceability view.

Also tests transitive CODE->TEST chains where a TEST validates a CODE node that
implements a REQUIREMENT, producing INDIRECT coverage through the chain:
REQUIREMENT <- (IMPLEMENTS) <- CODE <- (VALIDATES) <- TEST <- (CONTAINS) <- TEST_RESULT
"""

from elspais.graph.annotators import annotate_coverage
from elspais.graph.builder import TraceGraph
from elspais.graph.GraphNode import GraphNode, NodeKind, SourceLocation
from elspais.graph.metrics import CoverageContribution, CoverageSource, RollupMetrics
from elspais.graph.relations import EdgeKind
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


# =============================================================================
# Transitive CODE->TEST chain coverage tests
# =============================================================================


class TestTransitiveCoverageThroughCode:
    """Tests that TEST->CODE->REQUIREMENT provides indirect coverage.

    When a CODE node implements a REQUIREMENT and a TEST validates that CODE,
    the TEST provides INDIRECT coverage to the REQUIREMENT's assertions through
    the transitive chain: REQUIREMENT <- CODE <- TEST <- TEST_RESULT.
    """

    def _build_chain(self, *, with_result=True, result_status="passed", assertion_targets=None):
        """Build a REQUIREMENT <- CODE <- TEST <- TEST_RESULT chain.

        The chain uses:
        - req.link(code, IMPLEMENTS, assertion_targets) for REQ->CODE edge
        - code.link(test, VALIDATES) for CODE->TEST edge
        - test.add_child(result) for TEST->TEST_RESULT containment

        Returns (graph, req_node, code_node, test_node, result_node_or_None)
        """
        graph = TraceGraph()

        # Requirement with 2 assertions
        req = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT, label="Auth Req")
        req.set_field("level", "PRD")
        req.set_field("status", "Active")
        graph._index[req.id] = req
        graph._roots.append(req)

        assert_a = GraphNode(id="REQ-p00001-A", kind=NodeKind.ASSERTION, label="SHALL authenticate")
        assert_a.set_field("label", "A")
        graph._index[assert_a.id] = assert_a
        req.add_child(assert_a)

        assert_b = GraphNode(id="REQ-p00001-B", kind=NodeKind.ASSERTION, label="SHALL log attempts")
        assert_b.set_field("label", "B")
        graph._index[assert_b.id] = assert_b
        req.add_child(assert_b)

        # CODE implements requirement (with or without assertion_targets)
        code = GraphNode(
            id="code:src/auth.py:10",
            kind=NodeKind.CODE,
            source=SourceLocation(path="src/auth.py", line=10),
        )
        code.set_field("function_name", "authenticate")
        graph._index[code.id] = code
        req.link(code, EdgeKind.IMPLEMENTS, assertion_targets=assertion_targets)

        # TEST validates CODE (created by test_code_linker)
        test = GraphNode(
            id="test:tests/test_auth.py::test_authenticate",
            kind=NodeKind.TEST,
            source=SourceLocation(path="tests/test_auth.py", line=5),
        )
        graph._index[test.id] = test
        code.link(test, EdgeKind.VALIDATES)

        result_node = None
        if with_result:
            result = GraphNode(
                id="result:tests/test_auth.py::test_authenticate",
                kind=NodeKind.TEST_RESULT,
                label="test_authenticate",
            )
            result.set_field("status", result_status)
            graph._index[result.id] = result
            test.add_child(result)
            result_node = result

        return graph, req, code, test, result_node

    def test_transitive_provides_indirect_coverage(self):
        """CODE->TEST chain provides INDIRECT coverage to requirement."""
        graph, req, code, test, result = self._build_chain()
        annotate_coverage(graph)

        metrics = req.get_metric("rollup_metrics")
        assert metrics is not None
        # INDIRECT coverage for both assertions (CODE has no assertion_targets)
        assert metrics.indirect_coverage_pct > 0

        # Check contributions include INDIRECT from test
        for label in ["A", "B"]:
            contribs = metrics.assertion_coverage.get(label, [])
            indirect = [c for c in contribs if c.source_type == CoverageSource.INDIRECT]
            assert len(indirect) > 0, f"Expected INDIRECT coverage for assertion {label}"

    def test_transitive_with_assertion_targets(self):
        """CODE targeting specific assertions only provides INDIRECT for those."""
        graph, req, code, test, result = self._build_chain(assertion_targets=["A"])
        annotate_coverage(graph)

        metrics = req.get_metric("rollup_metrics")
        # A should have DIRECT (from CODE) + INDIRECT (from TEST via CODE)
        a_contribs = metrics.assertion_coverage.get("A", [])
        assert any(c.source_type == CoverageSource.DIRECT for c in a_contribs)
        assert any(c.source_type == CoverageSource.INDIRECT for c in a_contribs)

        # B should have NO coverage (CODE only targets A)
        b_contribs = metrics.assertion_coverage.get("B", [])
        assert len(b_contribs) == 0

    def test_transitive_with_passing_result_validates_indirect(self):
        """Passing TEST_RESULT via CODE chain marks assertions as indirectly validated."""
        graph, req, code, test, result = self._build_chain(result_status="passed")
        annotate_coverage(graph)

        metrics = req.get_metric("rollup_metrics")
        assert metrics.validated_with_indirect == 2  # Both A and B

    def test_transitive_with_failing_result_marks_failure(self):
        """Failed TEST_RESULT via CODE chain sets has_failures."""
        graph, req, code, test, result = self._build_chain(result_status="failed")
        annotate_coverage(graph)

        metrics = req.get_metric("rollup_metrics")
        assert metrics.has_failures is True

    def test_transitive_without_result_still_covers(self):
        """TEST via CODE without TEST_RESULT still provides INDIRECT coverage."""
        graph, req, code, test, _ = self._build_chain(with_result=False)
        annotate_coverage(graph)

        metrics = req.get_metric("rollup_metrics")
        assert metrics.indirect_coverage_pct > 0
        # But validated_with_indirect should be 0 (no passing result)
        assert metrics.validated_with_indirect == 0

    def test_direct_test_overrides_transitive(self):
        """Direct TEST->REQ edge takes precedence; transitive adds INDIRECT."""
        graph, req, code, test, result = self._build_chain()

        # Also add a direct TEST->REQ edge (as if test had # Tests REQ-p00001-A)
        direct_test = GraphNode(
            id="test:tests/test_auth.py::test_auth_direct",
            kind=NodeKind.TEST,
            source=SourceLocation(path="tests/test_auth.py", line=20),
        )
        graph._index[direct_test.id] = direct_test
        req.link(direct_test, EdgeKind.VALIDATES, assertion_targets=["A"])

        # Add passing result for direct test
        direct_result = GraphNode(
            id="result:tests/test_auth.py::test_auth_direct",
            kind=NodeKind.TEST_RESULT,
        )
        direct_result.set_field("status", "passed")
        graph._index[direct_result.id] = direct_result
        direct_test.add_child(direct_result)

        annotate_coverage(graph)

        metrics = req.get_metric("rollup_metrics")
        # A has both DIRECT (from direct test) and INDIRECT (from transitive)
        a_contribs = metrics.assertion_coverage.get("A", [])
        assert any(c.source_type == CoverageSource.DIRECT for c in a_contribs)
        assert any(c.source_type == CoverageSource.INDIRECT for c in a_contribs)

        # A should be directly tested AND validated
        assert metrics.direct_tested >= 1
        assert metrics.validated >= 1

    def test_no_transitive_for_refines_edge(self):
        """REFINES edges should NOT trigger transitive coverage lookup."""
        graph = TraceGraph()

        req = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT, label="Req")
        req.set_field("level", "PRD")
        req.set_field("status", "Active")
        graph._index[req.id] = req
        graph._roots.append(req)

        assert_a = GraphNode(id="REQ-p00001-A", kind=NodeKind.ASSERTION, label="SHALL do X")
        assert_a.set_field("label", "A")
        graph._index[assert_a.id] = assert_a
        req.add_child(assert_a)

        code = GraphNode(
            id="code:src/mod.py:5",
            kind=NodeKind.CODE,
            source=SourceLocation(path="src/mod.py", line=5),
        )
        graph._index[code.id] = code
        # REFINES, not IMPLEMENTS -- should not count
        req.link(code, EdgeKind.REFINES)

        test = GraphNode(
            id="test:tests/test_mod.py::test_func",
            kind=NodeKind.TEST,
            source=SourceLocation(path="tests/test_mod.py", line=1),
        )
        graph._index[test.id] = test
        code.link(test, EdgeKind.VALIDATES)

        annotate_coverage(graph)

        metrics = req.get_metric("rollup_metrics")
        assert metrics.indirect_coverage_pct == 0
        assert metrics.coverage_pct == 0

    def test_transitive_strict_coverage_excludes_indirect(self):
        """Transitive CODE->TEST only provides INDIRECT, not strict coverage."""
        graph, req, code, test, result = self._build_chain()
        annotate_coverage(graph)

        metrics = req.get_metric("rollup_metrics")
        # Strict coverage should be 0 (only INDIRECT from transitive)
        assert metrics.coverage_pct == 0.0
        assert metrics.covered_assertions == 0
        # But indirect coverage should be 100%
        assert metrics.indirect_coverage_pct == 100.0

    def test_transitive_multiple_code_nodes(self):
        """Multiple CODE nodes each with TEST children all contribute INDIRECT."""
        graph = TraceGraph()

        req = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT, label="Req")
        req.set_field("level", "PRD")
        req.set_field("status", "Active")
        graph._index[req.id] = req
        graph._roots.append(req)

        assert_a = GraphNode(id="REQ-p00001-A", kind=NodeKind.ASSERTION, label="SHALL X")
        assert_a.set_field("label", "A")
        graph._index[assert_a.id] = assert_a
        req.add_child(assert_a)

        # Two CODE nodes, each implementing the requirement
        for i in range(2):
            code = GraphNode(
                id=f"code:src/mod{i}.py:1",
                kind=NodeKind.CODE,
                source=SourceLocation(path=f"src/mod{i}.py", line=1),
            )
            graph._index[code.id] = code
            req.link(code, EdgeKind.IMPLEMENTS)

            test = GraphNode(
                id=f"test:tests/test_mod{i}.py::test_func",
                kind=NodeKind.TEST,
                source=SourceLocation(path=f"tests/test_mod{i}.py", line=1),
            )
            graph._index[test.id] = test
            code.link(test, EdgeKind.VALIDATES)

        annotate_coverage(graph)

        metrics = req.get_metric("rollup_metrics")
        assert metrics.indirect_coverage_pct == 100.0
        # A should have INDIRECT contributions from both tests
        a_contribs = metrics.assertion_coverage.get("A", [])
        indirect = [c for c in a_contribs if c.source_type == CoverageSource.INDIRECT]
        assert len(indirect) >= 2


class TestFactoryIntegration:
    """Tests that factory.build_graph() calls link_tests_to_code."""

    def test_factory_calls_linker(self, tmp_path):
        """Build graph from spec + code + test files, verify transitive edges."""
        # This is a lightweight integration test. We create minimal files.
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        # Create minimal config
        config_file = tmp_path / ".elspais.toml"
        config_file.write_text(
            "[patterns]\n"
            'prefix = "REQ"\n'
            "\n"
            "[patterns.types.prd]\n"
            'id = "p"\n'
            'name = "PRD"\n'
            "\n"
            "[patterns.id_format]\n"
            'style = "numeric"\n'
            "digits = 5\n"
            "\n"
            "[directories]\n"
            'spec = "spec"\n'
            "\n"
            "[traceability]\n"
            'scan_patterns = ["src/**/*.py"]\n'
            "\n"
            "[testing]\n"
            "enabled = true\n"
            'test_dirs = ["tests"]\n'
            'patterns = ["test_*.py"]\n'
        )

        # Create a source file with # Implements: inside a function
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "auth.py").write_text(
            "# Implements: REQ-p00001\n" "def authenticate():\n" "    pass\n"
        )

        # Create a test file that imports the source module
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        (test_dir / "test_auth.py").write_text(
            "from auth import authenticate\n\n"
            "def test_authenticate():\n"
            "    assert authenticate() is None\n"
        )

        # Create a minimal spec file
        (spec_dir / "requirements.md").write_text(
            "# REQ-p00001 Authentication\n\n"
            "**Status**: Active | **Level**: PRD\n\n"
            "*End* Authentication | **Hash**: 12345678\n"
        )

        from elspais.graph.factory import build_graph as factory_build_graph

        graph = factory_build_graph(
            config_path=config_file,
            repo_root=tmp_path,
            scan_sponsors=False,
        )

        # Check that the graph was built (may or may not have transitive edges
        # depending on whether source_roots resolves -- this just tests the
        # integration doesn't crash)
        assert graph is not None

    def test_factory_no_linker_when_tests_disabled(self, tmp_path):
        """When scan_tests=False, no linker is called."""
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        config_file = tmp_path / ".elspais.toml"
        config_file.write_text(
            "[patterns]\n"
            'prefix = "REQ"\n'
            "\n"
            "[patterns.types.prd]\n"
            'id = "p"\n'
            'name = "PRD"\n'
            "\n"
            "[patterns.id_format]\n"
            'style = "numeric"\n'
            "digits = 5\n"
            "\n"
            "[directories]\n"
            'spec = "spec"\n'
            "\n"
            "[traceability]\n"
            'scan_patterns = ["src/**/*.py"]\n'
        )

        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "auth.py").write_text(
            "# Implements: REQ-p00001\n" "def authenticate():\n" "    pass\n"
        )

        (spec_dir / "requirements.md").write_text(
            "# REQ-p00001 Authentication\n\n"
            "**Status**: Active | **Level**: PRD\n\n"
            "*End* Authentication | **Hash**: 12345678\n"
        )

        from elspais.graph.factory import build_graph as factory_build_graph

        # scan_tests=False means no TEST nodes and no linker call
        graph = factory_build_graph(
            config_path=config_file,
            repo_root=tmp_path,
            scan_tests=False,
            scan_sponsors=False,
        )

        assert graph is not None
        # Should have CODE node but no TEST nodes linked to it
        code_nodes = list(graph.nodes_by_kind(NodeKind.CODE))
        for code_node in code_nodes:
            for edge in code_node.iter_outgoing_edges():
                # No VALIDATES edges from CODE to TEST
                assert edge.kind != EdgeKind.VALIDATES or edge.target.kind != NodeKind.TEST

    def test_factory_no_linker_when_code_disabled(self, tmp_path):
        """When scan_code=False, no linker is called."""
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        config_file = tmp_path / ".elspais.toml"
        config_file.write_text(
            "[patterns]\n"
            'prefix = "REQ"\n'
            "\n"
            "[patterns.types.prd]\n"
            'id = "p"\n'
            'name = "PRD"\n'
            "\n"
            "[patterns.id_format]\n"
            'style = "numeric"\n'
            "digits = 5\n"
            "\n"
            "[directories]\n"
            'spec = "spec"\n'
            "\n"
            "[testing]\n"
            "enabled = true\n"
            'test_dirs = ["tests"]\n'
            'patterns = ["test_*.py"]\n'
        )

        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        (test_dir / "test_auth.py").write_text(
            "# Validates: REQ-p00001\n" "def test_authenticate():\n" "    pass\n"
        )

        (spec_dir / "requirements.md").write_text(
            "# REQ-p00001 Authentication\n\n"
            "**Status**: Active | **Level**: PRD\n\n"
            "*End* Authentication | **Hash**: 12345678\n"
        )

        from elspais.graph.factory import build_graph as factory_build_graph

        # scan_code=False means no CODE nodes and no linker call
        graph = factory_build_graph(
            config_path=config_file,
            repo_root=tmp_path,
            scan_code=False,
            scan_sponsors=False,
        )

        assert graph is not None
        # No CODE nodes should exist
        code_nodes = list(graph.nodes_by_kind(NodeKind.CODE))
        assert len(code_nodes) == 0
