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
        coverage_format="lcov",
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

    The coverage file is read in the format its `coverage_format` declares.
    """
    t = TestTargetConfig(name="x", coverage="coverage/lcov.info", coverage_format="lcov")
    assert t.coverage == "coverage/lcov.info"
    assert t.coverage_format == "lcov"
    assert t.reporter == ""


def test_bare_name_target_still_validates():
    """A target with only name (no command/results/coverage) validates fine."""
    t = TestTargetConfig(name="provenance")
    assert t.reporter == ""


# Verifies: REQ-d00311-R
def test_a_target_declares_its_environment_as_named_probes():
    t = TestTargetConfig(
        name="unit",
        environment_probes=[
            {"name": "python", "command": "python --version"},
            {"name": "packages", "command": "pip freeze"},
        ],
    )
    assert [(p.name, p.command) for p in t.environment_probes] == [
        ("python", "python --version"),
        ("packages", "pip freeze"),
    ]


# Verifies: REQ-d00311-R
@pytest.mark.parametrize(
    "probe,needs",
    [
        ({"name": "", "command": "python --version"}, "needs a name"),
        ({"name": "python", "command": "  "}, "needs a command"),
    ],
)
def test_a_probe_without_a_name_or_a_command_is_refused_naming_the_form(probe, needs):
    with pytest.raises(ValidationError, match=needs) as exc:
        TestTargetConfig(name="unit", environment_probes=[probe])
    assert 'name = "python"' in str(exc.value)


# Verifies: REQ-d00311-R
def test_a_bare_string_probe_is_refused():
    with pytest.raises(ValidationError):
        TestTargetConfig(name="unit", environment_probes=["python --version"])


# Verifies: REQ-d00311-R
def test_two_probes_differing_only_in_case_are_refused_naming_both():
    with pytest.raises(ValidationError, match='"Python" and "python"'):
        TestTargetConfig(
            name="unit",
            environment_probes=[
                {"name": "Python", "command": "python --version"},
                {"name": "python", "command": "python3 --version"},
            ],
        )


# Verifies: REQ-d00333-F
def test_a_fetch_command_names_the_directory_it_fills():
    config = TestScanningConfig(baseline={"fetch_command": "tools/fetch.sh {dest}"})
    assert config.baseline.fetch_command == "tools/fetch.sh {dest}"
    assert TestScanningConfig().baseline.fetch_command == ""


# Verifies: REQ-d00333-F
def test_a_fetch_command_without_its_placeholder_is_refused_naming_it():
    with pytest.raises(ValidationError, match=r"does not name \{dest\}"):
        TestScanningConfig(baseline={"fetch_command": "tools/fetch.sh /tmp/out"})


# Verifies: REQ-d00333-F
def test_an_unknown_baseline_setting_is_refused():
    with pytest.raises(ValidationError):
        TestScanningConfig(baseline={"fetch": "tools/fetch.sh {dest}"})


# ---------------------------------------------------------------------------
# coverage_format names the coverage reporter that reads `coverage`
# ---------------------------------------------------------------------------

COVERAGE_FORMATS = ("lcov", "coverage-json", "coverage-sqlite")


# Verifies: REQ-d00254-C
@pytest.mark.parametrize(
    "settings",
    [
        {"coverage": "lcov.info"},
        {"coverage": "lcov.info", "coverage_format": "junit"},
    ],
    ids=["coverage-without-format", "results-reporter-as-format"],
)
def test_a_coverage_file_without_a_coverage_reporter_is_refused_naming_the_formats(
    settings,
):
    with pytest.raises(ValidationError) as exc:
        TestTargetConfig(name="x", **settings)
    message = str(exc.value)
    assert "coverage_format" in message
    for fmt in COVERAGE_FORMATS:
        assert fmt in message


# Verifies: REQ-d00254-C
def test_a_coverage_file_with_its_coverage_reporter_validates():
    t = TestTargetConfig(name="x", coverage="lcov.info", coverage_format="lcov")
    assert t.coverage == "lcov.info"
    assert t.coverage_format == "lcov"


# Verifies: REQ-d00254-C
def test_a_target_without_coverage_needs_no_coverage_format():
    t = TestTargetConfig(name="x")
    assert t.coverage == ""
    assert t.coverage_format == ""
