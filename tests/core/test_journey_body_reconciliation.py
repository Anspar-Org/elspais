# Verifies: REQ-d00131-L, REQ-o00062-K
"""Journey body/version reconciliation after graph-level mutations.

USER_JOURNEY nodes render from a cached ``body`` field. Any mutation that
changes what the journey would look like on disk (title, VALIDATES edge set)
must fold back into that cache, otherwise:

- ``render_node()`` (and therefore ``render_save()``) writes the STALE text
  back to disk, silently discarding the edit; and
- ``node_version()`` -- a digest of the rendered text -- does not move, so a
  successful mutation hands the caller back the very token it consumed
  (REQ-d00131-L: the version changes when, and only when, the on-disk
  representation would change).

These tests pin the behavior at the TraceGraph mutation API, the single
place all surfaces (MCP tools, HTTP routes) must share. The HTTP routes
currently compensate by calling ``reconstruct_journey_body()`` themselves;
the graph-level contract must not depend on each caller remembering to.
"""

from pathlib import Path

import pytest

from elspais.graph.factory import build_graph as build_repo_graph
from elspais.graph.relations import EdgeKind
from elspais.graph.render import node_version, render_node

CANONICAL_JOURNEY_ID = "JNY-001"
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def journey_graph_from_disk():
    """A private build of the hht-like fixture (see test_journey_mutations).

    Private on purpose: these tests mutate the journey and assert on the
    rendered body, so leaking into the session-scoped ``canonical_graph``
    would poison every later read-only test.
    """
    fg = build_repo_graph(repo_root=FIXTURES_DIR / "hht-like")
    return fg._repos[fg._root_repo].graph


def _journey(graph):
    node = graph.find_by_id(CANONICAL_JOURNEY_ID)
    assert node is not None
    return node


class TestJourneyTitleReconciliation:
    """Validates REQ-d00131-L: a journey title edit changes what would be
    written to disk, so the rendered body and the version token must both
    move with it -- and move back on undo."""

    NEW_TITLE = "Revised Login Flow"

    def test_REQ_d00131_L_update_title_reflects_in_rendered_body(self, journey_graph_from_disk):
        """Validates REQ-d00131-L: render_node() shows the live title, not the
        parse-time cache."""
        journey = _journey(journey_graph_from_disk)
        # Guard: the fixture journey renders with its original title.
        assert f"{CANONICAL_JOURNEY_ID}: Login Flow" in render_node(journey)

        journey_graph_from_disk.update_title(CANONICAL_JOURNEY_ID, self.NEW_TITLE)

        rendered = render_node(journey)
        assert f"{CANONICAL_JOURNEY_ID}: {self.NEW_TITLE}" in rendered

    def test_REQ_d00131_L_update_title_moves_the_version(self, journey_graph_from_disk):
        """Validates REQ-d00131-L: the on-disk representation changed, so the
        version token must change -- a frozen token masks the edit."""
        journey = _journey(journey_graph_from_disk)
        before = node_version(journey)

        journey_graph_from_disk.update_title(CANONICAL_JOURNEY_ID, self.NEW_TITLE)

        assert node_version(journey) != before

    def test_REQ_d00131_L_undo_restores_rendered_body_and_version(self, journey_graph_from_disk):
        """Validates REQ-d00131-L: undo symmetry -- undoing the title change
        restores the old rendered body byte-for-byte and the old token."""
        journey = _journey(journey_graph_from_disk)
        before_render = render_node(journey)
        before_version = node_version(journey)

        journey_graph_from_disk.update_title(CANONICAL_JOURNEY_ID, self.NEW_TITLE)
        # The mutation must be visible before the undo, or this test would
        # pass vacuously on the stale-cache defect.
        assert render_node(journey) != before_render
        assert node_version(journey) != before_version

        journey_graph_from_disk.undo_last()

        assert render_node(journey) == before_render
        assert node_version(journey) == before_version


class TestJourneyValidatesEdgeReconciliation:
    """Validates REQ-d00131-L: the journey's ``Validates:`` line is derived
    from live VALIDATES edges, so edge mutations naming the journey as the
    validating side must change the rendered body and move the version.

    Fixture topology: JNY-001 validates REQ-p00001-A+B, stored as two
    VALIDATES graph edges REQ-p00001 -> JNY-001 (assertion_targets A and B).
    At the mutation API the journey is the ``source_id`` (child) argument.
    """

    def test_REQ_d00131_L_add_validates_edge_reflects_in_rendered_body(
        self, journey_graph_from_disk
    ):
        """Validates REQ-d00131-L: a newly validated requirement appears in
        the rendered Validates references and the version moves."""
        journey = _journey(journey_graph_from_disk)
        before_version = node_version(journey)
        assert "REQ-p00003" not in render_node(journey)

        journey_graph_from_disk.add_edge(CANONICAL_JOURNEY_ID, "REQ-p00003", EdgeKind.VALIDATES)

        assert "REQ-p00003" in render_node(journey)
        assert node_version(journey) != before_version

    def test_REQ_d00131_L_delete_validates_edge_updates_render_and_version(
        self, journey_graph_from_disk
    ):
        """Validates REQ-d00131-L: removing one of the journey's VALIDATES
        edges changes what would be written to disk, so both the rendered
        body and the version must move."""
        journey = _journey(journey_graph_from_disk)
        before_render = render_node(journey)
        before_version = node_version(journey)

        journey_graph_from_disk.delete_edge(CANONICAL_JOURNEY_ID, "REQ-p00001")

        assert render_node(journey) != before_render
        assert node_version(journey) != before_version

    def test_REQ_d00131_L_change_edge_kind_updates_render_and_version(
        self, journey_graph_from_disk
    ):
        """Validates REQ-d00131-L: retyping a VALIDATES edge removes it from
        the journey's Validates set -- render and version must follow."""
        journey = _journey(journey_graph_from_disk)
        before_render = render_node(journey)
        before_version = node_version(journey)

        journey_graph_from_disk.change_edge_kind(
            CANONICAL_JOURNEY_ID, "REQ-p00001", EdgeKind.REFINES
        )

        assert render_node(journey) != before_render
        assert node_version(journey) != before_version

    def test_REQ_d00131_L_undo_of_edge_mutation_restores_render_and_version(
        self, journey_graph_from_disk
    ):
        """Validates REQ-d00131-L: undo symmetry for edge-driven body
        reconciliation."""
        journey = _journey(journey_graph_from_disk)
        before_render = render_node(journey)
        before_version = node_version(journey)

        journey_graph_from_disk.add_edge(CANONICAL_JOURNEY_ID, "REQ-p00003", EdgeKind.VALIDATES)
        assert node_version(journey) != before_version

        journey_graph_from_disk.undo_last()

        assert render_node(journey) == before_render
        assert node_version(journey) == before_version
