"""Tests for comment system integration with TraceGraph and FederatedGraph.

Validates REQ-d00230: Comment delegate methods on TraceGraph and
FederatedGraph, anchor rename consistency, and repo_root_for routing.
"""

from pathlib import Path

from elspais.graph import GraphNode, NodeKind
from elspais.graph.builder import TraceGraph
from elspais.graph.comments import CommentEvent, CommentIndex, CommentThread
from elspais.graph.federated import FederatedGraph, RepoEntry


def _make_thread(anchor, cid="c1"):
    root = CommentEvent(
        event="comment",
        id=cid,
        anchor=anchor,
        author="Alice",
        author_id="alice@co.org",
        date="2026-03-20",
        text="Hello",
    )
    return CommentThread(root=root)


class TestTraceGraphComments:
    """Validates REQ-d00230-A: TraceGraph comment delegate methods."""

    def test_REQ_d00230_A_empty_graph_has_no_comments(self):
        """An empty TraceGraph has zero comments and no orphans."""
        graph = TraceGraph()
        assert graph.comment_count("REQ-p00001#A") == 0
        assert not graph.has_comments("REQ-p00001#A")
        assert list(graph.iter_comments("REQ-p00001#A")) == []
        assert list(graph.iter_orphaned_comments()) == []

    def test_REQ_d00230_A_graph_with_comment_index(self):
        """Setting a CommentIndex on TraceGraph makes delegates work."""
        graph = TraceGraph()
        idx = CommentIndex()
        thread = _make_thread("REQ-p00001#A", cid="c1")
        idx.add_thread(thread, "comments/root.jsonl")
        graph._comment_index = idx

        assert graph.comment_count("REQ-p00001#A") == 1
        assert graph.has_comments("REQ-p00001#A")
        threads = list(graph.iter_comments("REQ-p00001#A"))
        assert len(threads) == 1
        assert threads[0].root.id == "c1"

    def test_REQ_d00230_A_orphaned_comments(self):
        """Orphaned threads are returned by iter_orphaned_comments."""
        graph = TraceGraph()
        idx = CommentIndex()
        orphan = _make_thread("REQ-GONE#X", cid="c-orphan")
        idx.add_orphaned(orphan)
        graph._comment_index = idx

        orphans = list(graph.iter_orphaned_comments())
        assert len(orphans) == 1
        assert orphans[0].root.id == "c-orphan"


class TestFederatedGraphComments:
    """Validates REQ-d00230-B: FederatedGraph comment routing."""

    def _build_federated(self):
        """Build a two-repo FederatedGraph with comments."""
        # Repo 1: REQ-p00001 with comment on #A, plus one orphan
        g1 = TraceGraph()
        req1 = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)
        g1._index["REQ-p00001"] = req1
        g1._roots.append(req1)
        idx1 = CommentIndex()
        idx1.add_thread(_make_thread("REQ-p00001#A", cid="c1"), "comments/r1.jsonl")
        orphan = _make_thread("REQ-VANISHED#Z", cid="c3")
        idx1.add_orphaned(orphan)
        g1._comment_index = idx1

        # Repo 2: REQ-d00001 with comment on #B
        g2 = TraceGraph()
        req2 = GraphNode(id="REQ-d00001", kind=NodeKind.REQUIREMENT)
        g2._index["REQ-d00001"] = req2
        g2._roots.append(req2)
        idx2 = CommentIndex()
        idx2.add_thread(_make_thread("REQ-d00001#B", cid="c2"), "comments/r2.jsonl")
        g2._comment_index = idx2

        fed = FederatedGraph(
            repos=[
                RepoEntry(name="root", graph=g1, config={}, repo_root=Path("/r1")),
                RepoEntry(name="mod", graph=g2, config={}, repo_root=Path("/r2")),
            ],
        )
        return fed

    def test_REQ_d00230_B_routes_to_correct_repo(self):
        """Comment queries route to the owning repo based on anchor prefix."""
        fed = self._build_federated()
        assert fed.comment_count("REQ-p00001#A") == 1
        assert fed.comment_count("REQ-d00001#B") == 1

    def test_REQ_d00230_B_unknown_anchor_returns_zero(self):
        """Unknown anchor returns zero comment count."""
        fed = self._build_federated()
        assert fed.comment_count("REQ-p99999#A") == 0

    def test_REQ_d00230_B_orphaned_aggregates_across_repos(self):
        """Orphaned comments are aggregated across all repos."""
        fed = self._build_federated()
        orphans = list(fed.iter_orphaned_comments())
        assert len(orphans) == 1
        assert orphans[0].root.id == "c3"

    def test_REQ_d00230_B_has_comments(self):
        """has_comments returns True for existing, False for non-existing."""
        fed = self._build_federated()
        assert fed.has_comments("REQ-p00001#A") is True
        assert fed.has_comments("REQ-p99999#A") is False


class TestRenameHooks:
    """Validates REQ-d00230-C: rename_node and rename_assertion update comment anchors."""

    def test_REQ_d00230_C_rename_node_updates_comment_anchors(self, tmp_path):
        """rename_node calls update_anchors_on_rename for comment consistency."""
        graph = TraceGraph(repo_root=tmp_path)
        req = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)
        graph._index["REQ-p00001"] = req
        graph._roots.append(req)

        # Set up comment index with a thread anchored to the old ID
        idx = CommentIndex()
        idx.add_thread(_make_thread("REQ-p00001#A", cid="c1"), "f.jsonl")
        graph._comment_index = idx

        # Create .elspais/comments dir for JSONL writes
        comments_dir = tmp_path / ".elspais" / "comments"
        comments_dir.mkdir(parents=True, exist_ok=True)
        jsonl_path = comments_dir / "f.jsonl"
        jsonl_path.write_text("")

        graph.rename_node("REQ-p00001", "REQ-p00002")

        # After rename, comments should be reachable under the new anchor
        assert graph.has_comments("REQ-p00002#A")
        assert not graph.has_comments("REQ-p00001#A")

    def test_REQ_d00230_C_rename_assertion_updates_comment_anchors(self, tmp_path):
        """rename_assertion calls update_anchors_on_rename for comment consistency."""
        from elspais.graph.relations import EdgeKind

        graph = TraceGraph(repo_root=tmp_path)
        req = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)
        assertion = GraphNode(id="REQ-p00001-A", kind=NodeKind.ASSERTION)
        assertion.set_field("label", "A")
        req.link(assertion, EdgeKind.STRUCTURES)
        graph._index["REQ-p00001"] = req
        graph._index["REQ-p00001-A"] = assertion
        graph._roots.append(req)

        # Set up comment index with a thread anchored to the old assertion
        idx = CommentIndex()
        idx.add_thread(_make_thread("REQ-p00001#A", cid="c1"), "f.jsonl")
        graph._comment_index = idx

        # Create .elspais/comments dir for JSONL writes
        comments_dir = tmp_path / ".elspais" / "comments"
        comments_dir.mkdir(parents=True, exist_ok=True)
        jsonl_path = comments_dir / "f.jsonl"
        jsonl_path.write_text("")

        graph.rename_assertion("REQ-p00001-A", "B")

        # After rename, comments should be reachable under the new anchor
        assert graph.has_comments("REQ-p00001#B")
        assert not graph.has_comments("REQ-p00001#A")


class TestFederatedRepoRootFor:
    """Validates REQ-d00230-D: FederatedGraph repo_root_for method."""

    def _build_federated(self):
        """Build a FederatedGraph with known nodes for repo_root_for tests."""
        g1 = TraceGraph()
        req1 = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)
        g1._index["REQ-p00001"] = req1
        g1._roots.append(req1)

        g2 = TraceGraph()
        req2 = GraphNode(id="REQ-d00001", kind=NodeKind.REQUIREMENT)
        g2._index["REQ-d00001"] = req2
        g2._roots.append(req2)

        return FederatedGraph(
            repos=[
                RepoEntry(name="root", graph=g1, config={}, repo_root=Path("/r1")),
                RepoEntry(name="mod", graph=g2, config={}, repo_root=Path("/r2")),
            ],
        )

    def test_REQ_d00230_D_repo_root_for_known_node(self):
        """repo_root_for returns correct Path for a known node."""
        fed = self._build_federated()
        assert fed.repo_root_for("REQ-p00001") == Path("/r1")
        assert fed.repo_root_for("REQ-d00001") == Path("/r2")

    def test_REQ_d00230_D_repo_root_for_unknown_node(self):
        """repo_root_for returns None for an unknown node."""
        fed = self._build_federated()
        assert fed.repo_root_for("REQ-UNKNOWN") is None
