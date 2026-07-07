# Verifies: REQ-d00258-I
"""Relative-denominator wiring in ``compute_coverage_tiers`` (REQ-d00258, Phase-2).

Phase 2 wires ``relative_tier`` into the badge projection so the chained
dimensions (Tested / Passing / UAT-Passed) are measured against their RELATIVE
denominator (the prior link's label-set), not against every assertion:

  - Tested   is measured over the IMPLEMENTED labels.
  - Passing  is measured over the TESTED labels.
  - UAT-Passed is measured over the UAT-COVERED labels.

``Implemented`` and ``UAT-Covered`` stay ABSOLUTE (over all assertions).

The visible bug this fixes (DIARY-GUI): a requirement with 0 implemented used
to show ``Tested: no coverage`` as a red/yellow badge. With relative denom, the
Tested denominator is EMPTY -> N/A -> a NEUTRAL grey badge, and it must not
drag ``combined_bucket`` below the (already red) Implemented dim.
"""

from elspais.graph.GraphNode import GraphNode, NodeKind
from elspais.graph.metrics import CoverageDimension, RollupMetrics
from elspais.html.generator import _severity_color, compute_coverage_tiers


def _dim(labels=(), *, total=5, failing=()):
    """A CoverageDimension crediting ``labels`` at fraction 1.0 (direct+indirect)."""
    labels = set(labels)
    return CoverageDimension(
        total=total,
        direct=len(labels),
        indirect=len(labels),
        has_failures=bool(failing),
        failing_labels=set(failing),
        direct_labels=set(labels),
        indirect_labels=set(labels),
        direct_pct_by_label=dict.fromkeys(labels, 1.0),
        indirect_pct_by_label=dict.fromkeys(labels, 1.0),
    )


def _rollup(*, implemented=(), tested=(), passing=(), uat_cov=(), uat_ver=(), total=5):
    r = RollupMetrics(total_assertions=total)
    r.implemented = _dim(implemented, total=total)
    r.tested = _dim(tested, total=total)
    # `verified` feeds tested_and_passing() -> the "Passing" badge numerator.
    r.verified = _dim(passing, total=total)
    r.uat_coverage = _dim(uat_cov, total=total)
    r.uat_verified = _dim(uat_ver, total=total)
    return r


def _node(rollup, *, status="Active", level="PRD"):
    n = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)
    n.set_field("status", status)
    n.set_field("level", level)
    n.set_metric("rollup_metrics", rollup)
    return n


# ── Scenario A: DIARY-GUI — 0 implemented, empty relative denominators ──


def test_REQ_d00258_B_empty_denominator_tested_is_neutral_not_yellow():
    """0 implemented -> Tested denom empty -> N/A -> neutral grey, NOT yellow/red."""
    node = _node(_rollup(implemented=(), tested=(), passing=()))
    result = compute_coverage_tiers(node)

    # Implemented is absolute and empty -> real red gap.
    assert result["impl_tier"] == "missing"
    assert result["impl_color"] == _severity_color("error")

    # Tested relative to an EMPTY implemented denominator -> N/A -> neutral GREY
    # (matches the per-assertion `missing` standing; NOT the yellow-green `info`
    # severity that the design never intended for the not-applicable case).
    assert result["tested_tier"] == "missing"
    assert result["tested_color"] == _severity_color("neutral")
    assert _severity_color("neutral") == "grey"
    assert result["tested_color"] != _severity_color("error")  # not red
    assert result["tested_color"] != _severity_color("warning")  # not yellow
    assert result["tested_color"] != _severity_color("ok")  # not green

    # Passing relative to an EMPTY tested denominator -> also N/A neutral grey.
    assert result["verified_color"] == _severity_color("neutral")


def test_REQ_d00258_B_empty_denominator_does_not_drag_bucket_below_implemented():
    """The neutral N/A Tested/Passing dims must not worsen combined_bucket."""
    node = _node(_rollup(implemented=(), tested=(), passing=()))
    result = compute_coverage_tiers(node)
    # Worst applicable severity is Implemented's own red -> "missing"; the
    # neutral relatives contribute nothing worse.
    assert result["combined_bucket"] == "missing"


# ── Scenario B: 1-of-5 implemented, that one tested & passing ──


def test_REQ_d00258_B_relative_full_when_the_one_implemented_is_covered():
    """1/5 implemented -> impl partial (yellow); Tested/Passing full over that 1."""
    node = _node(_rollup(implemented={"A"}, tested={"A"}, passing={"A"}))
    result = compute_coverage_tiers(node)

    assert result["impl_tier"] == "partial"
    assert result["impl_color"] == _severity_color("warning")

    # 1 of 1 implemented label is tested -> full green (RELATIVE, not 1/5).
    assert result["tested_tier"] == "full"
    assert result["tested_color"] == _severity_color("ok")

    # 1 of 1 tested label is passing -> full green.
    assert result["verified_tier"] == "full"
    assert result["verified_color"] == _severity_color("ok")


def test_REQ_d00258_B_green_relatives_do_not_drag_bucket_up_or_down():
    """combined_bucket = worst APPLICABLE (Implemented partial), not the greens."""
    node = _node(_rollup(implemented={"A"}, tested={"A"}, passing={"A"}))
    result = compute_coverage_tiers(node)
    # Implemented is partial/warning -> bucket partial; the full relatives must
    # neither lift it to "full" nor a stray N/A drop it to "missing".
    assert result["combined_bucket"] == "partial"


# ── Scenario C: some implemented, none tested — a REAL relative gap ──


def test_REQ_d00258_B_nonempty_denominator_uncovered_is_real_gap():
    """Implemented labels exist but none tested -> Tested missing, is_na FALSE.

    A non-empty denominator with zero coverage is a genuine gap and must use
    the CONFIGURED missing severity (red), NOT the neutral N/A override.
    """
    node = _node(_rollup(implemented={"A", "B"}, tested=(), passing=()))
    result = compute_coverage_tiers(node)

    assert result["tested_tier"] == "missing"
    assert result["tested_color"] == _severity_color("error")
    assert result["tested_color"] != _severity_color("neutral")  # not the grey N/A override

    # Worst applicable is the red Tested gap -> bucket missing.
    assert result["combined_bucket"] == "missing"


def test_REQ_d00258_B_partial_relative_when_some_denom_covered():
    """2 implemented, 1 tested -> Tested partial (relative), yellow."""
    node = _node(_rollup(implemented={"A", "B"}, tested={"A"}, passing={"A"}))
    result = compute_coverage_tiers(node)
    assert result["tested_tier"] == "partial"
    assert result["tested_color"] == _severity_color("warning")


# ── Scenario D: 0.0-conducted labels must not enter the relative denominator ──


def _dim_with_zeros(covered=(), zeros=(), *, total=5, failing=()):
    """A CoverageDimension crediting ``covered`` at 1.0 while seeding ``zeros``
    at 0.0 in the per-label maps.

    Mirrors ``_conduct_refines_coverage``, which rebuilds
    ``indirect_pct_by_label`` with a 0.0 entry for every unimplemented
    assertion label. The relative denominator must EXCLUDE those 0.0 labels
    (REQ-d00258-I).
    """
    covered = set(covered)
    zeros = set(zeros)
    pct = {**dict.fromkeys(covered, 1.0), **dict.fromkeys(zeros, 0.0)}
    return CoverageDimension(
        total=total,
        direct=len(covered),
        indirect=len(covered),
        has_failures=bool(failing),
        failing_labels=set(failing),
        direct_labels=set(covered),
        indirect_labels=set(covered),
        direct_pct_by_label=dict(pct),
        indirect_pct_by_label=dict(pct),
    )


def test_REQ_d00258_I_zero_conducted_label_excluded_from_tested_denominator():
    """REGRESSION: implemented seeds a 0.0 entry for unimplemented label B; the
    Tested denominator must exclude B so the single implemented+tested label A
    reads FULL/green, not partial over {A, B}."""
    rollup = RollupMetrics(total_assertions=2)
    rollup.implemented = _dim_with_zeros({"A"}, {"B"}, total=2)
    rollup.tested = _dim_with_zeros({"A"}, {"B"}, total=2)
    rollup.verified = _dim_with_zeros({"A"}, {"B"}, total=2)
    result = compute_coverage_tiers(_node(rollup))

    assert result["tested_tier"] == "full"
    assert result["tested_color"] == _severity_color("ok")


def test_REQ_d00258_I_all_zero_implemented_makes_tested_na_neutral():
    """REGRESSION: implemented all-0.0 (nothing implemented) but every label has
    a test edge -> Tested denominator is EMPTY -> N/A neutral grey, NOT
    full/green. (Self-repo REQ-d00125.)"""
    rollup = RollupMetrics(total_assertions=2)
    rollup.implemented = _dim_with_zeros(set(), {"A", "B"}, total=2)
    rollup.tested = _dim_with_zeros({"A", "B"}, set(), total=2)
    rollup.verified = _dim_with_zeros({"A", "B"}, set(), total=2)
    result = compute_coverage_tiers(_node(rollup))

    assert result["tested_tier"] == "missing"
    assert result["tested_color"] == _severity_color("neutral")
    assert result["tested_color"] != _severity_color("ok")


def test_REQ_d00258_F_expects_validation_still_reds_empty_uat_coverage():
    """expects_validation level: empty UAT-Covered is a real red gap, not neutral.

    UAT-Covered is ABSOLUTE; the expects_validation override makes its `missing`
    resolve to error even though the default UAT severity is info. UAT-Passed
    relative to the empty UAT-Covered denominator stays N/A neutral.
    """
    config = {
        "levels": {"prd": {"rank": 1, "expects_validation": True}},
    }
    node = _node(_rollup(implemented={"A"}, tested={"A"}, passing={"A"}), level="PRD")
    result = compute_coverage_tiers(node, config)

    assert result["expects_validation"] is True
    # Empty UAT coverage, expects_validation -> red (REQ-d00258-F preserved).
    assert result["uat_cov_tier"] == "missing"
    assert result["uat_cov_color"] == _severity_color("error")
    # UAT-Passed relative to empty UAT-Covered denom -> neutral N/A grey.
    assert result["uat_ver_color"] == _severity_color("neutral")
