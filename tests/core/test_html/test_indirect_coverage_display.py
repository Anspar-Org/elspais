# Verifies: REQ-d00069-B, REQ-d00069-J, REQ-d00069-N, REQ-d00258-G
"""End-to-end: header badge and per-assertion standings AGREE for a
whole-requirement-covered requirement (the DIARY-PRD-linking-code-lifecycle
class of bug: blanket Implements + blanket Verifies rendered '12% implemented,
no direct coverage' contradicting a 'tested full' header).

The agreement is now visible in what each surface SAYS rather than in a shared
caveat flag: both headline the total standing, and both name the four measures
behind it (REQ-d00258-J).
"""

from elspais.graph.annotators import annotate_coverage
from elspais.html.generator import (
    compute_assertion_coverage_measures,
    compute_assertion_coverage_states,
    compute_coverage_tiers,
)
from tests.core.graph_test_helpers import (
    build_graph,
    make_code_ref,
    make_requirement,
    make_test_ref,
)


def _prd_like():
    graph = build_graph(
        make_requirement(
            "REQ-P",
            level="PRD",
            assertions=[{"label": lbl, "text": f"SHALL {lbl}"} for lbl in "ABC"],
        ),
        make_code_ref(implements=["REQ-P"], source_path="src/impl.py"),  # blanket Implements
        make_test_ref(verifies=["REQ-P"], source_path="tests/t.py"),  # blanket Verifies
    )
    annotate_coverage(graph)
    return graph.find_by_id("REQ-P")


def test_REQ_d00258_G_header_and_pills_agree_on_blanket_coverage():
    node = _prd_like()
    tiers = compute_coverage_tiers(node)
    states = compute_assertion_coverage_states(node, None)
    # Header: implemented + tested both full on the total measure.
    assert tiers["impl_tier"] == "full"
    assert tiers["tested_tier"] == "full"
    # Per-assertion: every assertion full on BOTH dims (no "no coverage", no
    # direct/indirect contradiction with the header).
    for lbl in "ABC":
        assert states[lbl]["implemented"] == "full"
        assert states[lbl]["tested"] == "full"


def test_REQ_d00069_B_blanket_credit_is_named_as_whole_requirement():
    """The credit that produced the standing is SHOWN, not flagged.

    A blanket `Implements:`/`Verifies:` names no *Assertion*, so its credit is
    the immediate INDIRECT measure -- 100% "whole-requirement" and 0% "cited by
    name here". Both the requirement badge tip and the per-assertion pill say
    so in those words, and neither carries a `~` (REQ-d00258-J).
    """
    node = _prd_like()
    tiers = compute_coverage_tiers(node)
    measures = compute_assertion_coverage_measures(node)

    assert "whole-requirement: 3" in tiers["impl_tip"], tiers["impl_tip"]
    assert "cited by name here: 0" in tiers["impl_tip"], tiers["impl_tip"]
    assert "~" not in tiers["impl_tip"], tiers["impl_tip"]

    for lbl in "ABC":
        phrase = measures[lbl]["implemented"]
        assert "cited by name here: 0%" in phrase, phrase
        assert "whole-requirement: 100%" in phrase, phrase
        assert "~" not in phrase, phrase
