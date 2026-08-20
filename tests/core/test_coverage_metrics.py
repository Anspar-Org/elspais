# Validates REQ-p00006-B
"""Tests for Coverage Metrics (RollupMetrics, annotate_coverage)."""

import pytest

from elspais.graph.aggregation import (
    MEASURES,
    absolute_tier,
    covered_labels,
    measure_by_label,
)
from elspais.graph.annotators import annotate_coverage
from elspais.graph.GraphNode import NodeKind
from elspais.graph.metrics import CoverageContribution, CoverageSource, RollupMetrics
from tests.core.graph_test_helpers import (
    build_graph,
    make_code_ref,
    make_requirement,
    make_test_ref,
)


class TestRollupMetrics:
    """Tests for RollupMetrics dataclass."""

    # Verifies: REQ-d00086-B
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

    # Verifies: REQ-d00069-D
    def test_finalize_computes_aggregates(self):
        """Finalize computes aggregate counts and percentage."""
        metrics = RollupMetrics(total_assertions=4)
        metrics.add_contribution(CoverageContribution("test:1", CoverageSource.DIRECT, "A"))
        metrics.add_contribution(CoverageContribution("req:2", CoverageSource.EXPLICIT, "B"))
        # C and D have no coverage

        metrics.finalize()

        # implemented.immediate_direct = DIRECT + EXPLICIT = {A, B} = 2
        assert metrics.implemented.immediate_direct == 2
        # implemented.covered = DIRECT + EXPLICIT + INFERRED = {A, B} = 2
        assert metrics.implemented.covered == 2
        # No inferred: indirect - direct == 0
        assert metrics.implemented.covered - metrics.implemented.immediate_direct == 0
        # 2/4 = 50%
        assert metrics.implemented.covered_pct == 50.0

    # Verifies: REQ-d00069-D
    def test_finalize_handles_zero_assertions(self):
        """Finalize handles zero assertions gracefully."""
        metrics = RollupMetrics(total_assertions=0)

        metrics.finalize()

        assert metrics.implemented.covered_pct == 0.0

    # Verifies: REQ-d00086-B
    def test_multiple_contributors_same_assertion(self):
        """Multiple contributors to same assertion only count once."""
        metrics = RollupMetrics(total_assertions=1)
        # Two different tests validate same assertion
        metrics.add_contribution(CoverageContribution("test:1", CoverageSource.DIRECT, "A"))
        metrics.add_contribution(CoverageContribution("test:2", CoverageSource.DIRECT, "A"))

        metrics.finalize()

        assert metrics.implemented.covered == 1  # Only one assertion covered
        assert metrics.implemented.immediate_direct == 1
        assert len(metrics.assertion_coverage["A"]) == 2  # But two contributors


class TestAnnotateCoverageDirect:
    """Tests for direct coverage (TEST/CODE -> assertion)."""

    # Verifies: REQ-d00086-B, REQ-d00084-D
    def test_direct_coverage_from_test(self):
        """TEST node verifies assertion -> `tested`, NOT `implemented`.

        Corrected over-counting (REQ-d00084-D): a test that Verifies an
        assertion is test evidence, so it credits the `tested` dimension. It
        used to also inflate `implemented` — implemented is now CODE evidence
        only.
        """
        # Build: REQ-100 with assertion A, verified by a test (no code)
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
        # No implementing code -> implemented stays empty.
        assert metrics.implemented.immediate_direct == 0
        assert metrics.implemented.covered == 0
        # Test evidence lands in `tested`.
        assert metrics.tested.immediate_direct == 1
        assert metrics.tested.covered == 1
        assert metrics.tested.covered_pct == 100.0

    # Verifies: REQ-d00086-B
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
        assert metrics.implemented.immediate_direct == 1
        assert metrics.implemented.covered_pct == 100.0


class TestAnnotateCoverageExplicit:
    """Tests for explicit coverage (REQ -> specific assertions)."""

    # Verifies: REQ-d00086-B
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
        assert metrics.implemented.immediate_direct == 1
        assert metrics.implemented.covered == 1  # Only B is covered
        # No inferred: indirect - direct == 0
        assert metrics.implemented.covered - metrics.implemented.immediate_direct == 0
        assert metrics.implemented.covered_pct == 50.0

        # Verify it's assertion B that's covered
        assert "B" in metrics.assertion_coverage
        assert metrics.assertion_coverage["B"][0].source_type == CoverageSource.EXPLICIT


class TestAnnotateCoverageInferred:
    """Tests for inferred coverage (REQ -> parent REQ)."""

    # Verifies: REQ-d00086-B
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
        assert metrics.implemented.covered == 2  # Both A and B covered (inferred)
        assert metrics.implemented.immediate_direct == 0  # No assertion-targeted coverage
        # All inferred: indirect - direct == 2
        assert metrics.implemented.covered - metrics.implemented.immediate_direct == 2
        assert metrics.implemented.covered_pct == 100.0


class TestAnnotateCoverageRefines:
    """Tests for REFINES edge coverage conduction (REQ-d00069-J)."""

    # Verifies: REQ-d00069-J
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
        assert metrics.implemented.covered == 0  # REFINES doesn't count
        assert metrics.implemented.covered_pct == 0.0

    # Verifies: REQ-d00069-J
    def test_a_refines_chain_conducts_the_mean_of_means_at_every_level(self):
        """A four-level `Refines:` chain conducts a mean of means, not a flat figure.

        Chain (each link an assertion-targeted `Refines:` naming the A of the
        level above): REQ-002 -> REQ-001-A -> REQ-010-A -> REQ-100-A. Every
        requirement has assertions A and B; only REQ-002's two assertions carry
        immediate direct evidence, from one `Implements:` naming them both.

        Derived by hand from REQ-d00069-J -- "the value conducted is the mean,
        in that measure, of the contributing requirements' own coverage, a
        requirement's coverage being the mean over its assertions", an
        assertion's coverage in a measure being the greater of what is attached
        to it and what is conducted into it:

          REQ-002 own direct = mean(A=1.0, B=1.0)          = 1.0
          -> conducted into REQ-001-A (the only assertion its citation names)
          REQ-001 own direct = mean(A=max(0,1.0), B=0)     = 0.5
          -> conducted into REQ-010-A
          REQ-010 own direct = mean(A=max(0,0.5), B=0)     = 0.25
          -> conducted into REQ-100-A

        The halving at each level is the mean-over-assertions step. A flattened
        walk (crediting the top with the chain's leaf evidence directly) would
        read 1.0 at every level; a double-counting one would exceed 1.0.
        """
        graph = build_graph(
            make_requirement(
                "REQ-100",
                level="PRD",
                assertions=[{"label": "A", "text": "a"}, {"label": "B", "text": "b"}],
            ),
            make_requirement(
                "REQ-010",
                level="OPS",
                refines=["REQ-100-A"],
                assertions=[{"label": "A", "text": "a"}, {"label": "B", "text": "b"}],
            ),
            make_requirement(
                "REQ-001",
                level="DEV",
                refines=["REQ-010-A"],
                assertions=[{"label": "A", "text": "a"}, {"label": "B", "text": "b"}],
            ),
            make_requirement(
                "REQ-002",
                level="DEV",
                refines=["REQ-001-A"],
                assertions=[{"label": "A", "text": "a"}, {"label": "B", "text": "b"}],
            ),
            make_code_ref(implements=["REQ-002-A", "REQ-002-B"], source_path="src/leaf.py"),
        )

        annotate_coverage(graph)

        conducted = {}
        for req_id in ("REQ-100", "REQ-010", "REQ-001", "REQ-002"):
            dim = graph.find_by_id(req_id).get_metric("rollup_metrics").implemented
            conducted[req_id] = dict(dim.rolled_direct_by_label)
            # Direct conducts into direct only, so nothing lands in the rolled
            # INDIRECT measure -- no measure is composed of another.
            assert dict(dim.rolled_indirect_by_label) == {}, req_id

        assert conducted["REQ-001"] == pytest.approx({"A": 1.0})
        assert conducted["REQ-010"] == pytest.approx({"A": 0.5})
        assert conducted["REQ-100"] == pytest.approx({"A": 0.25})
        # The leaf is where the evidence is attached; nothing refines it.
        assert conducted["REQ-002"] == {}

    # Verifies: REQ-d00069-J
    def test_conduction_round_a_cycle_does_not_depend_on_annotation_order(self):
        """The conducted value is a property of the graph, not of where the walk began.

        REQ-d00069-J defines what is conducted as a mean over the graph, so two
        builds of the SAME graph must agree whatever order the requirements are
        annotated in. REQ-001 and REQ-002 refine each other's A, forming a
        cycle; REQ-001's own assertions carry immediate direct evidence.

        The exact figures below reflect how the walk degrades a cycle (it
        refuses to re-enter a requirement already on its path and conducts 0 for
        it), which no assertion legislates -- what REQ-d00069-J does bind is
        that one graph yields one answer. Both are asserted: cross-order
        equality alone would also hold if both orders were equally wrong.
        """

        def build(reversed_order: bool):
            first = make_requirement(
                "REQ-001",
                level="DEV",
                refines=["REQ-002-A"],
                assertions=[{"label": "A", "text": "a"}, {"label": "B", "text": "b"}],
            )
            second = make_requirement(
                "REQ-002",
                level="DEV",
                refines=["REQ-001-A"],
                assertions=[{"label": "A", "text": "a"}, {"label": "B", "text": "b"}],
            )
            reqs = [second, first] if reversed_order else [first, second]
            graph = build_graph(
                *reqs,
                make_code_ref(implements=["REQ-001-A", "REQ-001-B"], source_path="src/one.py"),
            )
            annotate_coverage(graph)
            return graph

        forward = build(reversed_order=False)
        backward = build(reversed_order=True)

        # Guard the lever: if the two builds ever iterate requirements in the
        # same order, this test stops testing anything at all.
        def order_of(graph):
            return [n.id for n in graph.nodes_by_kind(NodeKind.REQUIREMENT)]

        assert order_of(forward) == ["REQ-001", "REQ-002"]
        assert order_of(backward) == ["REQ-002", "REQ-001"]

        def conducted(graph):
            return {
                req_id: (
                    dict(
                        graph.find_by_id(req_id)
                        .get_metric("rollup_metrics")
                        .implemented.rolled_direct_by_label
                    ),
                    dict(
                        graph.find_by_id(req_id)
                        .get_metric("rollup_metrics")
                        .implemented.rolled_indirect_by_label
                    ),
                )
                for req_id in ("REQ-001", "REQ-002")
            }

        assert conducted(forward) == conducted(backward)
        assert conducted(forward) == {
            "REQ-001": ({"A": 0.5}, {}),
            "REQ-002": ({"A": 1.0}, {}),
        }


class TestImplementedExcludesTestVerifies:
    """A test that Verifies an assertion must NOT inflate `implemented`.

    Implemented = CODE evidence only (Implements refs, conducted, or inherited)
    per REQ-d00084-D. A `Verifies:` reference is TEST evidence: it populates the
    `tested` dimension, never `implemented`. This keeps the Implemented-vs-Tested
    distinction that REQ-d00258-K rests on. (Regression: test Verifies used to
    leak into implemented via CoverageSource.DIRECT.)
    """

    # Verifies: REQ-d00084-D
    def test_verifies_alone_does_not_imply_implemented(self):
        """A test Verifies with NO implementing code -> implemented == 0, tested == 1."""
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
        # No implementing code -> implemented is empty.
        assert metrics.implemented.immediate_direct == 0
        assert metrics.implemented.covered == 0
        # The test evidence lands in the `tested` dimension instead.
        assert metrics.tested.immediate_direct == 1
        assert metrics.tested.covered == 1

    # Verifies: REQ-d00084-D
    def test_code_implements_gives_implemented(self):
        """CODE Implements -> implemented credited (the positive control)."""
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

        assert metrics.implemented.immediate_direct == 1
        assert metrics.implemented.covered == 1
        # No test evidence -> tested empty.
        assert metrics.tested.immediate_direct == 0

    # Verifies: REQ-d00084-D
    def test_code_implemented_stays_credited_when_also_tested(self):
        """CODE Implements + TEST Verifies the same assertion.

        The implemented credit comes from the CODE Implements edge and must
        survive alongside a verifying test; the test adds `tested`, not a second
        (or inflated) implemented credit.
        """
        graph = build_graph(
            make_requirement(
                "REQ-100",
                level="PRD",
                assertions=[{"label": "A", "text": "The system shall..."}],
            ),
            make_code_ref(implements=["REQ-100-A"]),
            make_test_ref(verifies=["REQ-100-A"]),
        )

        annotate_coverage(graph)

        node = graph.find_by_id("REQ-100")
        metrics: RollupMetrics = node.get_metric("rollup_metrics")

        # Implemented credited from CODE (unchanged by the presence of a test).
        assert metrics.implemented.immediate_direct == 1
        assert metrics.implemented.covered == 1
        # Tested credited from the verifying test.
        assert metrics.tested.immediate_direct == 1


class TestAnnotateCoverageMixed:
    """Tests for mixed coverage sources."""

    # Verifies: REQ-d00086-B, REQ-d00084-D
    def test_mixed_coverage_sources(self):
        """Multiple coverage sources on different assertions.

        Corrected over-counting (REQ-d00084-D): assertion A is only *tested*
        (a Verifies with no code), so it no longer counts toward `implemented`.
        Implemented now reflects the CODE/REQ evidence for B (explicit) and C
        (code) only.
        """
        # REQ-100 has A, B, C, D
        # - A: verified by TEST -> `tested`, NOT `implemented`
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
            make_test_ref(verifies=["REQ-100-A"]),  # A - tested only (not implemented)
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
        # implemented.immediate_direct = DIRECT(code C) + EXPLICIT(req B) = {B, C} = 2
        # (A is test-only -> not implemented)
        assert metrics.implemented.immediate_direct == 2
        assert metrics.implemented.covered == 2
        # No inferred: indirect - direct == 0
        assert metrics.implemented.covered - metrics.implemented.immediate_direct == 0
        assert metrics.implemented.covered_pct == 50.0
        # A is credited to `tested` instead.
        assert metrics.tested.immediate_direct == 1
        assert "A" in covered_labels(metrics.tested, "immediate_direct")


class TestUserExample:
    """The specific 4-assertion scenario from user.

    REQ-100: 4 assertions (A, B, C, D)
    REQ-010 refines REQ-100-A (no coverage!)
    REQ-020 implements REQ-100-B (explicit coverage)
    TEST verifies REQ-100-A and REQ-100-B

    Expected (implemented dimension, REQ-d00084-D):
    - A: TEST_DIRECT from TEST (tested only, NOT implemented)
    - B: EXPLICIT from REQ-020 (implemented); also TEST_DIRECT (tested)
    - C, D: no coverage
    """

    # Verifies: REQ-d00069-J, REQ-d00084-D
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

        # IMPLEMENTED dimension (REQ-d00084-D): only CODE/REQ evidence counts.
        # - A: TEST-only (Verifies) -> NOT implemented. Its sole refiner REQ-010
        #   is empty (conducts 0.0), so A's implemented fraction is 0.0.
        # - B: REQ-020 implements it (EXPLICIT) -> 1.0. No diluting refiner.
        # - C, D: 0. Covered sum = 1.0.
        assert metrics.implemented.covered == 1.0

        # A's coverage contribution from the test is TEST_DIRECT (feeds `tested`),
        # so A lands in the `tested` dimension, not `implemented`.
        assert "A" in metrics.assertion_coverage
        assert any(
            c.source_type == CoverageSource.TEST_DIRECT for c in metrics.assertion_coverage["A"]
        )
        assert "A" in covered_labels(metrics.tested, "immediate_direct")
        assert "A" not in covered_labels(metrics.implemented, "total")

        # B is verified by a TEST (TEST_DIRECT) AND implemented by REQ-020 (EXPLICIT)
        assert "B" in metrics.assertion_coverage
        b_sources = {c.source_type for c in metrics.assertion_coverage["B"]}
        assert CoverageSource.TEST_DIRECT in b_sources
        assert CoverageSource.EXPLICIT in b_sources

        # REFINES from REQ-010 should NOT contribute to A's coverage
        a_contributors = [c.source_id for c in metrics.assertion_coverage["A"]]
        assert all("REQ-010" not in c for c in a_contributors)

        # C and D have no coverage
        assert "C" not in metrics.assertion_coverage
        assert "D" not in metrics.assertion_coverage

        # Implemented percentage: 1.0/4 = 25% (only B is implemented).
        assert metrics.implemented.covered_pct == 25.0


class TestCoverageDimensionTierVocabulary:
    """A dimension's tier uses the unified {full,partial,failing,missing}
    vocabulary (REQ-d00258-H). What a citation named is not a tier -- a
    dimension fully covered on the total reads ``full`` whichever measure
    carried it; ``none`` is renamed ``missing``.
    """

    # Verifies: REQ-d00258-A
    def test_all_direct_reads_full(self):
        """A dimension fully covered by direct evidence reads ``full``
        (was ``full-direct``)."""
        from elspais.graph.metrics import CoverageDimension

        dim = CoverageDimension(total=2, immediate_direct_by_label={"A": 1.0, "B": 1.0})
        assert absolute_tier(dim, measure="total") == "full"

    # Verifies: REQ-d00258-A
    def test_fully_covered_including_indirect_reads_full(self):
        """A dimension fully covered only by whole-requirement evidence still
        reads ``full`` -- the measure is published, never a caveat."""
        from elspais.graph.metrics import CoverageDimension

        dim = CoverageDimension(total=2, immediate_indirect_by_label={"A": 1.0, "B": 1.0})
        assert absolute_tier(dim, measure="total") == "full"

    # Verifies: REQ-d00258-A
    def test_some_covered_reads_partial(self):
        """A partially-covered dimension reads ``partial``."""
        from elspais.graph.metrics import CoverageDimension

        dim = CoverageDimension(total=2, immediate_indirect_by_label={"A": 1.0})
        assert absolute_tier(dim, measure="total") == "partial"

    # Verifies: REQ-d00258-A
    def test_no_coverage_reads_missing(self):
        """An uncovered dimension reads ``missing`` (was ``none``)."""
        from elspais.graph.metrics import CoverageDimension

        dim = CoverageDimension(total=2)
        assert absolute_tier(dim, measure="total") == "missing"

    # Verifies: REQ-d00258-A
    def test_failures_read_failing(self):
        """A dimension with failures reads ``failing`` regardless of coverage."""
        from elspais.graph.metrics import CoverageDimension

        dim = CoverageDimension(
            total=2, has_failures=True, immediate_direct_by_label={"A": 1.0, "B": 1.0}
        )
        assert absolute_tier(dim, measure="total") == "failing"


class TestNoAssertions:
    """Tests for requirements without assertions."""

    # Verifies: REQ-d00051-E
    def test_requirement_with_no_assertions(self):
        """Requirements with no assertions have zero metrics.

        The base case of per-requirement coverage status from node.metrics:
        the counts start from zero, so a requirement contributing no
        assertions reads as zero covered of zero, not as an error or a
        missing metric.
        """
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
        assert metrics.implemented.covered == 0
        assert metrics.implemented.covered_pct == 0.0


class TestCoveragePercentStored:
    """Verify implemented.covered_pct is accessible from rollup_metrics."""

    # Verifies: REQ-d00055-D
    def test_coverage_pct_accessible_from_rollup(self):
        """implemented.covered_pct is accessible from the rollup_metrics object."""
        graph = build_graph(
            make_requirement(
                "REQ-100",
                level="PRD",
                assertions=[
                    {"label": "A", "text": "Assertion A"},
                    {"label": "B", "text": "Assertion B"},
                ],
            ),
            make_code_ref(implements=["REQ-100-A"]),  # implemented 1/2 = 50%
        )

        annotate_coverage(graph)

        node = graph.find_by_id("REQ-100")

        rollup: RollupMetrics = node.get_metric("rollup_metrics")
        assert rollup.implemented.covered_pct == 50.0


class TestTestSpecificMetrics:
    """Tests for TEST-specific metrics (tested, verified dimensions)."""

    # Verifies: REQ-d00069-B
    def test_direct_tested_counts_test_coverage(self):
        """tested.immediate_direct counts assertions with TEST nodes (not CODE)."""
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

        assert rollup.tested.immediate_direct == 1  # Only A (TEST), not B (CODE)
        # Implemented is CODE/REQ evidence only (REQ-d00084-D): B is implemented
        # by CODE; A is TEST-only so it does NOT count toward implemented.
        assert rollup.implemented.covered == 1  # Only B (CODE)

    # Verifies: REQ-d00069-F
    def test_validated_counts_passing_tests(self):
        """verified.immediate_direct counts assertions with passing TEST_RESULTs."""
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
                match="source",
            ),
            make_test_result(
                "result-b",
                status="failed",
                test_id="test:tests/test_b.py:1",
                match="source",
            ),
        )

        annotate_coverage(graph)

        node = graph.find_by_id("REQ-100")
        rollup: RollupMetrics = node.get_metric("rollup_metrics")

        assert rollup.tested.immediate_direct == 2  # Both have TEST nodes
        assert rollup.verified.immediate_direct == 1  # Only A has passing result
        assert rollup.verified.has_failures is True  # B failed

    # Verifies: REQ-d00069-F
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
            make_test_result(
                "result-1", status="error", test_id="test:tests/test_module.py:1", match="source"
            ),
        )

        annotate_coverage(graph)

        node = graph.find_by_id("REQ-100")
        rollup: RollupMetrics = node.get_metric("rollup_metrics")

        assert rollup.verified.has_failures is True

    # Verifies: REQ-d00069-F
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
            make_test_result(
                "result-1", status="passed", test_id="test:tests/test_module.py:1", match="source"
            ),
        )

        annotate_coverage(graph)

        node = graph.find_by_id("REQ-100")
        rollup: RollupMetrics = node.get_metric("rollup_metrics")

        assert rollup.verified.has_failures is False
        assert rollup.verified.immediate_direct == 1

    # Verifies: REQ-d00069-B
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

        assert rollup.tested.immediate_direct == 0
        assert rollup.verified.immediate_direct == 0
        assert rollup.verified.has_failures is False
        assert rollup.implemented.covered == 1  # Still covered by CODE


class TestPerAssertionFailureAttribution:
    """REQ-d00258-G: the per-assertion 'failing' standing is attributed to the
    assertion that actually failed, not to a non-failing sibling.

    ``has_failures`` stays requirement-wide (drives the requirement badge/tier);
    ``failing_labels`` records which assertions failed so the per-assertion
    standing (via ``compute_assertion_coverage_states``) reddens only them.
    """

    # Verifies: REQ-d00258-G
    def test_verified_failing_labels_only_the_failed_assertion(self):
        """Failing test on B must not redden the passing sibling A."""
        from elspais.html.generator import compute_assertion_coverage_states
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
            make_test_ref(verifies=["REQ-100-A"], source_path="tests/test_a.py"),
            make_test_ref(verifies=["REQ-100-B"], source_path="tests/test_b.py"),
            make_test_result(
                "result-a", status="passed", test_id="test:tests/test_a.py:1", match="source"
            ),
            make_test_result(
                "result-b", status="failed", test_id="test:tests/test_b.py:1", match="source"
            ),
        )

        annotate_coverage(graph)
        node = graph.find_by_id("REQ-100")
        rollup: RollupMetrics = node.get_metric("rollup_metrics")

        # Failure attributed to B only -- NOT the passing sibling A.
        assert rollup.verified.failing_labels == {"B"}
        # Requirement-level dimension unchanged: any assertion failing -> failing.
        assert rollup.verified.has_failures is True
        assert absolute_tier(rollup.verified, measure="total") == "failing"

        # Per-assertion standings: A passing (full), B failing -- B does NOT
        # leak its red onto A.
        states = compute_assertion_coverage_states(node)
        assert states["A"]["verified"] == "full"
        assert states["B"]["verified"] == "failing"

    # Verifies: REQ-d00258-G
    def test_blanket_failing_test_attributes_to_all_assertions(self):
        """A whole-requirement failing test blames every assertion it covers."""
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
            make_test_ref(verifies=["REQ-100"], source_path="tests/test_all.py"),
            make_test_result(
                "result-all",
                status="failed",
                test_id="test:tests/test_all.py:1",
                match="source",
            ),
        )

        annotate_coverage(graph)
        rollup: RollupMetrics = graph.find_by_id("REQ-100").get_metric("rollup_metrics")

        assert rollup.verified.failing_labels == {"A", "B"}
        assert rollup.verified.has_failures is True


class TestRefinesCoverageConduction:
    """REFINES edges conduct the refiner's own coverage up to the parent assertion.

    Per REQ-d00069-J, a `Refines:` edge contributes the refining requirement's
    own rolled-up coverage as one equal-weight incoming contribution to the
    targeted parent *Assertion*, computed per dimension and recursively.
    """

    # Verifies: REQ-d00069-J
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
        assert parent.tested.total_by_label["A"] == 1.0
        assert parent.tested.total_by_label.get("B", 0.0) == 0.0
        assert parent.tested.covered_pct == 50.0  # 1 of 2 assertions covered

        # The refiner itself is directly tested.
        child = graph.find_by_id("REQ-010").get_metric("rollup_metrics")
        assert child.tested.total_by_label["A"] == 1.0

    # Verifies: REQ-d00069-J
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
        assert parent.tested.total_by_label["A"] == pytest.approx(2 / 3)
        assert parent.tested.total_by_label["B"] == 1.0
        assert parent.tested.covered_pct == pytest.approx(83.33, abs=0.01)

    # Verifies: REQ-d00069-J
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
        assert top.tested.total_by_label["A"] == 1.0

    # Verifies: REQ-d00069-J
    def test_blanket_refine_conducts_at_full_weight(self):
        """A whole-requirement refine conducts into every parent assertion.

        REQ-C refines REQ-P (no /A suffix == blanket), so it names no
        assertion and conducts the refiner's OWN rolled-up coverage at FULL
        weight to every parent assertion -- the old 1/N-per-assertion
        deflation is retired (REQ-d00069-J). The citation shape decides WHICH
        assertions receive a value, not which measure it lands in, so the
        refiner's direct coverage lands in the parent's ROLLED DIRECT measure.
        REQ-C is fully tested, so each parent assertion gets the full 1.0.
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
        # The value is CONDUCTED, so it is in the rolled measures -- nothing
        # was attached to REQ-P itself.
        assert parent.tested.rolled_direct_by_label["A"] == 1.0
        assert parent.tested.rolled_direct_by_label["B"] == 1.0
        assert parent.tested.immediate_direct_by_label.get("A", 0.0) == 0.0
        # Full credit (REQ-d00069-J): the refiner's own coverage (1.0) conducts
        # at full weight, not (1/N)*1.0 == 0.5 under the retired rule.
        assert parent.tested.total_by_label["A"] == 1.0
        assert parent.tested.total_by_label["B"] == 1.0

    # Verifies: REQ-d00069-J
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
        assert parent.tested.total_by_label["A"] == 1.0
        # No UAT/journey coverage anywhere -> stays 0 in that dimension.
        assert parent.uat_coverage.total_by_label.get("A", 0.0) == 0.0

    # Verifies: REQ-d00069-J
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
            for measure in MEASURES:
                value = measure_by_label(metrics.tested, measure).get("A", 0.0)
                assert isinstance(value, float)
                assert 0.0 <= value <= 1.0
            assert 0.0 <= metrics.tested.total_by_label.get("A", 0.0) <= 1.0

    # Verifies: REQ-d00069-J
    def test_blanket_refine_multiple_edges_averaged(self):
        """Multiple blanket refines are averaged, at full weight (REQ-d00069-J).

        PARENT has N=3 assertions (A, B, C) with no direct coverage. Three
        requirements each blanket-refine PARENT (`Refines: PARENT`); two are
        fully tested and one is untested, so the mean child coverage across the
        blanket edges is (1 + 1 + 0) / 3 == 2/3. Full credit (the retired 1/N
        deflation no longer applies): each uncovered parent assertion gets the
        mean directly == 2/3 == 0.6667, not (1/3) * (2/3) == 0.2222.
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
        expected = 2 / 3  # full credit, no 1/N deflation (REQ-d00069-J)
        assert parent.tested.total_by_label["A"] == pytest.approx(expected, abs=0.001)
        assert parent.tested.total_by_label["B"] == pytest.approx(expected, abs=0.001)
        assert parent.tested.total_by_label["C"] == pytest.approx(expected, abs=0.001)
        # The credit is conducted, never attached here.
        for lbl in ("A", "B", "C"):
            assert parent.tested.immediate_direct_by_label.get(lbl, 0.0) == 0.0
            assert parent.tested.immediate_indirect_by_label.get(lbl, 0.0) == 0.0

    # Verifies: REQ-d00069-J
    def test_blanket_credit_skips_assertions_with_direct_coverage(self):
        """Blanket credit is monotone-maxed against direct, at full weight.

        PARENT has N=2 assertions (A, B). A has its own direct test (1.0). One
        requirement blanket-refines PARENT and is itself only half-tested (A
        tested, B untested -> its own mean coverage is 0.5) -- REQ-d00069-J's
        full-credit rule conducts that 0.5 (not a 1/N-deflated fraction of a
        full 1.0) to every uncovered parent assertion. A's own direct 1.0
        already exceeds the 0.5 blanket candidate, so the monotone max keeps it
        at 1.0 (blanket never LOWERS it); B, with no direct coverage, gets the
        blanket's actual (partial) conducted value, 0.5.
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
                assertions=[
                    {"label": "A", "text": "Refined A"},
                    {"label": "B", "text": "Refined B (untested)"},
                ],
            ),
            make_test_ref(verifies=["PARENT-A"], source_path="tests/test_a.py"),
            make_test_ref(verifies=["REQ-BLANK-A"], source_path="tests/test_blank.py"),
        )

        annotate_coverage(graph)

        parent = graph.find_by_id("PARENT").get_metric("rollup_metrics")
        # A has its own direct test -> 1.0, monotone max keeps it (blanket's
        # 0.5 candidate does not lower it).
        assert parent.tested.total_by_label["A"] == pytest.approx(1.0)
        # B has no direct coverage -> full-credit blanket conduction of
        # REQ-BLANK's own (partial) coverage, 0.5, not a 1/N-deflated 1.0.
        assert parent.tested.total_by_label["B"] == pytest.approx(0.5)

    # Verifies: REQ-d00069-J
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
        assert parent.tested.total_by_label["A"] == pytest.approx(1.0)
        assert parent.tested.total_by_label.get("B", 0.0) == pytest.approx(0.0)

    # Verifies: REQ-d00069-J
    # Verifies: REQ-d00258-A
    # Verifies: REQ-d00258-M
    def test_partial_conducted_coverage_is_a_gap(self):
        """Partial conducted coverage (0 < f < 1) is still reported as a gap.

        PARENT has N=2 assertions (A, B), both directly implemented by code.
        REQ-BLANK blanket-refines PARENT and is itself only half-tested (its
        own A tested, its own B untested), so its own rolled-up TESTED coverage
        is genuinely 0.5. Full credit (REQ-d00069-J) conducts that actual 0.5 --
        not an arbitrary 1/N-deflated fraction of a full 1.0 -- to each parent
        assertion, which is what the reporting surfaces headline. The work
        list answers the other question (REQ-d00258-M): no test names either
        assertion and none is attached to PARENT, so both remain *testing*
        gaps -- they are IMPLEMENTED and untested (REQ-d00258-I's relative
        denominator: a testing gap is implemented AND not tested).

        Exercises the real ``collect_gaps`` entry point, which passes assertion
        nodes (IDs keyed by label) -- guarding against the regression where the
        ID/label key mismatch marked every assertion uncovered.
        """
        from elspais.commands.gaps import collect_gaps

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
                assertions=[
                    {"label": "A", "text": "Refined A"},
                    {"label": "B", "text": "Refined B (untested)"},
                ],
            ),
            make_test_ref(verifies=["REQ-BLANK-A"], source_path="tests/test_blank.py"),
            # PARENT's assertions must be IMPLEMENTED for a partial TEST gap to
            # count under the relative denominator (REQ-d00258): code implements
            # A and B directly (implemented dimension), leaving TEST coverage
            # partial (0.5) via refines conduction of REQ-BLANK's own 0.5.
            make_code_ref(implements=["PARENT-A"], source_path="src/parent_a.py"),
            make_code_ref(implements=["PARENT-B"], source_path="src/parent_b.py"),
        )

        annotate_coverage(graph)

        metrics = graph.find_by_id("PARENT").get_metric("rollup_metrics")
        assert metrics.implemented.total_by_label["A"] == pytest.approx(1.0)
        assert metrics.implemented.total_by_label["B"] == pytest.approx(1.0)
        assert metrics.tested.total_by_label["A"] == pytest.approx(0.5)
        assert metrics.tested.total_by_label["B"] == pytest.approx(0.5)

        data = collect_gaps(graph, set())
        untested = next(e for e in data.untested if e.req_id == "PARENT")
        # REQ-d00258-M: the work list reads the immediate direct measure. No
        # test names PARENT-A or PARENT-B and none is attached to PARENT at
        # all -- REQ-BLANK's 0.5 was conducted from below -- so every
        # implemented assertion of PARENT is untested and the entry takes the
        # whole-requirement form. The conducted 0.5 is not lost: it is what the
        # reporting surfaces headline, asserted above.
        assert untested.assertions == []
