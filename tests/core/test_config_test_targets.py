# Verifies: REQ-d00254-C
"""[[scanning.test.targets]] config model (test-ingestion architecture)."""

import pytest
from pydantic import ValidationError

from elspais.config.schema import TestScanningConfig, TestTargetConfig


def test_target_defaults():
    t = TestTargetConfig(name="provenance")
    assert t.cwd == "" and t.command == "" and t.reporter == ""
    assert t.results == "" and t.coverage == ""
    assert t.match == "source"
    assert t.credit_coverage == "off"
    assert t.min_coverage_fraction == 0.0


def test_target_full():
    t = TestTargetConfig(
        name="provenance",
        cwd="provenance",
        command="flutter test --machine --coverage",
        reporter="flutter-machine",
        coverage="coverage/lcov.info",
        match="source",
        credit_coverage="verified",
        min_coverage_fraction=0.0,
    )
    assert t.reporter == "flutter-machine" and t.match == "source"


@pytest.mark.parametrize(
    "field,bad",
    [
        ("match", "fuzzy"),
        ("credit_coverage", "bogus"),
    ],
)
def test_target_enum_validation(field, bad):
    with pytest.raises(ValidationError):
        TestTargetConfig(name="x", **{field: bad})


@pytest.mark.parametrize("frac", [-0.1, 1.5])
def test_target_fraction_range(frac):
    with pytest.raises(ValidationError):
        TestTargetConfig(name="x", min_coverage_fraction=frac)


def test_test_scanning_has_targets_list():
    cfg = TestScanningConfig(targets=[{"name": "a", "reporter": "flutter-machine"}])
    assert cfg.targets[0].name == "a"


# Verifies: REQ-d00254-C
def test_obsolete_config_removed():
    import elspais.config.schema as s

    for name in ("ResultScanningConfig", "CoverageScanningConfig", "TestRunnerConfig"):
        assert not hasattr(s, name)


# ---------------------------------------------------------------------------
# FIX 9: reporter required when command/results/coverage is set
# ---------------------------------------------------------------------------


def test_target_with_command_but_no_reporter_raises():
    """A target with command but no reporter must raise ValidationError."""
    with pytest.raises(ValidationError):
        TestTargetConfig(name="x", command="flutter test --machine")


def test_target_with_results_but_no_reporter_raises():
    """A target with results glob but no reporter must raise ValidationError."""
    with pytest.raises(ValidationError):
        TestTargetConfig(name="x", results="results/*.xml")


def test_target_with_coverage_only_no_reporter_is_valid():
    """A target with only coverage (no command/results) is valid without a reporter.

    Coverage ingestion uses format auto-detection, not the reporter registry.
    """
    t = TestTargetConfig(name="x", coverage="coverage/lcov.info")
    assert t.coverage == "coverage/lcov.info"
    assert t.reporter == ""


def test_bare_name_target_still_validates():
    """A target with only name (no command/results/coverage) validates fine."""
    t = TestTargetConfig(name="provenance")
    assert t.reporter == ""
