# Verifies: REQ-d00258
# Verifies: REQ-d00069-L
"""``[rules.coverage] allow_indirect`` toggles whether indirect (REFINES-conducted
etc.) coverage credits the badge/tier state (Phase 4, Task 4.1).

Default is ``True`` -- the generous/indirect footing (REQ-d00069-L) is preserved
byte-for-byte. When ``False``, ONLY direct coverage lifts a dimension's state;
a dimension covered solely via indirect conduction reads ``missing``. This is
exercised for a RELATIVE dimension (tested, via ``relative_tier``) AND an
ABSOLUTE dimension (implemented, via ``absolute_tier``).

These tests pin ONLY the crediting toggle -- not the ~ marker / hover provenance
(Task 4.2), and not any change to the direct/indirect metrics themselves.
"""

from elspais.graph.GraphNode import GraphNode, NodeKind
from elspais.graph.metrics import CoverageDimension, RollupMetrics
from elspais.html.generator import _severity_color, compute_coverage_tiers


def _dim(indirect=(), *, direct=(), total=5, failing=()):
    """A CoverageDimension crediting ``indirect`` labels indirectly and
    ``direct`` labels directly (both at fraction 1.0).

    Setting ``direct`` disjoint from ``indirect`` lets a test build an
    indirect-ONLY dimension (direct empty) to exercise the allow_indirect gate.
    """
    indirect = set(indirect)
    direct = set(direct)
    return CoverageDimension(
        total=total,
        direct=len(direct),
        indirect=len(indirect),
        has_failures=bool(failing),
        failing_labels=set(failing),
        direct_labels=set(direct),
        indirect_labels=set(indirect),
        direct_pct_by_label=dict.fromkeys(direct, 1.0),
        indirect_pct_by_label=dict.fromkeys(indirect, 1.0),
    )


def _rollup(*, implemented, tested, total=5):
    r = RollupMetrics(total_assertions=total)
    r.implemented = implemented
    r.tested = tested
    r.verified = _dim(total=total)
    r.uat_coverage = _dim(total=total)
    r.uat_verified = _dim(total=total)
    return r


def _node(rollup, *, status="Active", level="DEV"):
    n = GraphNode(id="REQ-d00001", kind=NodeKind.REQUIREMENT)
    n.set_field("status", status)
    n.set_field("level", level)
    n.set_metric("rollup_metrics", rollup)
    return n


# A rollup whose ONLY coverage is indirect: every implemented+tested label is
# credited via conduction (indirect) with zero direct fraction.
def _indirect_only_rollup(total=2):
    labels = {"A", "B"}
    return _rollup(
        implemented=_dim(labels, direct=set(), total=total),
        tested=_dim(labels, direct=set(), total=total),
        total=total,
    )


def _direct_rollup(total=2):
    labels = {"A", "B"}
    return _rollup(
        implemented=_dim(labels, direct=labels, total=total),
        tested=_dim(labels, direct=labels, total=total),
        total=total,
    )


def _cfg(allow_indirect):
    return {"rules": {"coverage": {"allow_indirect": allow_indirect}}}


# ── Scenario A: default (allow_indirect=True) -- indirect credits, unchanged ──


def test_REQ_d00258_default_true_indirect_credits_absolute_and_relative():
    """No config knob (default True): indirect-only coverage reads ``full`` for
    both the absolute (implemented) and relative (tested) dimensions."""
    node = _node(_indirect_only_rollup())
    result = compute_coverage_tiers(node)  # default config -> allow_indirect True
    assert result["impl_tier"] == "full"
    assert result["tested_tier"] == "full"


def test_REQ_d00258_explicit_true_matches_default():
    """`allow_indirect: true` in config is identical to the default."""
    node = _node(_indirect_only_rollup())
    default = compute_coverage_tiers(node)
    explicit = compute_coverage_tiers(_node(_indirect_only_rollup()), _cfg(True))
    assert explicit["impl_tier"] == default["impl_tier"] == "full"
    assert explicit["tested_tier"] == default["tested_tier"] == "full"


# ── Scenario B: allow_indirect=False -- indirect-only reads missing ──


def test_REQ_d00258_false_indirect_only_absolute_dim_missing():
    """allow_indirect=False: an implemented dimension covered ONLY via indirect
    conduction (direct=0) reads ``missing`` -- the absolute tier credits direct
    only."""
    node = _node(_indirect_only_rollup())
    result = compute_coverage_tiers(node, _cfg(False))
    assert result["impl_tier"] == "missing"
    # Active status expects implementation -> a real red gap.
    assert result["impl_color"] == _severity_color("error")


def test_REQ_d00258_false_indirect_only_relative_dim_missing():
    """allow_indirect=False: a tested dimension whose only credit is indirect
    reads ``missing`` (relative tier credits direct only)."""
    node = _node(_indirect_only_rollup())
    result = compute_coverage_tiers(node, _cfg(False))
    assert result["tested_tier"] == "missing"


# ── Scenario C: direct coverage reads full under BOTH settings ──


def test_REQ_d00258_direct_coverage_full_under_both_settings():
    """Direct coverage credits the state regardless of allow_indirect."""
    for allow in (True, False):
        node = _node(_direct_rollup())
        result = compute_coverage_tiers(node, _cfg(allow))
        assert result["impl_tier"] == "full", allow
        assert result["tested_tier"] == "full", allow
