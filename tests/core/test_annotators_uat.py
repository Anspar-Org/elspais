# Verifies: REQ-d00069-A
"""Tests for UAT coverage annotation via JNY Validates edges."""
from elspais.graph.annotators import annotate_coverage
from tests.core.graph_test_helpers import build_graph, make_journey, make_requirement


class TestJnyValidatesExplicitCoverage:
    """Validates REQ-d00069-A: JNY Validates gives UAT_EXPLICIT for specific assertions."""

    def test_jny_validates_explicit_REQ_d00069_A_uat_explicit(self):
        """JNY with Validates: REQ-xxx-A gives UAT_EXPLICIT for assertion A only."""
        req = make_requirement(
            "REQ-p00001",
            assertions=[
                {"label": "A", "text": "assertion A"},
                {"label": "B", "text": "assertion B"},
            ],
        )
        jny = make_journey("JNY-TST-001", validates=["REQ-p00001-A"])
        graph = build_graph(req, jny)
        annotate_coverage(graph)

        req_node = graph.find_by_id("REQ-p00001")
        metrics = req_node.get_metric("rollup_metrics")
        assert metrics is not None
        assert metrics.uat_coverage.indirect == 1
        assert metrics.uat_coverage.direct == 1
        assert metrics.uat_coverage.indirect - metrics.uat_coverage.direct == 0


class TestJnyValidatesInferredCoverage:
    """Validates REQ-d00069-A: JNY Validates whole REQ gives UAT_INFERRED for all assertions."""

    def test_jny_validates_whole_req_REQ_d00069_A_uat_inferred(self):
        """JNY with Validates: REQ-xxx gives UAT_INFERRED for all assertions."""
        req = make_requirement(
            "REQ-p00001",
            assertions=[
                {"label": "A", "text": "assertion A"},
                {"label": "B", "text": "assertion B"},
            ],
        )
        jny = make_journey("JNY-TST-001", validates=["REQ-p00001"])
        graph = build_graph(req, jny)
        annotate_coverage(graph)

        req_node = graph.find_by_id("REQ-p00001")
        metrics = req_node.get_metric("rollup_metrics")
        assert metrics.uat_coverage.indirect == 2
        assert metrics.uat_coverage.indirect - metrics.uat_coverage.direct == 2
        assert metrics.uat_coverage.direct == 0


class TestJnyValidatesIsolation:
    """Validates REQ-d00069-A: UAT coverage does not bleed into automated coverage."""

    def test_jny_validates_no_bleed_into_automated_REQ_d00069_A(self):
        """UAT coverage does not bleed into automated coverage fields."""
        req = make_requirement(
            "REQ-p00001",
            assertions=[
                {"label": "A", "text": "assertion A"},
            ],
        )
        jny = make_journey("JNY-TST-001", validates=["REQ-p00001-A"])
        graph = build_graph(req, jny)
        annotate_coverage(graph)

        req_node = graph.find_by_id("REQ-p00001")
        metrics = req_node.get_metric("rollup_metrics")
        assert metrics.implemented.indirect == 0  # automated unaffected
        assert metrics.implemented.direct == 0
        assert metrics.uat_coverage.indirect == 1


class TestUatRollupThroughImplements:
    """Validates REQ-d00069-A: UAT coverage rolls up from child to parent REQ."""

    def test_uat_rollup_through_implements_REQ_d00069_A(self):
        """UAT coverage rolls up from child DEV REQ to parent OPS REQ via IMPLEMENTS."""
        ops_req = make_requirement(
            "REQ-o00001",
            level="OPS",
            assertions=[
                {"label": "A", "text": "ops assertion A"},
            ],
        )
        dev_req = make_requirement("REQ-d00001", level="DEV", implements=["REQ-o00001"])
        jny = make_journey("JNY-TST-001", validates=["REQ-d00001"])
        graph = build_graph(ops_req, dev_req, jny)
        annotate_coverage(graph)

        ops_node = graph.find_by_id("REQ-o00001")
        metrics = ops_node.get_metric("rollup_metrics")
        assert metrics.uat_coverage.indirect > 0


class TestUatPerAssertionFailureAttribution:
    """REQ-d00258-G: uat_verified 'failing' is attributed to the assertion the
    failing journey validates, not to a sibling validated by a passing journey.

    The requirement-level dimension still reports failure via has_failures; only
    the per-assertion standing is scoped to failing_labels.
    """

    # Verifies: REQ-d00258-G
    def test_uat_verified_failing_labels_only_failed_assertion(self):
        """A failing journey on A must not redden a sibling B verified by a
        different, fully-passing journey."""
        from elspais.graph.annotators import JourneyVerification
        from elspais.html.generator import compute_assertion_coverage_states

        req = make_requirement(
            "REQ-p00001",
            assertions=[
                {"label": "A", "text": "assertion A"},
                {"label": "B", "text": "assertion B"},
            ],
        )
        jny_a = make_journey("JNY-TST-001", validates=["REQ-p00001-A"])
        jny_b = make_journey("JNY-TST-002", validates=["REQ-p00001-B"])
        graph = build_graph(req, jny_a, jny_b)

        # Journey A has a failing step; Journey B is fully verified (no failure).
        graph.find_by_id("JNY-TST-001").set_metric(
            "journey_verification",
            JourneyVerification(tier="failing", has_failures=True, total_steps=1),
        )
        graph.find_by_id("JNY-TST-002").set_metric(
            "journey_verification",
            JourneyVerification(
                tier="full-direct", fully_verified=True, verified_steps=1, total_steps=1
            ),
        )

        annotate_coverage(graph)
        node = graph.find_by_id("REQ-p00001")
        metrics = node.get_metric("rollup_metrics")

        # Failure attributed to A only -- not the passing sibling B.
        assert metrics.uat_verified.failing_labels == {"A"}
        # Requirement-level dimension unchanged.
        assert metrics.uat_verified.has_failures is True
        assert metrics.uat_verified.tier == "failing"

        states = compute_assertion_coverage_states(node)
        assert states["A"]["uat_verified"] == "failing"
        assert states["B"]["uat_verified"] == "full"

    # Verifies: REQ-d00258-G
    def test_uat_single_failing_journey_blames_all_it_validates(self):
        """One journey with a failing step validating the whole REQ legitimately
        reddens every assertion it validates (this is NOT the bug)."""
        from elspais.graph.annotators import JourneyVerification

        req = make_requirement(
            "REQ-p00001",
            assertions=[
                {"label": "A", "text": "assertion A"},
                {"label": "B", "text": "assertion B"},
            ],
        )
        jny = make_journey("JNY-TST-001", validates=["REQ-p00001"])  # whole-REQ (blanket)
        graph = build_graph(req, jny)
        graph.find_by_id("JNY-TST-001").set_metric(
            "journey_verification",
            JourneyVerification(tier="failing", has_failures=True, total_steps=1),
        )

        annotate_coverage(graph)
        metrics = graph.find_by_id("REQ-p00001").get_metric("rollup_metrics")

        assert metrics.uat_verified.failing_labels == {"A", "B"}
        assert metrics.uat_verified.has_failures is True
