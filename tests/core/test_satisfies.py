"""Tests for the Satisfies relationship feature.

Covers: REQ-p00014, REQ-d00069-G, REQ-d00069-H, REQ-d00069-I
"""

from elspais.graph.relations import EdgeKind


class TestEdgeKindSatisfies:
    """EdgeKind.SATISFIES exists and contributes to coverage.

    Validates REQ-d00069-G: SATISFIES edge kind.
    """

    def test_REQ_d00069_G_satisfies_enum_value(self):
        assert EdgeKind.SATISFIES.value == "satisfies"

    def test_REQ_d00069_G_satisfies_contributes_to_coverage(self):
        assert EdgeKind.SATISFIES.contributes_to_coverage() is True

    def test_REQ_d00069_G_refines_does_not_contribute(self):
        """Ensure REFINES still doesn't contribute (regression guard)."""
        assert EdgeKind.REFINES.contributes_to_coverage() is False
