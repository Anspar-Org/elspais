# Verifies: REQ-o00062-P
"""Undoing a requirement deletion must restore the node's attachment.

REQ-o00062-P: undoing a deletion SHALL restore the node's structural
attachment -- file membership, both edge directions with their edge metadata
and assertion targets, assertion children, and root membership. Restoring
index membership alone brings the requirement back as a detached ghost: it
belongs to no file (so the next ``render_save()`` silently drops it from
disk), its parents no longer implement anything through it, and its
assertion children stay deleted.

Mirrors ``TestUndoDeleteJourneyRestoresAttachment`` in
test_journey_mutations.py, for REQUIREMENT deletion.

Target: REQ-d00001 in the hht-like fixture -- a mid-tree requirement with a
FILE CONTAINS parent, incoming IMPLEMENTS edges carrying assertion targets
(REQ-p00001 -> REQ-d00001 targeting A/B/C), a plain incoming IMPLEMENTS edge
(REQ-o00001), STRUCTURES children (assertions A-D plus sections), and
outgoing IMPLEMENTS/VERIFIES edges to CODE and TEST nodes with assertion
targets.
"""

from pathlib import Path

import pytest

from elspais.graph.factory import build_graph as build_repo_graph
from elspais.graph.GraphNode import make_file_id
from elspais.graph.render import render_file

TARGET_ID = "REQ-d00001"
ASSERTION_LABELS = ("A", "B", "C", "D")
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
# The namespace the hht-like fixture declares; structural node ids carry it.
NAMESPACE = "REQ"


@pytest.fixture
def requirement_graph_from_disk():
    """A private build of the hht-like fixture for delete/undo round trips.

    Deliberately NOT the session-scoped ``canonical_graph``/``mutable_graph``:
    the delete_requirement + undo round trip under test is known lossy today,
    so mutating the shared graph would leak the detached node into every
    later test. Same fixture content, private copy -- mirrors
    ``journey_graph_from_disk`` in test_journey_mutations.py.
    """
    fg = build_repo_graph(repo_root=FIXTURES_DIR / "hht-like")
    return fg._repos[fg._root_repo].graph


def _edge_signature(node):
    """Structural fingerprint of a node's attachment.

    File membership plus both edge directions, INCLUDING assertion_targets --
    an edge restored without its targets changes coverage attribution, so it
    must count as a difference. Tuples are sorted but duplicates retained.
    """
    file_node = node.file_node()
    return {
        "file_id": file_node.id if file_node is not None else None,
        "incoming": sorted(
            (e.source.id, e.kind.value, tuple(sorted(e.assertion_targets or [])))
            for e in node.iter_incoming_edges()
        ),
        "outgoing": sorted(
            (e.target.id, e.kind.value, tuple(sorted(e.assertion_targets or [])))
            for e in node.iter_outgoing_edges()
        ),
    }


class TestUndoDeleteRequirementRestoresAttachment:
    """Validates REQ-o00062-P: undoing delete_requirement SHALL restore the
    node's structural attachment, not just its index entry."""

    def test_REQ_o00062_P_undo_restores_file_parent_and_edge_signature(
        self, requirement_graph_from_disk
    ):
        """Validates REQ-o00062-P: file membership, both edge directions, and
        assertion targets all survive the delete/undo round trip."""
        graph = requirement_graph_from_disk
        node = graph.find_by_id(TARGET_ID)
        before = _edge_signature(node)
        was_root = graph.has_root(TARGET_ID)
        root_count = graph.root_count()
        # Guard: the fixture requirement must actually be attached, otherwise
        # the round trip below would compare orphan to orphan.
        assert before["file_id"] == make_file_id(NAMESPACE, "spec/dev-impl.md")
        assert before["incoming"] and before["outgoing"]

        graph.delete_requirement(TARGET_ID)
        assert graph.find_by_id(TARGET_ID) is None

        graph.undo_last()
        restored = graph.find_by_id(TARGET_ID)
        assert restored is not None
        assert restored.file_node() is not None
        assert _edge_signature(restored) == before
        # Root membership unchanged by the round trip.
        assert graph.has_root(TARGET_ID) == was_root
        assert graph.root_count() == root_count

    def test_REQ_o00062_P_undo_restores_assertion_children_to_index(
        self, requirement_graph_from_disk
    ):
        """Validates REQ-o00062-P: the assertion children deleted with the
        requirement come back resolvable by ID."""
        graph = requirement_graph_from_disk
        for label in ASSERTION_LABELS:
            assert graph.find_by_id(f"{TARGET_ID}-{label}") is not None

        graph.delete_requirement(TARGET_ID)
        for label in ASSERTION_LABELS:
            assert graph.find_by_id(f"{TARGET_ID}-{label}") is None

        graph.undo_last()
        for label in ASSERTION_LABELS:
            assert (
                graph.find_by_id(f"{TARGET_ID}-{label}") is not None
            ), f"{TARGET_ID}-{label} not restored by undo"

    def test_REQ_o00062_P_undo_restores_requirement_to_rendered_file(
        self, requirement_graph_from_disk
    ):
        """Validates REQ-o00062-P: the real consequence -- a detached
        requirement belongs to no file, so render_file()/render_save() would
        write the file back without it. The round trip must be byte-identical."""
        graph = requirement_graph_from_disk
        node = graph.find_by_id(TARGET_ID)
        file_node = node.file_node()
        before_text = render_file(file_node)
        assert f"{TARGET_ID}: Authentication Module" in before_text

        graph.delete_requirement(TARGET_ID)
        assert f"{TARGET_ID}: Authentication Module" not in render_file(file_node)

        graph.undo_last()
        after_text = render_file(file_node)
        assert f"{TARGET_ID}: Authentication Module" in after_text
        assert after_text == before_text
