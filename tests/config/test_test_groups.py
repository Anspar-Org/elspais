# Verifies: REQ-d00283-A
"""The test-target group model: membership, declaration and selection.

Three authorities are exercised here, all reached from `elspais.config`:

* `target_groups()` -- which groups one target belongs to (A, B, C).
* `targets_in_groups()` -- which targets a group selection names (D, E, H).
* `selected_targets()` -- what a run covers given both selectors, normalised
  to `None` where the selection covers every configured target, which is what
  makes a run full rather than selective (I, and REQ-d00254-J).

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
    assert selected_targets(cfg, None, None) == {"a"}


# Verifies: REQ-d00283-C+D
def test_no_selection_with_no_groups_declared_covers_every_target():
    """A project that declares no groups has every target in `default`."""
    cfg = _cfg(None, {"a": [], "b": []})
    assert targets_in_groups(cfg, None) == {"a", "b"}
    # Covering every configured target is a full run, not a selective one.
    assert selected_targets(cfg, None, None) is None


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
    assert selected_targets(cfg, None, [GROUP_ALL]) is None
    # A group naming fewer than every target stays a selective run.
    assert selected_targets(cfg, None, ["uat"]) == {"b", "d"}


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


# ---------------------------------------------------------------------------
# H -- an undefined name in a selection
# ---------------------------------------------------------------------------


# Verifies: REQ-d00283-H
@pytest.mark.parametrize(
    "resolve",
    [
        lambda cfg: targets_in_groups(cfg, ["uta"]),
        lambda cfg: selected_targets(cfg, None, ["uta"]),
        # An undefined name among defined ones is still refused.
        lambda cfg: targets_in_groups(cfg, ["uat", "uta"]),
        lambda cfg: selected_targets(cfg, ["b"], ["uta"]),
    ],
)
def test_selecting_an_undefined_group_is_refused(resolve):
    """Refused, never resolved to no targets: an empty selection's report is
    indistinguishable from one whose targets all passed."""
    cfg = _cfg(_DECLARED, _CLAIMS)
    with pytest.raises(ValueError) as excinfo:
        resolve(cfg)
    assert "uta" in str(excinfo.value), "the refusal must name the group it could not resolve"


# ---------------------------------------------------------------------------
# I -- two selectors together
# ---------------------------------------------------------------------------


# Verifies: REQ-d00283-I
def test_each_selector_narrows_the_other():
    cfg = _cfg(_DECLARED, _CLAIMS)
    by_target = {"a", "b"}
    by_group = targets_in_groups(cfg, ["uat"])
    assert by_group == {"b", "d"}

    both = selected_targets(cfg, sorted(by_target), ["uat"])

    assert both == {"b"}
    assert both < by_target and both < by_group, "stating both selectors must not widen either"


# Verifies: REQ-d00283-I
def test_selectors_that_share_no_target_name_nothing():
    """An empty intersection is an empty selection -- not a full run."""
    cfg = _cfg(_DECLARED, _CLAIMS)

    both = selected_targets(cfg, ["a"], ["uat"])

    assert both == set()
    assert both is not None, "an empty selection must not read as `run everything`"
