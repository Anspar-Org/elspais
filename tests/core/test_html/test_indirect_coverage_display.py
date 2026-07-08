# Validates REQ-d00069-B, REQ-d00069-J, REQ-d00258-G
"""End-to-end: header badge and per-assertion states/caveats AGREE for a
whole-requirement-covered requirement (the DIARY-PRD-linking-code-lifecycle
class of bug: blanket Implements + blanket Refines rendered '12% implemented,
no direct coverage' contradicting a 'tested full' header)."""

from elspais.graph.annotators import annotate_coverage
from elspais.html.generator import (
    compute_assertion_coverage_caveats,
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
    caveats = compute_assertion_coverage_caveats(node)
    # Header: implemented + tested both full, both caveated (~).
    assert tiers["impl_tier"] == "full"
    assert tiers["tested_tier"] == "full"
    assert tiers["impl_marker"] == "~"
    assert tiers["tested_marker"] == "~"
    # Per-assertion: every assertion full + caveated on BOTH dims (no "no
    # coverage", no direct/indirect contradiction).
    for lbl in "ABC":
        assert states[lbl]["implemented"] == "full"
        assert states[lbl]["tested"] == "full"
        assert caveats[lbl]["implemented"] is True
        assert caveats[lbl]["tested"] is True
