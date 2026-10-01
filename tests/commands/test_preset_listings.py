# Verifies: REQ-d00285-B, REQ-d00285-C, REQ-d00285-F, REQ-d00285-G, REQ-d00285-H, REQ-d00285-I
# Verifies: REQ-d00272-P
"""The preset listings are the findings report narrowed, not a second report.

`elspais unresolved`, `elspais malformed`, `elspais errors` and `elspais
uncited` each answer one question over the one findings stream. The tests here pin the property that
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
    _format_report,
    apply_finding_filter,
    preset_reference_checks,
    run_checks,
)
from elspais.graph.reference_faults import FaultClass
from elspais.utilities import findings as findings_module
from elspais.utilities.findings import PRESETS, REGISTRY, preset_checks, remedy_for

# The two reference listings and the checks each one names. A reference that
# read as an identifier and named nothing is unresolved; one that did not read
# as an identifier is malformed (REQ-d00272-P).
_UNRESOLVED_CHECKS = {
    "references.unknown_namespace",
    "references.unknown_requirement",
    "references.unknown_assertion",
}
_MALFORMED_CHECKS = {"references.malformed"}
_REFERENCE_PRESETS = {"unresolved": _UNRESOLVED_CHECKS, "malformed": _MALFORMED_CHECKS}

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


def _write_project(tmp_path: pathlib.Path, repo_root: pathlib.Path, code: str) -> pathlib.Path:
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
    (src / "m.py").write_text(code)
    return tmp_path


def _build(project_dir: pathlib.Path):
    from elspais.config import load_config
    from elspais.graph.factory import build_graph

    config_path = project_dir / ".elspais.toml"
    return build_graph(
        load_config(config_path),
        config_path=config_path,
        repo_root=project_dir,
        scan_code=True,
        scan_tests=False,
    )


@pytest.fixture(scope="module")
def _project_dir(tmp_path_factory, repo_root):
    return _write_project(tmp_path_factory.mktemp("preset_listings"), repo_root, _CODE)


@pytest.fixture(scope="module")
def faulted_graph(_project_dir):
    return _build(_project_dir)


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


# Verifies: REQ-d00285-F, REQ-d00272-P
def test_unresolved_selects_exactly_the_three_unknown_reference_classes():
    """The unresolved listing is the references that read and named nothing.

    Adding `spec.implements_resolve` and its siblings would list one
    unresolved target twice under two names, which is the double-count the
    class partition exists to prevent. A malformed reference never read as an
    identifier, so it is not among them.
    """
    assert set(preset_checks("unresolved")) == _UNRESOLVED_CHECKS
    assert {cls for cls, _name, _desc in preset_reference_checks("unresolved")} == {
        FaultClass.UNKNOWN_NAMESPACE,
        FaultClass.UNKNOWN_REQUIREMENT,
        FaultClass.UNKNOWN_ASSERTION,
    }


# Verifies: REQ-d00272-P
def test_malformed_selects_exactly_the_malformed_reference_class():
    assert set(preset_checks("malformed")) == _MALFORMED_CHECKS
    assert {cls for cls, _name, _desc in preset_reference_checks("malformed")} == {
        FaultClass.MALFORMED
    }


# Verifies: REQ-d00272-P
def test_the_unresolved_and_malformed_listings_are_disjoint():
    """No reference fault class is named by both listings, so one reference
    is never called both malformed and unresolved."""
    unresolved = set(preset_checks("unresolved"))
    malformed = set(preset_checks("malformed"))
    assert unresolved.isdisjoint(malformed)
    for _cls, name, _desc in _REFERENCE_CHECKS:
        assert not (name in unresolved and name in malformed), f"{name} is in both listings"


# Verifies: REQ-d00272-P
def test_a_forbidden_reference_is_in_no_preset():
    """A forbidden reference resolved; it is neither malformed nor unresolved,
    so no shortcut lists it and its remedy names the check itself."""
    for preset, names in PRESETS.items():
        assert "references.forbidden" not in names, f"{preset} lists references.forbidden"
    remedy = remedy_for("references.forbidden")
    assert remedy not in {f"elspais {preset}" for preset in PRESETS}
    assert "--check references.forbidden" in remedy


# Verifies: REQ-d00272-P
def test_an_unknown_preset_names_no_reference_checks():
    with pytest.raises(KeyError):
        preset_reference_checks("nonesuch")


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


# Verifies: REQ-d00285-F, REQ-d00272-P
def test_the_preset_table_is_refused_when_two_presets_claim_one_check(monkeypatch):
    """The shipped table is checked at import; a table naming one registered
    check under two presets is refused rather than counted twice."""
    monkeypatch.setattr(
        findings_module,
        "PRESETS",
        {
            "unresolved": ("references.unknown_requirement",),
            "malformed": ("references.malformed", "references.unknown_requirement"),
        },
    )
    with pytest.raises(ValueError, match="in both"):
        findings_module._check_presets()


# Verifies: REQ-d00285-F
def test_the_preset_table_is_refused_when_it_names_an_unregistered_check(monkeypatch):
    monkeypatch.setattr(findings_module, "PRESETS", {"unresolved": ("references.nonesuch",)})
    with pytest.raises(ValueError, match="not registered"):
        findings_module._check_presets()


# ---------------------------------------------------------------------------
# The listing keeps what a separate renderer dropped
# ---------------------------------------------------------------------------


# Verifies: REQ-d00285-C, REQ-d00272-P
@pytest.mark.parametrize("preset", sorted(_REFERENCE_PRESETS))
def test_a_reference_listing_carries_the_fault_class_and_codes(whole_run, preset):
    """Every finding names the class it reached and the codes reading it
    produced.

    A listing rendered separately from the report has to be handed each field
    a finding carries a second time; these are the two that went missing.
    """
    narrowed = apply_finding_filter(whole_run, FindingFilter.for_preset(preset)).report
    findings = [(c, f) for c in narrowed.checks for f in c.findings]
    assert findings, f"fixture must produce {preset} references"

    classes = {name for _cls, name, _desc in preset_reference_checks(preset)}
    assert classes == _REFERENCE_PRESETS[preset]
    for check, finding in findings:
        assert check.name in classes, f"{finding.message} is filed under {check.name}"
        assert check.remedy, f"{check.name} carries no remedy"
        assert finding.codes, (
            f"{finding.message} carries no diagnostic code; the class it reached "
            f"is knowable and was dropped"
        )
        assert finding.file_path, f"{finding.message} carries no location"


# Verifies: REQ-d00285-C
@pytest.mark.parametrize("preset", sorted(_REFERENCE_PRESETS))
def test_the_listing_reports_exactly_what_the_whole_report_reports(whole_run, preset):
    """The narrowed report and the whole report agree, finding for finding.

    Not merely in count: identity, severity, location and remedy all travel,
    because the listing is the same objects.
    """
    narrowed = apply_finding_filter(whole_run, FindingFilter.for_preset(preset)).report
    selected = set(preset_checks(preset))

    def shape(report):
        return sorted(
            (c.name, c.severity, c.remedy, f.message, f.file_path, f.line, tuple(f.codes))
            for c in report.checks
            if c.name in selected
            for f in c.findings
        )

    assert shape(narrowed) == shape(whole_run)
    assert shape(narrowed), "fixture must produce findings for this to mean anything"


# The citing line in `_CODE` of each faulted reference, by the check that
# raises it. `f5` cites a label that exists and raises nothing.
_FAULT_LINES = {
    "references.malformed": 1,
    "references.unknown_requirement": 6,
    "references.unknown_assertion": 11,
    "references.forbidden": 16,
}


def _listed_lines(output: str, fmt: str) -> dict[str, set[int]]:
    """The `src/m.py` lines a rendered listing names, by check."""
    import json
    import re

    listed: dict[str, set[int]] = {}
    if fmt == "json":
        for check in json.loads(output)["checks"]:
            for finding in check["findings"]:
                if finding["file_path"] == "src/m.py":
                    listed.setdefault(check["name"], set()).add(finding["line"])
        return listed
    current = None
    for line in output.splitlines():
        header = re.match(r"\s*\S+ (references\.\w+):", line)
        if header:
            current = header.group(1)
            continue
        location = re.match(r"\s*- src/m\.py:(\d+):", line)
        if location and current:
            listed.setdefault(current, set()).add(int(location.group(1)))
    return listed


# Verifies: REQ-d00272-P
@pytest.mark.parametrize("fmt", ["text", "json"])
@pytest.mark.parametrize("preset", sorted(_REFERENCE_PRESETS))
def test_each_reference_listing_names_only_its_own_population(whole_run, preset, fmt):
    """The unresolved listing names the reference that read and named nothing,
    the malformed listing the one that did not read, and neither names the
    forbidden one -- in every format the listing renders."""
    output = _format_report(
        whole_run,
        argparse.Namespace(format=fmt),
        filt=FindingFilter.for_preset(preset),
        verdict_over_filtered=True,
    )
    listed = _listed_lines(output, fmt)
    expected = {
        name: {line} for name, line in _FAULT_LINES.items() if name in _REFERENCE_PRESETS[preset]
    }
    assert listed == expected, f"`elspais {preset}` ({fmt}) listed {listed}"
    assert _FAULT_LINES["references.forbidden"] not in set().union(*listed.values())


# Verifies: REQ-d00285-C, REQ-d00272-P
@pytest.mark.parametrize("preset", sorted(_REFERENCE_PRESETS))
def test_the_mcp_tool_reports_the_same_findings_as_the_listing(
    faulted_graph, config, whole_run, preset
):
    """The MCP surface answers about each reference population from the same
    stream, so an agent and a person are never told different things about
    one reference."""
    from elspais.mcp.server import _get_preset_references

    result = _get_preset_references(faulted_graph, preset, config)
    selected = set(preset_checks(preset))

    from_mcp = sorted(
        (f["check"], f["severity"], f["remedy"], f["message"], f["file_path"], tuple(f["codes"]))
        for f in result[f"{preset}_references"]
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
    assert {c["name"] for c in result["checks"]} == _REFERENCE_PRESETS[preset]


# Verifies: REQ-d00272-P
def test_the_mcp_counts_agree_with_the_listings_and_omit_forbidden(
    faulted_graph, config, whole_run
):
    """The health counts an agent reads, the MCP listings and the CLI listings
    count the same references; the forbidden reference is counted by none."""
    from elspais.mcp.server import _get_preset_references, _reference_fault_counts

    counts = _reference_fault_counts(faulted_graph)
    for preset in _REFERENCE_PRESETS:
        narrowed = apply_finding_filter(whole_run, FindingFilter.for_preset(preset)).report
        from_cli = sum(len(c.findings) for c in narrowed.checks)
        from_mcp = _get_preset_references(faulted_graph, preset, config)["count"]
        assert from_cli == from_mcp == counts[f"{preset}_reference_count"], preset
        assert counts[f"has_{preset}_references"] is True

    assert counts["unresolved_reference_count"] == 2
    assert counts["malformed_reference_count"] == 1
    forbidden = [
        f for f in faulted_graph.unresolved_references() if f.fault_class is FaultClass.FORBIDDEN
    ]
    assert len(forbidden) == 1, "fixture must carry one forbidden reference"
    assert len(faulted_graph.unresolved_references()) == (
        counts["unresolved_reference_count"] + counts["malformed_reference_count"] + 1
    )


# Verifies: REQ-d00272-P
def test_graph_status_flags_each_population_on_its_own(faulted_graph):
    from elspais.mcp.server import _get_graph_status

    status = _get_graph_status(faulted_graph)
    assert status["has_unresolved_references"] is True
    assert status["has_malformed_references"] is True


# Verifies: REQ-d00285-G
@pytest.mark.parametrize(
    ("preset", "check"),
    [("unresolved", "unknown_requirement"), ("malformed", "malformed")],
)
def test_the_mcp_tool_names_a_class_the_project_turned_off(faulted_graph, config, preset, check):
    """A class set to `off` produced no findings, and the surface says which
    -- otherwise "none" and "not reported" read alike."""
    from elspais.mcp.server import _get_preset_references

    config["rules"]["references"][check] = "off"
    result = _get_preset_references(faulted_graph, preset, config)

    name = f"references.{check}"
    entry = next(c for c in result["checks"] if c["name"] == name)
    assert entry["skipped"] is True
    assert entry["count"] == 0
    assert not any(f["check"] == name for f in result[f"{preset}_references"])


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
    check it does not list -- a malformed reference among them -- must not
    decide its exit code, or the command stops being a predicate about the
    thing it is named for."""
    unrelated = HealthCheck(
        name="spec.hash_integrity",
        passed=False,
        message="stale",
        category="spec",
        severity="error",
    )
    malformed = HealthCheck(
        name="references.malformed",
        passed=False,
        message="1 reference(s): do not read as a reference",
        category="references",
        severity="error",
    )
    clean = HealthCheck(
        name="references.unknown_requirement",
        passed=True,
        message="none",
        category="references",
        severity="error",
    )
    report = _report(unrelated, malformed, clean)

    assert report.is_healthy is False
    narrowed = apply_finding_filter(report, FindingFilter.for_preset("unresolved")).report
    assert [c.name for c in narrowed.checks] == ["references.unknown_requirement"]
    assert narrowed.is_healthy is True
    malformed_only = apply_finding_filter(report, FindingFilter.for_preset("malformed")).report
    assert [c.name for c in malformed_only.checks] == ["references.malformed"]
    assert malformed_only.is_healthy is False


# Verifies: REQ-d00285-I
def test_a_preset_listing_discloses_which_listing_it_is_and_what_it_withheld():
    """A short list must not read as a clean run."""
    report = _report(
        HealthCheck(
            name="references.unknown_requirement",
            passed=False,
            message="1 reference",
            category="references",
            severity="error",
            findings=[HealthFinding(message="bad", file_path="src/m.py", line=6)],
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
    assert (
        "--check references.unknown_namespace references.unknown_requirement "
        "references.unknown_assertion" in disclosure
    )


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
    assert "malformed" in COMMAND_GROUPS
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("elspais.commands.broken")


# ---------------------------------------------------------------------------
# The two listings composed into one report
# ---------------------------------------------------------------------------

# One faulted reference of each population, cited alone.
_ONLY_UNKNOWN = "# Implements: REQ-d09999\ndef f():\n    pass\n"
_ONLY_MALFORMED = "# Implements: not a reference\ndef f():\n    pass\n"


def _composed_exit(monkeypatch, project_dir, graph, sections):
    from elspais.commands import report
    from elspais.config import load_config

    config = load_config(project_dir / ".elspais.toml")
    monkeypatch.chdir(project_dir)
    monkeypatch.setattr("elspais.graph.factory.build_graph", lambda *a, **k: graph)
    monkeypatch.setattr("elspais.config.get_config", lambda *a, **k: config)
    return report.run(sections, ["--format", "text"])


# Verifies: REQ-d00085-C, REQ-d00272-P
def test_composed_reference_listings_each_set_their_own_exit_bit(
    monkeypatch, capsys, _project_dir, faulted_graph
):
    """A graph holding both populations fails both sections, and the exit code
    carries the bit of each."""
    from elspais.commands.report import EXIT_BIT

    code = _composed_exit(monkeypatch, _project_dir, faulted_graph, ["unresolved", "malformed"])
    assert code == EXIT_BIT["unresolved"] | EXIT_BIT["malformed"]
    out = capsys.readouterr().out
    assert "Listing `unresolved`" in out
    assert "Listing `malformed`" in out


# Verifies: REQ-d00085-C, REQ-d00272-P
@pytest.mark.parametrize(
    ("code", "failing"),
    [(_ONLY_UNKNOWN, "unresolved"), (_ONLY_MALFORMED, "malformed")],
)
def test_a_reference_population_sets_only_its_own_sections_bit(
    monkeypatch, tmp_path, repo_root, code, failing
):
    """A graph holding only one population fails only the section naming it:
    an unresolved reference never sets the malformed bit, nor the reverse."""
    from elspais.commands.report import EXIT_BIT

    project_dir = _write_project(tmp_path, repo_root, code)
    graph = _build(project_dir)
    exit_code = _composed_exit(monkeypatch, project_dir, graph, ["unresolved", "malformed"])
    assert exit_code == EXIT_BIT[failing]


# ---------------------------------------------------------------------------
# Each command's help describes one population
# ---------------------------------------------------------------------------

# The phrase each population's description is written in.
_POPULATION_PHRASE = {
    "unresolved": "named nothing",
    "malformed": "did not read as an identifier",
}


def _help_description(capsys, command: str) -> str:
    """The summary and description of `elspais COMMAND --help`, one line."""
    import re

    from elspais.cli import main

    try:
        code = main([command, "--help"])
    except SystemExit as exc:
        code = exc.code
    assert code in (0, None)
    out = re.sub(r"\x1b\[[0-9;]*m", "", capsys.readouterr().out)
    description = out.split("\n", 1)[1]
    for box_start in ("\u256d", "options:"):
        if box_start in description:
            description = description.split(box_start, 1)[0]
    return " ".join(description.split())


# Verifies: REQ-d00272-P
@pytest.mark.parametrize("command", sorted(_POPULATION_PHRASE))
def test_each_listings_help_describes_only_its_own_population(capsys, command):
    """A sentence in one listing's help that speaks of the other population
    does so only to send the reader to the other listing."""
    (other,) = set(_POPULATION_PHRASE) - {command}
    description = _help_description(capsys, command)
    sentences = [s for s in description.split(". ") if s]
    assert sentences, f"`elspais {command} --help` printed no description"

    summary = sentences[0].lower()
    assert "reference" in summary
    for sentence in sentences:
        if f"`{other}`" in sentence:
            continue
        assert _POPULATION_PHRASE[other] not in sentence, (
            f"`elspais {command} --help` claims the {other} population: {sentence!r}"
        )
    assert any(f"`{other}`" in s and _POPULATION_PHRASE[other] in s for s in sentences), (
        f"`elspais {command} --help` does not send a reader to `{other}`"
    )
