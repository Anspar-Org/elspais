# Verifies: REQ-d00288-A, REQ-d00288-B, REQ-d00288-C, REQ-d00288-D, REQ-d00288-E
"""Reporting journeys that validate nothing.

A journey that validates nothing is complete on the page -- it has an
actor, a goal and steps -- and reaches no requirement and no figure, which
is why nothing else finds it. REQ-d00288 obliges the tool to report it, and
to separate three states a reader acts on differently:

- the declaration yields no target, because none was written or because
  what was written names nothing this estate holds (`uat.inert_journey`);
- the targets resolve but fall outside what the report counts, which is a
  question about the selection as much as about the journey
  (`uat.journey_scope`); and
- the target is a placeholder, so the journey is awaiting a requirement
  rather than missing one (`references.placeholder`).

These build a small on-disk project rather than reusing `canonical_graph`:
the estate under test is defined by the journeys it does NOT wire, which a
healthy canonical fixture (rightly) does not carry.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from elspais.commands.health import (
    HealthReport,
    check_inert_journeys,
    check_journey_scope,
    check_reference_placeholder,
    check_uat_coverage,
)

_CONFIG = """\
version = 5

[project]
name = "inert-journeys"
namespace = "REQ"

[id-patterns.assertions]
label_style = "uppercase"

[levels.prd]
rank = 1
letter = "p"
implements = []
expects_validation = true

[levels.dev]
rank = 2
letter = "d"
implements = ["dev", "prd"]

[scanning.spec]
directories = ["spec"]

[scanning.journey]
directories = ["spec"]

[scanning.code]
directories = ["src"]
"""

_SPEC = """\
# REQ-p00001: Widget

**Level**: prd | **Status**: Active | **Implements**: -

The system provides widgets.

## Assertions

A. The system SHALL frob.

*End* *Widget* | **Hash**: 00000000

# REQ-d00001: Widget detail

**Level**: dev | **Status**: Active | **Implements**: REQ-p00001-A

The widget detail.

## Assertions

A. The system SHALL detail.

*End* *Widget detail* | **Hash**: 00000000
"""

# One journey per state REQ-d00288 separates.
_JOURNEYS = """\
## JNY-001: Declares nothing

**Actor**: User
**Goal**: Use a widget

## Steps

1. Open the widget.

*End* *JNY-001*

## JNY-002: Declares a target this estate does not hold

**Actor**: User
**Goal**: Use a widget
Validates: REQ-p09999

## Steps

1. Open the widget.

*End* *JNY-002*

## JNY-003: Awaiting its requirement

**Actor**: User
**Goal**: Use a widget
Validates: <TBD>

## Steps

1. Open the widget.

*End* *JNY-003*

## JNY-004: Validates something counted

**Actor**: User
**Goal**: Use a widget
Validates: REQ-p00001

## Steps

1. Open the widget.

*End* *JNY-004*

## JNY-005: Validates outside the selection

**Actor**: User
**Goal**: Use a widget
Validates: REQ-d00001

## Steps

1. Open the widget.

*End* *JNY-005*

## JNY-006: Validates inside and outside the selection

**Actor**: User
**Goal**: Use a widget
Validates: REQ-p00001, REQ-d00001

## Steps

1. Open the widget.

*End* *JNY-006*
"""

# The placeholder written from a code annotation rather than a journey, so
# `references.placeholder` is asked of both surfaces that reach it.
_CODE = """\
# Implements: <not chosen yet>
def frob():
    pass
"""


def _write_project(root: Path, journeys: str) -> Path:
    project = root / "inert"
    (project / "spec").mkdir(parents=True)
    (project / "src").mkdir(parents=True)
    (project / ".elspais.toml").write_text(_CONFIG, encoding="utf-8")
    (project / "spec" / "spec.md").write_text(_SPEC, encoding="utf-8")
    (project / "spec" / "journeys.md").write_text(journeys, encoding="utf-8")
    (project / "src" / "widget.py").write_text(_CODE, encoding="utf-8")
    return project


def _build(project: Path):
    from elspais.config import load_config
    from elspais.graph.factory import build_graph

    config_path = project / ".elspais.toml"
    config = load_config(config_path)
    graph = build_graph(
        config,
        config_path=config_path,
        repo_root=project,
        scan_code=True,
        scan_tests=False,
    )
    return graph, config


@pytest.fixture(scope="module")
def project(tmp_path_factory) -> Path:
    return _write_project(tmp_path_factory.mktemp("journeys"), _JOURNEYS)


@pytest.fixture(scope="module")
def built(project):
    return _build(project)


@pytest.fixture
def graph(built):
    return built[0]


@pytest.fixture
def config(built):
    return copy.deepcopy(built[1])


def _reported(check) -> set[str]:
    return {f.node_id for f in check.findings}


# Verifies: REQ-d00288-A, REQ-d00288-C
def test_a_journey_that_validates_nothing_is_reported_and_a_working_one_is_not(graph, config):
    """Both states that yield no target are reported, and the two journeys
    that DO reach a requirement -- one counted, one outside the selection --
    are not: the check is about the absence of a relationship, not about
    what the relationship reaches."""
    check = check_inert_journeys(graph, config)

    assert check.passed is False
    assert _reported(check) == {"JNY-001", "JNY-002"}, (
        "JNY-004 validates something and JNY-005 validates something this "
        "report does not count; neither validates nothing"
    )


# Verifies: REQ-d00288-C
def test_the_two_ways_of_yielding_no_target_are_reported_apart(graph, config):
    """Only the author can repair either, but not by the same edit: one
    journey has no declaration to fix and the other has one that names
    nothing. Reported in identical words, a reader cannot tell which."""
    check = check_inert_journeys(graph, config)
    messages = {f.node_id: f.message for f in check.findings}

    assert "declares no validation target" in messages["JNY-001"]
    assert "declares no validation target" not in messages["JNY-002"]
    assert "REQ-p09999" not in messages["JNY-001"]


# Verifies: REQ-d00288-D
def test_a_journey_awaiting_its_requirement_is_not_reported_as_validating_nothing(graph, config):
    """A journey written ahead of the requirement it will validate is a
    legitimate state. Its author said so with a placeholder, and reporting
    it alongside the author who forgot would retire the distinction the
    placeholder exists to make."""
    inert = check_inert_journeys(graph, config)
    placeholder = check_reference_placeholder(graph, config)

    assert "JNY-003" not in _reported(inert)
    assert "JNY-003" in _reported(placeholder)
    awaiting = next(f for f in placeholder.findings if f.node_id == "JNY-003")
    assert "awaiting" in awaiting.message
    assert "<TBD>" in awaiting.message, "the placeholder is reported as its author wrote it"


# Verifies: REQ-d00287-I
def test_a_placeholder_in_a_journey_and_in_an_annotation_are_both_reported(graph, config):
    """A journey's `Validates:` and a code annotation's `Implements:` are
    two places an author declares a target, and a blank deliberately left
    stays visible in both."""
    check = check_reference_placeholder(graph, config)
    texts = {f.node_id: f.message for f in check.findings}

    assert "JNY-003" in texts
    annotation = [msg for node_id, msg in texts.items() if node_id.startswith("file:")]
    assert annotation, f"the code annotation's placeholder must be reported; got {texts}"
    assert "<not chosen yet>" in annotation[0]


# Verifies: REQ-d00287-H
def test_a_placeholder_wires_no_edge_and_reports_no_broken_reference(graph):
    """The placeholder is neither a reference nor a reference that failed:
    binding it would credit a requirement nobody has written, and reporting
    it as broken would call a deliberate blank a defect."""
    from elspais.graph.relations import EdgeKind

    journey = graph.find_by_id("JNY-003")
    assert journey is not None
    validating = [e for e in journey.iter_incoming_edges() if e.kind == EdgeKind.VALIDATES]
    assert validating == []

    broken = [br.target_id for br in graph.unresolved_references()]
    assert not any("TBD" in target or "not chosen" in target for target in broken), (
        f"a placeholder must reach no broken-reference report; got {broken}"
    )


def _heading_line(journey_id: str) -> int:
    """The 1-based line the journey's heading sits on in the fixture."""
    for number, text in enumerate(_JOURNEYS.splitlines(), start=1):
        if text.startswith(f"## {journey_id}:"):
            return number
    raise AssertionError(f"{journey_id} is not in the fixture")


# Verifies: REQ-d00288-B
@pytest.mark.parametrize(
    ("check_fn", "node_id"),
    [
        (check_inert_journeys, "JNY-001"),
        (check_inert_journeys, "JNY-002"),
        (check_reference_placeholder, "JNY-003"),
    ],
)
def test_a_reported_journey_names_the_file_and_line_it_was_written_at(
    graph, config, check_fn, node_id
):
    """A report naming the journey and not where it sits leaves a reader
    grepping an estate for it. The line is the journey's heading, read back
    out of the fixture so the expectation cannot drift from the input."""
    finding = next(f for f in check_fn(graph, config).findings if f.node_id == node_id)

    assert finding.file_path == "spec/journeys.md"
    assert finding.line == _heading_line(node_id)


# Verifies: REQ-d00288-C
def test_a_journey_validating_only_outside_the_selection_is_reported_apart(graph, config):
    """A different condition and a different remedy: the journey validates
    something, and the selection this run reports over does not reach it.
    It is answered by changing the question rather than the journey."""
    scope = check_journey_scope(graph, config)

    assert _reported(scope) == {"JNY-005"}, (
        "only the journey whose every target sits at a level this report "
        "does not count belongs here"
    )
    assert "REQ-d00001" in scope.findings[0].message
    assert "JNY-005" not in _reported(check_inert_journeys(graph, config))


# Verifies: REQ-d00288-C
def test_no_journey_is_reported_under_two_names(graph, config):
    """The three conditions partition the journeys they report: one remedy
    per journey, so a reader is never sent to two places for one edit."""
    reported = [
        _reported(check_inert_journeys(graph, config)),
        _reported(check_journey_scope(graph, config)),
        {n for n in _reported(check_reference_placeholder(graph, config)) if n.startswith("JNY-")},
    ]
    seen = [node for bucket in reported for node in bucket]

    assert len(seen) == len(set(seen)), f"a journey is reported twice; got {reported}"


# Verifies: REQ-d00288-C
def test_every_validated_requirement_counts_where_no_level_expects_validation(graph, config):
    """With nothing configured to expect validation there is no narrowing to
    apply, so every requirement a journey validates counts and no journey is
    reported for validating outside a selection that does not exist."""
    for level in config["levels"].values():
        level.pop("expects_validation", None)

    check = check_journey_scope(graph, config)

    assert check.passed is True
    assert check.findings == []


# Verifies: REQ-d00288-C
def test_a_journey_validating_nothing_is_reported_whatever_the_selection(graph, config):
    """The scope question is the selection's; the inert question is the
    journey's, and withdrawing the selection cannot repair a journey that
    declared no target."""
    for level in config["levels"].values():
        level.pop("expects_validation", None)

    assert _reported(check_inert_journeys(graph, config)) == {"JNY-001", "JNY-002"}


# Verifies: REQ-d00288-E
@pytest.mark.parametrize(
    "name", ["uat.inert_journey", "uat.journey_scope", "references.placeholder"]
)
def test_the_condition_is_informational_where_the_project_configures_nothing(graph, config, name):
    """Repositories carry journeys in these states today, and a rule that
    fails a run the first time one appears teaches projects to switch it
    off rather than to look at it."""
    checks = [
        check_inert_journeys(graph, config),
        check_journey_scope(graph, config),
        check_reference_placeholder(graph, config),
    ]
    check = next(c for c in checks if c.name == name)

    assert check.passed is False, f"{name} must actually have fired for this to mean anything"
    assert check.severity == "info"
    assert HealthReport(checks=checks).is_healthy, (
        "a failing informational check must leave the run's verdict alone"
    )


# Verifies: REQ-d00288-E
@pytest.mark.parametrize(
    "name", ["uat.inert_journey", "uat.journey_scope", "references.placeholder"]
)
def test_a_project_that_wants_the_condition_to_bite_says_so(graph, config, name):
    """Informational is the default, not the definition: the severity comes
    from the one authority, so raising it in the general table takes
    effect and the run's verdict follows."""
    config.setdefault("rules", {}).setdefault("severity", {})[name] = "error"

    checks = [
        check_inert_journeys(graph, config),
        check_journey_scope(graph, config),
        check_reference_placeholder(graph, config),
    ]
    check = next(c for c in checks if c.name == name)

    assert check.severity == "error"
    assert not HealthReport(checks=checks).is_healthy


# Verifies: REQ-d00288-A
def test_reporting_a_journey_that_validates_nothing_moves_no_coverage_figure(
    tmp_path_factory, graph, config
):
    """The report is a disclosure, never a credit or a discredit. An estate
    carrying the three journeys that validate nothing must reach exactly
    the UAT coverage figures it reaches without them -- otherwise a
    requirement's coverage would depend on journeys that reach it not at
    all."""
    without = _JOURNEYS.split("## JNY-004:")[1]
    trimmed = _write_project(tmp_path_factory.mktemp("counted-only"), f"## JNY-004:{without}")
    lean_graph, lean_config = _build(trimmed)

    full = check_uat_coverage(graph, config=config)
    lean = check_uat_coverage(lean_graph, config=lean_config)

    assert lean.details == full.details, (
        "every UAT coverage figure must be identical -- a journey that "
        "validates nothing may neither credit nor discredit one"
    )
    assert lean.message == full.message
    assert lean.details["total_assertions"] > 0, (
        "the comparison is only meaningful over an estate with something to count"
    )


# ---------------------------------------------------------------------------
# What a journey is judged against (REQ-d00288-F).
#
# Every journey declared is examined -- the selection narrows the list of
# requirements a journey is credited with, never which journeys are looked
# at. Being credited with one counted requirement is enough, and the report
# names that list so an empty one is stated rather than inferred.
# ---------------------------------------------------------------------------


# Verifies: REQ-d00288-F
@pytest.mark.parametrize("node_id", ["JNY-004", "JNY-006"])
def test_a_journey_credited_with_a_counted_requirement_is_reported_by_neither_check(
    graph, config, node_id
):
    """JNY-004 validates only a counted requirement; JNY-006 validates one
    counted and one the report does not count. Both are credited with at
    least one, which is what a journey is judged on -- reporting JNY-006
    would charge it for a requirement it validates over and above the one it
    was asked for."""
    reported = _reported(check_inert_journeys(graph, config)) | _reported(
        check_journey_scope(graph, config)
    )

    assert node_id not in reported, (
        f"{node_id} is credited with a counted requirement; got {reported}"
    )


# Verifies: REQ-d00288-F, REQ-d00288-C
def test_a_journey_credited_with_nothing_is_still_reported_beside_the_mixed_one(graph, config):
    """The control for the test above: JNY-005 differs from JNY-006 only by
    lacking the counted target, and it IS reported. Without this, the pair
    above would pass on a check that had stopped reporting anything."""
    assert _reported(check_journey_scope(graph, config)) == {"JNY-005"}


# Verifies: REQ-d00288-F
@pytest.mark.parametrize(
    ("check_fn", "node_id"),
    [(check_inert_journeys, "JNY-001"), (check_journey_scope, "JNY-005")],
)
def test_a_report_of_a_journey_states_that_it_is_credited_with_nothing(
    graph, config, check_fn, node_id
):
    """Both checks report a journey credited with no counted requirement,
    and both say so outright. Left to be inferred from a finding that
    happens to mention no requirement, an empty list reads like an omission
    from the message rather than a fact about the journey."""
    finding = next(f for f in check_fn(graph, config).findings if f.node_id == node_id)

    assert "in scope" in finding.message
    assert "none" in finding.message, (
        f"the empty credit list must be stated; got {finding.message!r}"
    )


# Verifies: REQ-d00288-F
def test_a_report_of_a_journey_names_the_levels_it_is_counted_over(graph, config):
    """A reader seeing `none` needs to know none of WHAT, without going to
    the configuration to find out which levels the run counted. Only `prd`
    expects validation here, so `dev` must not be named."""
    finding = next(f for f in check_journey_scope(graph, config).findings if f.node_id == "JNY-005")

    assert "(prd)" in finding.message, (
        f"the levels being counted must be named; got {finding.message!r}"
    )
    assert "dev" not in finding.message.split("in scope")[1]


# Verifies: REQ-d00288-F
def test_a_journey_is_credited_only_with_the_requirements_the_report_counts(graph, config):
    """The judging half of F. A journey naming one counted requirement and
    one uncounted one is credited with the first and not the second, which
    is what decides that it is reported by neither check."""
    from elspais.commands.health import _counted_targets, _validating_targets

    journey = graph.find_by_id("JNY-006")
    assert journey is not None
    validated = {node.id for node in _validating_targets(journey)}
    assert {"REQ-p00001", "REQ-d00001"} <= validated, (
        f"the fixture must name one counted and one uncounted target; got {validated}"
    )

    credited = {node.id for node in _counted_targets(_validating_targets(journey), config)}

    assert credited == {"REQ-p00001"}, (
        f"only the requirement at an expects_validation level is credited; got {credited}"
    )


# Verifies: REQ-d00288-F
def test_a_journey_validating_an_unselected_level_is_credited_where_nothing_is_selected(
    graph, config
):
    """JNY-005 validates only a `dev` requirement, which is exactly what the
    selection excludes when `prd` expects validation. Withdraw the selection
    and there is no narrowing to apply, so the same journey is credited with
    that requirement and reported by neither check."""
    assert "JNY-005" in _reported(check_journey_scope(graph, config)), (
        "JNY-005 must be reported under the selection, or withdrawing it proves nothing"
    )

    for level in config["levels"].values():
        level.pop("expects_validation", None)

    reported = _reported(check_inert_journeys(graph, config)) | _reported(
        check_journey_scope(graph, config)
    )
    assert "JNY-005" not in reported, f"got {reported}"
