# Implements: REQ-d00069-A
"""Tests for CoverageSource UAT values and RollupMetrics UAT fields."""

from elspais.graph.metrics import CoverageContribution, CoverageSource, RollupMetrics


class TestUATCoverageSource:
    """Validates REQ-d00069-A: UAT coverage source values."""

    def test_coverage_source_has_uat_explicit_REQ_d00069_A(self):
        """CoverageSource.UAT_EXPLICIT has correct string value."""
        assert CoverageSource.UAT_EXPLICIT.value == "uat_explicit"

    def test_coverage_source_has_uat_inferred_REQ_d00069_A(self):
        """CoverageSource.UAT_INFERRED has correct string value."""
        assert CoverageSource.UAT_INFERRED.value == "uat_inferred"


class TestUATRollupMetrics:
    """Validates REQ-d00069-A: UAT metrics fields in RollupMetrics."""

    def test_rollup_metrics_has_uat_covered_REQ_d00069_A(self):
        """RollupMetrics has uat_covered field defaulting to 0."""
        m = RollupMetrics()
        assert m.uat_covered == 0

    def test_rollup_metrics_has_uat_direct_covered_REQ_d00069_A(self):
        """RollupMetrics has uat_direct_covered field defaulting to 0."""
        m = RollupMetrics()
        assert m.uat_direct_covered == 0

    def test_rollup_metrics_has_uat_inferred_covered_REQ_d00069_A(self):
        """RollupMetrics has uat_inferred_covered field defaulting to 0."""
        m = RollupMetrics()
        assert m.uat_inferred_covered == 0

    def test_rollup_metrics_has_uat_referenced_pct_REQ_d00069_A(self):
        """RollupMetrics has uat_referenced_pct field defaulting to 0.0."""
        m = RollupMetrics()
        assert m.uat_referenced_pct == 0.0

    def test_rollup_metrics_has_uat_validated_REQ_d00069_A(self):
        """RollupMetrics has uat_validated field defaulting to 0."""
        m = RollupMetrics()
        assert m.uat_validated == 0

    def test_rollup_metrics_has_uat_has_failures_REQ_d00069_A(self):
        """RollupMetrics has uat_has_failures field defaulting to False."""
        m = RollupMetrics()
        assert m.uat_has_failures is False

    def test_rollup_metrics_has_uat_validated_pct_REQ_d00069_A(self):
        """RollupMetrics has uat_validated_pct field defaulting to 0.0."""
        m = RollupMetrics()
        assert m.uat_validated_pct == 0.0


class TestUATFinalizeComputation:
    """Validates REQ-d00069-A: finalize() computes UAT coverage aggregates."""

    def test_finalize_computes_uat_covered_REQ_d00069_A(self):
        """finalize() computes uat_covered from UAT contributions."""
        m = RollupMetrics(total_assertions=3)
        m.add_contribution(
            CoverageContribution(
                source_id="JNY-001", source_type=CoverageSource.UAT_EXPLICIT, assertion_label="A"
            )
        )
        m.add_contribution(
            CoverageContribution(
                source_id="JNY-001", source_type=CoverageSource.UAT_INFERRED, assertion_label="B"
            )
        )
        m.finalize()
        assert m.uat_covered == 2
        assert m.uat_direct_covered == 1
        assert m.uat_inferred_covered == 1
        assert round(m.uat_referenced_pct, 1) == round(2 / 3 * 100, 1)

    def test_finalize_uat_pct_zero_when_no_assertions_REQ_d00069_A(self):
        """finalize() sets uat_referenced_pct=0.0 when total_assertions==0."""
        m = RollupMetrics(total_assertions=0)
        m.finalize()
        assert m.uat_referenced_pct == 0.0
        assert m.uat_validated_pct == 0.0

    def test_finalize_uat_does_not_affect_test_coverage_REQ_d00069_A(self):
        """UAT contributions do not bleed into automated test coverage fields."""
        m = RollupMetrics(total_assertions=2)
        m.add_contribution(
            CoverageContribution(
                source_id="JNY-001", source_type=CoverageSource.UAT_EXPLICIT, assertion_label="A"
            )
        )
        m.finalize()
        assert m.covered_assertions == 0  # automated unaffected
        assert m.uat_covered == 1
