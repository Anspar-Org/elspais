# Verifies: REQ-d00069-L
# Verifies: REQ-d00258
"""Hover provenance + per-dimension ``~`` caveat marker (Phase 4, Task 4.2).

The badge STATE color no longer distinguishes direct from indirect coverage
(Phase 1 collapsed full-direct/full-indirect into one green). This task surfaces
the distinction as a CAVEAT instead: ``compute_coverage_tiers`` enriches each
dimension's hover tip with a provenance clause (``Nn% direct[, Mm% indirect]``)
and sets a per-dimension ``*_marker`` == "~" when ``indirect > direct + eps``
(REQ-d00069-L). Under ``allow_indirect=False`` the indirect portion is annotated
``(not credited)``.

These tests pin ONLY the display projection -- the tip wording and the marker.
They do NOT re-assert crediting (Task 4.1) or the metrics themselves.
"""

from elspais.graph.GraphNode import GraphNode, NodeKind
from elspais.graph.metrics import CoverageDimension, RollupMetrics
from elspais.html.generator import compute_coverage_tiers


def _impl_dim(*, direct, indirect, total=1):
    """An `implemented` (absolute) dimension with explicit direct/indirect
    fractions over a single assertion label ``A``."""
    return CoverageDimension(
        total=total,
        direct=direct,
        indirect=indirect,
        direct_labels={"A"} if direct else set(),
        indirect_labels={"A"} if indirect else set(),
        direct_pct_by_label={"A": direct} if direct else {},
        indirect_pct_by_label={"A": indirect} if indirect else {},
    )


def _empty_dim(total=1):
    return CoverageDimension(total=total)


def _rollup(impl, *, total=1):
    r = RollupMetrics(total_assertions=total)
    r.implemented = impl
    r.tested = _empty_dim(total)
    r.verified = _empty_dim(total)
    r.uat_coverage = _empty_dim(total)
    r.uat_verified = _empty_dim(total)
    return r


def _node(rollup, *, status="Active", level="DEV"):
    n = GraphNode(id="REQ-d00001", kind=NodeKind.REQUIREMENT)
    n.set_field("status", status)
    n.set_field("level", level)
    n.set_metric("rollup_metrics", rollup)
    return n


def _cfg(allow_indirect):
    return {"rules": {"coverage": {"allow_indirect": allow_indirect}}}


# ── Scenario (a): mixed direct+indirect -> marker "~", tip states both ──


def test_REQ_d00069_L_mixed_dimension_tip_and_marker():
    """direct=0.4, indirect=1.0 over 1 assertion: tip states "40% direct" and
    "60% indirect", ends with "~", and impl_marker == "~"."""
    node = _node(_rollup(_impl_dim(direct=0.4, indirect=1.0)))
    result = compute_coverage_tiers(node)
    tip = result["impl_tip"]
    assert "40% direct" in tip, tip
    assert "60% indirect" in tip, tip
    assert tip.rstrip().endswith("~"), tip
    assert result["impl_marker"] == "~"


# ── Scenario (b): fully direct -> no marker, no "~" ──


def test_REQ_d00069_L_fully_direct_no_marker():
    """direct=1.0, indirect=1.0: tip states "100% direct", no "~", empty marker."""
    node = _node(_rollup(_impl_dim(direct=1.0, indirect=1.0)))
    result = compute_coverage_tiers(node)
    tip = result["impl_tip"]
    assert "100% direct" in tip, tip
    assert "~" not in tip, tip
    assert "indirect" not in tip, tip
    assert result["impl_marker"] == ""


# ── Scenario (c): allow_indirect=False, indirect-only -> "not credited" ──


def test_REQ_d00258_indirect_only_not_credited_note():
    """direct=0, indirect=0.6 under allow_indirect=False: the state is not
    credited, so the provenance clause annotates the indirect portion
    "(not credited)" and still carries the "~" caveat (indirect > direct)."""
    node = _node(_rollup(_impl_dim(direct=0.0, indirect=0.6)))
    result = compute_coverage_tiers(node, _cfg(False))
    tip = result["impl_tip"]
    assert "not credited" in tip, tip
    assert "0% direct" in tip, tip
    assert result["impl_marker"] == "~"


def test_REQ_d00069_L_marker_key_present_for_every_dimension():
    """Every dimension prefix exposes a ``*_marker`` key (backward-compatible
    additive contract); a zero-coverage dimension has an empty marker."""
    node = _node(_rollup(_impl_dim(direct=1.0, indirect=1.0)))
    result = compute_coverage_tiers(node)
    for prefix in ("impl", "tested", "verified", "uat_cov", "uat_ver"):
        assert f"{prefix}_marker" in result, prefix
    # tested/verified/uat dims have zero coverage here -> no caveat.
    assert result["tested_marker"] == ""
