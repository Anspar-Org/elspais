# Verifies: REQ-d00254-A
"""Unit tests for _derive_credit_config: per-target credit reduction logic.

Tests the pure helper that collapses [[scanning.test.targets]] settings into a
single CoverageCreditConfig for the annotator.
"""

from elspais.config.schema import TestTargetConfig
from elspais.graph.annotators import CoverageCreditConfig
from elspais.graph.factory import _derive_credit_config


def _make_target(**kwargs) -> TestTargetConfig:
    """Create a TestTargetConfig with the given overrides and required name."""
    kwargs.setdefault("name", "t")
    return TestTargetConfig(**kwargs)


class TestDeriveCreditConfig:
    """Tests for _derive_credit_config: per-target → CoverageCreditConfig reduction."""

    def test_empty_targets_returns_defaults(self) -> None:
        """Empty target list → CoverageCreditConfig() defaults."""
        result = _derive_credit_config([])
        assert result == CoverageCreditConfig(
            app_dirs=(),
            coverage_dirs=(),
            unmatched_credit="off",
            assertion_credit="off",
            min_coverage_fraction=0.0,
        )

    def test_strongest_credit_coverage_wins(self) -> None:
        """With targets off/tested/verified, assertion_credit == 'verified'."""
        targets = [
            _make_target(name="a", credit_coverage="off"),
            _make_target(name="b", credit_coverage="tested"),
            _make_target(name="c", credit_coverage="verified"),
        ]
        result = _derive_credit_config(targets)
        assert result.assertion_credit == "verified"

    def test_tested_beats_off(self) -> None:
        """With targets off and tested only, assertion_credit == 'tested'."""
        targets = [
            _make_target(name="a", credit_coverage="off"),
            _make_target(name="b", credit_coverage="tested"),
        ]
        result = _derive_credit_config(targets)
        assert result.assertion_credit == "tested"

    def test_all_off_stays_off(self) -> None:
        """All targets with credit_coverage='off' → assertion_credit 'off'."""
        targets = [
            _make_target(name="a", credit_coverage="off"),
            _make_target(name="b", credit_coverage="off"),
        ]
        result = _derive_credit_config(targets)
        assert result.assertion_credit == "off"

    def test_unmatched_credit_verified_when_any_aggregate(self) -> None:
        """unmatched_credit='verified' iff at least one target has match='aggregate'."""
        targets = [
            _make_target(name="a", match="precise"),
            _make_target(name="b", match="aggregate"),
        ]
        result = _derive_credit_config(targets)
        assert result.unmatched_credit == "verified"

    def test_unmatched_credit_off_when_all_precise(self) -> None:
        """All precise → unmatched_credit 'off'."""
        targets = [
            _make_target(name="a", match="precise"),
            _make_target(name="b", match="precise"),
        ]
        result = _derive_credit_config(targets)
        assert result.unmatched_credit == "off"

    def test_app_dirs_excludes_empty_and_dot(self) -> None:
        """cwd='' and cwd='.' are excluded; non-trivial cwds are included."""
        targets = [
            _make_target(name="a", cwd=""),
            _make_target(name="b", cwd="."),
            _make_target(name="c", cwd="packages/app"),
            _make_target(name="d", cwd="packages/core"),
        ]
        result = _derive_credit_config(targets)
        assert result.app_dirs == ("packages/app", "packages/core")
        assert result.coverage_dirs == ("packages/app", "packages/core")

    def test_app_dirs_and_coverage_dirs_are_identical(self) -> None:
        """app_dirs and coverage_dirs always carry the same tuple."""
        targets = [_make_target(name="a", cwd="lib")]
        result = _derive_credit_config(targets)
        assert result.app_dirs == result.coverage_dirs

    def test_min_coverage_fraction_is_max_across_targets(self) -> None:
        """min_coverage_fraction = max of all target values."""
        targets = [
            _make_target(name="a", min_coverage_fraction=0.5),
            _make_target(name="b", min_coverage_fraction=0.9),
            _make_target(name="c", min_coverage_fraction=0.3),
        ]
        result = _derive_credit_config(targets)
        assert result.min_coverage_fraction == 0.9

    def test_min_coverage_fraction_single_target(self) -> None:
        """Single target: min_coverage_fraction passes through unchanged."""
        targets = [_make_target(name="a", min_coverage_fraction=0.75)]
        result = _derive_credit_config(targets)
        assert result.min_coverage_fraction == 0.75

    def test_single_aggregate_target_all_defaults_except_unmatched(self) -> None:
        """Single aggregate target with default credit settings."""
        targets = [_make_target(name="a", match="aggregate", cwd="app")]
        result = _derive_credit_config(targets)
        assert result.unmatched_credit == "verified"
        assert result.assertion_credit == "off"
        assert result.app_dirs == ("app",)
        assert result.min_coverage_fraction == 0.0
