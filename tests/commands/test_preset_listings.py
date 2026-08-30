# Verifies: REQ-d00285-B, REQ-d00285-C, REQ-d00285-F, REQ-d00285-G, REQ-d00285-H, REQ-d00285-I
"""The preset listings are the findings report narrowed, not a second report.

`elspais unresolved`, `elspais errors` and `elspais uncited` each answer one
question over the one findings stream. The tests here pin the property that
makes the arrangement worth having: a listing cannot say less about a finding
than the report it is a view of, because it IS that report.
"""

from __future__ import annotations

import argparse
import pathlib

import pytest

from elspais.commands.health import (
    _REFERENCE_CHECKS,
    FindingFilter,
    HealthCheck,
    HealthFinding,
    HealthReport,
    apply_finding_filter,
    run_checks,
)
from elspais.utilities.findings import PRESETS, REGISTRY, preset_checks, remedy_for

# A code file carrying one item of several fault classes, so the listing has
# something to lose.  "not a reference" has a space and never reads as an
# identifier (MALFORMED); "REQ-d09999" reads and names no requirement
# (UNKNOWN_REQUIREMENT); "REQ-d00001-Z" names a label its requirement lacks
# (UNKNOWN_ASSERTION); "Refines:" is a keyword a code file may not use
# (FORBIDDEN).
_CODE = """# Implements: not a reference
def f1():
    pass


# Implements: REQ-d09999
def f2():
    pass


# Implements: REQ-d00001-Z
def f3():
    pass


# Refines: REQ-d00001
def f4():
    pass


# Implements: REQ-d00001-A
def f5():
    pass
"""


@pytest.fixture(scope="module")
def repo_root():
    return pathlib.Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def _project_dir(tmp_path_factory, repo_root):
    tmp_path = tmp_path_factory.mktemp("preset_listings")
    (tmp_path / ".elspais.toml").write_text((repo_root / ".elspais.toml").read_text())
    spec = tmp_path / "spec"
    spec.mkdir()
    (spec / "r.md").write_text(
        "# REQ-d00001: Thing\n\n"
        "**Level**: dev | **Status**: Active | **Implements**: -\n\n"
        "## Assertions\n\n"
        "A. The system SHALL do a thing.\n\n"
        "*End* *Thing* | **Hash**: 00000000\n"
    )
    src = tmp_path / "src"
    src.mkdir()
    (src / "m.py").write_text(_CODE)
    return tmp_path


@pytest.fixture(scope="module")
def faulted_graph(_project_dir):
    from elspais.config import load_config
    from elspais.graph.factory import build_graph

    config_path = _project_dir / ".elspais.toml"
    return build_graph(
        load_config(config_path),
        config_path=config_path,
        repo_root=_project_dir,
        scan_code=True,
        scan_tests=False,
    )


@pytest.fixture
def config(_project_dir):
    from elspais.config import load_config

    return load_config(_project_dir / ".elspais.toml")


@pytest.fixture
def whole_run(faulted_graph, config):
    report = HealthReport()
    for check in run_checks(faulted_graph, config):
        report.add(check)
    return report


# ---------------------------------------------------------------------------
# What a preset IS
# ---------------------------------------------------------------------------


# Verifies: REQ-d00285-F
def test_unresolved_selects_exactly_the_five_reference_classes():
    """The listing's population is the partition of unresolved references.

    Adding `spec.implements_resolve` and its siblings would list one
    unresolved target twice under two names, which is the double-count the
    class partition exists to prevent.
    """
    assert set(preset_checks("unresolved")) == {name for _cls, name, _desc in _REFERENCE_CHECKS}


# Verifies: REQ-d00285-B
@pytest.mark.parametrize("preset", sorted(PRESETS))
def test_every_preset_member_sends_readers_to_that_preset(preset):
    """A check listed by `elspais X` names `elspais X` as its remedy.

    The two are written separately, so a check added to a preset without its
    remedy being moved would send a reader to a listing their finding is not
    on -- which is worse than naming no remedy at all.
    """
    for name in preset_checks(preset):
        assert remedy_for(name) == f"elspais {preset}", (
            f"{name} is listed by `elspais {preset}` but its remedy names {remedy_for(name)!r}"
        )


# Verifies: REQ-d00285-F
@pytest.mark.parametrize("preset", sorted(PRESETS))
def test_a_preset_names_only_checks_the_tool_runs(preset):
    unregistered = sorted(set(preset_checks(preset)) - set(REGISTRY))
    assert unregistered == [], f"{preset} names checks that are not registered: {unregistered}"


# Verifies: REQ-d00285-F
def test_no_two_presets_claim_the_same_check():
    """One check, one listing: a check on two listings is counted twice by a
    reader who runs both, with nothing to say the two are one fact."""
    seen: dict[str, str] = {}
    for preset, names in PRESETS.items():
        for name in names:
            assert name not in seen, f"{name} is claimed by both {seen[name]!r} and {preset!r}"
            seen[name] = preset


# ---------------------------------------------------------------------------
# The listing keeps what a separate renderer dropped
# ---------------------------------------------------------------------------


# Verifies: REQ-d00285-C
def test_the_unresolved_listing_carries_the_fault_class_and_codes(whole_run):
    """Every finding names the class it reached and the codes reading it
    produced.

    A listing rendered separately from the report has to be handed each field
    a finding carries a second time; these are the two that went missing.
    """
    narrowed = apply_finding_filter(whole_run, FindingFilter.for_preset("unresolved")).report
    findings = [(c, f) for c in narrowed.checks for f in c.findings]
    assert findings, "fixture must produce unresolved references"

    classes = {name for _cls, name, _desc in _REFERENCE_CHECKS}
    for check, finding in findings:
        assert check.name in classes, f"{finding.message} is filed under {check.name}"
        assert check.remedy, f"{check.name} carries no remedy"
        assert finding.codes, (
            f"{finding.message} carries no diagnostic code; the class it reached "
            f"is knowable and was dropped"
        )
        assert finding.file_path, f"{finding.message} carries no location"


# Verifies: REQ-d00285-C
def test_the_listing_reports_exactly_what_the_whole_report_reports(whole_run):
    """The narrowed report and the whole report agree, finding for finding.

    Not merely in count: identity, severity, location and remedy all travel,
    because the listing is the same objects.
    """
    narrowed = apply_finding_filter(whole_run, FindingFilter.for_preset("unresolved")).report
    selected = set(preset_checks("unresolved"))

    def shape(report):
        return sorted(
            (c.name, c.severity, c.remedy, f.message, f.file_path, f.line, tuple(f.codes))
            for c in report.checks
            if c.name in selected
            for f in c.findings
        )

    assert shape(narrowed) == shape(whole_run)
    assert shape(narrowed), "fixture must produce findings for this to mean anything"


# Verifies: REQ-d00285-C
def test_the_mcp_tool_reports_the_same_findings_as_the_listing(faulted_graph, config, whole_run):
    """The MCP surface answers about unresolved references from the same
    stream, so an agent and a person are never told different things about
    one reference."""
    from elspais.mcp.server import _get_unresolved_references

    result = _get_unresolved_references(faulted_graph, config)
    selected = set(preset_checks("unresolved"))

    from_mcp = sorted(
        (f["check"], f["severity"], f["remedy"], f["message"], f["file_path"], tuple(f["codes"]))
        for f in result["unresolved_references"]
    )
    from_report = sorted(
        (c.name, c.severity, c.remedy, f.message, f.file_path, tuple(f.codes))
        for c in whole_run.checks
        if c.name in selected
        for f in c.findings
    )
    assert from_mcp == from_report
    assert from_mcp, "fixture must produce findings for this to mean anything"
    assert result["count"] == len(from_report)


# Verifies: REQ-d00285-G
def test_the_mcp_tool_names_a_class_the_project_turned_off(faulted_graph, config):
    """A class set to `off` produced no findings, and the surface says which
    -- otherwise "none" and "not reported" read alike."""
    from elspais.mcp.server import _get_unresolved_references

    config["rules"]["references"]["malformed"] = "off"
    result = _get_unresolved_references(faulted_graph, config)

    entry = next(c for c in result["checks"] if c["name"] == "references.malformed")
    assert entry["skipped"] is True
    assert entry["count"] == 0
    assert not any(f["check"] == "references.malformed" for f in result["unresolved_references"])


# ---------------------------------------------------------------------------
# The verdict, and the disclosure
# ---------------------------------------------------------------------------


def _report(*checks: HealthCheck) -> HealthReport:
    report = HealthReport()
    for check in checks:
        report.add(check)
    return report


# Verifies: REQ-d00285-H
def test_a_readers_narrowing_does_not_move_the_verdict():
    """`checks --severity` chooses what to look at, never what the run found.

    `_format_report` renders the narrowed report and takes its verdict from
    the whole run unless a preset says otherwise, so the property to pin is
    that narrowing away the failure leaves the run's own verdict standing.
    """
    report = _report(
        HealthCheck(
            name="spec.hash_integrity",
            passed=False,
            message="stale",
            category="spec",
            severity="error",
        ),
        HealthCheck(
            name="config.exists",
            passed=True,
            message="present",
            category="config",
            severity="info",
        ),
    )
    outcome = apply_finding_filter(report, FindingFilter(severities=("info",)))
    assert outcome.report.is_healthy is True, "the narrowing kept only the passing check"
    assert report.is_healthy is False, "the run's own verdict must be untouched by it"


# Verifies: REQ-d00285-H
def test_a_preset_takes_its_verdict_from_the_checks_it_names():
    """`elspais unresolved` answers about unresolved references. A failing
    check it does not list must not decide its exit code, or the command stops
    being a predicate about the thing it is named for."""
    unrelated = HealthCheck(
        name="spec.hash_integrity",
        passed=False,
        message="stale",
        category="spec",
        severity="error",
    )
    clean = HealthCheck(
        name="references.malformed",
        passed=True,
        message="none",
        category="references",
        severity="warning",
    )
    report = _report(unrelated, clean)

    assert report.is_healthy is False
    narrowed = apply_finding_filter(report, FindingFilter.for_preset("unresolved")).report
    assert narrowed.is_healthy is True


# Verifies: REQ-d00285-I
def test_a_preset_listing_discloses_which_listing_it_is_and_what_it_withheld():
    """A short list must not read as a clean run."""
    report = _report(
        HealthCheck(
            name="references.malformed",
            passed=False,
            message="1 reference",
            category="references",
            severity="warning",
            findings=[HealthFinding(message="bad", file_path="src/m.py", line=1)],
        ),
        HealthCheck(
            name="spec.hash_integrity",
            passed=False,
            message="stale",
            category="spec",
            severity="error",
            findings=[HealthFinding(message="stale", file_path="spec/r.md", line=1)],
        ),
    )
    disclosure = apply_finding_filter(report, FindingFilter.for_preset("unresolved")).disclosure()
    assert disclosure is not None
    assert "unresolved" in disclosure
    assert "1 of 2 checks" in disclosure
    assert "1 of 2 findings" in disclosure
    # Reproducible by hand: a narrowing a reader cannot restate is a narrowing
    # they cannot check.
    assert "--check references.malformed" in disclosure


# ---------------------------------------------------------------------------
# The `--check` narrowing the presets are made of
# ---------------------------------------------------------------------------


# Verifies: REQ-d00282-F
def test_an_unregistered_check_name_is_refused_rather_than_selecting_nothing():
    """A report narrowed by a name that selects nothing looks exactly like a
    report with nothing to say."""
    args = argparse.Namespace(check=["references.malformed", "references.nonesuch"])
    problems = FindingFilter.from_args(args).unadmitted()
    assert any("references.nonesuch" in p for p in problems)
    assert not any("references.malformed" in p for p in problems)


# Verifies: REQ-d00285-C
def test_naming_a_check_renders_its_findings_without_verbose():
    """A reader who named a check asked for its findings by name."""
    assert FindingFilter(names=("references.malformed",)).shows_findings is True
    assert FindingFilter(severities=("error",)).shows_findings is False


# ---------------------------------------------------------------------------
# The retired word
# ---------------------------------------------------------------------------


# Verifies: REQ-d00286-C
def test_the_retired_command_is_gone_with_no_alias():
    """`broken` is retired as a reporting word; this project ships no alias."""
    import importlib

    from elspais.commands.args import COMMAND_GROUPS

    assert "broken" not in COMMAND_GROUPS
    assert "unresolved" in COMMAND_GROUPS
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("elspais.commands.broken")
