# Verifies: REQ-d00231-A+B+C+D+E, REQ-d00296-A+B+C+D
"""Tests for comment API endpoints (/api/comment/*, /api/comments/*)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from elspais.graph import GraphNode, NodeKind
from elspais.graph.builder import TraceGraph
from elspais.graph.federated import FederatedGraph, RepoEntry
from elspais.graph.relations import EdgeKind
from elspais.server import proxy_trust
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

    repos = [
        RepoEntry(
            name="root",
            graph=graph,
            config={"project": {"name": "root", "namespace": "REQ"}},
            repo_root=tmp_path,
        )
    ]
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

    # Verifies: REQ-d00231-A
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

    # Verifies: REQ-d00231-A
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

    # Verifies: REQ-d00231-A
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

    # Verifies: REQ-d00231-B
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

    # Verifies: REQ-d00231-B
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

    # Verifies: REQ-d00231-C
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

    # Verifies: REQ-d00231-C
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

    # Verifies: REQ-d00231-D
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

    # Verifies: REQ-d00231-D
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

    # Verifies: REQ-d00231-D
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

    # Verifies: REQ-d00231-E
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


# ---------------------------------------------------------------------------
# TestAuthorFromTrustedProxy (REQ-d00296)
# ---------------------------------------------------------------------------

PROXY_SECRET = "shared-with-the-hub"
PROXIED_HEADERS = {
    "X-Elspais-Proxy-Secret": PROXY_SECRET,
    "X-Elspais-User-Name": "Bob Jones",
    "X-Elspais-User-Email": "bob@co.org",
}
SERVER_AUTHOR = {"name": "Alice Smith", "id": "alice@co.org"}


class TestAuthorFromTrustedProxy:
    """Validates REQ-d00296: the author of an annotation made through a request
    is the identity a trusted proxy supplied with it, else the server's own.
    """

    @pytest.fixture
    def secret_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(proxy_trust, "_SECRET", PROXY_SECRET)

    @pytest.fixture
    def secret_unconfigured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(proxy_trust, "_SECRET", None)

    @staticmethod
    def _add(client: TestClient, headers: dict[str, str]) -> dict:
        with patch("elspais.server.routes_api.get_author_info", return_value=SERVER_AUTHOR):
            resp = client.post(
                "/api/comment/add",
                json={"anchor": "REQ-p00001#A", "text": "From a session"},
                headers=headers,
            )
        assert resp.status_code == 200, resp.text
        return resp.json()["comment"]

    # Verifies: REQ-d00296-A
    def test_REQ_d00296_A_trusted_identity_names_the_author(
        self, tmp_path: Path, secret_configured: None
    ) -> None:
        client, _ = _make_app(tmp_path)
        comment = self._add(client, PROXIED_HEADERS)
        assert comment["author"] == "Bob Jones"
        assert comment["author_id"] == "bob@co.org"

    # Verifies: REQ-d00296-A
    @pytest.mark.parametrize("route", ["reply", "resolve"])
    def test_REQ_d00296_A_reply_and_resolve_name_the_session_user(
        self, tmp_path: Path, secret_configured: None, route: str
    ) -> None:
        client, root = _make_app(tmp_path)
        parent = self._add(client, PROXIED_HEADERS)
        follow_up_headers = {
            **PROXIED_HEADERS,
            "X-Elspais-User-Name": "Carol Nguyen",
            "X-Elspais-User-Email": "carol@co.org",
        }
        body = (
            {"parent_id": parent["id"], "text": "Agreed"}
            if route == "reply"
            else {"comment_id": parent["id"]}
        )
        with patch("elspais.server.routes_api.get_author_info", return_value=SERVER_AUTHOR):
            resp = client.post(f"/api/comment/{route}", json=body, headers=follow_up_headers)
        assert resp.status_code == 200, resp.text
        jsonl = root / ".elspais" / "comments" / "spec" / "auth.md.json"
        events = [json.loads(line) for line in jsonl.read_text().splitlines() if line.strip()]
        assert events[-1]["event"] == route
        assert events[-1]["author"] == "Carol Nguyen"
        assert events[-1]["author_id"] == "carol@co.org"

    # Verifies: REQ-d00296-B, REQ-d00296-C
    @pytest.mark.parametrize(
        "secret_header",
        [
            pytest.param({}, id="secret-missing"),
            pytest.param({"X-Elspais-Proxy-Secret": "wrong"}, id="secret-wrong"),
        ],
    )
    def test_REQ_d00296_C_identity_without_proof_falls_back_to_server(
        self, tmp_path: Path, secret_configured: None, secret_header: dict[str, str]
    ) -> None:
        client, _ = _make_app(tmp_path)
        headers = {k: v for k, v in PROXIED_HEADERS.items() if k != "X-Elspais-Proxy-Secret"}
        comment = self._add(client, {**headers, **secret_header})
        assert comment["author"] == "Alice Smith"
        assert comment["author_id"] == "alice@co.org"

    # Verifies: REQ-d00296-D
    def test_REQ_d00296_D_unconfigured_secret_ignores_headers(
        self, tmp_path: Path, secret_unconfigured: None
    ) -> None:
        client, _ = _make_app(tmp_path)
        comment = self._add(client, PROXIED_HEADERS)
        assert comment["author"] == "Alice Smith"
        assert comment["author_id"] == "alice@co.org"

    # Verifies: REQ-d00296-B
    def test_REQ_d00296_B_empty_identity_headers_fall_back_to_server(
        self, tmp_path: Path, secret_configured: None
    ) -> None:
        client, _ = _make_app(tmp_path)
        comment = self._add(
            client,
            {
                "X-Elspais-Proxy-Secret": PROXY_SECRET,
                "X-Elspais-User-Name": "",
                "X-Elspais-User-Email": "",
            },
        )
        assert comment["author"] == "Alice Smith"
        assert comment["author_id"] == "alice@co.org"
