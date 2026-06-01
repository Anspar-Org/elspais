# Verifies: REQ-d00252
"""Validates REQ-d00252-D: INTEGRATES is a coverage-contributing traceability edge."""
from elspais.graph.edge_sets import TRACEABILITY_EDGE_KINDS
from elspais.graph.relations import EdgeKind


def test_REQ_d00252_D_integrates_value():
    assert EdgeKind.INTEGRATES.value == "integrates"


def test_REQ_d00252_D_integrates_contributes_to_coverage():
    assert EdgeKind.INTEGRATES.contributes_to_coverage() is True


def test_REQ_d00252_D_integrates_is_traceability_edge():
    assert EdgeKind.INTEGRATES in TRACEABILITY_EDGE_KINDS
