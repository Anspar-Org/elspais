# Verifies: REQ-d00283-A
"""The test-target group model: membership, declaration and selection.

Three authorities are exercised here, all reached from `elspais.config`:

* `target_groups()` -- which groups one target belongs to (A, B, C).
* `targets_in_groups()` -- which targets a group selection names (D, E, H).
* `selected_targets()` -- what a run covers given the ONE list of names it
  states, normalised to `None` where the selection covers every configured
  target, which is what makes a run full rather than selective (I, and
  REQ-d00254-J).

A group is an ALIAS for a set of targets (E), not a second selector: a run
names targets, some of them by a name standing for several, and covers
everything it named (I). So there is one list, its names are unioned, and a
name that is neither a target nor a group is CARRIED for the caller that runs
targets to refuse (H).

Declaration-time refusals (F, G) are exercised through `TestScanningConfig`,
which is where the model validator that enforces them lives.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from elspais.config import selected_targets, target_groups, targets_in_groups
from elspais.config.schema import (
    GROUP_ALL,
    GROUP_DEFAULT,
    RESERVED_GROUPS,
    ElspaisConfig,
    ScanningConfig,
    TestScanningConfig,
    TestTargetConfig,
)


def _cfg(
    groups: dict[str, str] | None = None,
    targets: dict[str, list[str]] | None = None,
) -> ElspaisConfig:
    """A config declaring *groups* and carrying *targets* (name -> claimed)."""
    return ElspaisConfig(
        scanning=ScanningConfig(
            test=TestScanningConfig(
                groups=dict(groups or {}),
                targets=[
                    TestTargetConfig(name=name, groups=list(claimed))
                    for name, claimed in (targets or {}).items()
                ],
            )
        )
    )


# A config a whole family of selection tests reads: `a` claims nothing (so it
# is the `default` group), `b` and `d` are UAT, `c` and `d` are slow.
_DECLARED = {"uat": "needs a live backend", "slow": "runs for over a minute"}
_CLAIMS = {"a": [], "b": ["uat"], "c": ["slow"], "d": ["uat", "slow"]}


# ---------------------------------------------------------------------------
# A, B, C -- membership
# ---------------------------------------------------------------------------


# Verifies: REQ-d00283-A+B+C
@pytest.mark.parametrize(
    "claimed,expected",
    [
        # A target claiming nothing is in `default` -- this is what keeps a
        # project that declares no groups running exactly what it ran before.
        ([], {GROUP_ALL, GROUP_DEFAULT}),
        # `all` conveys no membership information (every target is already in
        # it), so a target claiming only `all` has still claimed nothing and
        # remains in `default`.
        ([GROUP_ALL], {GROUP_ALL, GROUP_DEFAULT}),
        # Claiming a real group takes the target OUT of `default`.
        (["uat"], {GROUP_ALL, "uat"}),
        (["uat", GROUP_ALL], {GROUP_ALL, "uat"}),
        (["uat", "slow"], {GROUP_ALL, "uat", "slow"}),
        # A claim is read in the same case-and-spacing-insensitive way the
        # declaration's uniqueness rule (G) is enforced in.
        ([" UAT "], {GROUP_ALL, "uat"}),
    ],
)
def test_target_membership_from_claims(claimed, expected):
    assert target_groups(TestTargetConfig(name="t", groups=list(claimed))) == expected


# Verifies: REQ-d00283-B
def test_every_target_belongs_to_all():
    cfg = _cfg(_DECLARED, _CLAIMS)
    for target in cfg.scanning.test.targets:
        assert GROUP_ALL in target_groups(target), f"{target.name} must belong to `all`"


# Verifies: REQ-d00283-C
def test_claiming_a_group_leaves_the_default_group():
    cfg = _cfg(_DECLARED, _CLAIMS)
    by_name = {t.name: target_groups(t) for t in cfg.scanning.test.targets}
    assert GROUP_DEFAULT in by_name["a"]
    for name in ("b", "c", "d"):
        assert GROUP_DEFAULT not in by_name[name]


# ---------------------------------------------------------------------------
# D -- a run selecting nothing
# ---------------------------------------------------------------------------


# Verifies: REQ-d00283-D
def test_no_selection_names_only_the_default_group():
    cfg = _cfg(_DECLARED, _CLAIMS)
    assert targets_in_groups(cfg, None) == {"a"}
    # A proper subset of the configured targets, so the run is selective.
    assert selected_targets(cfg, None) == {"a"}


# Verifies: REQ-d00283-C+D
def test_no_selection_with_no_groups_declared_covers_every_target():
    """A project that declares no groups has every target in `default`."""
    cfg = _cfg(None, {"a": [], "b": []})
    assert targets_in_groups(cfg, None) == {"a", "b"}
    # Covering every configured target is a full run, not a selective one.
    assert selected_targets(cfg, None) is None


# ---------------------------------------------------------------------------
# E -- a run selecting groups
# ---------------------------------------------------------------------------


# Verifies: REQ-d00283-E
@pytest.mark.parametrize(
    "selection,expected",
    [
        (["uat"], {"b", "d"}),
        (["slow"], {"c", "d"}),
        # A target in either group is named once, not twice.
        (["uat", "slow"], {"b", "c", "d"}),
        ([GROUP_DEFAULT], {"a"}),
        ([GROUP_ALL], {"a", "b", "c", "d"}),
        # `all` selects by the same rule as any other group, so pairing it
        # with another name still yields every target.
        ([GROUP_ALL, "uat"], {"a", "b", "c", "d"}),
    ],
)
def test_group_selection_names_exactly_its_targets(selection, expected):
    assert targets_in_groups(_cfg(_DECLARED, _CLAIMS), selection) == expected


# Verifies: REQ-d00283-E
def test_selecting_all_normalises_to_a_full_run():
    cfg = _cfg(_DECLARED, _CLAIMS)
    assert selected_targets(cfg, [GROUP_ALL]) is None
    # A group naming fewer than every target stays a selective run.
    assert selected_targets(cfg, ["uat"]) == {"b", "d"}


# ---------------------------------------------------------------------------
# F -- a target may claim any declared group, and no undefined name
# ---------------------------------------------------------------------------


# Verifies: REQ-d00283-F
def test_target_may_claim_any_declared_group():
    cfg = _cfg({"uat": "live backend", "slow": "minutes", "device": "device farm"}, _CLAIMS)
    assert {t.name for t in cfg.scanning.test.targets} == {"a", "b", "c", "d"}


# Verifies: REQ-d00283-F
@pytest.mark.parametrize("reserved", sorted(RESERVED_GROUPS))
def test_target_may_claim_a_reserved_name(reserved):
    """A reservation defines a name just as a declaration does."""
    cfg = TestScanningConfig(targets=[TestTargetConfig(name="a", groups=[reserved])])
    assert cfg.targets[0].groups == [reserved]


# Verifies: REQ-d00283-F
def test_target_claiming_an_undeclared_group_is_refused():
    with pytest.raises(ValidationError) as excinfo:
        TestScanningConfig(
            groups={"uat": "needs a live backend"},
            targets=[
                TestTargetConfig(name="a"),
                TestTargetConfig(name="integration", groups=["slwo"]),
            ],
        )
    message = str(excinfo.value)
    assert "integration" in message, "the refusal must name the offending target"
    assert "slwo" in message, "the refusal must name the group it could not resolve"


# ---------------------------------------------------------------------------
# G -- what a project may declare
# ---------------------------------------------------------------------------


# Verifies: REQ-d00283-G
def test_any_number_of_groups_may_be_declared():
    declared = {f"tier{n}": f"targets of tier {n}" for n in range(1, 8)}
    claims = {f"t{n}": [f"tier{n}"] for n in range(1, 8)}
    cfg = _cfg(declared, claims)
    for n in range(1, 8):
        assert targets_in_groups(cfg, [f"tier{n}"]) == {f"t{n}"}


# Verifies: REQ-d00283-G
@pytest.mark.parametrize(
    "declared,culprit",
    [
        # A reserved name may not be declared: its meaning is fixed by B, C
        # and D, and a project description could contradict it.
        ({"all": "everything"}, "all"),
        ({"default": "the usual"}, "default"),
        ({"All": "everything"}, "All"),
        ({"DEFAULT": "the usual"}, "DEFAULT"),
        # Two names a selection could not tell apart.
        ({"uat": "live backend", "UAT": "also live backend"}, "UAT"),
        ({"uat": "live backend", " uat ": "also live backend"}, "uat"),
        # A keyword must be there to be selected by.
        ({"": "nameless"}, "keyword"),
        ({"   ": "nameless"}, "keyword"),
        # A description is the only place a group's purpose has to live.
        ({"uat": ""}, "description"),
        ({"uat": "   "}, "description"),
    ],
)
def test_bad_group_declarations_are_refused(declared, culprit):
    with pytest.raises(ValidationError) as excinfo:
        TestScanningConfig(groups=declared)
    assert culprit in str(excinfo.value)


# Verifies: REQ-d00283-G
@pytest.mark.parametrize(
    "declared,target_name,kind",
    [
        # A declared group and a target of the same name.
        ({"uat": "needs a live backend"}, "uat", "declared"),
        # The same collision reached case-insensitively: selection lowercases,
        # so `UAT` and `uat` are one name and neither reader could be answered.
        ({"uat": "needs a live backend"}, "UAT", "declared"),
        ({"slow": "runs for over a minute"}, " slow ", "declared"),
        # A reservation defines a name as surely as a declaration does, and
        # `all`/`default` cannot be declared away, so the target must move.
        ({}, "all", "reserved"),
        ({}, "default", "reserved"),
        ({}, "ALL", "reserved"),
    ],
)
def test_a_target_named_like_a_group_is_refused(declared, target_name, kind):
    """One namespace: a run names targets and groups alike, so a name meaning
    both is refused when the configuration is read rather than resolved by a
    precedence rule every reader would afterwards have to know."""
    with pytest.raises(ValidationError) as excinfo:
        TestScanningConfig(
            groups=dict(declared),
            targets=[TestTargetConfig(name="unit"), TestTargetConfig(name=target_name)],
        )
    message = str(excinfo.value)
    assert target_name in message, "the refusal must name the target it could not admit"
    assert kind in message, f"the refusal must say the colliding group is {kind}"


# Verifies: REQ-d00283-G
def test_a_target_may_share_a_name_with_nothing_declared():
    """The refusal is about a collision, not about the spelling of a name:
    a group named `uat` and a target named `uat-api` sit together."""
    cfg = TestScanningConfig(
        groups={"uat": "needs a live backend"},
        targets=[TestTargetConfig(name="uat-api", groups=["uat"])],
    )
    assert [t.name for t in cfg.targets] == ["uat-api"]


# ---------------------------------------------------------------------------
# H -- an undefined name in a selection
# ---------------------------------------------------------------------------


# Verifies: REQ-d00283-H
@pytest.mark.parametrize(
    "resolve",
    [
        lambda cfg: targets_in_groups(cfg, ["uta"]),
        # An undefined name among defined ones is still refused.
        lambda cfg: targets_in_groups(cfg, ["uat", "uta"]),
    ],
)
def test_selecting_an_undefined_group_is_refused(resolve):
    """Refused, never resolved to no targets: an empty selection's report is
    indistinguishable from one whose targets all passed."""
    cfg = _cfg(_DECLARED, _CLAIMS)
    with pytest.raises(ValueError) as excinfo:
        resolve(cfg)
    assert "uta" in str(excinfo.value), "the refusal must name the group it could not resolve"


# Verifies: REQ-d00283-H
@pytest.mark.parametrize(
    "named,expected",
    [
        # Nothing here can resolve it, so it survives to be reported.
        (["uta"], {"uta"}),
        # Carried BESIDE the names that did resolve: the caller sees both what
        # was asked for and what it could not account for.
        (["b", "uta"], {"b", "uta"}),
        (["uat", "uta"], {"b", "d", "uta"}),
    ],
)
def test_an_unresolvable_name_is_carried_rather_than_dropped(named, expected):
    """`selected_targets` does not refuse: it hands the name on. The caller
    that runs targets is the one that knows the target vocabulary, and
    resolving the name away here would turn its refusal into silence."""
    assert selected_targets(_cfg(_DECLARED, _CLAIMS), named) == expected


# ---------------------------------------------------------------------------
# E + I -- one list of names, unioned
# ---------------------------------------------------------------------------


# The shape the group model is really about: four targets across two groups,
# one of them (`stress`) claiming nothing and so standing alone in `default`.
_ALIAS_DECLARED = {"fast": "seconds, run on every change", "slow": "minutes"}
_ALIAS_CLAIMS = {
    "unit": ["fast"],
    "e2e": ["slow"],
    "browser": ["slow"],
    "stress": [],
}


# Verifies: REQ-d00283-D+E+I
@pytest.mark.parametrize(
    "named,expected",
    [
        # D: naming nothing is the `default` group.
        (None, {"stress"}),
        # A bare target name still names one target.
        (["unit"], {"unit"}),
        # E: a group name stands for every target belonging to it.
        (["slow"], {"browser", "e2e"}),
        # I: a run executes everything it named. A target name beside a group
        # name WIDENS -- the two are one vocabulary, not two filters.
        (["unit", "slow"], {"browser", "e2e", "unit"}),
        (["stress", "fast"], {"stress", "unit"}),
        # `all` covers every configured target, which is a full run.
        (["all"], None),
    ],
)
def test_one_list_of_names_unions_targets_and_groups(named, expected):
    assert selected_targets(_cfg(_ALIAS_DECLARED, _ALIAS_CLAIMS), named) == expected


# Verifies: REQ-d00283-I
def test_naming_a_target_already_inside_a_named_group_changes_nothing():
    """A group is an alias, so naming one of its members alongside it is a
    restatement -- not a narrowing of the group to that member."""
    cfg = _cfg(_ALIAS_DECLARED, _ALIAS_CLAIMS)

    assert selected_targets(cfg, ["slow", "e2e"]) == selected_targets(cfg, ["slow"])


# Verifies: REQ-d00283-E
def test_a_group_no_target_claims_selects_nothing_rather_than_everything():
    """An empty selection must not read as `run everything`: a report over no
    targets is not one whose targets all passed."""
    cfg = _cfg(dict(_DECLARED, device="the device farm"), _CLAIMS)

    selection = selected_targets(cfg, ["device"])

    assert selection == set()
    assert selection is not None


# ---------------------------------------------------------------------------
# The group vocabulary a project admits
# ---------------------------------------------------------------------------


# Verifies: REQ-d00283-F+G
def test_known_group_names_are_the_declared_ones_and_the_reserved_ones():
    from elspais.config import known_group_names

    cfg = _cfg(_ALIAS_DECLARED, _ALIAS_CLAIMS)

    assert known_group_names(cfg) == {"fast", "slow"} | set(RESERVED_GROUPS)
    # A project declaring nothing still admits the two reservations, which is
    # what lets a bare project say `--targets all`.
    assert known_group_names(_cfg(None, {"a": []})) == set(RESERVED_GROUPS)
    # Published in the one spelling a selection is matched in: a declaration
    # differing only in case is the same name, which is why G refuses two of
    # them and why a run may write either.
    declared_loudly = _cfg({" Slow ": "runs for over a minute"}, {"a": []})
    assert known_group_names(declared_loudly) == {"slow"} | set(RESERVED_GROUPS)
