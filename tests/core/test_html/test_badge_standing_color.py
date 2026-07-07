# Verifies: REQ-d00258-D
# Verifies: REQ-d00258-H
"""Badge COLOR decoupled from severity (CUR-1568).

Coverage severity is overloaded to drive three things: the requirement-badge
COLOR, combined-bucket dragging, and the ``elspais checks`` gate. Deriving badge
COLOR from severity let a project set ``[rules.coverage.uat_verified] partial =
"info"`` purely to keep CI green (job 3) and silently repaint the badge
yellow-green (job 1) -- inconsistent with the per-*Assertion* ``partial``
standing, which renders yellow.

This module pins the decoupled contract (REQ-d00258-D/H):

  - Badge COLOR comes from the coverage STANDING via the theme catalog, the same
    for the requirement dimension badge and the per-*Assertion* badge, so a given
    standing is one color everywhere: ``full``->green, ``partial``->yellow,
    ``failing``->red -- regardless of the dimension's configured severity.
  - A ``missing`` standing renders RED only when it is a hard required gap
    (resolved severity ``error``); otherwise GREY (soft info/warning missing and
    N/A missing all render grey).
  - ``yellow-green`` (severity ``info``) colors NO badge.
  - SEVERITY still governs combined-bucket dragging and the checks gate: an
    ``info`` partial stays non-dragging even though the badge is honestly yellow.
"""

from elspais.graph.GraphNode import GraphNode, NodeKind
from elspais.graph.metrics import CoverageDimension, RollupMetrics
from elspais.graph.relations import EdgeKind
from elspais.html.generator import (
    _severity_color,
    _standing_color,
    compute_assertion_coverage_states,
    compute_coverage_tiers,
)

YELLOW_GREEN = _severity_color("info")  # the retired color


def _dim(pct_by_label, *, total, failing=()):
    """A CoverageDimension crediting each label at its given fraction."""
    pct = dict(pct_by_label)
    covered = {lbl for lbl, f in pct.items() if f >= 1.0 - 1e-9}
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


def _node(rollup, *, status="Active", level="PRD", labels=()):
    n = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)
    n.set_field("status", status)
    n.set_field("level", level)
    n.set_metric("rollup_metrics", rollup)
    for label in labels:
        a = GraphNode(id=f"REQ-p00001-{label}", kind=NodeKind.ASSERTION)
        a.set_field("label", label)
        n.link(a, EdgeKind.STRUCTURES)
    return n


def _all_full_rollup():
    """Every dimension fully covers label A (single assertion)."""
    r = RollupMetrics(total_assertions=1)
    r.implemented = _dim({"A": 1.0}, total=1)
    r.tested = _dim({"A": 1.0}, total=1)
    r.verified = _dim({"A": 1.0}, total=1)
    r.uat_coverage = _dim({"A": 1.0}, total=1)
    r.uat_verified = _dim({"A": 1.0}, total=1)
    return r


# ── Scenario (a): uat_verified partial with partial="info" ────────────────────


def test_REQ_d00258_D_uat_partial_info_badge_is_yellow_not_yellow_green():
    """A partial uat_verified dimension configured ``partial="info"`` (purely to
    keep CI non-failing) must STILL badge YELLOW (the honest partial standing),
    NOT the severity-derived yellow-green. This is the CUR-1568 bug: severity
    was recoloring the badge."""
    r = _all_full_rollup()
    # uat_coverage full over {A}; uat_verified only HALF-covers A -> partial
    # (relative to the uat-covered denominator {A}).
    r.uat_verified = _dim({"A": 0.5}, total=1)
    node = _node(r)
    config = {"rules": {"coverage": {"uat_verified": {"partial": "info"}}}}

    tiers = compute_coverage_tiers(node, config)

    assert tiers["uat_ver_tier"] == "partial"
    # Color comes from the STANDING (yellow), NOT from the info severity.
    assert tiers["uat_ver_color"] == _standing_color("partial")
    assert tiers["uat_ver_color"] == "yellow"
    assert tiers["uat_ver_color"] != YELLOW_GREEN


def test_REQ_d00258_H_uat_partial_info_bucket_still_non_dragging():
    """The SAME info-partial dimension must keep its two real severity jobs:
    ``info`` does not drag the combined bucket below ``full`` (job 2). Color is
    yellow (state); the bucket stays full (policy)."""
    r = _all_full_rollup()
    r.uat_verified = _dim({"A": 0.5}, total=1)
    node = _node(r)
    config = {"rules": {"coverage": {"uat_verified": {"partial": "info"}}}}

    tiers = compute_coverage_tiers(node, config)

    # info severity -> bucket "full" (non-dragging) even though the badge is yellow.
    assert tiers["combined_bucket"] == "full"


def test_REQ_d00258_H_requirement_partial_matches_assertion_partial_color():
    """The requirement uat_verified partial badge and the per-*Assertion* partial
    standing resolve to the SAME color (a standing is one color everywhere)."""
    r = _all_full_rollup()
    r.uat_verified = _dim({"A": 0.5}, total=1)
    node = _node(r, labels=("A",))
    config = {"rules": {"coverage": {"uat_verified": {"partial": "info"}}}}

    tiers = compute_coverage_tiers(node, config)
    states = compute_assertion_coverage_states(node, config)

    assert states["A"]["uat_verified"] == "partial"
    # Both the requirement dim badge and the assertion standing map through the
    # same standing catalog entry -> identical color.
    assert tiers["uat_ver_color"] == _standing_color(states["A"]["uat_verified"])


# ── Scenario (b): implemented missing on an expecting status -> RED ───────────


def test_REQ_d00258_D_implemented_missing_expecting_status_is_red():
    r = RollupMetrics(total_assertions=2)
    r.implemented = _dim({}, total=2)  # nothing implemented
    node = _node(r, status="Active")

    tiers = compute_coverage_tiers(node)

    assert tiers["impl_tier"] == "missing"
    # Hard required gap (error severity) -> red.
    assert tiers["impl_color"] == _severity_color("error")
    assert tiers["impl_color"] == "red"


# ── Scenario (c): implemented missing on a non-expecting status -> GREY ───────


def test_REQ_d00258_D_implemented_missing_draft_status_is_grey():
    r = RollupMetrics(total_assertions=2)
    r.implemented = _dim({}, total=2)
    node = _node(r, status="Draft")  # Draft does not expect implementation

    tiers = compute_coverage_tiers(node)

    assert tiers["impl_tier"] == "missing"
    # Soft (not-expected) missing -> grey, not red, not yellow-green.
    assert tiers["impl_color"] == _standing_color("missing")
    assert tiers["impl_color"] == "grey"
    assert tiers["impl_color"] != YELLOW_GREEN


# ── Scenario (d): empty relative denominator -> GREY ─────────────────────────


def test_REQ_d00258_H_empty_denominator_tested_is_grey():
    """0 implemented -> Tested relative denominator empty -> N/A missing -> grey
    (neutral), never yellow-green."""
    r = RollupMetrics(total_assertions=2)
    r.implemented = _dim({}, total=2)
    r.tested = _dim({}, total=2)
    node = _node(r)

    tiers = compute_coverage_tiers(node)

    assert tiers["tested_tier"] == "missing"
    assert tiers["tested_color"] == _standing_color("missing")
    assert tiers["tested_color"] == "grey"
    assert tiers["tested_color"] != YELLOW_GREEN


# ── Scenario (e): no badge is ever yellow-green ──────────────────────────────


def test_REQ_d00258_D_no_badge_is_ever_yellow_green():
    """Across a representative matrix of dimension states and severity configs,
    NO requirement badge color is yellow-green. Badge colors are drawn from the
    standing catalog {green, yellow, red, grey} plus the hard-gap red override."""
    badge_prefixes = ("impl", "tested", "verified", "uat_cov", "uat_ver")

    # A mix: partial impl, half-tested, fully-passing-of-tested, partial uat,
    # empty uat_verified denominator -- under both default config and the
    # info-softened configs that used to yield yellow-green.
    scenarios = []

    r1 = RollupMetrics(total_assertions=2)
    r1.implemented = _dim({"A": 1.0}, total=2)  # partial (1 of 2)
    r1.tested = _dim({"A": 1.0}, total=2)
    r1.verified = _dim({"A": 1.0}, total=2)
    r1.uat_coverage = _dim({"A": 1.0}, total=2)  # partial absolute
    r1.uat_verified = _dim({"A": 0.5}, total=2)  # partial relative
    scenarios.append((r1, None, "Active"))

    r2 = _all_full_rollup()
    r2.uat_verified = _dim({"A": 0.5}, total=1)
    scenarios.append((r2, {"rules": {"coverage": {"uat_verified": {"partial": "info"}}}}, "Active"))

    # Default config, journey-less: uat missing severity is info -- must be grey,
    # not yellow-green.
    r3 = _all_full_rollup()
    r3.uat_coverage = _dim({}, total=1)
    r3.uat_verified = _dim({}, total=1)
    scenarios.append((r3, None, "Active"))

    for rollup, config, status in scenarios:
        tiers = compute_coverage_tiers(_node(rollup, status=status), config)
        for prefix in badge_prefixes:
            color = tiers[f"{prefix}_color"]
            assert color != YELLOW_GREEN, f"{prefix} badge is yellow-green in {config!r}"
            assert color in (
                "green",
                "yellow",
                "red",
                "grey",
            ), f"{prefix} badge color {color!r} not in the standing palette"
        assert tiers["combined_color"] != YELLOW_GREEN
