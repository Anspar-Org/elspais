# Verifies: REQ-d00254-C
"""[[scanning.test.targets]] config model (test-ingestion architecture)."""

import pytest
from pydantic import ValidationError

from elspais.config.schema import TestScanningConfig, TestTargetConfig


def test_target_defaults():
    t = TestTargetConfig(name="provenance")
    assert t.cwd == "" and t.command == "" and t.reporter == ""
    assert t.results == "" and t.coverage == ""
    assert t.match == "aggregate"
    assert t.credit_coverage == "off"
    assert t.min_coverage_fraction == 0.0


def test_target_full():
    t = TestTargetConfig(
        name="provenance",
        cwd="provenance",
        command="flutter test --machine --coverage",
        reporter="flutter-machine",
        coverage="coverage/lcov.info",
        match="precise",
        credit_coverage="verified",
        min_coverage_fraction=0.0,
    )
    assert t.reporter == "flutter-machine" and t.match == "precise"


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
