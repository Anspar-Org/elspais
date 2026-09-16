# Verifies: REQ-d00291-D+E+F+G, REQ-d00258-C
"""``--treat-active`` is a run-scoped overlay on the configuration.

Four functions in ``elspais.config`` answer for a status, and they are
deliberately not interchangeable:

``statuses_weighed_active``
    the names this run promoted, normalized once so every reader spells them
    the same way.
``config_with_active_overlay``
    those names folded into ``[statuses.<Name>].expects_implementation``, so
    that ONE resolver -- ``status_expects_implementation`` -- answers for a
    status whether the answer came from a project's declaration or from a
    reader's flag (REQ-d00258-C).
``statuses_withheld_from_coverage``
    the set form of that resolver's answer, which is the population gate every
    coverage figure and every work list is taken over (REQ-d00291-F).
``reference_excluded_statuses``
    a DIFFERENT question -- is citing this status worth reporting -- which a
    project's ``expects_implementation`` declaration must NOT change and a
    ``--treat-active`` promotion must.

The contrast in the last two is the point of this module. A declaration says
those requirements still need work; it does not say to stop reporting a
citation of them. A run-scoped promotion applies to every reading of the
status in the run (REQ-d00291-G).
"""

from __future__ import annotations

import copy

import pytest

from elspais.config import (
    config_with_active_overlay,
    reference_excluded_statuses,
    status_expects_implementation,
    statuses_weighed_active,
    statuses_withheld_from_coverage,
)

# Stated explicitly rather than leaned on from the defaults: these tests are
# about what follows from a role, so the role assignment must be visible here.
# The path is [rules.format.status_roles] -- the schema rejects a top-level
# [status_roles] table.
ROLES = {
    "rules": {
        "format": {
            "status_roles": {
                "active": ["Active"],
                "provisional": ["Draft"],
                "retired": ["Deprecated"],
            }
        }
    }
}


def _with_statuses(**entries: dict) -> dict:
    """``ROLES`` plus a ``[statuses]`` table -- a project's own declarations."""
    return {**copy.deepcopy(ROLES), "statuses": entries}


# ─────────────────────────────────────────────────────────────────────────────
# statuses_weighed_active: one normalization, once
# ─────────────────────────────────────────────────────────────────────────────


class TestStatusesWeighedActive:
    # Verifies: REQ-d00291-G
    @pytest.mark.parametrize(
        "named,expected",
        [
            (("draft",), {"Draft"}),
            (("DRAFT", "review"), {"Draft", "Review"}),
            (("in-review",), {"In-Review"}),
            ((), set()),
            (None, set()),
        ],
    )
    def test_every_status_named_is_weighed_under_one_spelling(self, named, expected):
        """Every status the caller named is weighed (REQ-d00291-G) and each is
        title-cased once here, so a ``[statuses.<Name>]`` table -- which is
        written in title case -- is reachable by every consumer without any of
        them re-deciding the spelling."""
        assert statuses_weighed_active(named) == expected


# ─────────────────────────────────────────────────────────────────────────────
# config_with_active_overlay: the overlay's own contract
# ─────────────────────────────────────────────────────────────────────────────


class TestOverlayContract:
    # Verifies: REQ-d00291-G
    @pytest.mark.parametrize("nothing", [(), None])
    def test_promoting_nothing_hands_back_the_very_same_config(self, nothing):
        """Identity, not equality: a run that promotes nothing is the default
        run, so no consumer downstream can be handed a copy that has quietly
        acquired a ``statuses`` key the project never wrote."""
        config = _with_statuses()
        assert config_with_active_overlay(config, nothing) is config

    # Verifies: REQ-d00291-G
    def test_the_config_handed_in_is_not_changed(self):
        """The overlay is valid for ONE run. One process serves several
        readers off one config object, so promoting a status for this reader
        must leave the next reader's answers alone."""
        config = _with_statuses()
        before = copy.deepcopy(config)
        config_with_active_overlay(config, ("Draft",))
        assert config == before

    # Verifies: REQ-d00291-D+G
    def test_promotion_merges_into_a_differently_cased_declaration(self):
        """A project may spell the table key in any case. The overlay must land
        IN that entry: a second, title-cased key beside it would leave
        ``status_expects_implementation`` -- which scans the table and takes the
        first case-insensitive match -- able to read either one, so the answer
        would depend on dict order. The rest of the declaration survives, and
        an ``expects_implementation = false`` the project wrote is composed
        over rather than sitting next to a rival True."""
        config = _with_statuses(draft={"expects_implementation": False, "description": "in flight"})

        overlaid = config_with_active_overlay(config, ("Draft",))

        assert list(overlaid["statuses"]) == ["draft"]
        entry = overlaid["statuses"]["draft"]
        assert entry["expects_implementation"] is True
        assert entry["description"] == "in flight"
        # And the resolver every consumer reads through agrees.
        assert status_expects_implementation(overlaid, "Draft") is True

    # Verifies: REQ-d00291-G
    def test_a_status_with_no_declaration_gains_one(self):
        config = copy.deepcopy(ROLES)
        overlaid = config_with_active_overlay(config, ("draft",))
        assert overlaid["statuses"]["Draft"]["expects_implementation"] is True


# ─────────────────────────────────────────────────────────────────────────────
# The two set-shaped questions, which are not the same question
# ─────────────────────────────────────────────────────────────────────────────


class TestWithheldTracksTheResolverNotTheRoles:
    """``statuses_withheld_from_coverage`` asks ``status_expects_implementation``
    about each status in the vocabulary. Deriving the set from the roles instead
    is the defect: a requirement a project declared to expect implementation was
    counted by ``summary`` and held out of ``gaps`` (REQ-d00258-C)."""

    # Verifies: REQ-d00291-E+F
    def test_a_provisional_status_declaring_nothing_is_withheld(self):
        assert "Draft" in statuses_withheld_from_coverage(ROLES, ())

    # Verifies: REQ-d00291-D+F
    def test_a_declaration_takes_the_status_out_of_the_withheld_set(self):
        """D: the status's own declaration decides, whatever role the project
        assigned it. The roles still say PROVISIONAL and the answer is still
        that it expects implementation."""
        config = _with_statuses(Draft={"expects_implementation": True})
        withheld = statuses_withheld_from_coverage(config, ())
        assert "Draft" not in withheld
        # The rest of the vocabulary is untouched, so a fix that merely
        # emptied the set would not pass here.
        assert "Deprecated" in withheld

    # Verifies: REQ-d00291-F+G
    def test_a_run_scoped_promotion_takes_the_status_out_of_the_withheld_set(self):
        withheld = statuses_withheld_from_coverage(ROLES, ("draft",))
        assert "Draft" not in withheld
        assert "Deprecated" in withheld

    # Verifies: REQ-d00291-D+E
    def test_a_declaration_can_withhold_an_active_role_status(self):
        """D over E in the other direction. E is only the default: a status
        whose role is active but which declares it expects no implementation is
        withheld, so the declaration really does decide rather than merely
        being able to widen."""
        config = _with_statuses(Active={"expects_implementation": False})
        assert "Active" in statuses_withheld_from_coverage(config, ())


class TestReferenceExclusionIsADifferentQuestion:
    """The contrast that makes the two sets worth having separately."""

    # Verifies: REQ-d00291-D
    def test_a_declaration_does_not_stop_a_citation_being_reported(self):
        """A project declaring that Draft requirements still need work has said
        nothing about whether citing one is worth a report. The two sets must
        therefore disagree on exactly this input -- if they agreed, one of them
        would be redundant and the declaration would be silently suppressing a
        check the project never turned off."""
        config = _with_statuses(Draft={"expects_implementation": True})
        assert "Draft" in reference_excluded_statuses(config, ())
        assert "Draft" not in statuses_withheld_from_coverage(config, ())

    # Verifies: REQ-d00291-G
    def test_a_run_scoped_promotion_does_stop_it(self):
        """G: a request to weigh a status as active applies to ALL of the
        reading of that status in the run, so both sets move together here."""
        assert "Draft" not in reference_excluded_statuses(ROLES, ("draft",))
        assert "Draft" not in statuses_withheld_from_coverage(ROLES, ("draft",))
        # Nothing else moved.
        assert "Deprecated" in reference_excluded_statuses(ROLES, ("draft",))

    # Verifies: REQ-d00291-G
    @pytest.mark.parametrize("named", ["draft", "Draft", "DRAFT"])
    def test_promotion_reaches_a_status_the_roles_spell_in_another_case(self, named):
        """G weighs EVERY status a caller names, whatever case either side
        wrote. The roles table holds the project's spelling and the caller
        writes their own, so the two are compared without case."""
        roles = {
            "rules": {"format": {"status_roles": {"active": ["Active"], "provisional": ["DRAFT"]}}}
        }
        assert "DRAFT" not in reference_excluded_statuses(roles, (named,))
        assert "DRAFT" not in statuses_withheld_from_coverage(roles, (named,))
