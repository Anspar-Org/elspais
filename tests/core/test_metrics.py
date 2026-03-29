# Verifies: REQ-d00069-A
"""Tests for CoverageSource UAT values and RollupMetrics UAT fields."""

from elspais.graph.metrics import CoverageContribution, CoverageSource, RollupMetrics


class TestUATRollupMetrics:
    """Validates REQ-d00069-A: UAT metrics fields in RollupMetrics."""

    def test_rollup_metrics_has_uat_coverage_indirect_REQ_d00069_A(self):
        """RollupMetrics has uat_coverage.indirect defaulting to 0."""
        m = RollupMetrics()
        assert m.uat_coverage.indirect == 0

    def test_rollup_metrics_has_uat_coverage_direct_REQ_d00069_A(self):
        """RollupMetrics has uat_coverage.direct defaulting to 0."""
        m = RollupMetrics()
        assert m.uat_coverage.direct == 0

    def test_rollup_metrics_has_uat_coverage_indirect_pct_REQ_d00069_A(self):
        """RollupMetrics has uat_coverage.indirect_pct defaulting to 0.0."""
        m = RollupMetrics()
        assert m.uat_coverage.indirect_pct == 0.0

    def test_rollup_metrics_has_uat_verified_indirect_REQ_d00069_A(self):
        """RollupMetrics has uat_verified.indirect defaulting to 0."""
        m = RollupMetrics()
        assert m.uat_verified.indirect == 0

    def test_rollup_metrics_has_uat_verified_has_failures_REQ_d00069_A(self):
        """RollupMetrics has uat_verified.has_failures defaulting to False."""
        m = RollupMetrics()
        assert m.uat_verified.has_failures is False

    def test_rollup_metrics_has_uat_verified_indirect_pct_REQ_d00069_A(self):
        """RollupMetrics has uat_verified.indirect_pct defaulting to 0.0."""
        m = RollupMetrics()
        assert m.uat_verified.indirect_pct == 0.0


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
        assert m.uat_coverage.indirect == 2
        assert m.uat_coverage.direct == 1
        assert m.uat_coverage.indirect - m.uat_coverage.direct == 1
        assert round(m.uat_coverage.indirect_pct, 1) == round(2 / 3 * 100, 1)

    def test_finalize_uat_pct_zero_when_no_assertions_REQ_d00069_A(self):
        """finalize() sets uat_referenced_pct=0.0 when total_assertions==0."""
        m = RollupMetrics(total_assertions=0)
        m.finalize()
        assert m.uat_coverage.indirect_pct == 0.0
        assert m.uat_verified.indirect_pct == 0.0

    def test_finalize_uat_does_not_affect_test_coverage_REQ_d00069_A(self):
        """UAT contributions do not bleed into automated test coverage fields."""
        m = RollupMetrics(total_assertions=2)
        m.add_contribution(
            CoverageContribution(
                source_id="JNY-001", source_type=CoverageSource.UAT_EXPLICIT, assertion_label="A"
            )
        )
        m.finalize()
        assert m.implemented.indirect == 0  # automated unaffected
        assert m.uat_coverage.indirect == 1
