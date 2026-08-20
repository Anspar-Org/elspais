# Verifies: REQ-d00069-L
# Verifies: REQ-d00069-N
# Verifies: REQ-d00258-A
# Verifies: REQ-d00258-G
"""The viewer's badges headline the total, whatever measure produced it.

A badge headlines the TOTAL measure -- each *Assertion* counted once at the
greatest of its four measures (REQ-d00069-N) -- and names the four measures
behind it on hover. Which of them "counts" is therefore not a configuration
question on this surface: the reader is shown what produced the figure and can
see for themselves.

These tests pin that whole-requirement and conducted evidence both reach the
headline, and that the requirement badge and the per-*Assertion* pill answer
the question the same way (REQ-d00258-G).
"""

import pytest

from elspais.graph.GraphNode import GraphNode, NodeKind
from elspais.graph.metrics import CoverageDimension, RollupMetrics
from elspais.html.generator import compute_assertion_coverage_states, compute_coverage_tiers


def _dim(*, immediate_direct=(), immediate_indirect=(), rolled_direct=(), total=2):
    return CoverageDimension(
        total=total,
        immediate_direct_by_label=dict.fromkeys(immediate_direct, 1.0),
        immediate_indirect_by_label=dict.fromkeys(immediate_indirect, 1.0),
        rolled_direct_by_label=dict.fromkeys(rolled_direct, 1.0),
    )


def _rollup(*, implemented, tested, total=2):
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


LABELS = ("A", "B")


def _whole_requirement_rollup():
    """Coverage credited only by citations naming the whole requirement."""
    return _rollup(
        implemented=_dim(immediate_indirect=LABELS),
        tested=_dim(immediate_indirect=LABELS),
    )


def _conducted_rollup():
    """Coverage reaching these assertions only by conduction from below."""
    return _rollup(
        implemented=_dim(rolled_direct=LABELS),
        tested=_dim(rolled_direct=LABELS),
    )


@pytest.mark.parametrize("rollup_fn", [_whole_requirement_rollup, _conducted_rollup])
def test_REQ_d00258_A_badge_tier_reads_the_total(rollup_fn):
    """Whole-requirement and conducted evidence both reach the headline total.

    Neither is a lesser kind of credit on this surface: the badge counts each
    *Assertion* once at the greatest of its four measures.
    """
    result = compute_coverage_tiers(_node(rollup_fn()), None)
    assert result["impl_tier"] == "full"
    assert result["tested_tier"] == "full"


def test_REQ_d00258_G_pill_and_badge_agree():
    """The pill and the badge beside it answer on the same measure."""
    from tests.core.graph_test_helpers import build_graph, make_requirement

    graph = build_graph(
        make_requirement(
            "REQ-d00001",
            status="Active",
            assertions=[{"label": lbl, "text": f"SHALL {lbl}"} for lbl in LABELS],
        ),
    )
    node = graph.find_by_id("REQ-d00001")
    node.set_metric("rollup_metrics", _whole_requirement_rollup())
    tiers = compute_coverage_tiers(node, None)
    states = compute_assertion_coverage_states(node, None)
    assert tiers["impl_tier"] == "full"
    for label in LABELS:
        assert states[label]["implemented"] == "full", label


def test_REQ_d00069_L_measures_are_named_in_the_hover():
    """The hover names the measure that produced the figure.

    Under the retired behaviour whole-requirement credit could be annotated
    "not credited"; the measure is now simply reported under its own name.
    """
    node = _node(_whole_requirement_rollup())
    tip = compute_coverage_tiers(node, None)["impl_tip"]
    assert "whole-requirement: 2" in tip, tip
    assert "not credited" not in tip, tip
