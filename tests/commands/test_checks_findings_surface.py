# Verifies: REQ-d00285-A+B+C+G+H+I, REQ-d00085-K+M
"""`elspais checks` as the one findings surface.

The report used to hand a reader a count and keep the names: findings reached
`--format json` and `--format sarif` and no other format, while the hint at the
foot of the terse report promised that `elspais -v checks` would show detail.
These tests hold the promise -- that a finding renders wherever the report
renders, carrying the same identity, severity, location and remedy in each --
and hold the narrowing that lets a reader ask for a few of them.
"""

from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET

import pytest

from elspais.commands.health import (
    FindingFilter,
    HealthCheck,
    HealthFinding,
    HealthReport,
    _build_summary_line,
    _format_report,
    _render_sarif,
    _report_from_dict,
    apply_finding_filter,
)
from elspais.utilities.findings import NO_KNOWN_REMEDY, REGISTRY, remedy_for

# One finding a reader must be able to act on: it names a file, a line, the
# node it is about, and the diagnostic code it reached.
LOCATED = HealthFinding(
    message="REQ-d00001-A extra -- identifier followed by text [E_IDENTIFIER_WITH_TRAILING_TEXT]",
    file_path="spec/dev-cli.md",
    line=247,
    node_id="REQ-d00001",
    repo="core",
    codes=["E_IDENTIFIER_WITH_TRAILING_TEXT"],
)

# A second finding, in another file and another category, so a narrowing has
# something to leave behind.
ELSEWHERE = HealthFinding(
    message="target 'unit': result named 'login.spec.ts' matched no test",
    file_path=".test-results/junit.xml",
    line=12,
    node_id="result:unit:login",
    related=["tests/e2e/login.spec.ts"],
)


def _report() -> HealthReport:
    return HealthReport(
        checks=[
            HealthCheck(
                name="references.malformed",
                passed=False,
                message="1 reference(s): does not read as a reference",
                category="references",
                severity="warning",
                findings=[LOCATED],
            ),
            HealthCheck(
                name="tests.unmatched_results",
                passed=False,
                message="1 ingested result(s) matched no test",
                category="tests",
                severity="warning",
                findings=[ELSEWHERE],
            ),
            HealthCheck(
                name="spec.parseable",
                passed=True,
                message="Parsed 12 requirements",
                category="spec",
                severity="warning",
            ),
        ]
    )


def _args(**kwargs) -> argparse.Namespace:
    base = {
        "format": "text",
        "verbose": False,
        "quiet": False,
        "lenient": False,
        "include_passing_details": False,
        "severity": None,
        "category": None,
        "code": None,
        "file": None,
    }
    base.update(kwargs)
    return argparse.Namespace(**base)


# ---------------------------------------------------------------------------
# A finding reaches the formats a person reads
# ---------------------------------------------------------------------------


# Verifies: REQ-d00085-K, REQ-d00285-A
@pytest.mark.parametrize("fmt", ["text", "markdown"])
def test_a_finding_renders_under_verbose_carrying_its_location(fmt: str) -> None:
    """`-v` shows each failing check's findings, with the file and line."""
    out = _format_report(_report(), _args(format=fmt, verbose=True))

    assert "identifier followed by text" in out, "the finding's own words reach the report"
    assert "spec/dev-cli.md:247" in out, "and the place a reader must go to act on it"
    assert "REQ-d00001" in out, "and what it is about"


# Verifies: REQ-d00085-K
@pytest.mark.parametrize("fmt", ["text", "markdown"])
def test_the_default_report_stays_terse(fmt: str) -> None:
    """Without `-v` the report is one line per check, as it has always been."""
    out = _format_report(_report(), _args(format=fmt))

    assert "1 reference(s): does not read as a reference" in out, "the check line stays"
    assert "spec/dev-cli.md:247" not in out, "the findings do not"


# Verifies: REQ-d00085-K
def test_the_verbose_hint_is_no_longer_a_promise_the_report_breaks() -> None:
    """The terse report points at `-v checks`; running it must show more."""
    terse = _format_report(_report(), _args())
    verbose = _format_report(_report(), _args(verbose=True))

    assert "elspais -v checks" in terse, "the terse report still points the reader at -v"
    assert len(verbose) > len(terse)
    assert "spec/dev-cli.md:247" in verbose


# Verifies: REQ-d00085-M
@pytest.mark.parametrize("fmt", ["text", "markdown"])
def test_a_passing_checks_findings_stay_behind_their_own_request(fmt: str) -> None:
    """Verbosity is not the request for passing detail; they are separate."""
    report = _report()
    report.checks[2].findings = [HealthFinding(message="REQ-p00001 parsed", file_path="spec/a.md")]

    verbose_only = _format_report(report, _args(format=fmt, verbose=True))
    on_request = _format_report(
        report, _args(format=fmt, verbose=True, include_passing_details=True)
    )

    assert "REQ-p00001 parsed" not in verbose_only
    assert "REQ-p00001 parsed" in on_request


# ---------------------------------------------------------------------------
# The same finding, whatever the format
# ---------------------------------------------------------------------------


# Verifies: REQ-d00285-C
def test_identity_severity_location_and_remedy_agree_across_formats() -> None:
    """One finding, four renderings, and no disagreement between them.

    This is REQ-d00285-C stated directly: a finding reaching one format and
    not another is, to the reader of the quieter one, a finding never raised.
    """
    report = _report()
    check = report.checks[0]

    text = _format_report(report, _args(verbose=True))
    markdown = _format_report(report, _args(format="markdown", verbose=True))
    payload = json.loads(_format_report(report, _args(format="json")))
    sarif = json.loads(_render_sarif(report))
    junit = ET.fromstring(_format_report(report, _args(format="junit")))

    # -- identity
    for rendering in (text, markdown):
        assert LOCATED.node_id in rendering
        assert check.name in rendering
    json_check = next(c for c in payload["checks"] if c["name"] == check.name)
    assert json_check["findings"][0]["node_id"] == LOCATED.node_id
    sarif_result = next(r for r in sarif["runs"][0]["results"] if r["ruleId"] == check.name)
    assert sarif_result["properties"]["nodeId"] == LOCATED.node_id

    # -- severity
    assert json_check["severity"] == check.severity == "warning"
    assert sarif_result["level"] == "warning"
    assert junit.find(f".//testcase[@name='{check.name}']/system-err") is not None

    # -- location
    assert "spec/dev-cli.md:247" in text
    assert "spec/dev-cli.md:247" in markdown
    assert json_check["findings"][0]["file_path"] == LOCATED.file_path
    assert json_check["findings"][0]["line"] == LOCATED.line
    location = sarif_result["locations"][0]["physicalLocation"]
    assert location["artifactLocation"]["uri"] == LOCATED.file_path
    assert location["region"]["startLine"] == LOCATED.line

    # -- remedy
    remedy = remedy_for(check.name)
    assert remedy and remedy != NO_KNOWN_REMEDY, "this check has a known remedy to carry"
    assert remedy in text
    assert remedy in markdown
    assert json_check["remedy"] == remedy
    assert sarif_result["properties"]["remedy"] == remedy
    rule = next(r for r in sarif["runs"][0]["tool"]["driver"]["rules"] if r["id"] == check.name)
    assert rule["help"]["text"] == remedy
    system_err = junit.find(f".//testcase[@name='{check.name}']/system-err")
    assert remedy in (system_err.text or "")


# Verifies: REQ-d00285-B
def test_a_check_with_no_recorded_remedy_says_that_none_is_known() -> None:
    """Silence about a remedy is indistinguishable from a forgotten one."""
    report = HealthReport(
        checks=[
            HealthCheck(
                name="worktree.status",
                passed=False,
                message="uncommitted changes",
                category="environment",
                severity="warning",
                findings=[HealthFinding(message="spec/a.md modified", file_path="spec/a.md")],
            )
        ]
    )

    text = _format_report(report, _args(verbose=True))
    payload = json.loads(_format_report(report, _args(format="json")))

    assert NO_KNOWN_REMEDY in text
    assert payload["checks"][0]["remedy"] == NO_KNOWN_REMEDY


# Verifies: REQ-d00285-B
def test_the_remedy_reaches_a_check_whose_name_is_composed() -> None:
    """A name built at run time is a registered name like any other.

    The table the text renderer used to consult was keyed by literal name, so
    every check whose name is composed from a category and a status role
    silently carried no remedy at all.
    """
    check = HealthCheck(
        name="code.retired_references",
        passed=False,
        message="2 reference(s) to retired requirements",
        category="code",
        severity="warning",
    )
    assert check.remedy == REGISTRY["code.retired_references"].remedy
    assert check.remedy.strip(), "a composed name reaches the registry like any other"


# Verifies: REQ-d00285-C
def test_remedy_and_codes_survive_the_serving_round_trip() -> None:
    """A report computed by a daemon renders as one computed here.

    Every report reaches the renderer through `to_dict()` and back, so a value
    the round trip drops is a value the served path renders without and the
    local path renders with.
    """
    restored = _report_from_dict(_report().to_dict())

    assert restored.checks[0].remedy == remedy_for("references.malformed")
    assert restored.checks[0].findings[0].codes == LOCATED.codes
    assert restored.checks[0].findings[0].file_path == LOCATED.file_path
    assert restored.checks[1].findings[0].related == ELSEWHERE.related


# ---------------------------------------------------------------------------
# Narrowing the report
# ---------------------------------------------------------------------------


# Verifies: REQ-d00285-C+G
@pytest.mark.parametrize(
    "flags,kept,dropped",
    [
        ({"severity": ["error"]}, [], ["references.malformed", "tests.unmatched_results"]),
        (
            {"severity": ["warning"]},
            ["references.malformed", "tests.unmatched_results"],
            [],
        ),
        ({"category": ["tests"]}, ["tests.unmatched_results"], ["references.malformed"]),
        (
            {"code": ["E_IDENTIFIER_WITH_TRAILING_TEXT"]},
            ["references.malformed"],
            ["tests.unmatched_results"],
        ),
        ({"code": ["E_NOT_RAISED"]}, [], ["references.malformed"]),
        ({"file": ["spec/*.md"]}, ["references.malformed"], ["tests.unmatched_results"]),
        ({"file": [".test-results/*"]}, ["tests.unmatched_results"], ["references.malformed"]),
    ],
)
def test_each_filter_narrows(flags: dict, kept: list[str], dropped: list[str]) -> None:
    outcome = apply_finding_filter(_report(), FindingFilter.from_args(_args(**flags)))
    names = [c.name for c in outcome.report.checks]

    for name in kept:
        assert name in names, f"{flags} should have kept {name}"
    for name in dropped:
        assert name not in names, f"{flags} should have dropped {name}"


# Verifies: REQ-d00285-G
def test_filters_compose_as_conditions_met_at_once() -> None:
    """Values within one filter are alternatives; filters are conditions."""
    both = apply_finding_filter(
        _report(),
        FindingFilter.from_args(_args(category=["references"], file=[".test-results/*"])),
    )
    assert both.report.checks == [], "no finding is in both a spec file and a results file"

    either = apply_finding_filter(
        _report(),
        FindingFilter.from_args(_args(file=["spec/*.md", ".test-results/*"])),
    )
    assert len(either.report.checks) == 2


# Verifies: REQ-d00285-G
@pytest.mark.parametrize("fmt", ["text", "markdown"])
def test_a_narrowed_report_says_what_it_withheld(fmt: str) -> None:
    """A report showing some of what it found and not saying so reads as clean."""
    out = _format_report(_report(), _args(format=fmt, category=["tests"]))

    assert "of 3 checks" in out
    assert "--category tests" in out


# Verifies: REQ-d00285-G
def test_a_narrowed_json_report_carries_the_narrowing() -> None:
    payload = json.loads(_format_report(_report(), _args(format="json", category=["tests"])))

    assert payload["filter"]["category"] == ["tests"]
    assert payload["filter"]["checks_total"] == 3
    assert payload["filter"]["checks_shown"] == 1
    assert [c["name"] for c in payload["checks"]] == ["tests.unmatched_results"]


# Verifies: REQ-d00285-G
def test_naming_a_finding_by_code_renders_it_without_asking_for_verbosity() -> None:
    """A reader who named the code asked for those findings, not for a count."""
    out = _format_report(_report(), _args(code=["E_IDENTIFIER_WITH_TRAILING_TEXT"]))

    assert "spec/dev-cli.md:247" in out


# Verifies: REQ-d00285-G
def test_narrowing_does_not_move_the_verdict() -> None:
    """A filter chooses what to look at, never what the run found."""
    report = _report()
    assert report.failed == 0 and report.warnings == 2

    outcome = apply_finding_filter(report, FindingFilter.from_args(_args(category=["tests"])))

    assert outcome.report is not report
    assert report.warnings == 2, "the report the exit code is taken from is untouched"
    assert outcome.findings_total == 2
    assert outcome.findings_shown == 1


# Verifies: REQ-d00285-G
@pytest.mark.parametrize(
    "flags,expected",
    [
        ({"severity": ["fatal"]}, "--severity fatal"),
        ({"category": ["speling"]}, "--category speling"),
    ],
)
def test_a_name_the_vocabulary_does_not_admit_is_refused(flags: dict, expected: str) -> None:
    """Selecting nothing must not look like finding nothing."""
    problems = FindingFilter.from_args(_args(**flags)).unadmitted()

    assert problems and problems[0].startswith(expected)


# Verifies: REQ-d00285-G
def test_a_code_or_path_is_not_judged_against_a_fixed_vocabulary() -> None:
    """Codes and paths are values the estate carries, not a list the tool owns."""
    filt = FindingFilter.from_args(_args(code=["E_ANYTHING"], file=["whatever/*"]))
    assert filt.unadmitted() == []


# Verifies: REQ-d00285-G
@pytest.mark.parametrize("fmt", ["text", "markdown"])
def test_a_narrowed_report_still_states_the_whole_runs_verdict(fmt: str) -> None:
    """The summary line speaks for the run, not for the part being looked at.

    A filter that also moved the verdict would let a reader narrow their way
    to a clean-looking report over a run that failed.
    """
    report = _report()
    whole = _format_report(report, _args(format=fmt))
    narrowed = _format_report(report, _args(format=fmt, category=["tests"]))

    verdict = _build_summary_line(report)
    assert verdict in whole
    assert verdict in narrowed


# Verifies: REQ-d00285-G
def test_a_narrowed_json_report_still_states_the_whole_runs_verdict() -> None:
    whole = json.loads(_format_report(_report(), _args(format="json")))
    narrowed = json.loads(_format_report(_report(), _args(format="json", category=["tests"])))

    assert narrowed["healthy"] == whole["healthy"]
    assert narrowed["summary"] == whole["summary"]
    assert len(narrowed["checks"]) == 1


# Verifies: REQ-d00085-K+M, REQ-d00285-A
def test_an_info_check_that_reported_a_condition_shows_its_findings_under_verbose() -> None:
    """Loudness is not the question; whether the check passed is.

    An info-severity check that found something has findings a reader came
    for. Gating them behind the request for PASSING detail hid the largest
    finding sets the tool produces -- `references.undeclared` among them --
    from every reader who asked for detail the ordinary way.
    """
    report = HealthReport(
        checks=[
            HealthCheck(
                name="references.undeclared",
                passed=False,
                message="3 comment(s) cite a requirement without declaring a relationship",
                category="references",
                severity="info",
                findings=[LOCATED],
            )
        ]
    )

    assert "spec/dev-cli.md:247" not in _format_report(report, _args())
    assert "spec/dev-cli.md:247" in _format_report(report, _args(verbose=True))


# ---------------------------------------------------------------------------
# The filed formats: the verdict, and the disclosure
# ---------------------------------------------------------------------------


def _narrowable() -> HealthReport:
    """A failing run in one category and a clean check in another.

    So a narrowing can be asked for that leaves the failure behind entirely.
    """
    return HealthReport(
        checks=[
            HealthCheck(
                name="spec.hash_integrity",
                passed=False,
                message="1 requirement(s) have stale hashes",
                category="spec",
                severity="error",
                findings=[HealthFinding(message="REQ-d00001 stale", file_path="spec/r.md", line=3)],
            ),
            HealthCheck(
                name="code.orphans",
                passed=True,
                message="no orphaned code references",
                category="code",
                severity="warning",
            ),
        ]
    )


# Verifies: REQ-d00285-H
def test_a_narrowed_junit_document_still_reaches_the_whole_runs_verdict() -> None:
    """A CI consumer reads the document, never the exit code.

    A JUnit file whose verdict came from the checks that survived the reader's
    narrowing would report green for a run that failed -- and the narrower the
    question, the greener the answer.
    """
    report = _narrowable()
    assert report.failed == 1, "the run failed, whatever is asked to be shown"

    narrowed = ET.fromstring(_format_report(report, _args(format="junit", category=["code"])))
    assert narrowed.findall(".//failure"), (
        "the failing check was narrowed away, but the run it belongs to still failed"
    )

    # And the same document over a run that did not fail stays green, so the
    # verdict is the run's and not a constant.
    clean = HealthReport(checks=[_narrowable().checks[1]])
    green = ET.fromstring(_format_report(clean, _args(format="junit", category=["code"])))
    assert green.findall(".//failure") == []


# Verifies: REQ-d00285-I
@pytest.mark.parametrize("fmt", ["junit", "sarif"])
def test_a_narrowed_filed_report_discloses_the_narrowing_and_its_extent(fmt: str) -> None:
    """A filed document holding fewer findings than the run produced, saying
    nothing about it, cannot be told from a run that found fewer."""
    report = _narrowable()
    args = _args(format=fmt, category=["code"])
    expected = apply_finding_filter(report, FindingFilter.from_args(args)).disclosure()
    assert expected, "this narrowing is one that withholds something"

    out = _format_report(report, args)
    assert expected in out, f"{fmt} does not disclose the narrowing"
    assert "--category code" in out, "nor how to ask for the same view again"

    whole = _format_report(report, _args(format=fmt))
    assert "of 2 checks" not in whole, "an unnarrowed run has no narrowing to disclose"


# ---------------------------------------------------------------------------
# The severity a finding carries, in the formats that had dropped it
# ---------------------------------------------------------------------------


def _one_failing(severity: str) -> HealthReport:
    return HealthReport(
        checks=[
            HealthCheck(
                name="spec.hash_integrity",
                passed=False,
                message="1 requirement(s) have stale hashes",
                category="spec",
                severity=severity,
            )
        ]
    )


# Verifies: REQ-d00285-C
def test_a_markdown_report_tells_a_failing_error_from_a_failing_warning() -> None:
    """An unticked box says the check did not pass, not how much it matters.

    Rendered with the box alone, an error and a warning are the same line, so
    a reader of the markdown cannot recover the severity every other format
    carries.
    """
    name = "spec.hash_integrity"

    def line(out: str) -> str:
        return next(ln for ln in out.splitlines() if name in ln)

    error_md = line(_format_report(_one_failing("error"), _args(format="markdown")))
    warning_md = line(_format_report(_one_failing("warning"), _args(format="markdown")))

    assert error_md != warning_md, "markdown renders both severities identically"

    # And the severity it shows is the one the text report shows, so the two
    # do not disagree about it either.
    error_text = line(_format_report(_one_failing("error"), _args(format="text")))
    warning_text = line(_format_report(_one_failing("warning"), _args(format="text")))
    for md, text in ((error_md, error_text), (warning_md, warning_text)):
        token = text.strip().split()[0]
        assert token in md, f"the text report marks this check {token!r}; markdown does not"


# Verifies: REQ-d00285-C
@pytest.mark.parametrize(
    "passed,flags",
    [
        (False, {}),
        (True, {"include_passing_details": True}),
    ],
    ids=["a-condition-reported-at-info", "a-passing-checks-findings-on-request"],
)
def test_a_junit_finding_carries_its_location_and_remedy_however_it_is_reported(
    passed: bool, flags: dict
) -> None:
    """The quiet element is still an element the reader acts from.

    `<system-out>` is where an info-severity check and a passing check's
    requested detail report, and a finding that reaches it stripped of its
    location and its remedy is a finding the reader of this format cannot act
    on -- while the reader of the text report can.
    """
    name = "references.undeclared"
    report = HealthReport(
        checks=[
            HealthCheck(
                name=name,
                passed=passed,
                message="3 comment(s) cite a requirement without declaring a relationship",
                category="references",
                severity="info",
                findings=[LOCATED],
            )
        ]
    )

    root = ET.fromstring(_format_report(report, _args(format="junit", **flags)))
    sys_out = root.find(f".//testcase[@name='{name}']/system-out")
    assert sys_out is not None and sys_out.text
    body = sys_out.text

    assert "spec/dev-cli.md:247" in body, "the place the reader must go was dropped"
    assert remedy_for(name) in body, "the action available to resolve it was dropped"
    assert "E_IDENTIFIER_WITH_TRAILING_TEXT" in body, "the code it reached was dropped"


# ---------------------------------------------------------------------------
# One invocation, read whole: a repeated selector accumulates
# ---------------------------------------------------------------------------
#
# `checks` narrows the findings it presents by severity, category, check name,
# diagnostic code and location; `--treat-active` widens which statuses count.
# All six are spelled the way a scope over requirements is -- values
# space-separated, the flag repeated, or both -- and a flag that kept only its
# last occurrence would put a narrowing the vocabulary admits out of a reader's
# reach while looking like the whole invocation had been read.
#
# NOTE: no assertion in spec/ governs the spelling of these six flags.
# REQ-d00278-C states it for a SCOPE over requirements, which these are not,
# and REQ-d00285-C -- the assertion `health.py` and `args.py` cite for this
# change -- is about a finding carrying the same identity, severity, location
# and remedy in every format. These tests therefore carry no `Verifies:` tag:
# the behaviour is real and silent when broken, but it is not yet asserted.

# The five selectors, under the name the invocation spells and the name the
# filter holds them under.
CHECKS_SELECTORS = [
    ("severity", "severities"),
    ("category", "categories"),
    ("check", "names"),
    ("code", "codes"),
    ("file", "paths"),
]


@pytest.mark.parametrize("field,attr", CHECKS_SELECTORS)
@pytest.mark.parametrize(
    "raw,expected",
    [
        ([["error"], ["warning"]], ("error", "warning")),
        ([["error", "warning"]], ("error", "warning")),
        ([["error"], ["warning", "info"]], ("error", "warning", "info")),
        (["error", "warning"], ("error", "warning")),
    ],
)
def test_a_repeated_checks_selector_accumulates(field, attr, raw, expected) -> None:
    """The values are asserted exactly rather than by count: a reading that
    kept the inner lists whole would carry ``"['error']"`` -- a severity no
    check can ever carry -- and a count would not notice."""
    filt = FindingFilter.from_args(_args(**{field: raw}))
    assert getattr(filt, attr) == expected


@pytest.mark.parametrize("field,attr", CHECKS_SELECTORS)
def test_a_selector_named_with_nothing_narrows_nothing(field, attr) -> None:
    for raw in (None, [], [[]], [""], [[" "]]):
        filt = FindingFilter.from_args(_args(**{field: raw}))
        assert getattr(filt, attr) == (), raw
        assert filt.active is False, raw


def test_the_cli_reads_a_repeated_selector_as_one_narrowing() -> None:
    """Through the real CLI path, not a hand-built namespace: the accumulation
    lives in the dataclass annotation as much as in the reading."""
    import tyro

    from elspais.cli import _to_namespace
    from elspais.commands.args import GlobalArgs

    repeated = _to_namespace(
        tyro.cli(
            GlobalArgs,
            args=[
                "checks",
                "--check",
                "references.malformed",
                "--check",
                "tests.unmatched_results",
            ],
        )
    )
    spaced = _to_namespace(
        tyro.cli(
            GlobalArgs,
            args=["checks", "--check", "references.malformed", "tests.unmatched_results"],
        )
    )
    expected = ("references.malformed", "tests.unmatched_results")
    assert FindingFilter.from_args(repeated).names == expected
    assert FindingFilter.from_args(spaced).names == expected


@pytest.mark.parametrize(
    "raw",
    [
        [["draft"], ["review", "active"]],
        [["draft", "review", "active"]],
        ["draft", "review", "active"],
    ],
)
def test_treat_active_accumulates_into_the_counted_statuses(raw) -> None:
    """``_status_flags`` title-cases what it gathers, so a nested list that
    survived unflattened would arrive as ``"['draft']"`` -- a status no
    requirement carries, and one a count of three would not tell apart."""
    from elspais.commands.health import _status_flags

    assert _status_flags(argparse.Namespace(treat_active=raw)) == {"Draft", "Review", "Active"}


def test_treat_active_is_disclosed_as_the_reader_spelled_it() -> None:
    """The report says which flags produced it. A disclosure naming one of two
    statuses describes a run that did not happen."""
    out = _format_report(_report(), _args(treat_active=[["Draft"], ["Review"]]))
    assert "--treat-active Draft Review" in out


@pytest.mark.parametrize("command", ["checks", "gaps", "uncovered"])
def test_the_cli_reads_a_repeated_treat_active_as_one_widening(command) -> None:
    """Through the real CLI path: the accumulation lives in each command's
    dataclass annotation as much as in the reading, and the flag is declared
    once per command -- so an annotation missed on one of them would widen the
    counted set differently depending on which report was asked for."""
    import tyro

    from elspais.cli import _to_namespace
    from elspais.commands.args import GlobalArgs
    from elspais.commands.health import _status_flags

    repeated = _to_namespace(
        tyro.cli(GlobalArgs, args=[command, "--treat-active", "Draft", "--treat-active", "Review"])
    )
    spaced = _to_namespace(
        tyro.cli(GlobalArgs, args=[command, "--treat-active", "Draft", "Review"])
    )
    assert _status_flags(repeated) == {"Draft", "Review"}
    assert _status_flags(spaced) == {"Draft", "Review"}
