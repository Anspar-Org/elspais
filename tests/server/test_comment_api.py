# Verifies: REQ-d00231-A+B+C+D+E
"""Tests for comment API endpoints (/api/comment/*, /api/comments/*)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from starlette.testclient import TestClient

from elspais.graph import GraphNode, NodeKind
from elspais.graph.builder import TraceGraph
from elspais.graph.federated import FederatedGraph, RepoEntry
from elspais.graph.relations import EdgeKind
from elspais.server.app import create_app
from elspais.server.state import AppState

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_app(tmp_path: Path) -> tuple[TestClient, Path]:
    """Create a test app with a graph containing REQ-p00001 with assertion A."""
    graph = TraceGraph(repo_root=tmp_path)
    req = GraphNode(id="REQ-p00001", kind=NodeKind.REQUIREMENT)
    req.set_field("title", "Auth")
    # Need a FILE node so file_node() works for JSONL path resolution
    file_node = GraphNode(id="file:spec/auth.md", kind=NodeKind.FILE)
    file_node.set_field("relative_path", "spec/auth.md")
    file_node.set_field("absolute_path", str(tmp_path / "spec" / "auth.md"))
    file_node.link(req, EdgeKind.CONTAINS)
    assertion_a = GraphNode(id="REQ-p00001-A", kind=NodeKind.ASSERTION)
    assertion_a.set_field("label", "A")
    req.link(assertion_a, EdgeKind.STRUCTURES)
    graph._index["file:spec/auth.md"] = file_node
    graph._index["REQ-p00001"] = req
    graph._index["REQ-p00001-A"] = assertion_a
    graph._roots.append(file_node)

    # Create the .elspais/comments directory
    (tmp_path / ".elspais" / "comments").mkdir(parents=True, exist_ok=True)

    repos = [RepoEntry(name="root", graph=graph, config={}, repo_root=tmp_path)]
    federated = FederatedGraph(repos)
    state = AppState(graph=federated, repo_root=tmp_path, config={})
    app = create_app(state=state, mount_mcp=False)
    return TestClient(app), tmp_path


# ---------------------------------------------------------------------------
# TestCommentAdd (REQ-d00231-A)
# ---------------------------------------------------------------------------


class TestCommentAdd:
    """Validates REQ-d00231-A: POST /api/comment/add creates a comment thread,
    persists it, updates the index, and returns the event. Missing text -> 400.
    """

    def test_REQ_d00231_A_add_comment(self, tmp_path: Path) -> None:
        """POST with anchor + text returns 200 with success=True and comment fields."""
        client, _ = _make_app(tmp_path)
        with patch("elspais.server.routes_api.get_author_info") as mock_author:
            mock_author.return_value = {"name": "Alice Smith", "id": "alice@co.org"}
            resp = client.post(
                "/api/comment/add",
                json={"anchor": "REQ-p00001#A", "text": "Needs clarification"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        comment = data["comment"]
        assert comment["anchor"] == "REQ-p00001#A"
        assert comment["text"] == "Needs clarification"
        assert comment["event"] == "comment"
        assert "id" in comment

    def test_REQ_d00231_A_add_comment_missing_text(self, tmp_path: Path) -> None:
        """POST with anchor but no text returns 400."""
        client, _ = _make_app(tmp_path)
        with patch("elspais.server.routes_api.get_author_info") as mock_author:
            mock_author.return_value = {"name": "Alice Smith", "id": "alice@co.org"}
            resp = client.post(
                "/api/comment/add",
                json={"anchor": "REQ-p00001#A"},
            )
        assert resp.status_code == 400

    def test_REQ_d00231_A_add_comment_missing_anchor(self, tmp_path: Path) -> None:
        """POST with text but no anchor returns 400."""
        client, _ = _make_app(tmp_path)
        with patch("elspais.server.routes_api.get_author_info") as mock_author:
            mock_author.return_value = {"name": "Alice Smith", "id": "alice@co.org"}
            resp = client.post(
                "/api/comment/add",
                json={"text": "Some comment"},
            )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# TestCommentReply (REQ-d00231-B)
# ---------------------------------------------------------------------------


class TestCommentReply:
    """Validates REQ-d00231-B: POST /api/comment/reply attaches a reply to an
    existing thread and returns the reply event. Missing parent -> 404.
    """

    def test_REQ_d00231_B_reply_to_comment(self, tmp_path: Path) -> None:
        """Add a comment then reply with parent_id; reply returns 200 with parent set."""
        client, _ = _make_app(tmp_path)
        with patch("elspais.server.routes_api.get_author_info") as mock_author:
            mock_author.return_value = {"name": "Alice Smith", "id": "alice@co.org"}
            # First create a comment
            add_resp = client.post(
                "/api/comment/add",
                json={"anchor": "REQ-p00001#A", "text": "Original comment"},
            )
            assert add_resp.status_code == 200
            parent_id = add_resp.json()["comment"]["id"]

            # Now reply
            reply_resp = client.post(
                "/api/comment/reply",
                json={"parent_id": parent_id, "text": "I agree"},
            )
        assert reply_resp.status_code == 200
        data = reply_resp.json()
        assert data["success"] is True
        reply = data["comment"]
        assert reply["parent"] == parent_id
        assert reply["text"] == "I agree"
        assert reply["event"] == "reply"

    def test_REQ_d00231_B_reply_missing_parent(self, tmp_path: Path) -> None:
        """Reply with nonexistent parent_id returns 404."""
        client, _ = _make_app(tmp_path)
        with patch("elspais.server.routes_api.get_author_info") as mock_author:
            mock_author.return_value = {"name": "Alice Smith", "id": "alice@co.org"}
            resp = client.post(
                "/api/comment/reply",
                json={"parent_id": "c-20260327-nonexistent", "text": "Reply"},
            )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# TestCommentResolve (REQ-d00231-C)
# ---------------------------------------------------------------------------


class TestCommentResolve:
    """Validates REQ-d00231-C: POST /api/comment/resolve removes the thread from
    the index, persists a resolve event, and returns success. Missing comment -> 404.
    """

    def test_REQ_d00231_C_resolve_comment(self, tmp_path: Path) -> None:
        """Add a comment then resolve it; returns 200."""
        client, _ = _make_app(tmp_path)
        with patch("elspais.server.routes_api.get_author_info") as mock_author:
            mock_author.return_value = {"name": "Alice Smith", "id": "alice@co.org"}
            # Create a comment first
            add_resp = client.post(
                "/api/comment/add",
                json={"anchor": "REQ-p00001#A", "text": "To be resolved"},
            )
            assert add_resp.status_code == 200
            comment_id = add_resp.json()["comment"]["id"]

            # Resolve it
            resolve_resp = client.post(
                "/api/comment/resolve",
                json={"comment_id": comment_id},
            )
        assert resolve_resp.status_code == 200
        data = resolve_resp.json()
        assert data["success"] is True

    def test_REQ_d00231_C_resolve_missing_comment(self, tmp_path: Path) -> None:
        """Resolve with nonexistent comment_id returns 404."""
        client, _ = _make_app(tmp_path)
        with patch("elspais.server.routes_api.get_author_info") as mock_author:
            mock_author.return_value = {"name": "Alice Smith", "id": "alice@co.org"}
            resp = client.post(
                "/api/comment/resolve",
                json={"comment_id": "c-20260327-nonexistent"},
            )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# TestCommentRead (REQ-d00231-D)
# ---------------------------------------------------------------------------


class TestCommentRead:
    """Validates REQ-d00231-D: GET /api/comments, GET /api/comments/card,
    GET /api/comments/orphaned query endpoints.
    """

    def test_REQ_d00231_D_get_comments_by_anchor(self, tmp_path: Path) -> None:
        """Add a comment then GET /api/comments?anchor=REQ-p00001%23A returns threads."""
        client, _ = _make_app(tmp_path)
        with patch("elspais.server.routes_api.get_author_info") as mock_author:
            mock_author.return_value = {"name": "Alice Smith", "id": "alice@co.org"}
            # Add a comment
            client.post(
                "/api/comment/add",
                json={"anchor": "REQ-p00001#A", "text": "A comment"},
            )
            # Query by anchor
            resp = client.get("/api/comments", params={"anchor": "REQ-p00001#A"})
        assert resp.status_code == 200
        data = resp.json()
        assert "threads" in data
        assert len(data["threads"]) >= 1
        assert data["threads"][0]["root"]["anchor"] == "REQ-p00001#A"

    def test_REQ_d00231_D_get_comments_for_card(self, tmp_path: Path) -> None:
        """Add comments then GET /api/comments/card?node_id=REQ-p00001 returns grouped."""
        client, _ = _make_app(tmp_path)
        with patch("elspais.server.routes_api.get_author_info") as mock_author:
            mock_author.return_value = {"name": "Alice Smith", "id": "alice@co.org"}
            # Add comments on the requirement and its assertion
            client.post(
                "/api/comment/add",
                json={"anchor": "REQ-p00001", "text": "Req-level comment"},
            )
            client.post(
                "/api/comment/add",
                json={"anchor": "REQ-p00001#A", "text": "Assertion comment"},
            )
            # Query for card
            resp = client.get("/api/comments/card", params={"node_id": "REQ-p00001"})
        assert resp.status_code == 200
        data = resp.json()
        # threads is a dict keyed by anchor
        assert "threads" in data
        threads = data["threads"]
        assert "REQ-p00001" in threads
        assert "REQ-p00001#A" in threads

    def test_REQ_d00231_D_get_orphaned_comments(self, tmp_path: Path) -> None:
        """GET /api/comments/orphaned returns empty list on fresh setup."""
        client, _ = _make_app(tmp_path)
        resp = client.get("/api/comments/orphaned")
        assert resp.status_code == 200
        data = resp.json()
        assert "threads" in data
        assert len(data["threads"]) == 0


# ---------------------------------------------------------------------------
# TestAuthorServerSide (REQ-d00231-E)
# ---------------------------------------------------------------------------


class TestAuthorServerSide:
    """Validates REQ-d00231-E: Author is resolved server-side via get_author_info,
    never from client-submitted data.
    """

    def test_REQ_d00231_E_author_resolved_server_side(self, tmp_path: Path) -> None:
        """Add comment with client-supplied author; verify stored author matches mock."""
        client, _ = _make_app(tmp_path)
        with patch("elspais.server.routes_api.get_author_info") as mock_author:
            mock_author.return_value = {"name": "Alice Smith", "id": "alice@co.org"}
            # Attempt to supply a different author from the client side
            resp = client.post(
                "/api/comment/add",
                json={
                    "anchor": "REQ-p00001#A",
                    "text": "My comment",
                    "author": "Evil Hacker",
                    "author_id": "evil@hacker.com",
                },
            )
        assert resp.status_code == 200
        comment = resp.json()["comment"]
        # Author must come from server-side get_author_info, not the client
        assert comment["author"] == "Alice Smith"
        assert comment["author_id"] == "alice@co.org"
