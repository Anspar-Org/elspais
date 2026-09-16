# Verifies: REQ-p00019-A, REQ-p00002-A
"""Tests for the single status selector on the coverage commands, and for
``errors`` having no status selector at all.

``--treat-active <S...>``
    Treat the named statuses as committed/active-like. WIDENS the counted
    set beyond the Active baseline. Offered ONLY on the six coverage
    commands (``checks``, ``gaps``, ``uncovered``, ``untested``,
    ``unvalidated``, ``failing``), where an active-vs-excluded distinction
    exists.

``errors`` offers no status option. It weighs every requirement whatever its
status, so its listing accounts for exactly what ``checks`` counts. Neither
``--status`` nor a narrowing selector exists on any of these seven commands.
(The unrelated ``elspais edit --status``, which sets a requirement's Status
value, is out of scope here and is neither tested nor asserted about.)

The engine-compatible compute functions carry the same surface in their
``params`` dicts: the coverage path reads ``params["treat_active"]``, and
``compute_errors`` reads no status key.
"""

from __future__ import annotations

import dataclasses
import os
from pathlib import Path

import pytest

# ─────────────────────────────────────────────────────────────────────────────
# Fixture project
# ─────────────────────────────────────────────────────────────────────────────

# require_hash is stated explicitly so the format rule definitely fires on
# every requirement in the fixture (none of them carry a hash). Changelog
# enforcement is off so the hash defect is the only violation in play.
CONFIG_TOML = """\
version = 5

[project]
name = "test"
namespace = "REQ"

[scanning.spec]
directories = ["spec"]

[changelog]
hash_current = false

[rules.format]
require_hash = true
"""

# Three requirements spanning the three role classes that matter here:
# Active (counted by default), Draft (PROVISIONAL — excluded from coverage
# by default, promotable by the widening option) and Deprecated (RETIRED —
# excluded by default and NOT promoted by naming Draft).
#
# The assertion counts deliberately differ (1 / 2 / 3). The assertion total
# is therefore a fingerprint of exactly WHICH requirements were counted.
ACTIVE_ID = "REQ-d00001"
DRAFT_ID = "REQ-d00002"
DEPRECATED_ID = "REQ-d00003"

SPEC_MD = """\
# REQ-d00001: Active Requirement

**Level**: DEV | **Status**: Active | **Implements**: -

Body text.

## Assertions

A. The system shall do the active thing.

*End* *Active Requirement*
---

# REQ-d00002: Draft Requirement

**Level**: DEV | **Status**: Draft | **Implements**: -

Body text.

## Assertions

A. The system shall do the first draft thing.

B. The system shall do the second draft thing.

*End* *Draft Requirement*
---

# REQ-d00003: Deprecated Requirement

**Level**: DEV | **Status**: Deprecated | **Implements**: -

Body text.

## Assertions

A. The system shall do the first deprecated thing.

B. The system shall do the second deprecated thing.

C. The system shall do the third deprecated thing.

*End* *Deprecated Requirement*
---
"""


def _make_project(tmp_path: Path) -> Path:
    """Create a minimal on-disk project holding the three-status spec file."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / ".elspais.toml").write_text(CONFIG_TOML)
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()
    (spec_dir / "requirements.md").write_text(SPEC_MD)
    return tmp_path


@pytest.fixture
def project(tmp_path):
    """The on-disk project root."""
    return _make_project(tmp_path)


@pytest.fixture
def built(project):
    """(graph, config) built from the fixture project, cwd pinned to it."""
    from elspais.config import get_config
    from elspais.graph.factory import build_graph

    old_cwd = os.getcwd()
    os.chdir(project)
    try:
        config = get_config(project / ".elspais.toml")
        graph = build_graph(
            spec_dirs=[project / "spec"],
            config_path=project / ".elspais.toml",
            repo_root=project,
            scan_code=False,
            scan_tests=False,
        )
        yield graph, config
    finally:
        os.chdir(old_cwd)


def _implemented_counts(graph, config, treat_active: tuple[str, ...] = ()) -> tuple[int, float]:
    """Run the checks compute path and return the Implemented dimension's
    (requirement count, assertion count) — the counted denominator.
    """
    from elspais.commands._requests import ChecksRequest
    from elspais.commands.health import compute_checks

    report = compute_checks(graph, config, ChecksRequest(treat_active=treat_active))
    for check in report["checks"]:
        if check["name"] == "code.implemented":
            details = check["details"]
            return details["total_requirements"], details["total_assertions"]
    raise AssertionError(
        "compute_checks produced no 'code.implemented' check; got "
        f"{[c['name'] for c in report['checks']]}"
    )


def _error_req_ids(graph, config) -> list[str]:
    """Requirement IDs carrying a format error, as `elspais errors` lists them.

    The listing is the findings report narrowed to the `errors` preset, so
    this reads the same checks the command does rather than a second
    collection walking the graph again.
    """
    from elspais.commands.health import (
        FindingFilter,
        HealthReport,
        apply_finding_filter,
        run_checks,
    )

    report = HealthReport()
    for check in run_checks(graph, config):
        report.add(check)
    narrowed = apply_finding_filter(report, FindingFilter.for_preset("errors")).report
    return sorted(
        {
            f.node_id
            for c in narrowed.checks
            if c.name == "spec.format_rules"
            for f in c.findings
            if f.node_id
        }
    )


# ─────────────────────────────────────────────────────────────────────────────
# Surface: which options each command offers
# ─────────────────────────────────────────────────────────────────────────────

COVERAGE_ARG_CLASSES = [
    "ChecksArgs",
    "GapsArgs",
    "UncoveredArgs",
    "UntestedArgs",
    "UnvalidatedArgs",
    "FailingArgs",
]


class TestOptionSurface:
    """Pins which status selector each command's CLI dataclass exposes."""

    @pytest.mark.parametrize("class_name", COVERAGE_ARG_CLASSES)
    # Verifies: REQ-d00278-B
    def test_coverage_commands_separate_measurement_from_emission(self, class_name):
        """A coverage command offers two status options answering two questions.

        ``treat_active`` widens what COUNTS: it promotes a status so requirements
        carrying it are measured alongside Active ones. ``status`` selects what is
        EMITTED: the requirements this report is about at all. They are not two
        spellings of one selector, which is why a narrowing ``only_status`` --
        which would have been a second, ambiguous way to say ``status`` -- still
        does not exist.
        """
        from elspais.commands import args as args_mod

        cls = getattr(args_mod, class_name)
        fields = {f.name for f in dataclasses.fields(cls)}

        assert "treat_active" in fields, (
            f"{class_name} must offer --treat-active (widening selector); fields were "
            f"{sorted(fields)}"
        )
        assert "only_status" not in fields, (
            f"{class_name} must not offer --only-status; fields were {sorted(fields)}"
        )
        if class_name == "ChecksArgs":
            # checks reaches a verdict over the whole estate; it does not yet
            # honour a scope, and a flag it cannot honour would be worse than
            # its absence.
            assert "status" not in fields
            return
        assert "status" in fields, (
            f"{class_name} must offer --status to scope what it emits; fields were {sorted(fields)}"
        )
        assert "not_status" in fields, (
            f"{class_name} must offer --not-status; fields were {sorted(fields)}"
        )

    # Verifies: REQ-d00285-C
    def test_errors_exposes_no_status_option(self):
        """``errors`` weighs every requirement whatever its status, so it
        carries no status selector of any kind.
        """
        from elspais.commands.args import ErrorsArgs

        fields = {f.name for f in dataclasses.fields(ErrorsArgs)}

        assert "status" not in fields, (
            f"ErrorsArgs must not offer --status; fields were {sorted(fields)}"
        )
        assert "treat_active" not in fields, (
            "ErrorsArgs must NOT offer --treat-active: errors reports every status, "
            f"so there is nothing to promote; fields were {sorted(fields)}"
        )
        assert "only_status" not in fields, (
            f"ErrorsArgs must not offer --only-status; fields were {sorted(fields)}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Semantics: errors accounts for every status
# ─────────────────────────────────────────────────────────────────────────────


class TestErrorsCoversEveryStatus:
    """Pins that the `errors` listing excludes nothing by status."""

    # Verifies: REQ-d00285-C
    def test_errors_lists_every_status(self, built):
        """``errors`` reports format violations on every requirement
        regardless of status — a format defect is a defect on a Draft or
        Deprecated requirement too, and the listing must therefore account
        for exactly what ``checks`` counts.
        """
        graph, config = built
        listed = _error_req_ids(graph, config)

        assert listed == sorted([ACTIVE_ID, DRAFT_ID, DEPRECATED_ID]), (
            f"the errors listing must exclude nothing; got {listed}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Semantics: coverage — widening
# ─────────────────────────────────────────────────────────────────────────────


class TestCoverageStatusSelector:
    """Pins the widening direction on the coverage compute path."""

    def test_treat_active_widens_the_counted_set(self, built):
        """``params['treat_active']`` promotes the named status to
        active-like, so the counted denominator GROWS by exactly those
        requirements — Active alone becomes Active + Draft, while the
        still-retired Deprecated requirement stays out.
        """
        graph, config = built

        baseline = _implemented_counts(graph, config)
        widened = _implemented_counts(graph, config, ("Draft",))

        assert baseline == (1, 1), (
            "Default coverage footing must count the Active requirement only "
            f"(1 REQ, 1 assertion); got {baseline}"
        )
        assert widened == (2, 3), (
            "treat_active=Draft must add the Draft requirement to the counted set "
            f"(2 REQs, 1+2 assertions) and nothing else; got {widened}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Surface: --treat-active reaches every report taken over a set of requirements
# ─────────────────────────────────────────────────────────────────────────────


def _scope_option_subclasses() -> list[type]:
    """Every command whose arguments are built on ``ScopeOptions``."""
    from elspais.commands.args import ScopeOptions

    subclasses = ScopeOptions.__subclasses__()
    assert subclasses, "ScopeOptions has no subclasses -- this test would assert nothing"
    return subclasses


def _checks_args() -> type:
    """``checks`` honours no scope, so it declares the field itself."""
    from elspais.commands.args import ChecksArgs

    return ChecksArgs


class TestEveryScopedReportCanWeighAStatus:
    """The field lives on ``ScopeOptions`` rather than on each command.

    The statuses a run weighs as active decide the POPULATION every figure in
    the report is taken over (REQ-d00291-F), so a command that cannot receive
    them answers a different question from its siblings about the same graph --
    which is exactly the disagreement REQ-d00258-C forbids. Derived from
    ``__subclasses__()`` rather than from a list of names so that a command
    added later is covered without anyone remembering to add it here.

    Scope note: this pins that each command ACCEPTS the names, not that each
    compute path HONOURS them. What a report does with them is pinned below
    for summary and gaps.
    """

    # Verifies: REQ-d00291-F+G, REQ-d00258-C
    @pytest.mark.parametrize(
        "cls",
        [*_scope_option_subclasses(), _checks_args()],
        ids=lambda c: c.__name__,
    )
    def test_the_command_can_be_told_which_statuses_to_weigh(self, cls):
        field = {f.name: f for f in dataclasses.fields(cls)}.get("treat_active")
        assert field is not None, (
            f"{cls.__name__} reports over a set of requirements but cannot be told which "
            "statuses to weigh as active, so its population differs from its siblings'"
        )
        # An accumulating list, not a scalar: REQ-d00291-G weighs EVERY status
        # named, and `_scope.flag_values` flattens the repeated occurrences
        # tyro's UseAppendAction produces. Redeclared as `str | None`, the flag
        # would keep the last occurrence and silently narrow the promotion.
        assert field.default_factory is list, (
            f"{cls.__name__}.treat_active must default to an empty list so repeated "
            f"occurrences accumulate; got default_factory={field.default_factory!r}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Semantics: the promotion reaches the report AND the work list, together
# ─────────────────────────────────────────────────────────────────────────────


def _summary(graph, config, treat_active: tuple[str, ...] = ()) -> dict:
    from elspais.commands._requests import SummaryRequest
    from elspais.commands.summary import compute_summary

    return compute_summary(graph, config, SummaryRequest(treat_active=treat_active))


def _gaps(graph, config, treat_active: tuple[str, ...] = ()) -> dict:
    from elspais.commands._requests import GapsRequest
    from elspais.commands.gaps import compute_gaps

    return compute_gaps(graph, config, GapsRequest(treat_active=treat_active, command="gaps"))


class TestPromotionReachesSummaryAndGapsAlike:
    """``summary`` counts a requirement and ``gaps`` lists it, or neither does.

    This was a live defect: ``gaps`` derived its population gate from the
    status ROLES while ``summary`` asked the resolver, so a promoted
    requirement was counted in a level row and refused a place in the work
    list -- a reader was told work existed and never told where. Both now read
    ``statuses_withheld_from_coverage`` (REQ-d00291-F), which is the one
    resolver in set form (REQ-d00258-C).
    """

    # Verifies: REQ-d00291-F+G+I, REQ-d00281-B
    def test_a_promoted_requirement_is_counted_and_not_also_excluded(self, built):
        graph, config = built
        baseline = _summary(graph, config)
        widened = _summary(graph, config, ("Draft",))

        dev = {row["level"]: row["total"] for row in widened["levels"]}["DEV"]
        assert dev == 2, (
            "the promoted Draft requirement must join the Active one in its level row; "
            f"got DEV total {dev}"
        )
        assert "Draft" not in widened["excluded"], (
            "a requirement counted in a level row must not also be reported as withheld "
            f"by its status; excluded was {widened['excluded']}"
        )
        # Still genuinely non-empty, so emptying the tally would not pass.
        assert widened["excluded"] == {"Deprecated": 1}
        assert baseline["excluded"] == {"Draft": 1, "Deprecated": 1}

    # Verifies: REQ-d00281-B, REQ-d00291-I
    @pytest.mark.parametrize("treat_active", [(), ("Draft",)])
    def test_every_requirement_is_accounted_for_exactly_once(self, built, treat_active):
        """A reader can add the level rows to the withheld counts and get the
        estate back. Whether a status was promoted changes which side of the
        sum a requirement falls on, never how many times it appears."""
        graph, config = built
        data = _summary(graph, config, treat_active)
        counted = sum(row["total"] for row in data["levels"])
        withheld = sum(data["excluded"].values())
        assert counted + withheld == 3, (
            f"levels={[(r['level'], r['total']) for r in data['levels']]} "
            f"excluded={data['excluded']}"
        )

    # Verifies: REQ-d00291-F+G
    def test_the_work_list_names_the_requirement_the_summary_counted(self, built):
        graph, config = built
        listed = {entry[0] for entry in _gaps(graph, config, ("Draft",))["uncovered"]}
        assert DRAFT_ID in listed, (
            "the promoted requirement is counted in the coverage figures, so the work "
            f"list must say where the work is; uncovered was {sorted(listed)}"
        )
        assert ACTIVE_ID in listed
        assert DEPRECATED_ID not in listed, (
            "naming Draft must not promote the still-retired Deprecated requirement"
        )

    # Verifies: REQ-d00291-F
    def test_an_unpromoted_requirement_is_in_neither(self, built):
        graph, config = built
        listed = {entry[0] for entry in _gaps(graph, config)["uncovered"]}
        assert listed == {ACTIVE_ID}, (
            "a status that expects no implementation is held out of the work list as it "
            f"is held out of the figures; uncovered was {sorted(listed)}"
        )


class TestTheReportStatesWhatItWeighed:
    """A promoted run's figures include requirements whose own text still reads
    ``Status: Draft``. A reader who cannot see the invocation cannot account for
    the difference, so the report states the request (REQ-d00291-G)."""

    DISCLOSURE = "Weighed as active: Draft (--treat-active)"

    # Verifies: REQ-d00291-G
    def test_the_disclosure_is_one_line_naming_the_statuses_and_the_flag(self):
        from elspais.commands._scope import active_overlay_disclosure

        assert active_overlay_disclosure(("draft",)) == [self.DISCLOSURE]
        # Sorted and normalized once, so two spellings of one invocation
        # produce one artifact.
        assert active_overlay_disclosure(("review", "DRAFT")) == [
            "Weighed as active: Draft, Review (--treat-active)"
        ]
        assert active_overlay_disclosure(()) == []

    # Verifies: REQ-d00291-G
    def test_it_reaches_the_summary_a_reader_is_handed(self, built):
        graph, config = built
        assert self.DISCLOSURE in _summary(graph, config, ("Draft",))["scope"]
        assert not _summary(graph, config)["scope"]

    # Verifies: REQ-d00291-G
    def test_it_reaches_the_gap_listing_a_reader_is_handed(self, built):
        graph, config = built
        assert self.DISCLOSURE in _gaps(graph, config, ("Draft",))["scope"]
        # `compute_gaps` omits the key entirely when there is nothing to
        # state, so an unpromoted listing declares nothing at all.
        assert "scope" not in _gaps(graph, config)
