# Verifies: REQ-d00069-L
# Verifies: REQ-d00069-N
# Verifies: REQ-d00258-A
# Verifies: REQ-d00258-J
"""What a viewer coverage badge says about the evidence behind its standing.

The badge STATE color does not distinguish what a citation named, and neither
does a marker beside it: the caveat is retired (REQ-d00258-J). A badge
headlines the TOTAL standing (REQ-d00069-N) and its hover text names all four
measures behind that figure (REQ-d00258-A), in the one shared vocabulary.

These tests pin ONLY the display projection -- the tip wording and the absence
of a marker. They do NOT re-assert crediting or the metrics themselves.
"""

from elspais.graph.GraphNode import GraphNode, NodeKind
from elspais.graph.metrics import CoverageDimension, RollupMetrics
from elspais.html.generator import compute_coverage_tiers


def _impl_dim(*, immediate_direct=0.0, immediate_indirect=0.0, rolled_direct=0.0, total=1):
    """An `implemented` (absolute) dimension over a single assertion label ``A``."""
    return CoverageDimension(
        total=total,
        immediate_direct_by_label={"A": immediate_direct} if immediate_direct else {},
        immediate_indirect_by_label={"A": immediate_indirect} if immediate_indirect else {},
        rolled_direct_by_label={"A": rolled_direct} if rolled_direct else {},
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


def test_REQ_d00258_A_tip_names_all_four_measures():
    """Every measure is named on hover, including the ones reading zero.

    A measure reported only when non-zero would leave a reader unable to tell
    "no conducted evidence" from "conducted evidence not shown", which is the
    ambiguity REQ-d00258-J exists to remove.
    """
    node = _node(_rollup(_impl_dim(immediate_direct=1.0)))
    tip = compute_coverage_tiers(node)["impl_tip"]
    for word in (
        "cited by name here",
        "whole-requirement",
        "conducted direct",
        "conducted indirect",
    ):
        assert word in tip, tip


def test_REQ_d00069_L_tip_reports_each_measure_in_its_own_right():
    """Two measures crediting the same assertion are each reported whole.

    An assertion cited by name AND covered by a whole-requirement citation
    reads 1 on both -- neither measure is the other's remainder.
    """
    node = _node(_rollup(_impl_dim(immediate_direct=1.0, immediate_indirect=1.0)))
    tip = compute_coverage_tiers(node)["impl_tip"]
    assert "cited by name here: 1" in tip, tip
    assert "whole-requirement: 1" in tip, tip
    assert "conducted direct: 0" in tip, tip


def test_REQ_d00069_N_headline_standing_is_the_total_measure():
    """The badge headlines total: the assertion covered twice is covered once.

    Immediate-direct and immediate-indirect each credit the single assertion
    fully; total takes the greatest per assertion, so the dimension reads
    ``full`` and not double.
    """
    node = _node(_rollup(_impl_dim(immediate_direct=1.0, immediate_indirect=1.0)))
    assert compute_coverage_tiers(node)["impl_tier"] == "full"


def test_REQ_d00069_N_conducted_evidence_alone_reaches_full():
    """Coverage conducted up a `Refines:` chain counts toward the headline.

    Nothing is attached to this assertion, but a refining requirement's own
    direct evidence conducts to it -- total is the greatest of the four, so the
    badge reads ``full`` and names where that came from.
    """
    node = _node(_rollup(_impl_dim(rolled_direct=1.0)))
    tiers = compute_coverage_tiers(node)
    assert tiers["impl_tier"] == "full"
    assert "conducted direct: 1" in tiers["impl_tip"], tiers["impl_tip"]
    assert "cited by name here: 0" in tiers["impl_tip"], tiers["impl_tip"]


def test_REQ_d00258_J_no_caveat_marker_anywhere_in_the_payload():
    """No dimension carries a `~`, in its tip or as a key of its own.

    A marker standing in for a measure the badge does not show is exactly what
    REQ-d00258-J forbids, now that the measures themselves are reported.
    """
    node = _node(_rollup(_impl_dim(immediate_indirect=1.0)))
    result = compute_coverage_tiers(node)
    for prefix in ("impl", "tested", "verified", "uat_cov", "uat_ver"):
        assert f"{prefix}_marker" not in result, prefix
        assert "~" not in result[f"{prefix}_tip"], result[f"{prefix}_tip"]
    assert "~" not in result["combined_tip"], result["combined_tip"]
