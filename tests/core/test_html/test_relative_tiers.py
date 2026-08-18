# Verifies: REQ-d00258-I
"""Relative-denominator tier projection helper (REQ-d00258, Phase-2 chain).

``relative_tier`` (in ``graph.aggregation``) measures one ``CoverageDimension`` against a RELATIVE
denominator -- the set of assertion labels that qualify at the prior link of
the coverage chain (e.g. Tested measured only over the IMPLEMENTED labels, not
over every assertion). The crux is the ``is_na`` return: an EMPTY denominator
means "nothing to measure" (N/A, neutral), whereas a NON-empty denominator
with zero coverage is a REAL gap (``missing`` but not N/A). These tests pin
both the tier word and the ``is_na`` boolean.
"""

from elspais.graph.aggregation import relative_tier
from elspais.graph.metrics import CoverageDimension


def _tested(labels, *, direct=None, failing=()):
    """A tested-like CoverageDimension crediting ``labels`` at fraction 1.0.

    ``direct`` (defaults to ``labels``) sets the labels a citation named here,
    so tests can exercise the ``measure="immediate_direct"`` path
    independently of whole-requirement credit.
    """
    labels = set(labels)
    direct = set(labels if direct is None else direct)
    return CoverageDimension(
        failing_labels=set(failing),
        immediate_direct_by_label=dict.fromkeys(direct, 1.0),
        immediate_indirect_by_label=dict.fromkeys(labels - direct, 1.0),
    )


def test_empty_denominator_is_na():
    """Empty denominator -> nothing to measure -> ('missing', is_na=True)."""
    dim = _tested({"A"})
    assert relative_tier(dim, set(), measure="total") == ("missing", True)


def test_nonempty_denominator_zero_covered_is_real_gap():
    """In-denominator but uncovered -> ('missing', False) -- a gap, NOT N/A."""
    dim = _tested(set())  # nothing tested
    assert relative_tier(dim, {"A", "B"}, measure="total") == ("missing", False)


def test_partial_when_some_denom_labels_covered():
    """1 of 2 implemented labels tested -> ('partial', False)."""
    dim = _tested({"A"})  # only A tested
    assert relative_tier(dim, {"A", "B"}, measure="total") == ("partial", False)


def test_full_when_all_denom_labels_covered():
    """Every denominator label credited -> ('full', False)."""
    dim = _tested({"A", "B"})
    assert relative_tier(dim, {"A", "B"}, measure="total") == ("full", False)


def test_failing_label_in_denominator_wins():
    """A failing label within the denominator -> ('failing', False)."""
    dim = _tested({"A", "B"}, failing={"B"})
    assert relative_tier(dim, {"A", "B"}, measure="total") == ("failing", False)


def test_failing_label_outside_denominator_does_not_win():
    """A failing label NOT in the denominator is ignored (measures relatively)."""
    dim = _tested({"A"}, failing={"Z"})
    # Z is failing but not in denom {A,B}; A covered, B not -> partial gap.
    assert relative_tier(dim, {"A", "B"}, measure="total") == ("partial", False)


def test_allow_indirect_true_credits_blanket_coverage():
    """Indirect-only coverage counts when measure="total" (the default)."""
    # A credited only indirectly (blanket), no direct fraction.
    dim = _tested({"A", "B"}, direct=set())
    assert relative_tier(dim, {"A", "B"}, measure="total") == ("full", False)


def test_immediate_direct_excludes_whole_requirement_coverage():
    """Whole-requirement-only coverage is NOT credited on immediate direct."""
    dim = _tested({"A", "B"}, direct=set())  # direct_pct empty
    # With no direct credit and non-empty denom, this is a real gap.
    assert relative_tier(dim, {"A", "B"}, measure="immediate_direct") == ("missing", False)


def test_immediate_direct_credits_cited_labels():
    """Coverage a citation named here is credited on immediate direct."""
    dim = _tested({"A", "B"}, direct={"A"})  # only A has direct credit
    assert relative_tier(dim, {"A", "B"}, measure="immediate_direct") == ("partial", False)


def test_fraction_clamped_per_label():
    """A per-label fraction > 1.0 is clamped so one label cannot mask a gap."""
    dim = CoverageDimension(
        immediate_direct_by_label={"A": 2.0},  # over-credited A
    )
    # Clamped to 1.0 for A, B uncovered -> covered sum 1.0 < 2 -> partial, not full.
    assert relative_tier(dim, {"A", "B"}, measure="total") == ("partial", False)
